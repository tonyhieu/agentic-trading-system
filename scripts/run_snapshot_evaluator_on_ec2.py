#!/usr/bin/env python3
"""Run a snapshot evaluation on a dedicated EC2 instance via SSM.

The snapshot workflow uploads the algorithm to S3, then uses this helper to:
1. Start the EC2 instance if needed.
2. Wait for it to come online in SSM.
3. Run the local evaluator on the instance.
4. Upload the evaluation report to S3.
5. Optionally stop the instance again.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run snapshot evaluation on EC2")
    parser.add_argument("--algorithm-name", required=True)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-east-1"))
    parser.add_argument("--github-repo", default=os.environ.get("GITHUB_REPO", "tonyhieu/agentic-trading-system"))
    parser.add_argument("--github-token", default=os.environ.get("GITHUB_TOKEN", ""))
    parser.add_argument("--s3-bucket", default=os.environ.get("S3_BUCKET_NAME", ""))
    parser.add_argument("--report-s3-key", required=True)
    parser.add_argument("--workdir", default=os.environ.get("EC2_EVALUATOR_WORKDIR", "/home/ubuntu/agentic-trading-system"))
    parser.add_argument("--stop-instance", action="store_true", default=True)
    parser.add_argument("--keep-instance-running", dest="stop_instance", action="store_false")
    return parser.parse_args()


def _aws(region: str, *args: str) -> str:
    cmd = ["aws", *args, "--region", region]
    return subprocess.check_output(cmd, text=True)


def _instance_state(region: str, instance_id: str) -> str:
    output = _aws(region, "ec2", "describe-instances", "--instance-ids", instance_id, "--output", "json")
    data = json.loads(output)
    reservations = data.get("Reservations", [])
    if not reservations or not reservations[0].get("Instances"):
        raise RuntimeError(f"Instance {instance_id} not found")
    return reservations[0]["Instances"][0]["State"]["Name"]


def _start_instance(region: str, instance_id: str) -> None:
    state = _instance_state(region, instance_id)
    if state == "terminated":
        raise RuntimeError(f"Instance {instance_id} is terminated")
    if state == "running":
        return
    _aws(region, "ec2", "start-instances", "--instance-ids", instance_id, "--output", "json")
    _aws(region, "ec2", "wait", "instance-running", "--instance-ids", instance_id)
    _aws(region, "ec2", "wait", "instance-status-ok", "--instance-ids", instance_id)


def _wait_for_ssm_online(region: str, instance_id: str, timeout_seconds: int = 900) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        output = _aws(
            region,
            "ssm",
            "describe-instance-information",
            "--filters",
            f"Key=InstanceIds,Values={instance_id}",
            "--output",
            "json",
        )
        infos = json.loads(output).get("InstanceInformationList", [])
        if infos and infos[0].get("PingStatus") == "Online":
            return
        time.sleep(10)
    raise TimeoutError(f"Timed out waiting for SSM online on {instance_id}")


def _build_remote_script(args: argparse.Namespace) -> str:
    repo_url = f"https://github.com/{args.github_repo}.git"
    if args.github_token:
        repo_url = f"https://x-access-token:{args.github_token}@github.com/{args.github_repo}.git"

    install_cmd = (
        "sudo apt-get update && "
        "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "
        "git python3 python3-venv python3-pip awscli zstd"
    )

    return f"""
set -euo pipefail

export WORKDIR={shlex.quote(args.workdir)}
export ALGO_NAME={shlex.quote(args.algorithm_name)}
export S3_BUCKET_NAME={shlex.quote(args.s3_bucket)}
export AWS_REGION={shlex.quote(args.region)}
export GITHUB_REPO={shlex.quote(args.github_repo)}
export GITHUB_TOKEN={shlex.quote(args.github_token)}
export EVALUATION_RUNTIME=ec2
export LOCAL_CACHE_DIR=/tmp/ec2-eval-cache

{install_cmd}

if [ ! -d "$WORKDIR/.git" ]; then
  sudo mkdir -p "$(dirname "$WORKDIR")"
  git clone {shlex.quote(repo_url)} "$WORKDIR"
fi

cd "$WORKDIR"
git fetch origin "refs/heads/snapshots/$ALGO_NAME:refs/remotes/origin/snapshots/$ALGO_NAME"
git checkout -B "snapshots/$ALGO_NAME" "origin/snapshots/$ALGO_NAME"
git reset --hard "origin/snapshots/$ALGO_NAME"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
. .venv/bin/activate
pip install --upgrade pip
pip install boto3 requests pandas numpy zstandard nautilus-trader==1.225.0 python-dotenv

python3 scripts/local-evaluator.py "$ALGO_NAME" 2 \
  --report-s3-bucket "$S3_BUCKET_NAME" \
  --report-s3-key {shlex.quote(args.report_s3_key)}
"""


def _send_command(region: str, instance_id: str, script: str) -> tuple[str, str, str, str]:
    response = _aws(
        region,
        "ssm",
        "send-command",
        "--instance-ids",
        instance_id,
        "--document-name",
        "AWS-RunShellScript",
        "--parameters",
        json.dumps({"commands": [f"bash -lc {shlex.quote(script)}"]}),
        "--output",
        "json",
    )
    command_id = json.loads(response)["Command"]["CommandId"]

    deadline = time.time() + 7200
    while time.time() < deadline:
        try:
            output = _aws(
                region,
                "ssm",
                "get-command-invocation",
                "--command-id",
                command_id,
                "--instance-id",
                instance_id,
                "--output",
                "json",
            )
            invocation = json.loads(output)
        except subprocess.CalledProcessError:
            time.sleep(10)
            continue
        status = invocation.get("Status", "Unknown")
        if status in {"Success", "Cancelled", "TimedOut", "Failed", "Cancelled"}:
            return (
                command_id,
                status,
                invocation.get("StandardOutputContent", ""),
                invocation.get("StandardErrorContent", ""),
            )
        time.sleep(15)

    raise TimeoutError(f"Timed out waiting for SSM command {command_id}")


def main() -> int:
    args = _parse_args()
    if not args.s3_bucket:
        raise SystemExit("S3 bucket is required (set S3_BUCKET_NAME or pass --s3-bucket)")

    _start_instance(args.region, args.instance_id)
    _wait_for_ssm_online(args.region, args.instance_id)
    script = _build_remote_script(args)

    try:
        command_id, status, stdout, stderr = _send_command(args.region, args.instance_id, script)
        print(stdout)
        if status != "Success":
            print(stderr, file=sys.stderr)
            return 1
        return 0
    finally:
        if args.stop_instance:
            try:
                _aws(args.region, "ec2", "stop-instances", "--instance-ids", args.instance_id, "--output", "json")
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
