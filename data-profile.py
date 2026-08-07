#!/usr/bin/env python3
"""
Lore Matrix - Automated Exploratory Data Analysis & Pre-Ingestion Data Scrubber
Evaluates raw flat files (CSV/XLSX), audits structural health with terminal profiling,
sanitizes formatting to ensure SQL schema compliance, and outputs a clean CSV.
"""

import os
import re

import pandas as pd


def clean_header(col_name):
    """
    Standardizes column headers: strips whitespace, replaces spaces/hyphens/dots with
    underscores, removes special characters, and makes everything lowercase.
    """
    col_str = str(col_name).strip()
    # Replace spaces, hyphens, slashes, and dots with a single underscore
    col_str = re.sub(r'[\s\-/\.]+', '_', col_str)
    # Remove any character that is not alphanumeric or an underscore (e.g. %, #)
    col_str = re.sub(r'[^\w]', '', col_str)
    # Collapse multiple consecutive underscores
    col_str = re.sub(r'_+', '_', col_str)
    # Strip leading or trailing underscores
    col_str = col_str.strip('_')
    return col_str.lower()

def run_health_audit(df):
    """
    Prints a highly readable ASCII terminal report detailing shape, schema,
    missing data, and statistics of the loaded dataset.
    """
    print("\n" + "=" * 80)
    print("📋 LORE MATRIX DATASET HEALTH AUDIT REPORT")
    print("=" * 80)
    print(f"📊 Dataset Shape: {df.shape[0]} rows, {df.shape[1]} columns")
    print("-" * 80)
    
    # Header summary columns
    print(f"{'Column Name':<32} | {'pandas dtype':<15} | {'Null Count':<12} | {'Null %':<10}")
    print("-" * 80)
    
    for col in df.columns:
        null_count = df[col].isnull().sum()
        null_pct = (null_count / len(df)) * 100 if len(df) > 0 else 0.0
        dtype_str = str(df[col].dtype)
        print(f"{col:<32} | {dtype_str:<15} | {null_count:<12} | {null_pct:.2f}%")
        
    print("-" * 80)
    print("📈 Descriptive Analysis & Cardinality:")
    print("-" * 80)
    
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            # Numeric column stats
            non_null_df = df[col].dropna()
            if not non_null_df.empty:
                col_min = non_null_df.min()
                col_max = non_null_df.max()
                col_mean = non_null_df.mean()
                print(f"🔹 {col:<25} (Numeric) -> Min: {col_min:.4f} | Max: {col_max:.4f} | Mean: {col_mean:.4f}")
            else:
                print(f"🔹 {col:<25} (Numeric) -> [No numeric values found]")
        else:
            # Categorical / string column unique counts
            unique_count = df[col].nunique()
            print(f"🔸 {col:<25} (Text/Cat) -> Unique Values: {unique_count}")
            
    print("=" * 80 + "\n")

def main():
    print("================================================================================")
    print("  Lore Matrix - Data Profiling & Sanitization Engine")
    print("================================================================================")
    
    df = None
    resolved_path = None
    
    while True:
        file_path = input("Enter path to target CSV/XLSX file (or 'q' to quit): ").strip()
        if file_path.lower() == 'q':
            print("Exiting Data Profiler.")
            return
            
        if not file_path:
            continue
            
        # Resolve absolute path for robustness
        resolved_path = os.path.abspath(file_path)
        if not os.path.exists(resolved_path):
            # Check relative to script directory
            script_dir = os.path.dirname(os.path.abspath(__file__))
            alt_path = os.path.join(script_dir, file_path)
            if os.path.exists(alt_path):
                resolved_path = alt_path
            else:
                print(f"❌ Error: File not found at '{file_path}'. Please check and try again.\n")
                continue
                
        try:
            ext = os.path.splitext(resolved_path)[1].lower()
            if ext == '.csv':
                df = pd.read_csv(resolved_path)
            elif ext in ['.xlsx', '.xls']:
                df = pd.read_excel(resolved_path)
            else:
                print(f"❌ Error: Unsupported file format '{ext}'. Must be .csv or .xlsx.\n")
                continue
            
            # Successfully loaded DataFrame
            break
        except Exception as e:
            print(f"❌ Error reading file: {e}. Please try again.\n")

    # Run health audit prior to sanitization
    run_health_audit(df)
    
    # Prompt user to proceed with clean
    confirm = input("Proceed with data sanitization and handoff? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Sanitization aborted. Returning to master pipeline.")
        return
        
    print("\n🚀 Executing Sanitization Engine...")
    
    # 1. Drop completely empty rows and columns
    row_before, col_before = df.shape
    df.dropna(how='all', inplace=True)
    df.dropna(axis=1, how='all', inplace=True)
    row_after, col_after = df.shape
    
    if (row_before - row_after) > 0 or (col_before - col_after) > 0:
        print(f"🧹 Dropped {row_before - row_after} empty rows and {col_before - col_after} empty columns.")
        
    # 2. Header Normalization
    original_columns = list(df.columns)
    normalized_columns = [clean_header(col) for col in original_columns]
    df.columns = normalized_columns
    
    # Log header transformations if anything changed
    changes = [f"'{orig}' -> '{new}'" for orig, new in zip(original_columns, normalized_columns, strict=False) if orig != new]
    if changes:
        print("📝 Normalized headers:")
        for change in changes:
            print(f"   - {change}")
            
    # 3. Data Row Scrubbing (strip whitespace from strings)
    for col in df.columns:
        if df[col].dtype == object or pd.api.types.is_string_dtype(df[col]):
            df[col] = df[col].apply(lambda x: x.strip() if isinstance(x, str) else x)
            
    print("✅ String cell whitespace successfully scrubbed.")
    
    # 4. Handoff to processed_data directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    processed_dir = os.path.join(script_dir, "processed_data")
    os.makedirs(processed_dir, exist_ok=True)
    
    orig_basename = os.path.basename(resolved_path)
    name_part, _ = os.path.splitext(orig_basename)
    name_part = name_part.replace("_scrubbed", "")
    out_filename = f"{name_part}_scrubbed.csv"
    out_path = os.path.join(processed_dir, out_filename)
    
    try:
        df.to_csv(out_path, index=False)
        print("\n" + "=" * 60)
        print("💾 SANITIZED HANDOFF SUCCESSFUL")
        print("=" * 60)
        print(f"📂 Output File: {out_path}")
        print(f"📊 Final Shape: {df.shape[0]} rows, {df.shape[1]} columns")
        print("=" * 60)
    except Exception as e:
        print(f"❌ Error writing scrubbed CSV: {e}")

if __name__ == "__main__":
    main()
