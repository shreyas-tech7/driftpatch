"""A pluggable LLM proposer with replay and record modes.

The proposer sends the breaking changes, the call sites and the affected client
files to a model. The model answers with the full new text of each file it
changes, inside <file path="..."> blocks. driftpatch turns that into a diff and
the verifier gates it like any other patch.

- replay mode reads a recorded answer from fixtures/llm/<model>/<prompt hash>.json.
  It makes no network call. A missing recording is an error, never a guess.
- record mode calls an OpenAI-compatible chat endpoint once per prompt and saves
  the answer. The key comes only from an environment variable.
"""

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .patch import PatchError, make_diff, safe_relpath
from .proposer_rule import Proposal
from .verifier import is_test_file

PROMPT_VERSION = "v1"
SYSTEM = (
    "You fix API client code after a breaking change in an OpenAPI spec. "
    "Change only the client source files you are shown. Never edit tests. "
    'Answer with the complete new text of each file you change, inside <file path="PATH"> and </file>. '
    "Keep every other line the same. Do not explain."
)
_FILE_BLOCK = re.compile(r'<file path="([^"]+)">\n?(.*?)</file>', re.S)


class ReplayMissing(RuntimeError):
    pass


class RecordError(RuntimeError):
    pass


def build_prompt(changes, sites, files: dict) -> str:
    lines = [f"Prompt version {PROMPT_VERSION}.", "", "Breaking changes:"]
    for i, change in enumerate(changes, start=1):
        lines.append(f"{i}. {change.describe()} Operations: {', '.join(change.operations)}.")
    lines += ["", "Call sites found by driftpatch:"]
    for site in sites:
        lines.append(f"- {site.file}:{site.line} {site.kind} `{site.symbol}` in {site.function}()")
    for rel in sorted(files):
        lines += ["", f'<file path="{rel}">', files[rel].rstrip("\n"), "</file>"]
    return "\n".join(lines) + "\n"


def prompt_sha(prompt: str, model: str) -> str:
    return hashlib.sha256(f"{model}\n{SYSTEM}\n{prompt}".encode()).hexdigest()


def parse_answer(answer: str, allowed: set) -> dict:
    """Return {relpath: text}. Rejects test files, unknown paths and unsafe paths."""
    out = {}
    for rel, body in _FILE_BLOCK.findall(answer):
        rel = safe_relpath(rel.strip())
        if rel not in allowed or is_test_file(rel):
            raise PatchError(f"the model tried to write a file it was not given: {rel}")
        out[rel] = body if body.endswith("\n") else body + "\n"
    return out


@dataclass
class Endpoint:
    url: str = "https://api.groq.com/openai/v1/chat/completions"
    model: str = "llama-3.3-70b-versatile"
    key_env: str = "GROQ_API_KEY"

    @property
    def host(self) -> str:
        return urllib.parse.urlsplit(self.url).hostname or ""


class LLMProposer:
    name = "llm"

    def __init__(
        self, mode="replay", endpoint: Endpoint = None, fixtures_dir="fixtures/llm", transport=None, max_tries=5, sleep=time.sleep
    ):
        if mode not in ("replay", "record"):
            raise ValueError("mode must be replay or record")
        self.mode = mode
        self.endpoint = endpoint or Endpoint()
        if not self.endpoint.url.startswith("https://"):
            raise ValueError("the model endpoint must use https")
        self.fixtures = Path(fixtures_dir) / re.sub(r"[^\w.-]", "_", self.endpoint.model)
        self.transport = transport or self._http
        self.max_tries = max_tries
        self.sleep = sleep

    def propose(self, client_dir, changes, sites, language) -> Proposal:
        client_dir = Path(client_dir)
        rels = sorted({s.file for s in sites})
        files = {rel: (client_dir / rel).read_text(encoding="utf-8") for rel in rels}
        prompt = build_prompt(changes, sites, files)
        sha = prompt_sha(prompt, self.endpoint.model)
        record = self._replay(sha) if self.mode == "replay" else self._record(sha, prompt)
        proposal = Proposal(self.name)
        usage = record.get("usage") or {}
        proposal.tokens = int(usage.get("prompt_tokens", 0)) + int(usage.get("completion_tokens", 0))
        try:
            new_files = parse_answer(record["answer"], set(files))
        except PatchError as err:
            proposal.notes.append(str(err))
            return proposal
        proposal.files = {rel: text for rel, text in new_files.items() if text != files[rel]}
        proposal.diff = make_diff({rel: files[rel] for rel in proposal.files}, proposal.files)
        proposal.handled = list(range(len(changes))) if proposal.diff else []
        return proposal

    def _path(self, sha):
        return self.fixtures / f"{sha}.json"

    def _replay(self, sha):
        path = self._path(sha)
        if not path.exists():
            raise ReplayMissing(f"no recording for prompt {sha[:12]} in {self.fixtures}")
        return json.loads(path.read_text())

    def _record(self, sha, prompt):
        key = os.environ.get(self.endpoint.key_env, "")
        payload = {
            "model": self.endpoint.model,
            "temperature": 0,
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        }
        wait = 2.0
        for attempt in range(1, self.max_tries + 1):
            status, body = self.transport(self.endpoint.url, payload, key)
            if status == 429 and attempt < self.max_tries:
                self.sleep(wait)
                wait *= 2
                continue
            if status in (401, 403):
                raise RecordError(f"record mode is blocked: the endpoint answered {status}")
            if status != 200:
                raise RecordError(f"the endpoint answered {status}")
            data = json.loads(body)
            record = {
                "prompt_sha256": sha,
                "model": self.endpoint.model,
                "endpoint_host": self.endpoint.host,
                "recorded_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "answer": data["choices"][0]["message"]["content"],
                "usage": data.get("usage") or {},
            }
            self.fixtures.mkdir(parents=True, exist_ok=True)
            self._path(sha).write_text(json.dumps(record, indent=2) + "\n")
            return record
        raise RecordError("rate limited on every try")

    @staticmethod
    def _http(url, payload, key):
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")  # noqa: S310 (Endpoint only accepts https)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (Endpoint only accepts https)
                return resp.status, resp.read().decode()
        except urllib.error.HTTPError as err:
            return err.code, err.read().decode(errors="replace")
        except (urllib.error.URLError, OSError) as err:
            return 0, str(err)
