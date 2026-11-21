"""A mock HTTP server built from an OpenAPI spec.

It binds to 127.0.0.1 only. It checks each request against the spec (path,
method, required query parameters, parameter types and enums, and the JSON
body) and answers with an example built from the response schema. Unknown body
properties are rejected when the schema sets additionalProperties to false.
"""

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .spec import iter_operations, operation_parameters, request_schema, resolve, response_schema

MAX_BODY_BYTES = 1_000_000


def _compile(path: str):
    pattern = re.sub(r"\\\{([^}/]+)\\\}", r"(?P<\1>[^/]+)", re.escape(path))
    return re.compile("^" + pattern + "$")


def example_for(spec, schema, depth=0):
    """Build a deterministic example value from a schema."""
    schema, _ = resolve(spec, schema or {})
    if depth > 12:
        return None
    if "example" in schema:
        return schema["example"]
    if "default" in schema:
        return schema["default"]
    if isinstance(schema.get("enum"), list) and schema["enum"]:
        return schema["enum"][0]
    t = schema.get("type")
    if isinstance(t, list):
        t = next((x for x in t if x != "null"), None)
    if t == "object" or "properties" in schema:
        return {k: example_for(spec, v, depth + 1) for k, v in (schema.get("properties") or {}).items()}
    if t == "array":
        return [example_for(spec, schema.get("items"), depth + 1)]
    return {"string": "string", "integer": 1, "number": 1.5, "boolean": True}.get(t)


_TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
}


def validate(spec, schema, value, where="body", depth=0):
    """Return a list of error strings. An empty list means the value fits."""
    schema, _ = resolve(spec, schema or {})
    if depth > 20 or not schema:
        return []
    if value is None and schema.get("nullable"):
        return []
    errors = []
    t = schema.get("type") or ("object" if "properties" in schema else None)
    types = t if isinstance(t, list) else [t] if t else []
    if types and not any(_TYPE_CHECKS.get(x, lambda v: True)(value) for x in types):
        return [f"{where}: expected {'|'.join(types)}, got {type(value).__name__}"]
    if isinstance(schema.get("enum"), list) and value not in schema["enum"]:
        errors.append(f"{where}: {value!r} is not one of {schema['enum']}")
    if isinstance(value, dict):
        props = schema.get("properties") or {}
        for name in schema.get("required") or []:
            if name not in value:
                errors.append(f"{where}: missing required property {name!r}")
        for name, sub in value.items():
            if name in props:
                errors.extend(validate(spec, props[name], sub, f"{where}.{name}", depth + 1))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{where}: unknown property {name!r}")
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            errors.extend(validate(spec, schema["items"], item, f"{where}[{i}]", depth + 1))
    return errors


def _coerce(raw: str, schema):
    t = schema.get("type")
    try:
        if t == "integer":
            return int(raw)
        if t == "number":
            return float(raw)
        if t == "boolean":
            return {"true": True, "false": False}[raw]
    except (ValueError, KeyError):
        return _BAD
    return raw


_BAD = object()


class MockServer:
    """Serve a spec on 127.0.0.1 in a background thread.

    Use it as a context manager. `url` holds the base URL. `requests` logs
    (method, path, status, errors) for each call.
    """

    def __init__(self, spec: dict, host: str = "127.0.0.1", port: int = 0):
        if host not in ("127.0.0.1", "localhost"):
            raise ValueError("the mock server binds to a loopback address only")
        self.spec = spec
        self.routes = [(_compile(path), path, method.upper(), op, item) for path, method, op, item in iter_operations(spec)]
        self.requests = []
        self._lock = threading.Lock()
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # keep test output quiet
                pass

            def _handle(self):
                status, payload, errors = server.respond(self.command, self.path, self.headers, self._body())
                with server._lock:
                    server.requests.append((self.command, self.path, status, errors))
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _body(self):
                length = int(self.headers.get("Content-Length") or 0)
                if length > MAX_BODY_BYTES:
                    return b"__too_large__"
                return self.rfile.read(length) if length else b""

            do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _handle

        self._httpd = ThreadingHTTPServer((host, port), Handler)
        self._thread = None

    @property
    def url(self) -> str:
        host, port = self._httpd.server_address[:2]
        return f"http://{host}:{port}"

    def respond(self, method, raw_path, headers, body):
        parts = urlsplit(raw_path)
        path_matched = False
        for pattern, _template, route_method, op, item in self.routes:
            match = pattern.match(parts.path)
            if not match:
                continue
            path_matched = True
            if route_method != method:
                continue
            errors = self._check(op, item, match.groupdict(), parse_qs(parts.query), headers, body)
            if errors:
                return 400, {"error": "invalid request", "details": errors}, errors
            code, schema = response_schema(self.spec, op)
            payload = example_for(self.spec, schema) if schema is not None else None
            return int(code or 200), payload, []
        if path_matched:
            return 405, {"error": "method not allowed"}, ["method not allowed"]
        return 404, {"error": "no such endpoint"}, ["no such endpoint"]

    def _check(self, op, item, path_values, query, headers, body):
        errors = []
        for (where, name), param in operation_parameters(self.spec, op, item).items():
            schema, _ = resolve(self.spec, param.get("schema") or {})
            if where == "query":
                raw = query.get(name, [None])[-1]
            elif where == "path":
                raw = path_values.get(name)
                if raw is None and len(path_values) == 1:
                    raw = next(iter(path_values.values()))
            elif where == "header":
                raw = headers.get(name)
            else:
                continue
            if raw is None:
                if param.get("required"):
                    errors.append(f"{where} parameter {name!r} is required")
                continue
            value = _coerce(raw, schema)
            if value is _BAD:
                errors.append(f"{where} parameter {name!r}: {raw!r} is not a valid {schema.get('type')}")
                continue
            errors.extend(validate(self.spec, schema, value, f"{where} parameter {name!r}"))
        req_schema = request_schema(self.spec, op)
        if req_schema is not None:
            if body == b"__too_large__":
                return errors + ["body too large"]
            if not body:
                req_body, _ = resolve(self.spec, op.get("requestBody") or {})
                if req_body.get("required"):
                    errors.append("a request body is required")
            else:
                try:
                    value = json.loads(body)
                except ValueError:
                    return errors + ["body is not valid JSON"]
                errors.extend(validate(self.spec, req_schema, value))
        return errors

    def __enter__(self):
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread:
            self._thread.join(timeout=5)
        return False
