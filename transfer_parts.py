"""Validate curl ranges and commit resumable fragments without saving response secrets."""
import json
import os
from pathlib import Path
import re
import shutil
import sys


def segment_chunk(total, mode="segmented"):
    parts = 2 if mode == "segmented2" else 8
    return total if mode == "single" else max(1, (total + parts - 1) // parts)


def initial_transfer_mode(provider, configured):
    return "segmented2" if provider == "gofile" and configured != "single" else configured


def segment_count(total, mode="segmented"):
    # Preserve the old ceil(total/8) layout for existing jobs, omitting empty tails.
    chunk = segment_chunk(total, mode)
    return 1 if mode == "single" else (total + chunk - 1) // chunk


def commit_fragment(part, start, end, total):
    part = Path(part)
    more = part.with_name(part.name + ".more")
    headers = part.with_name(part.name + ".headers")
    discard = True
    try:
        if not headers.exists():
            return False
        raw = headers.read_bytes()[:65536]
        blocks = re.split(rb"\r?\n\r?\n", raw)
        blocks = [block for block in blocks if re.match(rb"HTTP/\S+ \d{3}", block)]
        if not blocks:
            return False
        block = blocks[-1]
        status = int(block.split(None, 2)[1])
        if status == 429:
            retry = re.search(rb"(?im)^retry-after:\s*([^\r\n]+)", block)
            marker = part.parent / ".rate-limit"
            marker.write_text(json.dumps({"retry_after": retry.group(1).decode("ascii", "replace") if retry else ""}), encoding="utf-8")
            return False
        if not more.exists():
            return False
        count = more.stat().st_size
        existing = part.stat().st_size if part.exists() else 0
        match = re.search(rb"(?im)^content-range:\s*bytes (\d+)-(\d+)/(\d+)\s*$", block)
        if status == 206 and match:
            first, last, size = map(int, match.groups())
            offset = first - start
            valid = size == total and last == end and 0 <= offset <= existing and count <= end - first + 1
        else:
            offset = 0
            valid = status == 200 and start == 0 and end == total - 1 and existing == 0 and count <= total
        if not valid:
            return False
        # Keep validated fragments on local I/O failure so a later attempt can
        # replay them at the original offset without losing downloaded bytes.
        safe_headers = block.splitlines()[0] + b"\r\n"
        for field in (b"content-range", b"content-disposition"):
            line = re.search(rb"(?im)^" + field + rb":[^\r\n]+", block)
            if line:
                safe_headers += line.group(0) + b"\r\n"
        headers.write_bytes(safe_headers + b"\r\n")
        discard = False
        # Write at the response's original offset, not append: safe even if a
        # previous commit was interrupted after writing but before removing .more.
        with part.open("r+b" if part.exists() else "wb") as output, more.open("rb") as source:
            output.seek(offset)
            shutil.copyfileobj(source, output, length=1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        if start == 0:
            disposition = re.search(rb"(?im)^content-disposition:\s*([^\r\n]+)", block)
            if disposition:
                (part.parent / ".response-headers").write_bytes(b"Content-Disposition: " + disposition.group(1) + b"\r\n")
        discard = True
        return True
    finally:
        # Never retain cookies, tokens, or full response headers after a transfer.
        if discard:
            headers.unlink(missing_ok=True)
            more.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        ok = commit_fragment(sys.argv[1], *map(int, sys.argv[2:5]))
        sys.exit(0 if ok else 1)
    except (OSError, ValueError):
        sys.exit(1)
