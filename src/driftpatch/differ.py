"""The built-in spec differ.

It finds six kinds of breaking change between two OpenAPI 3.x specs:

- removed-endpoint: a path and method in the old spec is gone.
- renamed-field: a property is gone and a new one of the same type took its place.
- removed-field: a property is gone with no replacement.
- new-required-parameter: a parameter (or request body property) is now required.
- changed-type: a property or parameter has a new JSON type.
- changed-enum: an enum lost values (or a response enum gained values).

The five kinds in the brief are the first four plus changed-enum. removed-field is
the leftover case when a rename has no partner (see DECISIONS.md).
"""

import difflib
from dataclasses import asdict, dataclass
from dataclasses import field as dc_field

from .spec import (
    iter_operations,
    operation_parameters,
    request_schema,
    resolve,
    response_schema,
    template_key,
)

REMOVED_ENDPOINT = "removed-endpoint"
RENAMED_FIELD = "renamed-field"
REMOVED_FIELD = "removed-field"
NEW_REQUIRED_PARAMETER = "new-required-parameter"
CHANGED_TYPE = "changed-type"
CHANGED_ENUM = "changed-enum"
KINDS = (REMOVED_ENDPOINT, RENAMED_FIELD, REMOVED_FIELD, NEW_REQUIRED_PARAMETER, CHANGED_TYPE, CHANGED_ENUM)

# Pair a removed and an added property as a rename only when the names are at
# least this similar, or when they are the only pair of that type in the schema.
RENAME_MIN_RATIO = 0.3


@dataclass
class Change:
    kind: str
    location: str  # endpoint, request, response, query, path, header, cookie
    path: str = ""
    method: str = ""
    operations: list = dc_field(default_factory=list)  # "METHOD path" strings
    schema: str = ""  # nearest component schema name, if any
    field: str = ""  # property or parameter name in the old spec
    new_field: str = ""  # renamed-field only
    old_type: str = ""
    new_type: str = ""
    removed_values: list = dc_field(default_factory=list)
    added_values: list = dc_field(default_factory=list)
    default: object = None
    example: object = None
    has_default: bool = False
    source: str = "builtin"

    def key(self):
        return (
            self.kind,
            self.location,
            self.schema,
            self.field,
            self.path if not self.schema else "",
            self.method if not self.schema else "",
        )

    def describe(self) -> str:
        where = f"`{self.schema}`" if self.schema else f"`{self.method.upper()} {self.path}`"
        if self.kind == REMOVED_ENDPOINT:
            return f"The endpoint `{self.method.upper()} {self.path}` was removed."
        if self.kind == RENAMED_FIELD:
            return f"The {self.location} field `{self.field}` in {where} was renamed to `{self.new_field}`."
        if self.kind == REMOVED_FIELD:
            return f"The {self.location} field `{self.field}` in {where} was removed."
        if self.kind == NEW_REQUIRED_PARAMETER:
            extra = f" Its default is `{self.default!r}`." if self.has_default else " It has no default."
            return f"The {self.location} parameter `{self.field}` of {where} is now required.{extra}"
        if self.kind == CHANGED_TYPE:
            return f"The {self.location} field `{self.field}` in {where} changed type from `{self.old_type}` to `{self.new_type}`."
        if self.kind == CHANGED_ENUM:
            parts = []
            if self.removed_values:
                parts.append("lost " + ", ".join(f"`{v}`" for v in self.removed_values))
            if self.added_values:
                parts.append("gained " + ", ".join(f"`{v}`" for v in self.added_values))
            return f"The {self.location} enum `{self.field}` in {where} " + " and ".join(parts) + "."
        return f"{self.kind} at {where}"

    def to_dict(self):
        return asdict(self)


def _type_of(schema) -> str:
    t = schema.get("type", "")
    if isinstance(t, list):
        t = "|".join(sorted(str(x) for x in t if x != "null"))
    if not t and "properties" in schema:
        t = "object"
    return str(t)


def _enum(schema):
    values = schema.get("enum")
    return list(values) if isinstance(values, list) else None


class _Walker:
    def __init__(self, old_spec, new_spec):
        self.old = old_spec
        self.new = new_spec
        self.changes = {}
        self.visited = set()
        self.children = {}  # component visit key -> nested component visit keys
        self.origin = {}  # change key -> component visit key where it was found
        self.stack = []

    def add(self, change: Change, op_label: str):
        key = change.key()
        existing = self.changes.get(key)
        if existing is None:
            change.operations = [op_label]
            self.changes[key] = change
            if self.stack:
                self.origin[key] = self.stack[-1]
        elif op_label not in existing.operations:
            existing.operations.append(op_label)

    def _credit(self, visit_key, op_label):
        """A second operation uses an already compared component. Credit it on every change below."""
        seen, todo = set(), [visit_key]
        while todo:
            k = todo.pop()
            if k in seen:
                continue
            seen.add(k)
            todo.extend(self.children.get(k, ()))
        for key, change in self.changes.items():
            if self.origin.get(key) in seen and op_label not in change.operations:
                change.operations.append(op_label)

    def compare(self, old_schema, new_schema, location, op_label, schema_name="", depth=0):
        if depth > 40:
            return
        old_schema, old_name = resolve(self.old, old_schema or {})
        new_schema, new_name = resolve(self.new, new_schema or {})
        name = old_name or schema_name
        if old_name:
            visit_key = (old_name, new_name, location)
            if self.stack:
                self.children.setdefault(self.stack[-1], set()).add(visit_key)
            if visit_key in self.visited:
                self._credit(visit_key, op_label)
                return
            self.visited.add(visit_key)
            self.stack.append(visit_key)
            try:
                self._compare_body(old_schema, new_schema, location, op_label, name, depth)
            finally:
                self.stack.pop()
            return
        self._compare_body(old_schema, new_schema, location, op_label, name, depth)

    def _compare_body(self, old_schema, new_schema, location, op_label, name, depth):
        ot, nt = _type_of(old_schema), _type_of(new_schema)
        if ot == "array" and nt == "array":
            self.compare(old_schema.get("items"), new_schema.get("items"), location, op_label, name, depth + 1)
            return
        for combo in ("allOf", "oneOf", "anyOf"):
            if combo in old_schema or combo in new_schema:
                return  # composed schemas are out of scope for the built-in differ
        old_props = old_schema.get("properties") or {}
        new_props = new_schema.get("properties") or {}
        if not isinstance(old_props, dict) or not isinstance(new_props, dict):
            return
        removed = [p for p in old_props if p not in new_props]
        added = [p for p in new_props if p not in old_props]
        renames = self._pair_renames(old_props, new_props, removed, added)
        for old_field, new_field in renames.items():
            self.add(Change(RENAMED_FIELD, location, schema=name, field=old_field, new_field=new_field), op_label)
        for prop in removed:
            if prop not in renames:
                self.add(Change(REMOVED_FIELD, location, schema=name, field=prop), op_label)
        if location == "request":
            old_req = set(old_schema.get("required") or [])
            for prop in new_schema.get("required") or []:
                if prop in renames.values() or prop not in new_props:
                    continue
                if prop not in old_req:
                    sub, _ = resolve(self.new, new_props[prop])
                    self.add(
                        Change(
                            NEW_REQUIRED_PARAMETER,
                            "request",
                            schema=name,
                            field=prop,
                            default=sub.get("default"),
                            has_default="default" in sub,
                            example=sub.get("example"),
                        ),
                        op_label,
                    )
        for prop in old_props:
            if prop in new_props:
                self._compare_leaf(old_props[prop], new_props[prop], location, op_label, name, prop, depth)

    def _compare_leaf(self, old_sub, new_sub, location, op_label, schema_name, prop, depth):
        old_res, _ = resolve(self.old, old_sub)
        new_res, _ = resolve(self.new, new_sub)
        ot, nt = _type_of(old_res), _type_of(new_res)
        if ot and nt and ot != nt:
            self.add(Change(CHANGED_TYPE, location, schema=schema_name, field=prop, old_type=ot, new_type=nt), op_label)
            return
        enum_change = _enum_change(old_res, new_res, location)
        if enum_change:
            removed_values, added_values = enum_change
            self.add(
                Change(CHANGED_ENUM, location, schema=schema_name, field=prop, removed_values=removed_values, added_values=added_values),
                op_label,
            )
        if ot in ("object", "array") or "$ref" in old_sub:
            self.compare(old_sub, new_sub, location, op_label, schema_name, depth + 1)

    def _pair_renames(self, old_props, new_props, removed, added):
        pairs = {}
        for prop in added:
            sub, _ = resolve(self.new, new_props[prop])
            origin = sub.get("x-renamed-from")
            if origin in removed:
                pairs[origin] = prop
        candidates = []
        for r in removed:
            if r in pairs:
                continue
            rt = _type_of(resolve(self.old, old_props[r])[0])
            for a in added:
                if a in pairs.values():
                    continue
                at = _type_of(resolve(self.new, new_props[a])[0])
                if rt and rt == at:
                    candidates.append((difflib.SequenceMatcher(None, r, a).ratio(), r, a))
        only_one = len(candidates) == 1
        for ratio, r, a in sorted(candidates, key=lambda c: (-c[0], c[1], c[2])):
            if r in pairs or a in pairs.values():
                continue
            if ratio >= RENAME_MIN_RATIO or only_one:
                pairs[r] = a
        return pairs


def _enum_change(old_schema, new_schema, location):
    old_enum, new_enum = _enum(old_schema), _enum(new_schema)
    if old_enum is None or new_enum is None:
        return None
    removed_values = [v for v in old_enum if v not in new_enum]
    added_values = [v for v in new_enum if v not in old_enum] if location == "response" else []
    if removed_values or added_values:
        return removed_values, added_values
    return None


def diff_specs(old_spec: dict, new_spec: dict) -> list:
    """Return the breaking changes from old_spec to new_spec, in a stable order."""
    walker = _Walker(old_spec, new_spec)
    new_ops = {}
    for path, method, op, item in iter_operations(new_spec):
        new_ops[(template_key(path), method)] = (path, op, item)
    for path, method, op, item in iter_operations(old_spec):
        label = f"{method.upper()} {path}"
        match = new_ops.get((template_key(path), method))
        if match is None:
            walker.add(Change(REMOVED_ENDPOINT, "endpoint", path=path, method=method), label)
            continue
        _, new_op, new_item = match
        old_params = operation_parameters(old_spec, op, item)
        new_params = operation_parameters(new_spec, new_op, new_item)
        for (where, name), param in new_params.items():
            old_param = old_params.get((where, name))
            if param.get("required") and (old_param is None or not old_param.get("required")):
                schema, _ = resolve(new_spec, param.get("schema") or {})
                walker.add(
                    Change(
                        NEW_REQUIRED_PARAMETER,
                        where,
                        path=path,
                        method=method,
                        field=name,
                        default=schema.get("default"),
                        has_default="default" in schema,
                        example=param.get("example", schema.get("example")),
                    ),
                    label,
                )
        for (where, name), old_param in old_params.items():
            param = new_params.get((where, name))
            if param is None:
                continue
            old_schema, _ = resolve(old_spec, old_param.get("schema") or {})
            new_schema, _ = resolve(new_spec, param.get("schema") or {})
            ot, nt = _type_of(old_schema), _type_of(new_schema)
            if ot and nt and ot != nt:
                walker.add(Change(CHANGED_TYPE, where, path=path, method=method, field=name, old_type=ot, new_type=nt), label)
                continue
            enum_change = _enum_change(old_schema, new_schema, "request")
            if enum_change:
                walker.add(
                    Change(CHANGED_ENUM, where, path=path, method=method, field=name, removed_values=enum_change[0]),
                    label,
                )
        old_req = request_schema(old_spec, op)
        new_req = request_schema(new_spec, new_op)
        if old_req is not None and new_req is not None:
            walker.compare(old_req, new_req, "request", label, f"{label} request")
        _, old_resp = response_schema(old_spec, op)
        _, new_resp = response_schema(new_spec, new_op)
        if old_resp is not None and new_resp is not None:
            walker.compare(old_resp, new_resp, "response", label, f"{label} response")
    changes = list(walker.changes.values())
    order = {k: i for i, k in enumerate(KINDS)}
    changes.sort(key=lambda c: (order[c.kind], c.location, c.schema, c.path, c.method, c.field))
    return changes


def count_by_kind(changes) -> dict:
    counts = {k: 0 for k in KINDS}
    for change in changes:
        counts[change.kind] = counts.get(change.kind, 0) + 1
    return counts
