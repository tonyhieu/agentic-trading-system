#!/usr/bin/env python3
"""
Snapshot Retrieval Tool

Helps download and browse strategy snapshots from S3.

Usage:
    python3 scripts/retrieve_snapshot.py list
    python3 scripts/retrieve_snapshot.py list momentum-trader
    python3 scripts/retrieve_snapshot.py latest momentum-trader
"""

import argparse
import json
import os
import subprocess
import sys
from dotenv import load_dotenv

load_dotenv()

class SnapshotRetriever:
    def __init__(self, bucket_name=None, region=None):
        self.bucket_name = bucket_name or os.getenv('S3_BUCKET_NAME')
        self.region = region or os.getenv('AWS_REGION', 'us-east-1')
        
        if not self.bucket_name:
            raise ValueError("Set S3_BUCKET_NAME environment variable")
        
        # Check if AWS CLI is installed
        try:
            subprocess.run(['aws', '--version'], capture_output=True, check=True)
        except FileNotFoundError:
            print("\nERROR: AWS CLI is not installed!\n")
            print("Please install AWS CLI:")
            print("  macOS:   brew install awscli")
            print("  Linux:   pip install awscli")
            print("  Windows: https://aws.amazon.com/cli/\n")
            print("After installing, configure it with:")
            print("  aws configure")
            print("\nOr set environment variables:")
            print("  export AWS_ACCESS_KEY_ID='...'")
            print("  export AWS_SECRET_ACCESS_KEY='...'")
            print("  export AWS_REGION='us-east-1'")
            sys.exit(1)
    
    def _run_aws(self, cmd):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return result.stdout
        except subprocess.CalledProcessError as e:
            print(f"AWS CLI error: {e.stderr}", file=sys.stderr)
            sys.exit(1)
    
    def list_strategies(self):
        cmd = ['aws', 's3', 'ls', f's3://{self.bucket_name}/strategies/', '--region', self.region]
        output = self._run_aws(cmd)
        
        strategies = []
        for line in output.strip().split('\n'):
            if line.strip():
                parts = line.strip().split()
                if len(parts) >= 2 and parts[0] == 'PRE':
                    strategies.append(parts[1].rstrip('/'))
        
        return sorted(strategies)
    
    def list_snapshots(self, strategy_name):
        cmd = ['aws', 's3', 'ls', f's3://{self.bucket_name}/strategies/{strategy_name}/', '--region', self.region]
        output = self._run_aws(cmd)
        
        snapshots = []
        for line in output.strip().split('\n'):
            if line.strip():
                parts = line.strip().split()
                if len(parts) >= 2 and parts[0] == 'PRE':
                    snapshot_dir = parts[1].rstrip('/')
                    try:
                        timestamp, commit = snapshot_dir.rsplit('-', 1)
                        snapshots.append({'timestamp': timestamp, 'commit': commit, 'path': snapshot_dir})
                    except:
                        continue
        
        return sorted(snapshots, key=lambda x: x['timestamp'], reverse=True)
    
    def download_snapshot(self, strategy_name, snapshot_path, output_dir='.'):
        s3_path = f's3://{self.bucket_name}/strategies/{strategy_name}/{snapshot_path}/'
        local_path = f'{output_dir}/snapshots/{strategy_name}/{snapshot_path}'
        
        os.makedirs(local_path, exist_ok=True)
        
        print(f"Downloading from {s3_path}")
        print(f"To: {local_path}")
        
        cmd = ['aws', 's3', 'sync', s3_path, local_path, '--region', self.region]
        self._run_aws(cmd)
        
        print(f"Complete!")
        return local_path


def main():
    parser = argparse.ArgumentParser(description='Retrieve snapshots from S3')
    parser.add_argument('command', choices=['list', 'download', 'latest'])
    parser.add_argument('strategy', nargs='?')
    parser.add_argument('snapshot', nargs='?')
    parser.add_argument('--output', default='.')
    
    args = parser.parse_args()
    
    try:
        retriever = SnapshotRetriever()
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    if args.command == 'list':
        if args.strategy:
            print(f"Snapshots for '{args.strategy}':\n")
            for snap in retriever.list_snapshots(args.strategy):
                print(f"  • {snap['timestamp']} (commit: {snap['commit']})")
        else:
            print("Available strategies:\n")
            for strategy in retriever.list_strategies():
                print(f"  • {strategy}")
    
    elif args.command == 'latest':
        if not args.strategy:
            print("Specify strategy name")
            sys.exit(1)
        snapshots = retriever.list_snapshots(args.strategy)
        if snapshots:
            latest = snapshots[0]
            print(f"Latest: {latest['timestamp']}")
            retriever.download_snapshot(args.strategy, latest['path'], args.output)
    
    elif args.command == 'download':
        if not args.strategy or not args.snapshot:
            print("Specify strategy and snapshot")
            sys.exit(1)
        retriever.download_snapshot(args.strategy, args.snapshot, args.output)


if __name__ == '__main__':
    main()
