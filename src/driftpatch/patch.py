"""Make and apply unified diffs. The applier is strict: every context line must match."""

import difflib
import re
from pathlib import Path, PurePosixPath

_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class PatchError(ValueError):
    pass


def _lines(text: str) -> list:
    """Split on \\n only. str.splitlines also splits on form feeds and other breaks, which diff tools do not."""
    return re.findall(r"[^\n]*\n|[^\n]+\Z", text)


def make_diff(old_files: dict, new_files: dict) -> str:
    """Unified diff with a/ and b/ prefixes for every file whose text changed."""
    out = []
    for rel in sorted(set(old_files) | set(new_files)):
        old = old_files.get(rel, "")
        new = new_files.get(rel, "")
        if old == new:
            continue
        out.extend(
            difflib.unified_diff(
                _lines(old),
                _lines(new),
                fromfile=f"a/{rel}",
                tofile=f"b/{rel}",
            )
        )
    text = "".join(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n" for line in out)
    return text


def diff_size(diff_text: str) -> int:
    """Changed lines: added plus removed, headers excluded."""
    size = 0
    for line in diff_text.split("\n"):
        if line.startswith(("+++", "---")):
            continue
        if line.startswith(("+", "-")):
            size += 1
    return size


def files_in_diff(diff_text: str) -> list:
    files = []
    for line in diff_text.split("\n"):
        if line.startswith("+++ "):
            name = line[4:].split("\t")[0].strip()
            if name.startswith("b/"):
                name = name[2:]
            files.append(name)
    return files


def safe_relpath(rel: str) -> str:
    """Refuse absolute paths and paths that climb out of the client folder."""
    p = PurePosixPath(rel)
    bad = not p.parts or p.is_absolute() or ".." in p.parts or "\\" in rel or ":" in p.parts[0] or "\x00" in rel
    if bad:
        raise PatchError(f"unsafe path in patch: {rel!r}")
    return str(p)


def parse_diff(diff_text: str) -> dict:
    """Return {relpath: [hunks]} where each hunk is (old_start, lines)."""
    files = {}
    current = None
    lines = _lines(diff_text)
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("--- "):
            if i + 1 >= len(lines) or not lines[i + 1].startswith("+++ "):
                raise PatchError("a '---' line must be followed by a '+++' line")
            name = lines[i + 1][4:].split("\t")[0].strip()
            if name.startswith("b/"):
                name = name[2:]
            current = files.setdefault(safe_relpath(name), [])
            i += 2
            continue
        m = _HUNK.match(line)
        if m:
            if current is None:
                raise PatchError("hunk before file header")
            old_start = int(m.group(1))
            # The header counts say how many lines the hunk has, so a removed line such as
            # "-- comment" is never mistaken for a "--- file" header.
            old_left = int(m.group(2)) if m.group(2) is not None else 1
            new_left = int(m.group(4)) if m.group(4) is not None else 1
            hunk = []
            i += 1
            while i < len(lines) and (old_left > 0 or new_left > 0 or lines[i].startswith("\\")):
                line = lines[i]
                if line.startswith("\\"):
                    if hunk:
                        tag, text = hunk[-1]
                        hunk[-1] = (tag, text.rstrip("\n"))
                elif line[:1] in (" ", "+", "-") or line.strip() == "":
                    tag = line[:1] if line[:1] in (" ", "+", "-") else " "
                    body = line[1:] if line[:1] in (" ", "+", "-") else "\n"
                    hunk.append((tag, body))
                    old_left -= tag in (" ", "-")
                    new_left -= tag in (" ", "+")
                else:
                    raise PatchError(f"bad hunk line: {line!r}")
                i += 1
            if old_left > 0 or new_left > 0:
                raise PatchError("hunk is shorter than its header says")
            current.append((old_start, hunk))
            continue
        i += 1
    return files


def apply_to_text(text: str, hunks) -> str:
    old_lines = _lines(text)
    out = []
    pos = 0
    for old_start, hunk in hunks:
        start = max(old_start - 1, 0)
        if old_start == 0:
            start = 0
        if start < pos:
            raise PatchError("overlapping hunks")
        out.extend(old_lines[pos:start])
        pos = start
        for tag, line in hunk:
            if tag in (" ", "-"):
                if pos >= len(old_lines) or old_lines[pos] != line:
                    have = old_lines[pos] if pos < len(old_lines) else "<end of file>"
                    raise PatchError(f"context does not match at line {pos + 1}: expected {line!r}, found {have!r}")
                if tag == " ":
                    out.append(line)
                pos += 1
            else:
                out.append(line)
    out.extend(old_lines[pos:])
    return "".join(out)


def apply_diff(diff_text: str, root) -> dict:
    """Apply a diff to the files under root. Returns {relpath: new_text}. Writes nothing."""
    root = Path(root)
    result = {}
    for rel, hunks in parse_diff(diff_text).items():
        target = root / rel
        old = target.read_text(encoding="utf-8") if target.exists() else ""
        result[rel] = apply_to_text(old, hunks)
    return result


def write_files(root, files: dict):
    root = Path(root).resolve()
    for rel, text in files.items():
        target = (root / safe_relpath(rel)).resolve()
        if root not in target.parents:
            raise PatchError(f"refusing to write outside {root}: {rel}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
