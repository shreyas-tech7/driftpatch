"""The rule-based proposer. It is the baseline that an LLM proposer must beat.

It handles three kinds of change and declines the rest:

- renamed-field: rewrite the key at each call site.
- new-required-parameter with a default in the spec: add the parameter with that default.
- removed-field: drop the key from a request body, or read a response key with .get().
"""

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .differ import NEW_REQUIRED_PARAMETER, REMOVED_FIELD, RENAMED_FIELD
from .finder import match_brace
from .patch import make_diff


@dataclass
class Proposal:
    proposer: str
    files: dict = field(default_factory=dict)  # relpath -> new text (changed files only)
    diff: str = ""
    handled: list = field(default_factory=list)  # change indexes the proposer acted on
    declined: list = field(default_factory=list)  # (change index, reason)
    tokens: int = 0
    notes: list = field(default_factory=list)

    @property
    def empty(self):
        return not self.diff


def _quote_like(original: str, value: str) -> str:
    q = "'" if original.startswith("'") else '"'
    return f"{q}{value}{q}"


def _py_literal(value):
    # Double quotes, like the code around it. json.dumps of a str is a valid Python literal.
    return json.dumps(value) if isinstance(value, str) else repr(value)


def _ts_literal(value):
    # Query values in the sample clients are strings.
    return json.dumps(value if isinstance(value, str) else str(value).lower() if isinstance(value, bool) else str(value))


class _Edits:
    def __init__(self):
        self.by_file = {}

    def add(self, rel, start, end, text):
        self.by_file.setdefault(rel, []).append((start, end, text))

    def apply(self, rel, original):
        edits = sorted(set(self.by_file.get(rel, [])), key=lambda e: (e[0], e[1]))
        out, pos = [], 0
        for start, end, text in edits:
            if start < pos:
                continue  # overlapping edit, keep the first
            out.append(original[pos:start])
            out.append(text)
            pos = end
        out.append(original[pos:])
        return "".join(out)


# ---------------------------------------------------------------- Python helpers


def _py_node_at(tree, site, offsets):
    """The AST node whose source span is exactly the site's span."""
    wanted = {
        "endpoint-call": (ast.Call,),
        "response-key": (ast.Subscript, ast.Call),
        "request-key": (ast.Constant,),
        "enum-literal": (ast.Constant,),
    }.get(site.kind, ())
    for node in ast.walk(tree):
        if isinstance(node, wanted) and _span(node, offsets) == (site.start, site.end):
            return node
    return None


def _line_offsets(text):
    offsets = [0]
    for line in text.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def _span(node, offsets):
    return offsets[node.lineno - 1] + node.col_offset, offsets[node.end_lineno - 1] + node.end_col_offset


def _py_enclosing_function(tree, call):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for sub in ast.walk(node):
                if sub is call:
                    return node
    return None


def _py_dict_insert(text, offsets, dict_node, key, value):
    """Return (offset, insertion text) that adds key: value at the end of a dict literal."""
    start, end = _span(dict_node, offsets)
    close = end - 1  # the closing brace
    inner = text[start + 1 : close]
    entry = f"{_py_literal(key)}: {_py_literal(value)}"
    if not inner.strip():
        return close, entry
    stripped = inner.rstrip()
    if "\n" in inner and stripped.endswith(","):
        indent = re.search(r"\n([ \t]*)\S", inner)
        pad = indent.group(1) if indent else "    "
        return start + 1 + len(stripped), f"\n{pad}{entry},"
    if stripped.endswith(","):
        return start + 1 + len(stripped), f" {entry}"
    return start + 1 + len(stripped), f", {entry}"


def _py_add_param(text, tree, offsets, call, kwarg_names, key, value):
    func = _py_enclosing_function(tree, call)
    for kw in call.keywords:
        if kw.arg in kwarg_names:
            target = kw.value
            if isinstance(target, ast.Dict):
                return _py_dict_insert(text, offsets, target, key, value)
            if isinstance(target, ast.Name) and func is not None:
                for node in ast.walk(func):
                    if (
                        isinstance(node, ast.Assign)
                        and len(node.targets) == 1
                        and isinstance(node.targets[0], ast.Name)
                        and node.targets[0].id == target.id
                        and isinstance(node.value, ast.Dict)
                    ):
                        return _py_dict_insert(text, offsets, node.value, key, value)
            return None
    # No such keyword yet: add one before the closing parenthesis.
    _, end = _span(call, offsets)
    close = end - 1
    return close, f", {kwarg_names[0]}={{{_py_literal(key)}: {_py_literal(value)}}}"


def _py_remove_dict_entry(text, offsets, dict_node, key_node):
    keys = list(dict_node.keys)
    i = next((n for n, k in enumerate(keys) if k is key_node), None)
    if i is None:
        return None
    value_node = dict_node.values[i]
    k_start, _ = _span(key_node, offsets)
    _, v_end = _span(value_node, offsets)
    if i + 1 < len(keys):
        nxt_start, _ = _span(keys[i + 1], offsets)
        return k_start, nxt_start, ""
    # Last entry: remove from the end of the previous value, or eat a trailing comma.
    if i > 0:
        _, prev_end = _span(dict_node.values[i - 1], offsets)
        tail = re.match(r"\s*,", text[v_end:])
        end = v_end + (tail.end() if tail else 0)
        if "\n" in text[prev_end:k_start]:
            line_start = text.rfind("\n", 0, k_start)
            return line_start, end, ""
        return prev_end, v_end, ""
    tail = re.match(r"\s*,?", text[v_end:])
    return k_start, v_end + (tail.end() if tail else 0), ""


# ---------------------------------------------------------------- TypeScript helpers


def _ts_call_args(text, paren_index):
    """Split the arguments of a call. Returns list of (start, end) and the closing paren index."""
    end = match_brace(text, paren_index) - 1
    args, depth, start, i = [], 0, paren_index + 1, paren_index + 1
    while i < end:
        c = text[i]
        if c in "\"'`":
            from .finder import _skip_string

            i = _skip_string(text, i)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            args.append((start, i))
            start = i + 1
        i += 1
    if text[start:end].strip():
        args.append((start, end))
    return args, end


def _ts_object_insert(text, open_index, key, value):
    close = match_brace(text, open_index) - 1
    inner = text[open_index + 1 : close]
    entry = f"{key}: {_ts_literal(value)}"
    if not inner.strip():
        return close, f" {entry} "
    stripped = inner.rstrip()
    if "\n" in inner and stripped.endswith(","):
        indent = re.search(r"\n([ \t]*)\S", inner)
        return open_index + 1 + len(stripped), f"\n{indent.group(1) if indent else '  '}{entry},"
    sep = " " if stripped.endswith(",") else ", "
    return open_index + 1 + len(stripped), f"{sep}{entry}"


def _ts_find_object_var(text, scope_start, scope_end, var):
    m = re.compile(r"\b(?:const|let|var)\s+" + re.escape(var) + r"\s*(?::[^=]+)?=\s*\{").search(text, scope_start, scope_end)
    return m.end() - 1 if m else None


def _ts_enclosing(functions, offset):
    best = None
    for name, start, end in functions:
        if start <= offset < end and (best is None or start > best[1]):
            best = (name, start, end)
    return best


def _ts_add_param(text, functions, call_start, key, value, slot):
    """slot is 'query' or 'body'."""
    paren = text.find("(", call_start)
    if paren < 0:
        return None
    args, close = _ts_call_args(text, paren)
    func = _ts_enclosing(functions, call_start)
    if len(args) >= 3:
        a_start, a_end = args[2]
        opts = text[a_start:a_end]
        brace = a_start + opts.find("{") if "{" in opts else -1
        if brace < 0:
            return None
        inner = text[brace + 1 : match_brace(text, brace) - 1]
        m = re.search(r"\b" + slot + r"\s*:\s*\{", inner)
        if m:
            return _ts_object_insert(text, brace + 1 + m.end() - 1, key, value)
        if re.search(r"(?<![\w$])" + slot + r"(?![\w$])", inner) and func is not None:
            obj = _ts_find_object_var(text, func[1], func[2], slot)
            if obj is not None:
                return _ts_object_insert(text, obj, key, value)
            return None
        return brace + 1, f" {slot}: {{ {key}: {_ts_literal(value)} }},"
    if len(args) == 2:
        return args[1][1], f", {{ {slot}: {{ {key}: {_ts_literal(value)} }} }}"
    return None


def _ts_remove_key(text, key_start, scope_end):
    """Remove `key: value,` starting at key_start."""
    colon = text.find(":", key_start)
    i, depth = colon + 1, 0
    while i < scope_end:
        c = text[i]
        if c in "\"'`":
            from .finder import _skip_string

            i = _skip_string(text, i)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                break
            depth -= 1
        elif c == "," and depth == 0:
            # remove through the comma and following spaces on the same line
            j = i + 1
            while j < scope_end and text[j] in " \t":
                j += 1
            return key_start, j, ""
        i += 1
    # last property: remove the preceding comma too, keep the space before the brace
    while i > key_start and text[i - 1] in " \t\n":
        i -= 1
    k = key_start - 1
    while k > 0 and text[k] in " \t\n":
        k -= 1
    if text[k] == ",":
        return k, i, ""
    return key_start, i, ""


# ---------------------------------------------------------------- the proposer


class RuleProposer:
    name = "rule"

    def propose(self, client_dir, changes, sites, language) -> Proposal:
        from .finder import _TsFile  # local import to keep module load light

        client_dir = Path(client_dir)
        proposal = Proposal(self.name)
        edits = _Edits()
        texts = {}
        by_change = {}
        for site in sites:
            by_change.setdefault(site.change, []).append(site)
        for index, change in enumerate(changes):
            change_sites = by_change.get(index, [])
            if change.kind not in (RENAMED_FIELD, NEW_REQUIRED_PARAMETER, REMOVED_FIELD):
                proposal.declined.append((index, f"the rule baseline does not handle {change.kind}"))
                continue
            if change.kind == NEW_REQUIRED_PARAMETER and not change.has_default:
                proposal.declined.append((index, "the new required parameter has no default in the spec"))
                continue
            if not change_sites:
                proposal.declined.append((index, "no call sites found"))
                continue
            acted = False
            for site in change_sites:
                text = texts.setdefault(site.file, (client_dir / site.file).read_text(encoding="utf-8"))
                edit = self._edit(text, site, change, language, _TsFile if language == "ts" else None)
                if edit is not None:
                    edits.add(site.file, *edit)
                    acted = True
            if acted:
                proposal.handled.append(index)
            else:
                proposal.declined.append((index, "no rule matched the call sites"))
        for rel, original in texts.items():
            new = edits.apply(rel, original)
            if new != original:
                proposal.files[rel] = new
        proposal.diff = make_diff({rel: texts[rel] for rel in proposal.files}, proposal.files)
        return proposal

    def _edit(self, text, site, change, language, ts_file_cls):
        if language == "python":
            return self._edit_py(text, site, change)
        return self._edit_ts(text, site, change, ts_file_cls)

    def _edit_py(self, text, site, change):
        tree = ast.parse(text)
        offsets = _line_offsets(text)
        segment = text[site.start : site.end]
        if change.kind == RENAMED_FIELD:
            if site.kind == "request-key":
                return site.start, site.end, _quote_like(segment, change.new_field)
            if site.kind == "response-key":
                node = _py_node_at(tree, site, offsets)
                key_node = node.slice if isinstance(node, ast.Subscript) else node.args[0] if isinstance(node, ast.Call) else None
                if key_node is None:
                    return None
                ks, ke = _span(key_node, offsets)
                return ks, ke, _quote_like(text[ks:ke], change.new_field)
            return None
        if change.kind == REMOVED_FIELD:
            if site.kind == "response-key":
                node = _py_node_at(tree, site, offsets)
                if isinstance(node, ast.Subscript):
                    vs, ve = _span(node.value, offsets)
                    ks, ke = _span(node.slice, offsets)
                    return site.start, site.end, f"{text[vs:ve]}.get({text[ks:ke]})"
                return None  # already a .get() call
            if site.kind == "request-key":
                for node in ast.walk(tree):
                    if isinstance(node, ast.Dict):
                        for k in node.keys:
                            if k is not None and _span(k, offsets) == (site.start, site.end):
                                return _py_remove_dict_entry(text, offsets, node, k)
            return None
        if change.kind == NEW_REQUIRED_PARAMETER and site.kind == "endpoint-call":
            call = _py_node_at(tree, site, offsets)
            if call is None:
                return None
            kwargs = ("params",) if change.location == "query" else ("body", "json") if change.location == "request" else ()
            if not kwargs:
                return None
            spot = _py_add_param(text, tree, offsets, call, kwargs, change.field, change.default)
            if spot is None:
                return None
            return spot[0], spot[0], spot[1]
        return None

    def _edit_ts(self, text, site, change, ts_file_cls):
        segment = text[site.start : site.end]
        if change.kind == RENAMED_FIELD:
            if site.kind == "response-key":
                return site.start, site.end, segment.replace(change.field, change.new_field, 1)
            if site.kind == "request-key":
                return site.start, site.end, segment.replace(change.field, change.new_field, 1)
            return None
        if change.kind == REMOVED_FIELD:
            if site.kind == "request-key":
                tf = ts_file_cls(site.file, text)
                func = _ts_enclosing(tf.functions, site.start)
                return _ts_remove_key(text, site.start, func[2] if func else len(text))
            return None  # a missing response key reads as undefined in TypeScript, no rule
        if change.kind == NEW_REQUIRED_PARAMETER and site.kind == "endpoint-call":
            slot = "query" if change.location == "query" else "body" if change.location == "request" else None
            if slot is None:
                return None
            tf = ts_file_cls(site.file, text)
            spot = _ts_add_param(text, tf.functions, site.start, change.field, change.default, slot)
            if spot is None:
                return None
            return spot[0], spot[0], spot[1]
        return None
