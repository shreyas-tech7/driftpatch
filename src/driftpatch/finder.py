"""Find the call sites in a client that a spec change affects.

Python clients are read with the `ast` module. TypeScript clients are read with
regular expressions and a small brace scanner. The TypeScript finder is weaker:
it does not understand types, imports, shorthand properties or code split
across files in unusual ways.

The finder works in two steps. First it finds the functions that call each
affected endpoint, plus the helpers they call and the functions that call them
(the scope). Then it looks for the changed field, parameter or enum value
inside that scope only, so a rename in one schema does not touch a field with
the same name in another schema.
"""

import ast
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .differ import CHANGED_ENUM, NEW_REQUIRED_PARAMETER, REMOVED_ENDPOINT
from .spec import template_key
from .verifier import detect_language, is_test_file

METHODS = ("GET", "PUT", "POST", "DELETE", "PATCH", "HEAD", "OPTIONS")


@dataclass
class Site:
    file: str
    line: int
    col: int
    start: int  # character offsets into the file text
    end: int
    kind: str  # endpoint-call, response-key, request-key, enum-literal
    symbol: str
    change: int  # index into the change list
    function: str
    lang: str

    def to_dict(self):
        return asdict(self)


def source_files(client_dir, language):
    client_dir = Path(client_dir)
    suffix = ".py" if language == "python" else ".ts"
    files = []
    for p in sorted(client_dir.rglob(f"*{suffix}")):
        rel = p.relative_to(client_dir).as_posix()
        if is_test_file(rel) or any(part in ("node_modules", ".venv", "__pycache__") for part in p.parts):
            continue
        if rel.endswith(".d.ts"):
            continue
        files.append(rel)
    return files


def _op_keys(change):
    keys = set()
    for label in change.operations or [f"{change.method.upper()} {change.path}"]:
        method, _, path = label.partition(" ")
        keys.add((method.upper(), template_key(path)))
    return keys


def _line_offsets(text):
    offsets = [0]
    for line in text.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def _offset(offsets, line, col):
    return offsets[line - 1] + col


def _field_kind(change):
    if change.location == "response":
        return "response"
    if change.location in ("request", "query", "header", "path", "cookie"):
        return "request"
    return ""


# ---------------------------------------------------------------- Python


class _PyFile:
    def __init__(self, rel, text):
        self.rel = rel
        self.text = text
        self.tree = ast.parse(text)
        self.offsets = _line_offsets(text)
        self.functions = {}  # name -> list of FunctionDef nodes
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.functions.setdefault(node.name, []).append(node)

    def span(self, node):
        start = _offset(self.offsets, node.lineno, node.col_offset)
        end = _offset(self.offsets, node.end_lineno, node.end_col_offset)
        return start, end


def _py_template(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.Constant):
                parts.append(str(value.value))
            else:
                parts.append("{}")
        return "".join(parts)
    return None


def _py_endpoint_calls(pf):
    """Yield (function node, call node, method, template key) for calls that name a path."""
    for funcs in pf.functions.values():
        for func in funcs:
            for node in ast.walk(func):
                if not isinstance(node, ast.Call):
                    continue
                method = None
                key = None
                for arg in node.args:
                    t = _py_template(arg)
                    if t is None:
                        continue
                    if t.upper() in METHODS and method is None:
                        method = t.upper()
                    elif t.startswith("/") and key is None:
                        key = template_key(t.split("?")[0])
                if key:
                    yield func, node, method, key


def _py_called_names(func):
    names = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
    return names


def _py_scope(pf, op_keys, callees=True, callers=True):
    direct = []
    calls = []
    for func, call, method, key in _py_endpoint_calls(pf):
        if any(key == k and (method is None or method == m) for m, k in op_keys):
            direct.append(func)
            calls.append((func, call))
    scope = {id(f): f for f in direct}
    frontier = list(direct) if callees else []
    for _ in range(2):  # helpers they call, two hops
        nxt = []
        for func in frontier:
            for name in _py_called_names(func):
                for callee in pf.functions.get(name, []):
                    if id(callee) not in scope:
                        scope[id(callee)] = callee
                        nxt.append(callee)
        frontier = nxt
    direct_names = {f.name for f in direct} if callers else set()
    for funcs in pf.functions.values():  # callers, one hop
        for func in funcs:
            if id(func) not in scope and _py_called_names(func) & direct_names:
                scope[id(func)] = func
    return list(scope.values()), calls


def _py_sites(pf, change, index):
    sites = []
    op_keys = _op_keys(change)
    side = _field_kind(change)
    # Response keys live in helpers that map the answer. Request keys live where the call is built.
    # Enum values can come from a caller's argument.
    enum = change.kind == CHANGED_ENUM
    scope, calls = _py_scope(pf, op_keys, callees=enum or side == "response", callers=enum)

    def add(node, kind, symbol, func):
        start, end = pf.span(node)
        sites.append(Site(pf.rel, node.lineno, node.col_offset, start, end, kind, symbol, index, func.name, "python"))

    if change.kind in (REMOVED_ENDPOINT,) or (change.kind == NEW_REQUIRED_PARAMETER and change.location != "request"):
        for func, call in calls:
            add(call, "endpoint-call", change.path or change.operations[0], func)
        return sites
    if change.kind == NEW_REQUIRED_PARAMETER and change.location == "request":
        for func, call in calls:
            add(call, "endpoint-call", change.field, func)
        return sites
    seen = set()
    for func in scope:
        for node in ast.walk(func):
            if change.kind == CHANGED_ENUM:
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in change.removed_values:
                    key = (node.lineno, node.col_offset)
                    if key not in seen:
                        seen.add(key)
                        add(node, "enum-literal", node.value, func)
                continue
            if side == "response":
                if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and node.slice.value == change.field:
                    add(node, "response-key", change.field, func)
                elif (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "get"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and node.args[0].value == change.field
                ):
                    add(node, "response-key", change.field, func)
            elif side == "request" and isinstance(node, ast.Dict):
                for k in node.keys:
                    if isinstance(k, ast.Constant) and k.value == change.field:
                        add(k, "request-key", change.field, func)
    return sites


# ---------------------------------------------------------------- TypeScript

_TS_FUNC = re.compile(r"(?:function\s+)?(?:async\s+)?\b([A-Za-z_$][\w$]*)\s*\([^()]*(?:\([^()]*\)[^()]*)*\)\s*(?::\s*[^{;=]+)?\{")
_TS_KEYWORDS = {"if", "for", "while", "switch", "catch", "function", "return", "constructor"}
_TS_STRING = re.compile(r'"((?:[^"\\\n]|\\.)*)"|\'((?:[^\'\\\n]|\\.)*)\'|`((?:[^`\\]|\\.)*)`')


def _skip_string(text, i):
    quote = text[i]
    i += 1
    while i < len(text):
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == quote:
            return i + 1
        i += 1
    return i


def match_brace(text, open_index):
    """Index just past the brace that closes text[open_index]. Skips strings and comments."""
    depth = 0
    i = open_index
    pairs = {"{": "}", "(": ")", "[": "]"}
    opener = text[open_index]
    closer = pairs[opener]
    while i < len(text):
        c = text[i]
        if c in "\"'`":
            i = _skip_string(text, i)
            continue
        if text.startswith("//", i):
            nl = text.find("\n", i)
            i = len(text) if nl < 0 else nl
            continue
        if text.startswith("/*", i):
            close = text.find("*/", i + 2)
            i = len(text) if close < 0 else close + 2
            continue
        if c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(text)


class _TsFile:
    def __init__(self, rel, text):
        self.rel = rel
        self.text = text
        self.offsets = _line_offsets(text)
        self.functions = []  # (name, body_start, body_end)
        for m in _TS_FUNC.finditer(text):
            name = m.group(1)
            if name in _TS_KEYWORDS:
                continue
            open_index = m.end() - 1
            self.functions.append((name, open_index, match_brace(text, open_index)))

    def line_col(self, offset):
        line = 1
        while line < len(self.offsets) and self.offsets[line] <= offset:
            line += 1
        return line, offset - self.offsets[line - 1]


def _ts_template(s):
    return re.sub(r"\$\{[^}]*\}", "{}", s)


def _ts_endpoint_calls(tf):
    for name, start, end in tf.functions:
        body = tf.text[start:end]
        for m in _TS_STRING.finditer(body):
            raw = m.group(1) if m.group(1) is not None else m.group(2) if m.group(2) is not None else m.group(3)
            if not raw.startswith("/"):
                continue
            before = body[max(0, m.start() - 40) : m.start()]
            method_m = re.search(r"[\"'](GET|PUT|POST|DELETE|PATCH|HEAD|OPTIONS)[\"']\s*,\s*$", before)
            yield (
                (name, start, end),
                start + m.start(),
                (method_m.group(1) if method_m else None),
                template_key(_ts_template(raw).split("?")[0]),
            )


def _ts_scope(tf, op_keys, callees=True, callers=True):
    direct = {}
    calls = []
    for func, offset, method, key in _ts_endpoint_calls(tf):
        if any(key == k and (method is None or method == m) for m, k in op_keys):
            direct[func[0]] = func
            calls.append((func, offset))
    scope = dict(direct)
    names = {f[0]: f for f in tf.functions}
    frontier = list(direct.values()) if callees else []
    for _ in range(2):
        nxt = []
        for _name, start, end in frontier:
            for ident in set(re.findall(r"[A-Za-z_$][\w$]*", tf.text[start:end])):
                if ident in names and ident not in scope:
                    scope[ident] = names[ident]
                    nxt.append(names[ident])
        frontier = nxt
    for name, start, end in tf.functions if callers else []:
        if name not in scope and set(re.findall(r"[A-Za-z_$][\w$]*", tf.text[start:end])) & set(direct):
            scope[name] = (name, start, end)
    return list(scope.values()), calls


def _ts_sites(tf, change, index):
    sites = []
    op_keys = _op_keys(change)
    side = _field_kind(change)
    enum = change.kind == CHANGED_ENUM
    scope, calls = _ts_scope(tf, op_keys, callees=enum or side == "response", callers=enum)

    def add(start, end, kind, symbol, func_name):
        line, col = tf.line_col(start)
        sites.append(Site(tf.rel, line, col, start, end, kind, symbol, index, func_name, "ts"))

    if change.kind == REMOVED_ENDPOINT or change.kind == NEW_REQUIRED_PARAMETER:
        for (name, _s, _e), offset in calls:
            call_start = tf.text.rfind("this.request(", 0, offset)
            start = call_start if call_start >= 0 and offset - call_start < 80 else offset
            add(start, offset, "endpoint-call", change.field or change.path, name)
        return sites
    field_re = re.escape(change.field)
    seen = set()
    for name, start, end in scope:
        body = tf.text[start:end]
        if change.kind == CHANGED_ENUM:
            for m in _TS_STRING.finditer(body):
                raw = next(g for g in m.groups() if g is not None) if any(g is not None for g in m.groups()) else ""
                if raw in change.removed_values and (start + m.start()) not in seen:
                    seen.add(start + m.start())
                    add(start + m.start(), start + m.end(), "enum-literal", raw, name)
            continue
        if side == "response":
            for m in re.finditer(r"\.(" + field_re + r")\b(?!\s*\()|\[\s*[\"'](" + field_re + r")[\"']\s*\]", body):
                add(start + m.start(), start + m.end(), "response-key", change.field, name)
        elif side == "request":
            for m in re.finditer(r"(?<![\w$.])[\"']?(" + field_re + r")[\"']?\s*:(?!:)", body):
                add(start + m.start(), start + m.end(), "request-key", change.field, name)
    return sites


# ---------------------------------------------------------------- entry point


def find_sites(client_dir, changes, language=None):
    """Return a list of Site for the given changes, sorted by file and position."""
    client_dir = Path(client_dir)
    language = language or detect_language(client_dir)
    sites = []
    for rel in source_files(client_dir, language):
        text = (client_dir / rel).read_text(encoding="utf-8")
        if language == "python":
            try:
                pf = _PyFile(rel, text)
            except SyntaxError:
                continue
            for index, change in enumerate(changes):
                sites.extend(_py_sites(pf, change, index))
        else:
            tf = _TsFile(rel, text)
            for index, change in enumerate(changes):
                sites.extend(_ts_sites(tf, change, index))
    unique = {}
    for site in sites:
        unique.setdefault((site.file, site.start, site.end, site.change, site.kind), site)
    return sorted(unique.values(), key=lambda s: (s.file, s.start, s.change))
