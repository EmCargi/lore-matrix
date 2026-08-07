import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

# Import BASE_DIR from config.settings (or define fallback if import fails)
try:
    from config.settings import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent.parent

def resolve_path(path):
    """Resolves path relative to BASE_DIR if it is not absolute."""
    p = Path(path)
    if p.is_absolute():
        return p
    return (BASE_DIR / p).resolve()

def load_data(input_path):
    """Loads CSV or Excel files based on their extension."""
    resolved_path = resolve_path(input_path)
    
    # Error Handling: Check if file exists
    if not resolved_path.exists():
        print(f"Error: The input file does not exist at '{resolved_path}'", file=sys.stderr)
        sys.exit(1)
        
    # Error Handling: Inspect file extension
    ext = resolved_path.suffix.lower()
    if ext == '.csv':
        try:
            return pd.read_csv(resolved_path)
        except Exception as e:
            print(f"Error reading CSV file: {e}", file=sys.stderr)
            sys.exit(1)
    elif ext == '.xlsx':
        try:
            return pd.read_excel(resolved_path)
        except Exception as e:
            print(f"Error reading Excel file: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"Error: Unsupported file extension '{ext}'. Only .csv and .xlsx files are supported.", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Universal Dataset-Agnostic Charting Engine")
    parser.add_argument('--input', help="Path to the input data file (CSV or XLSX)")
    parser.add_argument('--db', help="Path to the target SQLite database file (.db)")
    parser.add_argument('--table', help="Name of the SQLite table to load data from")
    parser.add_argument('--output', required=True, help="Path or name to save the output chart image")
    parser.add_argument('--chart-type', required=True, choices=['bar', 'line', 'box'], help="Type of chart to generate")
    
    args = parser.parse_args()
    
    # Load data from database or raw file
    if args.db and args.table:
        db_path = resolve_path(args.db)
        if not db_path.exists():
            print(f"Error: The database file does not exist at '{db_path}'", file=sys.stderr)
            sys.exit(1)
        try:
            import sqlite3
            print(f"[*] Connecting to database: {db_path.name}")
            print(f"[*] Reading table '{args.table}'...")
            with sqlite3.connect(db_path) as conn:
                df = pd.read_sql_query(f"SELECT * FROM {args.table}", conn)
        except Exception as e:
            print(f"Error reading from SQLite database: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.input:
        df = load_data(args.input)
    else:
        print("Error: Either --input or both --db and --table must be specified.", file=sys.stderr)
        sys.exit(1)
    
    # Print a numbered list of all available column headers
    print("\nAvailable column headers:")
    for idx, col in enumerate(df.columns, start=1):
        print(f"{idx}. {col}")
    print()
    
    # Prompt for X-axis column with basic error handling
    while True:
        x_col = input("Enter the exact name of the column for the X-axis: ").strip()
        if x_col in df.columns:
            break
        print(f"Error: Column '{x_col}' does not exist in the dataset. Please try again.")
        
    # Prompt for Y-axis column with basic error handling
    while True:
        y_col = input("Enter the exact name of the column for the Y-axis: ").strip()
        if y_col in df.columns:
            break
        print(f"Error: Column '{y_col}' does not exist in the dataset. Please try again.")

    # Prepare base plot configurations
    plt.figure(figsize=(10, 6), dpi=150)
    plt.grid(visible=True, linestyle='--', alpha=0.5, zorder=0)
    
    try:
        # Dynamic Visualization logic
        if args.chart_type in ['bar', 'line']:
            # Group the data by the chosen X-axis and sum the chosen Y-axis
            # Ensure Y-axis is numeric or can be coerced to numeric for summation
            try:
                df[y_col] = pd.to_numeric(df[y_col])
            except Exception as e:
                print(f"Warning: Failed to convert Y-axis column '{y_col}' to numeric. Sum operation might fail: {e}", file=sys.stderr)
                
            grouped = df.groupby(x_col, observed=False)[y_col].sum().reset_index()
            
            # Sort by X-axis values for structured visualization
            try:
                grouped = grouped.sort_values(x_col)
            except Exception:
                pass # Fallback if columns are of mixed incomparable types
                
            x_data = grouped[x_col]
            y_data = grouped[y_col]
            
            if args.chart_type == 'bar':
                plt.bar(
                    x_data, 
                    y_data, 
                    color='#1f77b4', 
                    edgecolor='none', 
                    alpha=0.85,
                    zorder=3
                )
                plt.title(f"Sum of {y_col} by {x_col} (Bar Chart)", fontsize=14, fontweight='bold', pad=15)
                
            elif args.chart_type == 'line':
                plt.plot(
                    x_data, 
                    y_data, 
                    color='#1f77b4', 
                    marker='o', 
                    linewidth=2.5, 
                    markersize=6,
                    zorder=3
                )
                plt.title(f"Sum of {y_col} Trend by {x_col} (Line Chart)", fontsize=14, fontweight='bold', pad=15)
                
            plt.ylabel(f"Sum of {y_col}", fontsize=11, labelpad=10)
            
        elif args.chart_type == 'box':
            # Distribution of chosen Y-axis grouped by chosen X-axis
            unique_x = df[x_col].dropna().unique()
            try:
                unique_x = sorted(unique_x)
            except TypeError:
                pass # Fallback if values cannot be sorted
                
            data_to_plot = []
            labels_to_plot = []
            for x_val in unique_x:
                # Get Y-axis values corresponding to X-axis value
                subset = df[df[x_col] == x_val][y_col].dropna()
                try:
                    subset = pd.to_numeric(subset)
                except Exception:
                    pass
                subset_vals = subset.values
                if len(subset_vals) > 0:
                    data_to_plot.append(subset_vals)
                    labels_to_plot.append(str(x_val))
                    
            if not data_to_plot:
                print(f"Error: No non-empty numeric data groups found for box plot with Y-axis '{y_col}'.", file=sys.stderr)
                sys.exit(1)
                
            plt.boxplot(data_to_plot, labels=labels_to_plot, zorder=3)
            plt.title(f"Distribution of {y_col} by {x_col} (Box Plot)", fontsize=14, fontweight='bold', pad=15)
            plt.ylabel(y_col, fontsize=11, labelpad=10)
            
        plt.xlabel(x_col, fontsize=11, labelpad=10)
        plt.xticks(rotation=45)
        
    except Exception as e:
        print(f"Error generating plot: {e}", file=sys.stderr)
        sys.exit(1)
        
    # Save the output cleanly into the BASE_DIR / "processed_data" directory
    output_filename = Path(args.output).name
    resolved_output = BASE_DIR / "processed_data" / output_filename
    
    # Ensure processed_data directory exists
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    
    plt.tight_layout()
    try:
        plt.savefig(resolved_output)
        print(f"Successfully generated and saved {args.chart_type} plot to: {resolved_output}")
    except Exception as e:
        print(f"Error saving plot to {resolved_output}: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        plt.close()

if __name__ == '__main__':
    main()
