"""Verify the per-iteration metadata backfill (`.claude/hooks/patch_program_db_tokens.py`).

The hook's correctness claim (issue #78): when the researcher subagent's
transcript persists and grows across research-loop iterations, each
`program_database.json` entry must record *its own* iteration's duration and
tokens — not a running total. An offset cursor (`research/.meta_cursor.json`)
makes the hook scan only the transcript slice produced since the last backfill.

These tests build synthetic transcripts and drive the hook the way the harness
does — a JSON payload on stdin — asserting per-iteration deltas, not cumulative.

No pytest required — run it directly:

    python tests/test_patch_program_db_tokens.py

It is also pytest-collectable. The git-isolation test skips cleanly when `git`
is not on PATH; everything else is pure-Python and always runs.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK_PATH = REPO_ROOT / ".claude" / "hooks" / "patch_program_db_tokens.py"

# The hook lives under a dotted directory and is not an importable package;
# load it straight from its file path.
_spec = importlib.util.spec_from_file_location("patch_program_db_tokens", HOOK_PATH)
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)


# --- Expected per-iteration aggregates of the synthetic transcript below ------
# iteration 1 == transcript lines 0-3, iteration 2 == lines 4-7.
ITER1_TOKENS = {"input": 18, "output": 7, "cache_creation": 100, "cache_read": 500, "total": 625}
ITER1_DURATION = 100.0  # 00:00:00 -> 00:01:40
ITER2_TOKENS = {"input": 15, "output": 15, "cache_creation": 50, "cache_read": 10000, "total": 10080}
ITER2_DURATION = 60.0  # 00:10:00 -> 00:11:00
COMBINED_TOKENS = {"input": 33, "output": 22, "cache_creation": 150, "cache_read": 10500, "total": 10705}
COMBINED_DURATION = 660.0  # 00:00:00 -> 00:11:00


def _usage(inp, out, cc, cr):
    return {
        "input_tokens": inp,
        "output_tokens": out,
        "cache_creation_input_tokens": cc,
        "cache_read_input_tokens": cr,
    }


def _iter1_lines():
    """4 transcript records: 3 carry usage, one is a usage-less user turn."""
    return [
        {"timestamp": "2026-01-01T00:00:00Z", "message": {"role": "assistant", "usage": _usage(10, 1, 100, 0)}},
        {"timestamp": "2026-01-01T00:00:30Z", "message": {"role": "assistant", "usage": _usage(5, 2, 0, 200)}},
        {"timestamp": "2026-01-01T00:01:00Z", "message": {"role": "user"}},
        {"timestamp": "2026-01-01T00:01:40Z", "message": {"role": "assistant", "usage": _usage(3, 4, 0, 300)}},
    ]


def _iter2_lines():
    """4 transcript records: 4 carry usage, one of them has no timestamp."""
    return [
        {"timestamp": "2026-01-01T00:10:00Z", "message": {"role": "assistant", "usage": _usage(1, 1, 50, 1000)}},
        {"timestamp": "2026-01-01T00:10:20Z", "message": {"role": "assistant", "usage": _usage(2, 2, 0, 2000)}},
        {"message": {"role": "assistant", "usage": _usage(4, 4, 0, 3000)}},
        {"timestamp": "2026-01-01T00:11:00Z", "message": {"role": "assistant", "usage": _usage(8, 8, 0, 4000)}},
    ]


def _write_jsonl(path: Path, records):
    path.write_text("".join(json.dumps(r) + "\n" for r in records))


def _db_entry(algo_id: str):
    """A minimal program_database entry with the researcher's backfill marker."""
    return {"id": algo_id, "status": "fail", "meta": {"duration_seconds": None, "tokens_used": None}}


def _load_json(path: Path):
    return json.loads(path.read_text())


def _run_hook(cwd: Path, transcript_path: Path) -> subprocess.CompletedProcess:
    """Drive the hook exactly as a SubagentStop fires it: a JSON stdin payload."""
    return subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=json.dumps({"transcript_path": str(transcript_path), "cwd": str(cwd)}),
        text=True,
        capture_output=True,
    )


def test_scan_slice_math():
    """`_scan_transcript` sums tokens/duration over [start_line, EOF) only."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "t.jsonl"
        _write_jsonl(path, _iter1_lines() + _iter2_lines())

        # Whole file == both iterations combined.
        tok, dur, seen = hook._scan_transcript(path, 0)
        assert tok == COMBINED_TOKENS, tok
        assert dur == COMBINED_DURATION, dur
        assert seen == 8, seen

        # Slice from line 4 == iteration 2 only (NOT cumulative).
        tok, dur, seen = hook._scan_transcript(path, 4)
        assert tok == ITER2_TOKENS, tok
        assert dur == ITER2_DURATION, dur
        assert seen == 8, seen

        # Empty slice (cursor already at EOF).
        tok, dur, seen = hook._scan_transcript(path, 8)
        assert tok is None and dur is None, (tok, dur)
        assert seen == 8, seen

        # A slice with a single timestamped record -> zero measured span.
        tok, dur, seen = hook._scan_transcript(path, 7)
        assert dur == 0.0, dur
        assert tok == {"input": 8, "output": 8, "cache_creation": 0, "cache_read": 4000, "total": 4016}, tok


def test_per_iteration_backfill_across_invocations():
    """Two SubagentStop firings on a growing transcript -> per-iteration meta."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        (repo / "research").mkdir()
        db_path = repo / "research" / "program_database.json"
        cursor_path = repo / "research" / ".meta_cursor.json"
        transcript = repo / "transcript.jsonl"

        # --- Iteration 1 -----------------------------------------------------
        db_path.write_text(json.dumps([_db_entry("algo-one")], indent=2) + "\n")
        _write_jsonl(transcript, _iter1_lines())
        proc = _run_hook(repo, transcript)
        assert proc.returncode == 0, proc.stderr

        db = _load_json(db_path)
        assert db[0]["meta"]["tokens_used"] == ITER1_TOKENS, db[0]["meta"]
        assert db[0]["meta"]["duration_seconds"] == ITER1_DURATION, db[0]["meta"]

        cursor = _load_json(cursor_path)
        assert cursor == {"transcript_path": str(transcript), "lines_consumed": 4}, cursor

        # --- Iteration 2: transcript grows, a new entry is appended ----------
        _write_jsonl(transcript, _iter1_lines() + _iter2_lines())
        db.append(_db_entry("algo-two"))
        db_path.write_text(json.dumps(db, indent=2) + "\n")
        proc = _run_hook(repo, transcript)
        assert proc.returncode == 0, proc.stderr

        db = _load_json(db_path)
        # The crux of issue #78: entry 2 gets ONLY iteration 2's cost.
        assert db[1]["meta"]["tokens_used"] == ITER2_TOKENS, db[1]["meta"]
        assert db[1]["meta"]["tokens_used"]["input"] == 15, "must be per-iteration, not the cumulative 33"
        assert db[1]["meta"]["duration_seconds"] == ITER2_DURATION, db[1]["meta"]
        # Entry 1 is untouched (append-only; already backfilled).
        assert db[0]["meta"]["tokens_used"] == ITER1_TOKENS, db[0]["meta"]
        assert _load_json(cursor_path)["lines_consumed"] == 8

        # --- Iteration 3: nothing new -> already-backfilled early-return -----
        proc = _run_hook(repo, transcript)
        assert proc.returncode == 0, proc.stderr
        assert _load_json(db_path) == db, "an already-backfilled entry must not change"
        assert _load_json(cursor_path)["lines_consumed"] == 8, "cursor must not advance"


def test_truncated_transcript_rescans_from_zero():
    """A cursor pointing past EOF (rotated/truncated transcript) re-scans whole."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        (repo / "research").mkdir()
        db_path = repo / "research" / "program_database.json"
        cursor_path = repo / "research" / ".meta_cursor.json"
        transcript = repo / "transcript.jsonl"

        db_path.write_text(json.dumps([_db_entry("algo-trunc")], indent=2) + "\n")
        _write_jsonl(transcript, _iter1_lines())  # only 4 lines
        # Cursor claims 100 lines already consumed -> stale / past EOF.
        cursor_path.write_text(json.dumps({"transcript_path": str(transcript), "lines_consumed": 100}))

        proc = _run_hook(repo, transcript)
        assert proc.returncode == 0, proc.stderr

        db = _load_json(db_path)
        assert db[0]["meta"]["tokens_used"] == ITER1_TOKENS, db[0]["meta"]
        assert db[0]["meta"]["duration_seconds"] == ITER1_DURATION, db[0]["meta"]
        assert _load_json(cursor_path)["lines_consumed"] == 4, "cursor reset to true length"


def test_corrupt_cursor_scans_from_zero():
    """An unreadable cursor file degrades to a full scan, never a crash."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        (repo / "research").mkdir()
        db_path = repo / "research" / "program_database.json"
        cursor_path = repo / "research" / ".meta_cursor.json"
        transcript = repo / "transcript.jsonl"

        db_path.write_text(json.dumps([_db_entry("algo-corrupt")], indent=2) + "\n")
        _write_jsonl(transcript, _iter1_lines())
        cursor_path.write_text("this is not json {{{")

        proc = _run_hook(repo, transcript)
        assert proc.returncode == 0, proc.stderr

        db = _load_json(db_path)
        assert db[0]["meta"]["tokens_used"] == ITER1_TOKENS, db[0]["meta"]
        # The corrupt cursor was overwritten with a valid one.
        assert _load_json(cursor_path) == {"transcript_path": str(transcript), "lines_consumed": 4}


def test_read_cursor_rejects_bad_shapes():
    """`_read_cursor` returns None for anything that isn't a well-formed cursor."""
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / ".meta_cursor.json"
        assert hook._read_cursor(p) is None  # absent
        p.write_text("{not json")
        assert hook._read_cursor(p) is None  # unparseable
        p.write_text("[1, 2, 3]")
        assert hook._read_cursor(p) is None  # not an object
        p.write_text(json.dumps({"transcript_path": "/x"}))
        assert hook._read_cursor(p) is None  # missing lines_consumed
        p.write_text(json.dumps({"transcript_path": "/x", "lines_consumed": "5"}))
        assert hook._read_cursor(p) is None  # lines_consumed wrong type
        p.write_text(json.dumps({"transcript_path": "/x", "lines_consumed": True}))
        assert hook._read_cursor(p) is None  # bool must not pass as int
        p.write_text(json.dumps({"transcript_path": "/x", "lines_consumed": -1}))
        assert hook._read_cursor(p) is None  # negative
        p.write_text(json.dumps({"transcript_path": "/x", "lines_consumed": 7}))
        assert hook._read_cursor(p) == {"transcript_path": "/x", "lines_consumed": 7}


def test_cursor_excluded_from_backfill_commit():
    """The auto-commit stages only program_database.json; the cursor stays out."""
    if shutil.which("git") is None:
        print("SKIP: git not on PATH")
        return
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)

        def git(*args):
            subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

        def git_out(*args):
            return subprocess.run(
                ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
            ).stdout

        git("init", "-q")
        git("config", "user.email", "test@example.com")
        git("config", "user.name", "Test")
        git("config", "commit.gpgsign", "false")
        # Neutralize any global core.hooksPath so a stray pre-commit hook can't fire.
        git("config", "core.hooksPath", str(repo / ".no-such-hooks"))

        (repo / "research").mkdir()
        (repo / ".gitignore").write_text("research/.meta_cursor.json\n")
        db_path = repo / "research" / "program_database.json"
        db_path.write_text(json.dumps([_db_entry("algo-git")], indent=2) + "\n")
        git("add", "-A")
        git("commit", "-q", "-m", "initial")

        transcript = repo / "transcript.jsonl"
        _write_jsonl(transcript, _iter1_lines())

        proc = _run_hook(repo, transcript)
        assert proc.returncode == 0, proc.stderr

        # The hook produced one backfill commit...
        assert git_out("log", "--format=%s").splitlines()[0] == (
            "chore(algo-git): backfill execution metadata"
        )
        # ...touching only the database file.
        files = git_out("show", "--name-only", "--format=", "HEAD").split()
        assert files == ["research/program_database.json"], files
        # The cursor exists on disk, is git-ignored, and is not a tracked change.
        assert (repo / "research" / ".meta_cursor.json").exists()
        assert ".meta_cursor.json" in git_out("status", "--porcelain", "--ignored")
        assert ".meta_cursor.json" not in git_out("status", "--porcelain")


if __name__ == "__main__":
    tests = [
        test_scan_slice_math,
        test_per_iteration_backfill_across_invocations,
        test_truncated_transcript_rescans_from_zero,
        test_corrupt_cursor_scans_from_zero,
        test_read_cursor_rejects_bad_shapes,
        test_cursor_excluded_from_backfill_commit,
    ]
    for t in tests:
        print(f"... {t.__name__}", flush=True)
        t()
        print(f"PASS {t.__name__}")
    print(f"\nAll {len(tests)} tests passed.")
