#!/usr/bin/env python3
"""SubagentStop hook: backfill the `meta` block of the most-recent entry in
research/program_database.json with execution metadata from the just-stopped
subagent's transcript.

Triggered on every SubagentStop. The hook is a no-op unless the most-recent
entry has `meta.duration_seconds is None` AND `meta.tokens_used is None` (the
researcher's marker that this entry expects a backfill). Subagents that are
not the researcher leave the file untouched.

Computes:
  - meta.duration_seconds: wall-clock seconds from first to last transcript
    message, parsed from the per-message `timestamp` field.
  - meta.tokens_used: {"input": ..., "output": ..., "cache_creation": ...,
    "cache_read": ..., "total": ...} summed across every message that
    carries a `usage` block in the transcript.

After patching, attempts a `chore(<algo-id>): backfill execution metadata`
commit so the working tree stays clean, then attempts
`git push --set-upstream origin <branch>` if the current branch is an
`iter/*` branch. Both steps are best-effort: a failure (pre-commit hook,
dirty unrelated files, no git, no remote, no auth, etc.) is silently
ignored — the local commit stays in place and the user can push manually.
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


def _scan_transcript(transcript_path: Path) -> tuple[dict[str, int] | None, float | None]:
    """Return (token totals, duration_seconds). Either may be None on failure."""
    totals = {"input": 0, "output": 0, "cache_creation": 0, "cache_read": 0}
    saw_usage = False
    first_ts: datetime | None = None
    last_ts: datetime | None = None

    try:
        with transcript_path.open() as f:
            for line in f:
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
        return None, None

    token_totals: dict[str, int] | None = None
    if saw_usage:
        totals["total"] = sum(totals.values())
        token_totals = totals

    duration: float | None = None
    if first_ts is not None and last_ts is not None and last_ts >= first_ts:
        duration = (last_ts - first_ts).total_seconds()

    return token_totals, duration


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
    # Only patch entries the researcher explicitly marked for backfill.
    if meta.get("tokens_used") is not None or meta.get("duration_seconds") is not None:
        return

    transcript_path = Path(transcript_path_s)
    if not transcript_path.exists():
        return

    token_totals, duration = _scan_transcript(transcript_path)
    if token_totals is None and duration is None:
        return  # Nothing useful extracted; skip silently

    if token_totals is not None:
        last["meta"]["tokens_used"] = token_totals
    if duration is not None:
        last["meta"]["duration_seconds"] = round(duration, 1)

    db_path.write_text(json.dumps(db, indent=2) + "\n")

    algo_id = str(last.get("id") or "unknown")
    _try_commit(cwd, algo_id)
    _try_push(cwd)


if __name__ == "__main__":
    main()
