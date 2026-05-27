#!/usr/bin/env python3
"""SubagentStop hook: backfill the `meta` block of the most-recent entry in
research/program_database.json with per-iteration execution metadata for the
researcher subagent.

Triggered on every SubagentStop. The hook is a no-op unless the most-recent
entry has `meta.duration_seconds is None` AND `meta.tokens_used is None` (the
researcher's marker that this entry expects a backfill). Subagents that are
not the researcher leave the file untouched.

Which transcript is measured (issue #88). A SubagentStop hook receives
`transcript_path` for the MAIN session transcript -- the parent conversation,
which accumulates across every subagent invocation. Scanning it measured the
orchestrator's compute, not the researcher's. Instead this hook derives the
researcher subagent's OWN transcript: subagent transcripts live beside the
main one at `<session>/subagents/agent-<id>.jsonl`, each with a sibling
`agent-<id>.meta.json` carrying `{"agentType": ...}`. The hook picks the
most-recently-modified `.jsonl` whose meta marks it `agentType == "researcher"`
-- the just-stopped researcher run. If no researcher transcript is found the
hook is a no-op (both `meta` fields stay null, which callers already tolerate).

Per-iteration scoping. When the loop driver continues the same researcher
subagent across iterations (SendMessage), one `agent-<id>.jsonl` keeps
growing, so the hook still scopes each backfill with an offset cursor at
`research/.meta_cursor.json` -- now keyed on the subagent transcript path.
Each run scans only the lines added since the last backfill. A fresh subagent
per iteration gets a new transcript file; the cursor path no longer matches
and the whole file is scanned. The cursor is machine-local runtime state (it
stores an absolute transcript path) and is git-ignored. If it is missing or
stale, the hook re-scans from the start -- over-counting at worst once, never
under-counting.

Computes (over the current iteration's slice only):
  - meta.duration_seconds: wall-clock seconds from the slice's first
    transcript message to its last, parsed from the per-message `timestamp`.
  - meta.tokens_used: {"input": ..., "output": ..., "cache_creation": ...,
    "cache_read": ..., "total": ...} taken from the LAST usage block in the
    slice, with `total` the sum of the four. The final turn's usage is a
    snapshot of the run's peak context plus its last output; its four-field
    sum matches the `total_tokens` Claude Code reports for the subagent.
    Summing usage across every turn instead would N-count the cached context
    that is re-read on each turn, inflating the figure by orders of magnitude.

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


def _find_researcher_transcript(main_transcript: Path) -> Path | None:
    """Locate the researcher subagent's own transcript.

    Subagent transcripts sit beside the main session transcript at
    `<main_transcript_stem>/subagents/agent-<id>.jsonl`, each paired with an
    `agent-<id>.meta.json` holding `{"agentType": ...}`. Returns the
    most-recently-modified `.jsonl` whose meta marks it the researcher (the
    just-stopped run), or None when no such transcript exists.
    """
    subagents_dir = main_transcript.with_suffix("") / "subagents"
    if not subagents_dir.is_dir():
        return None

    newest: Path | None = None
    newest_mtime = -1.0
    for jsonl in subagents_dir.glob("agent-*.jsonl"):
        meta_path = jsonl.parent / (jsonl.stem + ".meta.json")
        try:
            meta = json.loads(meta_path.read_text())
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if not isinstance(meta, dict) or meta.get("agentType") not in (
            "researcher",
            "per-iteration-researcher",
            "best-of-n-researcher",
        ):
            continue
        try:
            mtime = jsonl.stat().st_mtime
        except OSError:
            continue
        if mtime > newest_mtime:
            newest_mtime, newest = mtime, jsonl
    return newest


def _scan_transcript(
    transcript_path: Path,
    start_line: int = 0,
) -> tuple[dict[str, int] | None, float | None, int]:
    """Scan transcript lines [start_line, EOF) for token usage and duration.

    Returns (token_totals, duration_seconds, lines_seen):
      - token_totals is the LAST usage block found in the slice, normalized to
        {"input", "output", "cache_creation", "cache_read", "total"} with
        `total` the sum of the four. None when the slice carries no usage
        block. The last block is used (not a per-turn sum) because the cached
        context is re-read every turn -- summing `cache_read` across turns
        N-counts it. The final turn's usage is a snapshot of peak context.
      - duration_seconds spans the slice's first to last timestamped message.
        None when the slice carries no timestamps.
      - lines_seen is the TOTAL physical line count of the file (including
        lines before start_line) -- the next cursor value. On an OSError it
        is 0, which signals "unreadable; do not advance the cursor".

    A physical-line offset is used (not a record index) because the transcript
    is append-only JSONL: line N keeps its content across runs, and the count
    is immune to JSON parse failures and blank lines.
    """
    last_usage: dict[str, Any] | None = None
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

                usage = (record.get("message") or {}).get("usage") or {}
                if usage:
                    last_usage = usage
    except OSError:
        return None, None, 0

    token_totals: dict[str, int] | None = None
    if last_usage is not None:
        token_totals = {
            "input": int(last_usage.get("input_tokens", 0) or 0),
            "output": int(last_usage.get("output_tokens", 0) or 0),
            "cache_creation": int(last_usage.get("cache_creation_input_tokens", 0) or 0),
            "cache_read": int(last_usage.get("cache_read_input_tokens", 0) or 0),
        }
        token_totals["total"] = sum(token_totals.values())

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


def _try_commit(cwd: str, algo_id: str, extra_files: list[str] | None = None) -> None:
    files = ["research/program_database.json"] + (extra_files or [])
    try:
        subprocess.run(
            ["git", "-C", cwd, "add"] + files,
            check=True,
            capture_output=True,
        )
        # `git diff --cached --quiet` exits 0 if nothing staged, 1 if changes staged.
        diff = subprocess.run(
            ["git", "-C", cwd, "diff", "--cached", "--quiet"] + files,
        )
        if diff.returncode == 0:
            return  # Nothing to commit
        subprocess.run(
            [
                "git", "-C", cwd, "commit",
                "-m", f"chore({algo_id}): backfill execution metadata",
                "--"] + files,
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

    # --- Determine what needs patching ---

    # Path 1: research program database (existing researcher agent).
    db_needs_patch = False
    db: list[Any] = []
    db_path = Path(cwd) / "research" / "program_database.json"
    if db_path.exists():
        try:
            db = json.loads(db_path.read_text())
            if isinstance(db, list) and db:
                last = db[-1]
                meta = last.get("meta")
                if isinstance(meta, dict):
                    if meta.get("tokens_used") is None and meta.get("duration_seconds") is None:
                        db_needs_patch = True
        except (json.JSONDecodeError, OSError):
            pass

    # Path 2: experiment loop file (any experiment with a `.current_loop.json`
    # pointer under experiments/<name>/). Each pointer file is git-ignored and
    # written by the experiment's agent before commit. New experiments hook
    # into the same backfill mechanism just by writing such a pointer.
    loop_file: Path | None = None
    loop_file_rel: str | None = None
    experiments_dir = Path(cwd) / "experiments"
    if experiments_dir.is_dir():
        for pointer_path in sorted(experiments_dir.glob("*/.current_loop.json")):
            try:
                pointer = json.loads(pointer_path.read_text())
                rel = pointer.get("loop_file")
                if not rel:
                    continue
                candidate = Path(cwd) / rel
                if not candidate.exists():
                    continue
                loop_data = json.loads(candidate.read_text())
                if loop_data.get("tokens_used") is None:
                    loop_file = candidate
                    loop_file_rel = rel
                    break  # First unbackfilled pointer wins; one loop per SubagentStop.
            except (OSError, json.JSONDecodeError, KeyError, TypeError):
                continue

    if not db_needs_patch and loop_file is None:
        return  # Nothing to patch — skip transcript scan entirely.

    # --- Find the subagent transcript to measure (issue #88) ---
    # Use the subagent's own transcript rather than the main session transcript
    # so meta reflects the subagent's compute, not the orchestrator's.
    # Both "researcher" and "per-iteration-researcher" agent types are supported.
    main_transcript = Path(transcript_path_s)
    if not main_transcript.exists():
        return

    sub_transcript = _find_researcher_transcript(main_transcript)
    if sub_transcript is None:
        return  # No researcher transcript to measure; leave meta null.

    # A continued subagent keeps appending to one transcript file. Scan only
    # the slice produced since the last backfill so each entry records its own
    # iteration. The cursor is keyed on the subagent transcript path.
    cursor_path = Path(cwd) / "research" / ".meta_cursor.json"
    cursor = _read_cursor(cursor_path)
    start_line = 0
    if cursor is not None and cursor["transcript_path"] == str(sub_transcript):
        start_line = cursor["lines_consumed"]

    token_totals, duration, lines_seen = _scan_transcript(sub_transcript, start_line)

    # Cursor pointed past EOF (transcript truncated or rotated) -> rescan whole.
    if start_line > lines_seen:
        token_totals, duration, lines_seen = _scan_transcript(sub_transcript, 0)

    if token_totals is None and duration is None:
        return  # Empty slice / nothing useful; leave the cursor unadvanced.

    # --- Patch: experiment loop file ---
    extra_files: list[str] = []
    if loop_file is not None and loop_file_rel is not None:
        try:
            loop_data = json.loads(loop_file.read_text())
            if token_totals is not None:
                loop_data["tokens_used"] = token_totals
            if duration is not None:
                loop_data["duration_seconds"] = round(duration, 1)
            loop_file.write_text(json.dumps(loop_data, indent=2) + "\n")
            extra_files.append(loop_file_rel)
        except (OSError, json.JSONDecodeError):
            pass  # Best-effort: leave loop file unpatched

    # --- Patch: research program database ---
    algo_id = "unknown"
    if db_needs_patch:
        last = db[-1]
        if token_totals is not None:
            last["meta"]["tokens_used"] = token_totals
        if duration is not None:
            last["meta"]["duration_seconds"] = round(duration, 1)
        db_path.write_text(json.dumps(db, indent=2) + "\n")
        algo_id = str(last.get("id") or "unknown")
    elif loop_file_rel is not None:
        # Derive a label for the commit message from the loop file path.
        algo_id = Path(loop_file_rel).parent.parent.name  # <mode> dir name

    # Advance the cursor only after a real backfill consumed this slice, and
    # before the git steps so a commit/push failure cannot lose the progress.
    _write_cursor(cursor_path, sub_transcript, lines_seen)

    _try_commit(cwd, algo_id, extra_files)
    _try_push(cwd)


if __name__ == "__main__":
    main()
