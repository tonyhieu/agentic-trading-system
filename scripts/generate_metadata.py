#!/usr/bin/env python3
"""
Generate metadata.json for a snapshot. Reads environment variables set by the GitHub workflow
and writes a metadata.json file into the ROOT snapshot directory.

Expected environment variables (set by workflow step):
- ROOT (required): path to snapshot root directory
- ALGO_NAME, TIMESTAMP, COMMIT_SHA, COMMIT_SHA_FULL, BRANCH, REPOSITORY, TRIGGERED_BY, ACTOR, RUN_ID

If some are missing, reasonable defaults are used.
"""
import json
import os
import sys
from datetime import datetime

ROOT = os.environ.get('ROOT')
if not ROOT:
    print('Error: ROOT environment variable is not set', file=sys.stderr)
    sys.exit(1)

meta = {
    'algo_name': os.environ.get('ALGO_NAME') or os.environ.get('NAME') or 'unknown',
    'timestamp': os.environ.get('TIMESTAMP') or datetime.utcnow().isoformat() + 'Z',
    'commit_short': os.environ.get('COMMIT_SHA') or os.environ.get('COMMIT') or os.environ.get('GITHUB_SHA', '')[:7],
    'commit_full': os.environ.get('COMMIT_SHA_FULL') or os.environ.get('GITHUB_SHA') or '',
    'branch': os.environ.get('BRANCH') or os.environ.get('GITHUB_REF_NAME') or os.environ.get('GITHUB_REF', ''),
    'repository': os.environ.get('REPOSITORY') or os.environ.get('GITHUB_REPOSITORY') or '',
    'triggered_by': os.environ.get('TRIGGERED_BY') or os.environ.get('GITHUB_EVENT_NAME') or '',
    'actor': os.environ.get('ACTOR') or os.environ.get('GITHUB_ACTOR') or '',
    'run_id': os.environ.get('RUN_ID') or os.environ.get('GITHUB_RUN_ID') or '',
}

# Try to include a short listing of files included in the snapshot
files = []
code_dir = os.path.join(ROOT, 'code')
results_dir = os.path.join(ROOT, 'results')
for base in (code_dir, results_dir):
    if os.path.isdir(base):
        for root, dirs, filenames in os.walk(base):
            for fn in filenames:
                rel = os.path.relpath(os.path.join(root, fn), ROOT)
                files.append(rel)

meta['files'] = sorted(files)

# Write metadata.json into ROOT
out_path = os.path.join(ROOT, 'metadata.json')
try:
    os.makedirs(ROOT, exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(meta, f, indent=2, sort_keys=True)
    print(f'Wrote metadata to {out_path}')
except Exception as e:
    print(f'Error writing metadata: {e}', file=sys.stderr)
    sys.exit(1)
