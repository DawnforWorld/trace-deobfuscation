"""Trace file parser — Intel Pin JSON Lines format.

Each line is a complete JSON object representing one executed instruction:

    {
      "addr": "7FF6A0B01000",
      "bytes": "E9 1B 06 00 00",
      "disasm": "jmp 0x7FF6A0B01620",
      "regs": {"RAX": "5", ..., "EFLAGS": "246"},
      "mem_r": [{"addr": "...", "size": 8, "val": "..."}],
      "mem_w": [{"addr": "...", "size": 8, "val": "..."}],
      "thread_id": 1234,
      "branch_taken": true
    }

All hex values are strings.  ``regs`` holds machine state *before* the
instruction executes; EFLAGS is one of the register entries.
``mem_r`` / ``mem_w`` capture runtime memory accesses (Pin IARG_MEMORYREAD_EA
/ IARG_MEMORYWRITE_EA).  ``branch_taken`` records the actual direction of
conditional branches (Pin IARG_BRANCH_TAKEN).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
import re

from .models import MemAccess, Record


# ---------------------------------------------------------------------------
# Sanitise JSON lines that contain raw control characters (Pin pintool may
# embed literal \t / \n inside disassembly strings).
# ---------------------------------------------------------------------------

def _sanitize_json_line(raw: str) -> str:
    """Escape literal control characters inside JSON string values."""

    def _escape_inner(m: re.Match) -> str:
        inner = m.group(1)
        result = []
        i = 0
        while i < len(inner):
            ch = inner[i]
            if ch == "\\" and i + 1 < len(inner):
                result.append("\\")
                result.append(inner[i + 1])
                i += 2
                continue
            if "\x00" <= ch <= "\x1f":
                result.append(_escape_char(ch))
            else:
                result.append(ch)
            i += 1
        return '"' + "".join(result) + '"'

    return _JSON_STRING_RE.sub(_escape_inner, raw)


def _escape_char(ch: str) -> str:
    mapping = {
        "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t",
    }
    return mapping.get(ch, f"\\u{ord(ch):04x}")


_JSON_STRING_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')


# ---------------------------------------------------------------------------
# Safe hex parsing
# ---------------------------------------------------------------------------


def _hex_int(s: object, default: int = 0) -> int:
    """Safely convert a hex string (or int) to int.

    Empty strings, whitespace, malformed hex, and ``None`` are treated
    as *default*.  Multi-value strings (e.g. ``"A:B"`` from XMM regs)
    only keep the first segment.
    """
    if isinstance(s, int):
        return s
    if isinstance(s, str):
        stripped = s.strip()
        if stripped:
            # Take only the first segment before any separator
            first = stripped.split(":")[0].split(",")[0]
            try:
                return int(first, 16)
            except ValueError:
                pass
    return default


def parse_trace(filepath: str | Path) -> list[Record]:
    """Parse an Intel Pin JSON Lines trace file.

    Args:
        filepath: Path to the ``.jsonl`` trace file.

    Returns:
        List of parsed Record objects in execution order.

    Raises:
        FileNotFoundError: If ``filepath`` does not exist.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Trace file not found: {filepath}")

    records: list[Record] = []
    errors: int = 0
    max_errors = 20  # don't flood stderr for huge files

    with path.open("r", encoding="utf-8", errors="replace") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                # Retry with control-character sanitisation
                try:
                    sanitized = _sanitize_json_line(line)
                    obj = json.loads(sanitized)
                except json.JSONDecodeError:
                    if errors < max_errors:
                        print(f"[parser] line {lineno}: invalid JSON — {exc}", file=__import__("sys").stderr)
                        print(f"         raw: {line}", file=__import__("sys").stderr)
                        errors += 1
                    continue

            try:
                # --- address ---
                address = _hex_int(obj.get("addr", 0))

                # --- registers (EFLAGS is inside regs) ---
                raw_regs = obj.get("regs") or {}
                registers: dict[str, int] = {}
                rflags = 0
                for k, v in raw_regs.items():
                    val = _hex_int(v)
                    if k.upper() == "EFLAGS":
                        rflags = val
                    else:
                        registers[k.upper()] = val

                # --- memory reads ---
                mem_reads: list[MemAccess] = []
                for mr in obj.get("mem_r") or []:
                    mem_reads.append(MemAccess(
                        address=_hex_int(mr.get("addr", 0)),
                        size=int(mr.get("size") or 0),
                        value=_hex_int(mr.get("val", 0)),
                    ))

                # --- memory writes ---
                mem_writes: list[MemAccess] = []
                for mw in obj.get("mem_w") or []:
                    mem_writes.append(MemAccess(
                        address=_hex_int(mw.get("addr", 0)),
                        size=int(mw.get("size") or 0),
                        value=_hex_int(mw.get("val", 0)),
                    ))

                # --- branch_taken ---
                raw_bt = obj.get("branch_taken")
                branch_taken: Optional[bool] = None
                if isinstance(raw_bt, bool):
                    branch_taken = raw_bt
                elif isinstance(raw_bt, int):
                    branch_taken = bool(raw_bt)

                # --- thread_id ---
                raw_tid = obj.get("thread_id")
                thread_id = int(raw_tid) if raw_tid is not None else 0

                record = Record(
                    address=address,
                    bytes_hex=obj.get("bytes") or "",
                    disasm=obj.get("disasm") or "",
                    registers=registers,
                    rflags=rflags,
                    mem_reads=mem_reads,
                    mem_writes=mem_writes,
                    branch_taken=branch_taken,
                    thread_id=thread_id,
                    comment=obj.get("comment") or "",
                )
                records.append(record)

            except Exception as exc:
                if errors < max_errors:
                    print(f"[parser] line {lineno}: {exc.__class__.__name__}: {exc}", file=__import__("sys").stderr)
                    print(f"         raw: {line}", file=__import__("sys").stderr)
                    errors += 1
                # skip this line and continue

    if errors:
        print(f"[parser] {errors} line(s) skipped due to parse errors", file=__import__("sys").stderr)

    return records
