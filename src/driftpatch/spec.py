"""Load OpenAPI 3.x specs and walk their operations."""

import json
import re
from pathlib import Path

HTTP_METHODS = ("get", "put", "post", "delete", "patch", "head", "options", "trace")


class SpecError(ValueError):
    pass


def load_spec(path) -> dict:
    """Read a JSON spec. YAML works too when PyYAML is installed."""
    text = Path(path).read_text(encoding="utf-8")
    if str(path).endswith((".yaml", ".yml")):
        try:
            import yaml  # optional
        except ImportError as err:  # pragma: no cover - depends on the environment
            raise SpecError("YAML specs need PyYAML. Convert the spec to JSON or install PyYAML.") from err
        spec = yaml.safe_load(text)
    else:
        spec = json.loads(text)
    if not isinstance(spec, dict) or not str(spec.get("openapi", "")).startswith("3."):
        raise SpecError(f"{path} is not an OpenAPI 3.x document")
    return spec


def resolve(spec: dict, schema):
    """Follow local $refs. Returns (schema, component name or None)."""
    name = None
    seen = set()
    while isinstance(schema, dict) and "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/") or ref in seen:
            return {}, name
        seen.add(ref)
        node = spec
        for part in ref[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            node = node.get(part, {}) if isinstance(node, dict) else {}
        name = ref.rsplit("/", 1)[-1]
        schema = node
    return (schema if isinstance(schema, dict) else {}), name


def template_key(path: str) -> str:
    """'/orders/{order_id}' and '/orders/{id}' share the key '/orders/{}'."""
    return re.sub(r"\{[^}/]*\}", "{}", path)


def iter_operations(spec: dict):
    """Yield (path, method, operation, path_item) for every operation."""
    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method in HTTP_METHODS:
            op = item.get(method)
            if isinstance(op, dict):
                yield path, method, op, item


def operation_parameters(spec: dict, op: dict, item: dict) -> dict:
    """Merge path-level and operation-level parameters, keyed by (in, name)."""
    params = {}
    for raw in list(item.get("parameters") or []) + list(op.get("parameters") or []):
        param, _ = resolve(spec, raw)
        if "name" in param and "in" in param:
            params[(param["in"], param["name"])] = param
    return params


def json_schema(content: dict):
    """Pick the JSON media type schema from a content map."""
    if not isinstance(content, dict):
        return None
    for media, body in content.items():
        if "json" in media and isinstance(body, dict):
            return body.get("schema")
    return None


def request_schema(spec: dict, op: dict):
    body, _ = resolve(spec, op.get("requestBody") or {})
    return json_schema(body.get("content"))


def response_schema(spec: dict, op: dict):
    """The schema of the first 2xx JSON response."""
    responses = op.get("responses") or {}
    for code in sorted(responses, key=str):
        if str(code).startswith("2"):
            resp, _ = resolve(spec, responses[code])
            schema = json_schema(resp.get("content"))
            if schema is not None:
                return str(code), schema
    return None, None
