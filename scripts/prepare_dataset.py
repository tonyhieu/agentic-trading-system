#!/usr/bin/env python3
"""
Download, analyze, and prepare dataset for S3 upload.

This script:
1. Downloads data from Box link
2. Analyzes structure and data types
3. Determines optimal partitioning strategy
4. Converts to Parquet with partitions
5. Generates manifest, schema, checksums
6. Estimates cost savings with selective retrieval
"""

import os
import json
import subprocess
import sys
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple
import pandas as pd
import numpy as np

class DatasetPreparer:
    def __init__(self, box_url: str, output_dir: str = "./dataset-output"):
        self.box_url = box_url
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.raw_file = self.output_dir / "raw_data"
        self.parquet_dir = self.output_dir / "partitions"
        self.parquet_dir.mkdir(parents=True, exist_ok=True)
        
    def download_box_data(self) -> Path:
        """Download dataset from Box link."""
        print("📥 Downloading from Box...")
        
        # Determine file format from URL or try to download
        output_file = self.raw_file
        
        try:
            # Use curl to download
            cmd = f"curl -L -o {output_file} {self.box_url}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"❌ Download failed: {result.stderr}")
                return None
            
            size_mb = output_file.stat().st_size / (1024**2)
            print(f"✓ Downloaded {size_mb:.2f} MB")
            return output_file
            
        except Exception as e:
            print(f"❌ Download error: {e}")
            return None
    
    def detect_format(self, file_path: Path) -> str:
        """Detect file format (CSV, JSON, Parquet, etc)."""
        # Check file extension
        ext = file_path.suffix.lower()
        if ext in ['.csv', '.tsv', '.json', '.parquet', '.xlsx', '.xls']:
            return ext[1:].upper()
        
        # Read first bytes to detect
        try:
            with open(file_path, 'rb') as f:
                header = f.read(100)
            
            # Check for Parquet magic bytes
            if header.startswith(b'PAR1'):
                return 'PARQUET'
            # Check for JSON
            if header.startswith(b'{') or header.startswith(b'['):
                return 'JSON'
            # Check for CSV (common headers)
            if b',' in header or b'\t' in header:
                return 'CSV'
            
            return 'UNKNOWN'
        except:
            return 'UNKNOWN'
    
    def load_data(self, file_path: Path) -> pd.DataFrame:
        """Load data based on format."""
        format_type = self.detect_format(file_path)
        print(f"📊 Detected format: {format_type}")
        
        try:
            if format_type == 'CSV':
                return pd.read_csv(file_path)
            elif format_type == 'JSON':
                return pd.read_json(file_path)
            elif format_type == 'PARQUET':
                return pd.read_parquet(file_path)
            elif format_type == 'XLSX':
                return pd.read_excel(file_path)
            else:
                print(f"❓ Unknown format. Trying CSV...")
                return pd.read_csv(file_path)
        except Exception as e:
            print(f"❌ Load error: {e}")
            return None
    
    def analyze_data(self, df: pd.DataFrame) -> Dict:
        """Analyze data structure and recommend partitioning."""
        print("\n📈 Analyzing data structure...")
        
        analysis = {
            "rows": len(df),
            "columns": len(df.columns),
            "column_info": {},
            "potential_partitions": {},
            "size_mb": df.memory_usage(deep=True).sum() / (1024**2),
            "date_columns": [],
            "symbol_columns": [],
            "numeric_columns": [],
            "categorical_columns": []
        }
        
        # Analyze columns
        for col in df.columns:
            col_type = df[col].dtype
            unique_count = df[col].nunique()
            
            analysis["column_info"][col] = {
                "type": str(col_type),
                "unique_values": unique_count,
                "null_count": df[col].isnull().sum(),
                "cardinality": unique_count / len(df)
            }
            
            # Detect date columns
            if col.lower() in ['date', 'timestamp', 'datetime', 'time']:
                analysis["date_columns"].append(col)
            
            # Detect symbol/ticker columns
            if col.lower() in ['symbol', 'ticker', 'exchange', 'instrument']:
                analysis["symbol_columns"].append(col)
            
            # Categorize by type
            if np.issubdtype(col_type, np.number):
                analysis["numeric_columns"].append(col)
            elif unique_count < 1000:
                analysis["categorical_columns"].append(col)
        
        # Recommend partitioning strategy
        print("\n🎯 Partitioning Strategy Recommendation:\n")
        
        # Primary partition: Date
        if analysis["date_columns"]:
            date_col = analysis["date_columns"][0]
            print(f"  Primary partition: {date_col}")
            analysis["potential_partitions"]["primary"] = date_col
            
            # Count unique dates
            unique_dates = df[date_col].nunique()
            print(f"    - Unique dates: {unique_dates}")
            analysis["potential_partitions"]["primary_cardinality"] = unique_dates
        
        # Secondary partition: Symbol
        if analysis["symbol_columns"]:
            symbol_col = analysis["symbol_columns"][0]
            print(f"  Secondary partition: {symbol_col}")
            analysis["potential_partitions"]["secondary"] = symbol_col
            
            unique_symbols = df[symbol_col].nunique()
            print(f"    - Unique symbols: {unique_symbols}")
            analysis["potential_partitions"]["secondary_cardinality"] = unique_symbols
        
        # Estimate partitions
        if analysis["potential_partitions"]:
            primary_card = analysis["potential_partitions"].get("primary_cardinality", 1)
            secondary_card = analysis["potential_partitions"].get("secondary_cardinality", 1)
            total_partitions = primary_card * secondary_card
            
            print(f"\n  Total partitions: {total_partitions}")
            print(f"  Avg rows per partition: {len(df) // max(total_partitions, 1):,}")
        
        return analysis
    
    def partition_and_convert(self, df: pd.DataFrame, analysis: Dict) -> List[Path]:
        """Convert to Parquet with optimal partitioning."""
        print("\n🔄 Converting to Parquet partitions...")
        
        if not analysis["potential_partitions"]:
            print("⚠ No date/symbol columns found. Saving as single file...")
            parquet_file = self.parquet_dir / "data.parquet"
            df.to_parquet(parquet_file, compression="snappy")
            return [parquet_file]
        
        # Get partition columns
        primary_col = analysis["potential_partitions"].get("primary")
        secondary_col = analysis["potential_partitions"].get("secondary")
        
        # Create partitions
        parquet_files = []
        
        if primary_col and secondary_col:
            # Partition by both
            for date_val, date_group in df.groupby(primary_col):
                for symbol_val, symbol_group in date_group.groupby(secondary_col):
                    date_str = str(date_val).split()[0] if isinstance(date_val, pd.Timestamp) else str(date_val)
                    partition_dir = self.parquet_dir / f"date={date_str}/symbol={symbol_val}"
                    partition_dir.mkdir(parents=True, exist_ok=True)
                    
                    parquet_file = partition_dir / "part-000.parquet"
                    symbol_group.to_parquet(parquet_file, compression="snappy", index=False)
                    parquet_files.append(parquet_file)
            
            print(f"✓ Created {len(parquet_files)} partitions")
        
        elif primary_col:
            # Partition by date only
            for date_val, date_group in df.groupby(primary_col):
                date_str = str(date_val).split()[0] if isinstance(date_val, pd.Timestamp) else str(date_val)
                partition_dir = self.parquet_dir / f"date={date_str}"
                partition_dir.mkdir(parents=True, exist_ok=True)
                
                parquet_file = partition_dir / "part-000.parquet"
                date_group.to_parquet(parquet_file, compression="snappy", index=False)
                parquet_files.append(parquet_file)
            
            print(f"✓ Created {len(parquet_files)} date partitions")
        
        return parquet_files
    
    def generate_schema(self, df: pd.DataFrame) -> Dict:
        """Generate schema.json."""
        schema = {
            "columns": []
        }
        
        for col in df.columns:
            col_type = str(df[col].dtype)
            
            # Map pandas types to Parquet types
            if 'int' in col_type:
                parquet_type = 'int64'
            elif 'float' in col_type:
                parquet_type = 'double'
            elif 'datetime' in col_type or 'timestamp' in col_type:
                parquet_type = 'int64'
            else:
                parquet_type = 'utf8'
            
            schema["columns"].append({
                "name": col,
                "type": parquet_type,
                "nullable": bool(df[col].isnull().any()),
                "description": f"{col} column"
            })
        
        return schema
    
    def generate_manifest(self, df: pd.DataFrame, parquet_files: List[Path], 
                         analysis: Dict) -> Dict:
        """Generate manifest.json."""
        timestamp = datetime.utcnow().isoformat() + "Z"
        timestamp_version = timestamp.replace(":", "-").split(".")[0] + "Z"
        
        # Calculate total size
        total_size = sum(f.stat().st_size for f in parquet_files if f.exists())
        
        # Generate partition list
        partition_list = []
        for f in parquet_files:
            rel_path = f.relative_to(self.parquet_dir)
            partition_list.append(f"partitions/{rel_path}")
        
        # Get date and symbol info
        primary_col = analysis["potential_partitions"].get("primary")
        secondary_col = analysis["potential_partitions"].get("secondary")
        
        manifest = {
            "dataset_name": "market-data-research",
            "dataset_version": timestamp_version,
            "created_at": timestamp,
            "format": "parquet",
            "compression": "snappy",
            "partition_scheme": ["date", "symbol"] if secondary_col else ["date"],
            "partitions": sorted(partition_list),
            "total_size_bytes": total_size,
            "record_count": len(df),
            "symbols": sorted(df[secondary_col].unique().tolist()) if secondary_col else [],
        }
        
        if primary_col:
            dates = sorted(df[primary_col].astype(str).unique().tolist())
            if dates:
                manifest["date_range"] = {
                    "start": dates[0].split()[0],
                    "end": dates[-1].split()[0]
                }
        
        return manifest
    
    def generate_checksums(self, parquet_files: List[Path]) -> str:
        """Generate checksums.txt."""
        checksums = []
        
        for f in sorted(parquet_files):
            if f.exists():
                with open(f, 'rb') as fp:
                    sha = hashlib.sha256(fp.read()).hexdigest()
                    rel_path = f.relative_to(self.parquet_dir.parent)
                    checksums.append(f"SHA256:{rel_path}={sha}")
        
        return "\n".join(checksums)
    
    def save_metadata(self, manifest: Dict, schema: Dict, checksums: str):
        """Save manifest, schema, and checksums."""
        manifest_file = self.output_dir / "manifest.json"
        schema_file = self.output_dir / "schema.json"
        checksums_file = self.output_dir / "checksums.txt"
        
        with open(manifest_file, 'w') as f:
            json.dump(manifest, f, indent=2)
        
        with open(schema_file, 'w') as f:
            json.dump({
                "dataset_name": manifest["dataset_name"],
                "dataset_version": manifest["dataset_version"],
                "columns": schema["columns"]
            }, f, indent=2)
        
        with open(checksums_file, 'w') as f:
            f.write(checksums)
        
        print("\n✓ Metadata saved:")
        print(f"  - manifest.json")
        print(f"  - schema.json")
        print(f"  - checksums.txt")
    
    def analyze_selective_retrieval(self, manifest: Dict, df: pd.DataFrame, 
                                    analysis: Dict) -> Dict:
        """Analyze cost savings with selective retrieval."""
        print("\n💰 Selective Retrieval Analysis:\n")
        
        primary_card = analysis["potential_partitions"].get("primary_cardinality", 1)
        secondary_card = analysis["potential_partitions"].get("secondary_cardinality", 1)
        total_partitions = primary_card * secondary_card
        total_size_gb = manifest["total_size_bytes"] / (1024**3)
        
        # Cost scenarios
        full_download = {
            "files": len(manifest["partitions"]),
            "get_cost": (len(manifest["partitions"]) / 1000) * 5,
            "transfer_cost": total_size_gb * 0.023,
            "total": (len(manifest["partitions"]) / 1000) * 5 + (total_size_gb * 0.023)
        }
        
        single_partition_size = total_size_gb / max(total_partitions, 1)
        single_partition = {
            "files": 5,  # average files per partition
            "get_cost": (5 / 1000) * 5,
            "transfer_cost": single_partition_size * 0.023,
            "total": (5 / 1000) * 5 + (single_partition_size * 0.023)
        }
        
        typical_backtest = {
            "files": primary_card * 5,  # 60-day backtest, ~5 files per day/symbol
            "get_cost": (primary_card * 5 / 1000) * 5,
            "transfer_cost": single_partition_size * 0.023 * primary_card,
            "total": (primary_card * 5 / 1000) * 5 + (single_partition_size * 0.023 * primary_card)
        }
        
        analysis_result = {
            "dataset_size_gb": total_size_gb,
            "total_partitions": total_partitions,
            "date_cardinality": primary_card,
            "symbol_cardinality": secondary_card,
            "scenarios": {
                "full_download": full_download,
                "single_partition": single_partition,
                "typical_backtest_60day": typical_backtest
            }
        }
        
        # Print analysis
        print(f"Dataset Size: {total_size_gb:.2f} GB")
        print(f"Total Partitions: {total_partitions:,}")
        print(f"  - Dates: {primary_card}")
        print(f"  - Symbols: {secondary_card}")
        print(f"\nCost Scenarios:")
        print(f"\n1️⃣  Full Download (40 GB)")
        print(f"    Files: {full_download['files']:,}")
        print(f"    GET cost: ${full_download['get_cost']:.2f}")
        print(f"    Transfer: ${full_download['transfer_cost']:.2f}")
        print(f"    TOTAL: ${full_download['total']:.2f}")
        
        print(f"\n2️⃣  Single Partition (1 date, 1 symbol)")
        print(f"    Files: {single_partition['files']}")
        print(f"    GET cost: ${single_partition['get_cost']:.4f}")
        print(f"    Transfer: ${single_partition['transfer_cost']:.4f}")
        print(f"    TOTAL: ${single_partition['total']:.4f}")
        
        print(f"\n3️⃣  Typical Backtest (60-day window, 1 symbol)")
        print(f"    Files: {typical_backtest['files']}")
        print(f"    GET cost: ${typical_backtest['get_cost']:.4f}")
        print(f"    Transfer: ${typical_backtest['transfer_cost']:.4f}")
        print(f"    TOTAL: ${typical_backtest['total']:.4f}")
        
        savings_pct = (full_download['total'] - typical_backtest['total']) / full_download['total'] * 100
        print(f"\n💡 Savings with selective retrieval: {savings_pct:.1f}%")
        print(f"   ({full_download['total'] / typical_backtest['total']:.0f}x cheaper)")
        
        return analysis_result
    
    def run(self) -> bool:
        """Execute full pipeline."""
        print("=" * 60)
        print("  Dataset Preparation Pipeline")
        print("=" * 60)
        
        # Step 1: Download
        file_path = self.download_box_data()
        if not file_path:
            return False
        
        # Step 2: Load
        df = self.load_data(file_path)
        if df is None:
            return False
        
        print(f"✓ Loaded {len(df):,} rows, {len(df.columns)} columns")
        print(f"✓ Memory usage: {df.memory_usage(deep=True).sum() / (1024**2):.2f} MB")
        
        # Step 3: Analyze
        analysis = self.analyze_data(df)
        
        # Step 4: Convert to Parquet
        parquet_files = self.partition_and_convert(df, analysis)
        
        # Step 5: Generate metadata
        schema = self.generate_schema(df)
        manifest = self.generate_manifest(df, parquet_files, analysis)
        checksums = self.generate_checksums(parquet_files)
        
        # Step 6: Save metadata
        self.save_metadata(manifest, schema, checksums)
        
        # Step 7: Analyze selective retrieval
        retrieval_analysis = self.analyze_selective_retrieval(manifest, df, analysis)
        
        # Step 8: Print summary
        print("\n" + "=" * 60)
        print("  Next Steps")
        print("=" * 60)
        print(f"\n1. Review manifest.json in {self.output_dir}/")
        print(f"2. Upload to S3:")
        print(f"   aws s3 sync {self.output_dir} \\")
        print(f"     s3://$S3_BUCKET_NAME/datasets/market-data-research/$(date +%Y-%m-%dT%H-%M-%SZ)/ \\")
        print(f"     --region us-east-1")
        print(f"\n3. Test retrieval:")
        print(f"   python scripts/data_retriever.py list-datasets")
        print(f"   python scripts/data_retriever.py sync-partition \\")
        print(f"     market-data-research <version> \"date=2026-04-01/symbol=AAPL\"")
        print("=" * 60)
        
        return True

def main():
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        raise ValueError("No URL provided")
    
    preparer = DatasetPreparer(url)
    success = preparer.run()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
