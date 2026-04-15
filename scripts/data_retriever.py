#!/usr/bin/env python3
"""
Data retrieval script for autonomous agents.

Enables agents to:
- Discover available datasets and versions
- Fetch manifest and schema
- Download selected partitions with resume capability
- Validate integrity with checksums
"""

import subprocess
import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Optional
import hashlib
from dotenv import load_dotenv

load_dotenv()

class DataRetriever:
    """Client for retrieving datasets from S3."""
    
    def __init__(self, bucket_name: str, region: str = "us-east-1", cache_dir: str = "./data-cache"):
        self.bucket_name = bucket_name
        self.region = region
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Verify AWS CLI is available
        self._check_aws_cli()
    
    def _check_aws_cli(self):
        """Verify AWS CLI is installed."""
        try:
            subprocess.run(["aws", "--version"], capture_output=True, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            print("Error: AWS CLI not installed.", file=sys.stderr)
            print("Install with: brew install awscli (macOS) or pip install awscli", file=sys.stderr)
            sys.exit(1)
    
    def _run_aws(self, cmd: str) -> str:
        """Execute AWS CLI command and return output."""
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"AWS command failed: {result.stderr}")
        return result.stdout.strip()
    
    def list_datasets(self) -> List[str]:
        """List all available datasets."""
        try:
            cmd = f"aws s3 ls s3://{self.bucket_name}/datasets/ --region {self.region}"
            output = self._run_aws(cmd)
            return [line.split()[-1].rstrip('/') for line in output.split('\n') if line and 'PRE' in line]
        except RuntimeError as e:
            print(f"Error listing datasets: {e}", file=sys.stderr)
            return []
    
    def list_versions(self, dataset_name: str) -> List[str]:
        """List all versions for a dataset."""
        try:
            cmd = f"aws s3 ls s3://{self.bucket_name}/datasets/{dataset_name}/ --region {self.region}"
            output = self._run_aws(cmd)
            return [line.split()[-1].rstrip('/') for line in output.split('\n') if line and 'PRE' in line]
        except RuntimeError as e:
            print(f"Error listing versions for {dataset_name}: {e}", file=sys.stderr)
            return []
    
    def fetch_manifest(self, dataset_name: str, version: str) -> Dict:
        """Download and parse manifest.json."""
        try:
            dataset_cache = self.cache_dir / dataset_name / version
            dataset_cache.mkdir(parents=True, exist_ok=True)
            
            manifest_path = dataset_cache / "manifest.json"
            s3_path = f"s3://{self.bucket_name}/datasets/{dataset_name}/{version}/manifest.json"
            
            cmd = f"aws s3 cp {s3_path} {manifest_path} --region {self.region}"
            self._run_aws(cmd)
            
            with open(manifest_path) as f:
                return json.load(f)
        except (RuntimeError, json.JSONDecodeError) as e:
            print(f"Error fetching manifest: {e}", file=sys.stderr)
            return {}
    
    def fetch_schema(self, dataset_name: str, version: str) -> Dict:
        """Download and parse schema.json."""
        try:
            dataset_cache = self.cache_dir / dataset_name / version
            dataset_cache.mkdir(parents=True, exist_ok=True)
            
            schema_path = dataset_cache / "schema.json"
            s3_path = f"s3://{self.bucket_name}/datasets/{dataset_name}/{version}/schema.json"
            
            cmd = f"aws s3 cp {s3_path} {schema_path} --region {self.region}"
            self._run_aws(cmd)
            
            with open(schema_path) as f:
                return json.load(f)
        except (RuntimeError, json.JSONDecodeError):
            return {}
    
    def sync_partition(self, dataset_name: str, version: str, partition_path: str, verbose: bool = False):
        """Download a partition by relative path."""
        try:
            dataset_cache = self.cache_dir / dataset_name / version / "partitions"
            dataset_cache.mkdir(parents=True, exist_ok=True)
            
            s3_prefix = f"s3://{self.bucket_name}/datasets/{dataset_name}/{version}/partitions/{partition_path}"
            local_dir = str(dataset_cache / partition_path)
            
            cmd = f"aws s3 sync {s3_prefix} {local_dir} --region {self.region}"
            if not verbose:
                cmd += " --no-progress"
            
            print(f"Syncing: {partition_path}")
            self._run_aws(cmd)
            print(f"✓ Synced: {partition_path}")
        except RuntimeError as e:
            print(f"Error syncing partition: {e}", file=sys.stderr)
    
    def validate_checksums(self, dataset_name: str, version: str) -> bool:
        """Validate downloaded files against checksums."""
        try:
            dataset_cache = self.cache_dir / dataset_name / version
            checksums_path = dataset_cache / "checksums.txt"
            s3_path = f"s3://{self.bucket_name}/datasets/{dataset_name}/{version}/checksums.txt"
            
            cmd = f"aws s3 cp {s3_path} {checksums_path} --region {self.region}"
            self._run_aws(cmd)
            
            passed = 0
            failed = 0
            
            with open(checksums_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    algo, rest = line.split(":", 1)
                    filename, expected_hash = rest.split("=", 1)
                    
                    file_path = dataset_cache / filename
                    if not file_path.exists():
                        print(f"✗ {filename} (not found)")
                        failed += 1
                        continue
                    
                    with open(file_path, 'rb') as f:
                        if algo.upper() == "SHA256":
                            actual_hash = hashlib.sha256(f.read()).hexdigest()
                        else:
                            print(f"⚠ Unsupported checksum algorithm: {algo}")
                            continue
                    
                    if actual_hash == expected_hash:
                        print(f"✓ {filename}")
                        passed += 1
                    else:
                        print(f"✗ {filename} (mismatch)")
                        failed += 1
            
            print(f"\nVerified: {passed}, Failed: {failed}")
            return failed == 0
        except Exception as e:
            print(f"Error validating checksums: {e}", file=sys.stderr)
            return False

def main():
    """CLI for data retrieval."""
    bucket_name = os.environ.get("S3_BUCKET_NAME")
    region = os.environ.get("AWS_REGION", "us-east-1")
    cache_dir = os.environ.get("DATA_CACHE_DIR", "./data-cache")
    
    if not bucket_name:
        print("Error: S3_BUCKET_NAME environment variable not set", file=sys.stderr)
        sys.exit(1)
    
    retriever = DataRetriever(bucket_name, region, cache_dir)
    
    if len(sys.argv) < 2:
        print("Usage: data_retriever.py <command> [args]")
        print("\nCommands:")
        print("  list-datasets              List all datasets")
        print("  list-versions <dataset>    List versions for dataset")
        print("  fetch-manifest <dataset> <version>")
        print("  fetch-schema <dataset> <version>")
        print("  sync-partition <dataset> <version> <partition-path>")
        print("  validate <dataset> <version>")
        sys.exit(0)
    
    command = sys.argv[1]
    
    if command == "list-datasets":
        datasets = retriever.list_datasets()
        if not datasets:
            print("No datasets found")
        else:
            for ds in datasets:
                print(f"  {ds}")
    
    elif command == "list-versions":
        if len(sys.argv) < 3:
            print("Error: dataset name required", file=sys.stderr)
            sys.exit(1)
        versions = retriever.list_versions(sys.argv[2])
        if not versions:
            print("No versions found")
        else:
            for v in versions:
                print(f"  {v}")
    
    elif command == "fetch-manifest":
        if len(sys.argv) < 4:
            print("Error: dataset and version required", file=sys.stderr)
            sys.exit(1)
        manifest = retriever.fetch_manifest(sys.argv[2], sys.argv[3])
        print(json.dumps(manifest, indent=2))
    
    elif command == "fetch-schema":
        if len(sys.argv) < 4:
            print("Error: dataset and version required", file=sys.stderr)
            sys.exit(1)
        schema = retriever.fetch_schema(sys.argv[2], sys.argv[3])
        print(json.dumps(schema, indent=2))
    
    elif command == "sync-partition":
        if len(sys.argv) < 5:
            print("Error: dataset, version, and partition path required", file=sys.stderr)
            sys.exit(1)
        retriever.sync_partition(sys.argv[2], sys.argv[3], sys.argv[4], verbose=True)
    
    elif command == "validate":
        if len(sys.argv) < 4:
            print("Error: dataset and version required", file=sys.stderr)
            sys.exit(1)
        success = retriever.validate_checksums(sys.argv[2], sys.argv[3])
        sys.exit(0 if success else 1)
    
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
