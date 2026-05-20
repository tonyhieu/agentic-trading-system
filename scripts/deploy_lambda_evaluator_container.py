#!/usr/bin/env python3
import base64
import json
import os
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

import boto3
from botocore.exceptions import ClientError


def run(cmd: List[str], cwd: Optional[str] = None, capture: bool = False) -> str:
    if capture:
        return subprocess.check_output(cmd, cwd=cwd, text=True).strip()
    subprocess.check_call(cmd, cwd=cwd)
    return ""


def extract_handler(source_script: Path, output_file: Path) -> None:
    start = 'cat >"${WORK_DIR}/index.py" <<\'LAMBDA_CODE\''
    end = "LAMBDA_CODE"
    lines = source_script.read_text().splitlines()
    in_block = False
    out: List[str] = []
    for line in lines:
        if not in_block and start in line:
            in_block = True
            continue
        if in_block and line.strip() == end:
            break
        if in_block:
            out.append(line)
    if not out:
        raise RuntimeError("Could not extract index.py from deploy script")
    output_file.write_text("\n".join(out) + "\n")


def download_current_lambda_handler(lam, function_name: str, output_file: Path) -> bool:
    try:
        fn = lam.get_function(FunctionName=function_name)
        code = fn.get("Code", {})
        image_uri = code.get("ImageUri")
        if image_uri:
            cid = subprocess.check_output(["docker", "create", "--platform", "linux/amd64", image_uri], text=True).strip()
            try:
                subprocess.check_call(["docker", "cp", f"{cid}:/var/task/index.py", str(output_file)])
                return output_file.exists() and output_file.stat().st_size > 0
            finally:
                subprocess.call(["docker", "rm", "-f", cid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        url = code.get("Location")
        if not url:
            return False
        data = urllib.request.urlopen(url, timeout=120).read()
        with tempfile.TemporaryDirectory() as td:
            zpath = Path(td) / "code.zip"
            zpath.write_bytes(data)
            with zipfile.ZipFile(zpath) as zf:
                if "index.py" not in zf.namelist():
                    return False
                output_file.write_text(zf.read("index.py").decode())
                return True
    except Exception:
        return False


def ensure_logs_permissions(role_arn: str, iam) -> None:
    role_name = role_arn.split("/")[-1]
    policy_doc = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "CloudWatchLogsWrite",
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:DescribeLogStreams",
                    "logs:DescribeLogGroups",
                ],
                "Resource": "*",
            }
        ],
    }
    iam.put_role_policy(
        RoleName=role_name,
        PolicyName="evaluator-cloudwatch-logs",
        PolicyDocument=json.dumps(policy_doc),
    )


def apply_robustness_fixes(index_file: Path) -> None:
    src = index_file.read_text()
    original = src

    # Fix 3: track OOS day failures and include reasons in fallback metadata.
    src = src.replace(
        "            successful_days = 0\n            for date in OOS_DATES:\n                try:\n                    day_results = run_backtest_for_day(algorithm_dir, algorithm_name, date, symbol)\n                    metrics.add_day_metrics(day_results)\n                    successful_days += 1\n                except Exception as e:\n                    log_print(f\"⚠ Skipping {date}: {e}\")\n                    continue\n",
        "            successful_days = 0\n            failed_days = []\n            failure_reasons: Dict[str, str] = {}\n            first_failure_reason = None\n            for date in OOS_DATES:\n                try:\n                    day_results = run_backtest_for_day(algorithm_dir, algorithm_name, date, symbol)\n                    metrics.add_day_metrics(day_results)\n                    successful_days += 1\n                except Exception as e:\n                    reason = str(e)\n                    if first_failure_reason is None:\n                        first_failure_reason = reason\n                    failed_days.append(date)\n                    failure_reasons[date] = reason\n                    log_print(f\"⚠ Skipping {date}: {e}\")\n                    continue\n",
    )
    src = src.replace(
        "            if successful_days == 0:\n                fallback_metrics = extract_fallback_metrics(algorithm_dir, algorithm_name)\n                if fallback_metrics is None:\n                    raise RuntimeError(\"All OOS dates failed and no fallback metrics were found\")\n                aggregated_metrics = fallback_metrics\n            else:\n                # Aggregate and save results\n                aggregated_metrics = metrics.aggregate()\n",
        "            if successful_days == 0:\n                fallback_metrics = extract_fallback_metrics(algorithm_dir, algorithm_name)\n                if fallback_metrics is None:\n                    raise RuntimeError(\n                        f\"All OOS dates failed and no fallback metrics were found. first_error={first_failure_reason}\"\n                    )\n                aggregated_metrics = fallback_metrics\n                meta = aggregated_metrics.setdefault(\"metadata\", {})\n                meta[\"oos_failed_dates\"] = failed_days\n                meta[\"oos_failure_reason\"] = first_failure_reason\n                meta[\"oos_failure_reasons_by_date\"] = failure_reasons\n            else:\n                # Aggregate and save results\n                aggregated_metrics = metrics.aggregate()\n",
    )

    if src == original:
        raise RuntimeError("Failed to patch handler with robustness fixes (unexpected source format)")
    index_file.write_text(src)


def main() -> None:
    region = os.environ.get("AWS_REGION", "us-east-1")
    function_name = os.environ.get("FUNCTION_NAME", "execution-algorithm-evaluator-container")
    source_function = os.environ.get("SOURCE_FUNCTION_NAME", "execution-algorithm-evaluator")
    ecr_repo = os.environ.get("ECR_REPO_NAME", "execution-algorithm-evaluator")
    image_tag = os.environ.get("IMAGE_TAG", time.strftime("%Y%m%d-%H%M%S", time.gmtime()))
    nautilus_version = os.environ.get("NAUTILUS_TRADER_VERSION", "1.225.0")

    sts = boto3.client("sts", region_name=region)
    lam = boto3.client("lambda", region_name=region)
    ecr = boto3.client("ecr", region_name=region)
    iam = boto3.client("iam", region_name=region)
    account_id = sts.get_caller_identity()["Account"]

    cfg = lam.get_function_configuration(FunctionName=source_function)
    role = cfg["Role"]
    timeout = cfg.get("Timeout", 900)
    memory = cfg.get("MemorySize", 1024)
    env_vars = (cfg.get("Environment") or {}).get("Variables", {})

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        # Prefer using the local, repository-backed handler source so
        # recent edits to scripts/ are included in the built image.
        extract_handler(Path("scripts/06-deploy-lambda-evaluator-v2.sh"), tdp / "index.py")
        apply_robustness_fixes(tdp / "index.py")
        (tdp / "requirements.txt").write_text(
            "\n".join(
                [
                    "awslambdaric==2.1.0",
                    f"nautilus-trader=={nautilus_version}",
                    "boto3==1.34.99",
                    "botocore==1.34.99",
                    "requests==2.32.3",
                    "gitpython==3.1.43",
                    "zstandard==0.23.0",
                    "python-dotenv>=1.0.0",
                    "awscli==1.32.99",
                ]
            )
            + "\n"
        )
        # Copy local scripts into the build context so the image can include them
        import shutil
        try:
            shutil.copytree("scripts", tdp / "scripts")
        except Exception:
            # If scripts/ is absent or copy fails, continue; runtime will still try S3-based sync
            pass

        (tdp / "Dockerfile").write_text(
            """FROM python:3.12-slim
WORKDIR /var/task
RUN apt-get update && apt-get install -y --no-install-recommends curl git ca-certificates zstd && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt
# Include repository scripts in the image so index.py can copy patched retrievers into cloned snapshots
COPY scripts ./scripts
COPY index.py ./index.py
ENTRYPOINT ["/usr/local/bin/python", "-m", "awslambdaric"]
CMD ["index.lambda_handler"]
"""
        )

        try:
            ecr.describe_repositories(repositoryNames=[ecr_repo])
        except ClientError as e:
            if e.response["Error"]["Code"] == "RepositoryNotFoundException":
                ecr.create_repository(repositoryName=ecr_repo)
            else:
                raise

        ecr_uri = f"{account_id}.dkr.ecr.{region}.amazonaws.com/{ecr_repo}"
        image_uri = f"{ecr_uri}:{image_tag}"

        auth = ecr.get_authorization_token()["authorizationData"][0]
        token = base64.b64decode(auth["authorizationToken"]).decode()
        _, password = token.split(":", 1)
        # Login with ECR auth token
        proc = subprocess.Popen(
            ["docker", "login", "--username", "AWS", "--password-stdin", auth["proxyEndpoint"]],
            stdin=subprocess.PIPE,
            text=True,
        )
        proc.communicate(password + "\n")
        if proc.returncode != 0:
            raise RuntimeError("docker login failed")

        print(f"[INFO] Building and pushing image {image_uri}")
        subprocess.check_call(
            [
                "docker",
                "buildx",
                "build",
                "--progress=plain",
                "--platform",
                "linux/amd64",
                "--provenance=false",
                "--sbom=false",
                "-t",
                image_uri,
                "--push",
                ".",
            ],
            cwd=td,
            env=os.environ.copy(),
        )
        ensure_logs_permissions(role, iam)

        try:
            lam.get_function(FunctionName=function_name)
            lam.update_function_code(FunctionName=function_name, ImageUri=image_uri)
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                lam.create_function(
                    FunctionName=function_name,
                    Role=role,
                    PackageType="Image",
                    Code={"ImageUri": image_uri},
                    Timeout=timeout,
                    MemorySize=memory,
                    Environment={"Variables": env_vars},
                )
            else:
                raise

        for _ in range(120):
            state_cfg = lam.get_function_configuration(FunctionName=function_name)
            state = state_cfg.get("State")
            update_status = state_cfg.get("LastUpdateStatus")
            if state == "Active" and (update_status in (None, "Successful")):
                break
            time.sleep(3)

        # Ensure function configuration matches source function (retry on transient conflicts).
        for _ in range(20):
            try:
                lam.update_function_configuration(
                    FunctionName=function_name,
                    Timeout=timeout,
                    MemorySize=memory,
                    Environment={"Variables": env_vars},
                )
                break
            except ClientError as e:
                if e.response["Error"]["Code"] == "ResourceConflictException":
                    time.sleep(3)
                    continue
                raise

        # Built and pushed image; do not auto-invoke the function.
        # Prefer testing via the GitHub Actions workflow (snapshots/spread-filter-v2).
        print(f"[SUCCESS] built and pushed image {image_uri}")
        print("Skipping automatic invoke; run the 'snapshot-execution-algo.yml' workflow for spread-filter-v2 to test the evaluator.")
        print(f"[INFO] Deployed {function_name} with image {image_uri}")


if __name__ == "__main__":
    main()
