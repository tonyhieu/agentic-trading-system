#!/usr/bin/env python3
"""SubagentStop hook: backfill the `meta` block of the most-recent entry in
research/program_database.json with per-iteration execution metadata from the
main session transcript.

Triggered on every SubagentStop. The hook is a no-op unless the most-recent
entry has `meta.duration_seconds is None` AND `meta.tokens_used is None` (the
researcher's marker that this entry expects a backfill). Subagents that are
not the researcher leave the file untouched.

Per-iteration scoping. The `transcript_path` a SubagentStop hook receives is
the main session transcript -- the parent conversation file, which
accumulates across every subagent invocation in the session. It is NOT the
just-stopped subagent's own transcript. Scanning the whole file every time
would make each entry cumulative (issue #78). Instead, an offset cursor at
`research/.meta_cursor.json` records how many transcript lines have already
been consumed; each run scans only the new slice. The cursor is machine-local
runtime state (it stores an absolute transcript path) and is git-ignored. If
it is missing or stale, the hook re-scans from the start -- over-counting at
worst once, never under-counting.

Because the transcript is the main session's, `meta` measures the session
slice between SubagentStop firings, not the researcher subagent's own compute
(which lives in a separate `subagents/agent-<id>.jsonl`). See issue #88 for
the follow-up to scan the per-subagent transcript instead.

Computes (over the current iteration's slice only):
  - meta.duration_seconds: wall-clock seconds from the slice's first
    transcript message to its last, parsed from the per-message `timestamp`.
  - meta.tokens_used: {"input": ..., "output": ..., "cache_creation": ...,
    "cache_read": ..., "total": ...} summed across every transcript record
    in the slice that carries a `usage` block.

After patching, attempts a `chore(<algo-id>): backfill execution metadata`
commit so the working tree stays clean, then attempts
`git push --set-upstream origin <branch>` if the current branch is an
`iter/*` branch. Both steps are best-effort: a failure (pre-commit hook,
dirty unrelated files, no git, no remote, no auth, etc.) is silently
ignored -- the local commit stays in place and the user can push manually.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    # fromisoformat in 3.11+ accepts "Z"; normalize for older versions too.
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _scan_transcript(
    transcript_path: Path,
    start_line: int = 0,
) -> tuple[dict[str, int] | None, float | None, int]:
    """Scan transcript lines [start_line, EOF) for token totals and duration.

    Returns (token_totals, duration_seconds, lines_seen):
      - token_totals / duration_seconds are computed ONLY over the slice of
        lines at index >= start_line. Either may be None when that slice
        carries no usage blocks / no timestamps.
      - lines_seen is the TOTAL physical line count of the file (including
        lines before start_line) -- the next cursor value. On an OSError it
        is 0, which signals "unreadable; do not advance the cursor".

    A physical-line offset is used (not a record index) because the transcript
    is append-only JSONL: line N keeps its content across runs, and the count
    is immune to JSON parse failures and blank lines.
    """
    totals = {"input": 0, "output": 0, "cache_creation": 0, "cache_read": 0}
    saw_usage = False
    first_ts: datetime | None = None
    last_ts: datetime | None = None
    lines_seen = 0

    try:
        with transcript_path.open() as f:
            for idx, line in enumerate(f):
                lines_seen = idx + 1
                if idx < start_line:
                    continue  # Already consumed by a prior iteration.
                line = line.strip()
                if not line:
                    continue
                try:
                    record: dict[str, Any] = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts = _parse_ts(record.get("timestamp"))
                if ts is not None:
                    if first_ts is None:
                        first_ts = ts
                    last_ts = ts

                msg = record.get("message") or {}
                usage = msg.get("usage") or {}
                if usage:
                    saw_usage = True
                    totals["input"] += int(usage.get("input_tokens", 0) or 0)
                    totals["output"] += int(usage.get("output_tokens", 0) or 0)
                    totals["cache_creation"] += int(usage.get("cache_creation_input_tokens", 0) or 0)
                    totals["cache_read"] += int(usage.get("cache_read_input_tokens", 0) or 0)
    except OSError:
        return None, None, 0

    token_totals: dict[str, int] | None = None
    if saw_usage:
        totals["total"] = sum(totals.values())
        token_totals = totals

    duration: float | None = None
    if first_ts is not None and last_ts is not None and last_ts >= first_ts:
        duration = (last_ts - first_ts).total_seconds()

    return token_totals, duration, lines_seen


def _read_cursor(cursor_path: Path) -> dict[str, Any] | None:
    """Return the cursor state `{"transcript_path": str, "lines_consumed":
    int >= 0}`, or None when the file is absent, unreadable, corrupt, or has
    the wrong shape. A None result makes the caller scan from line 0."""
    try:
        data = json.loads(cursor_path.read_text())
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    tp = data.get("transcript_path")
    lc = data.get("lines_consumed")
    # bool is a subclass of int -- reject it explicitly.
    if not isinstance(tp, str) or isinstance(lc, bool) or not isinstance(lc, int) or lc < 0:
        return None
    return {"transcript_path": tp, "lines_consumed": lc}


def _write_cursor(cursor_path: Path, transcript_path: Path, lines_consumed: int) -> None:
    """Best-effort: persist the offset cursor so the next SubagentStop scans
    only new transcript lines. A failure here is non-fatal -- the next run
    finds no/old cursor and re-scans from the start, which over-counts at
    worst once and never under-counts."""
    try:
        cursor_path.write_text(
            json.dumps(
                {
                    "transcript_path": str(transcript_path),
                    "lines_consumed": lines_consumed,
                },
                indent=2,
            )
            + "\n"
        )
    except OSError:
        return  # Best-effort: next run resets to a full scan.


def _try_commit(cwd: str, algo_id: str) -> None:
    try:
        subprocess.run(
            ["git", "-C", cwd, "add", "research/program_database.json"],
            check=True,
            capture_output=True,
        )
        # `git diff --cached --quiet` exits 0 if nothing staged, 1 if changes staged.
        diff = subprocess.run(
            ["git", "-C", cwd, "diff", "--cached", "--quiet", "research/program_database.json"],
        )
        if diff.returncode == 0:
            return  # Nothing to commit
        subprocess.run(
            [
                "git", "-C", cwd, "commit",
                "-m", f"chore({algo_id}): backfill execution metadata",
                "--", "research/program_database.json",
            ],
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, OSError, FileNotFoundError):
        return  # Best-effort: leave file dirty for next iteration


def _try_push(cwd: str) -> None:
    """Best-effort: push the current branch to origin if it looks like a
    researcher iter branch. Silently no-op on any failure (no auth, no
    remote, detached HEAD, etc.). The user can always push manually."""
    try:
        branch = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if not branch.startswith("iter/"):
            return  # Only push researcher iter branches from this hook.
        subprocess.run(
            ["git", "-C", cwd, "push", "--set-upstream", "origin", branch],
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, OSError, FileNotFoundError):
        return  # Best-effort: leave unpushed; remote can be updated manually.


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    transcript_path_s = payload.get("transcript_path")
    cwd = payload.get("cwd")
    if not transcript_path_s or not cwd:
        return

    db_path = Path(cwd) / "research" / "program_database.json"
    if not db_path.exists():
        return

    try:
        db = json.loads(db_path.read_text())
    except (json.JSONDecodeError, OSError):
        return

    if not isinstance(db, list) or not db:
        return

    last = db[-1]
    meta = last.get("meta")
    if not isinstance(meta, dict):
        return
    # Only patch entries the researcher explicitly marked for backfill. This
    # early-return runs before the cursor is read, so an already-backfilled
    # entry never advances the cursor.
    if meta.get("tokens_used") is not None or meta.get("duration_seconds") is not None:
        return

    transcript_path = Path(transcript_path_s)
    if not transcript_path.exists():
        return

    # The transcript persists and grows when the loop driver continues the same
    # researcher subagent across iterations. Scan only the slice produced since
    # the last backfill so each entry records its own iteration, not a running
    # total (issue #78). The cursor lives next to the database and is git-ignored.
    cursor_path = Path(cwd) / "research" / ".meta_cursor.json"
    cursor = _read_cursor(cursor_path)
    start_line = 0
    if cursor is not None and cursor["transcript_path"] == str(transcript_path):
        start_line = cursor["lines_consumed"]

    token_totals, duration, lines_seen = _scan_transcript(transcript_path, start_line)

    # Cursor pointed past EOF (transcript truncated or rotated) -> rescan whole.
    if start_line > lines_seen:
        token_totals, duration, lines_seen = _scan_transcript(transcript_path, 0)

    if token_totals is None and duration is None:
        return  # Empty slice / nothing useful; leave the cursor unadvanced.

    if token_totals is not None:
        last["meta"]["tokens_used"] = token_totals
    if duration is not None:
        last["meta"]["duration_seconds"] = round(duration, 1)

    db_path.write_text(json.dumps(db, indent=2) + "\n")

    # Advance the cursor only after a real backfill consumed this slice, and
    # before the git steps so a commit/push failure cannot lose the progress.
    _write_cursor(cursor_path, transcript_path, lines_seen)

    algo_id = str(last.get("id") or "unknown")
    _try_commit(cwd, algo_id)
    _try_push(cwd)


if __name__ == "__main__":
    main()
