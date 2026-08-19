import argparse
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd
from mpl_toolkits.mplot3d import Axes3D

# Import BASE_DIR from config.settings (or define fallback if import fails)
try:
    from config.settings import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent.parent

# Import MidiDensityLog schema (mido project sibling)
try:
    _midi_project = (BASE_DIR.parent / "midi-project").resolve()
    if str(_midi_project) not in sys.path:
        sys.path.insert(0, str(_midi_project))
    from midi_density_compiler import MidiDensityLog
    _MIDI_AVAILABLE = True
except (ImportError, OSError):
    _MIDI_AVAILABLE = False

def load_midi_density(input_path: Path) -> pd.DataFrame:
    """Load MidiDensityLog JSON and flatten to a DataFrame."""
    if not _MIDI_AVAILABLE:
        print("Error: midi_density_compiler not found. Ensure midi-project/ is accessible.",
              file=sys.stderr)
        sys.exit(1)

    resolved_path = resolve_path(input_path)
    if not resolved_path.exists():
        print(f"Error: The input file does not exist at '{resolved_path}'", file=sys.stderr)
        sys.exit(1)

    log = MidiDensityLog.model_validate_json(resolved_path.read_text())
    rows = []
    for entry in log.entries:
        for track_name, track_data in entry.tracks.items():
            for sw in track_data.sub_windows:
                rows.append({
                    'track_name': track_name,
                    'measure': entry.measure_number,
                    'time_offset': sw.time_offset,
                    'note_density': sw.note_density,
                    'active_polyphony': sw.active_polyphony,
                    'average_velocity': sw.average_velocity,
                    'average_pitch': sw.average_pitch,
                })
    return pd.DataFrame(rows)


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

def _plot_narrative_fingerprint(df, x_col, y_cols, args):
    """Grouped bar chart comparing NME fingerprints across stories."""
    default_palette = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
    if args.palette:
        colors = [c.strip() for c in args.palette.split(",")]
    else:
        colors = default_palette

    labels = df[x_col].astype(str).tolist()
    x = np.arange(len(labels))
    width = 0.8 / len(y_cols)

    for i, col in enumerate(y_cols):
        offset = (i - len(y_cols) / 2 + 0.5) * width
        values = pd.to_numeric(df[col], errors='coerce').fillna(0)
        plt.bar(
            x + offset,
            values,
            width,
            label=col.replace("_", " ").title(),
            color=colors[i % len(colors)],
            edgecolor='none',
            alpha=0.85,
            zorder=3,
        )

    plt.xlabel(x_col.replace("_", " ").title(), fontsize=11, labelpad=10)
    plt.ylabel("Score (0-10)", fontsize=11, labelpad=10)
    plt.ylim(0, 10.5)
    plt.gca().yaxis.set_major_locator(ticker.MultipleLocator(1))
    plt.xticks(x, labels, rotation=30, ha='right')
    plt.legend(loc='upper right', fontsize=9, framealpha=0.9)
    title = args.title or "Narrative Fingerprint Comparison"
    plt.title(title, fontsize=14, fontweight='bold', pad=15)


def _plot_scatter3d(df, x_col, y_cols, args):
    """3D scatter plot from three numeric columns. Track-colored if track_name column present."""
    if len(y_cols) < 3:
        print("Error: scatter3d requires at least 3 Y columns (x, y, z).", file=sys.stderr)
        sys.exit(1)

    x_vals = pd.to_numeric(df[x_col], errors='coerce').fillna(0)
    y_vals = pd.to_numeric(df[y_cols[0]], errors='coerce').fillna(0)
    z_vals = pd.to_numeric(df[y_cols[1]], errors='coerce').fillna(0)

    color_vals = None
    if len(y_cols) >= 4:
        color_vals = pd.to_numeric(df[y_cols[2]], errors='coerce').fillna(0)

    fig = plt.figure(figsize=(10, 8), dpi=150)
    ax = fig.add_subplot(111, projection='3d')

    if 'track_name' in df.columns:
        track_colors = {
            'Track_01': '#E74C3C', 'Track_02': '#3498DB',
            'Track_03': '#2ECC71', 'Track_04': '#9B59B6',
        }
        fallback = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                    '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
        tracks = df['track_name'].unique()
        for i, track in enumerate(tracks):
            mask = df['track_name'] == track
            color = track_colors.get(track, fallback[i % len(fallback)])
            ax.scatter(x_vals[mask], y_vals[mask], z_vals[mask],
                       c=color, s=80, alpha=0.85, label=track, zorder=3)
        ax.legend(loc='upper left', fontsize=8, framealpha=0.7, title='Voices')
    elif color_vals is not None:
        scatter = ax.scatter(x_vals, y_vals, z_vals, c=color_vals, cmap='coolwarm',
                             s=80, alpha=0.85, zorder=3)
        cbar = plt.colorbar(scatter, ax=ax, shrink=0.6, pad=0.1)
        cbar.set_label(y_cols[2].replace("_", " ").title(), fontsize=10)
    else:
        ax.scatter(x_vals, y_vals, z_vals, color='#1f77b4', s=80, alpha=0.85, zorder=3)

    ax.set_xlabel(x_col.replace("_", " ").title(), fontsize=10, labelpad=8)
    ax.set_ylabel(y_cols[0].replace("_", " ").title(), fontsize=10, labelpad=8)
    ax.set_zlabel(y_cols[1].replace("_", " ").title(), fontsize=10, labelpad=8)

    if 'track_name' not in df.columns:
        labels = df[x_col].astype(str).tolist()
        for i, label in enumerate(labels):
            ax.text(x_vals.iloc[i], y_vals.iloc[i], z_vals.iloc[i], label, fontsize=7)

    title = args.title or f"3D Scatter: {x_col} vs {y_cols[0]} vs {y_cols[1]}"
    ax.set_title(title, fontsize=13, fontweight='bold', pad=20)


def _plot_animate3d(df, x_col, y_cols, args):
    """3D scatter with sequence-based coloring (acts as frames). Measure-aware for MIDI data."""
    from matplotlib.animation import FuncAnimation, PillowWriter

    if len(y_cols) < 3:
        print("Error: animate3d requires at least 3 Y columns (x, y, z).", file=sys.stderr)
        sys.exit(1)

    x_vals = pd.to_numeric(df[x_col], errors='coerce').fillna(0)
    y_vals = pd.to_numeric(df[y_cols[0]], errors='coerce').fillna(0)
    z_vals = pd.to_numeric(df[y_cols[1]], errors='coerce').fillna(0)
    sequence = pd.to_numeric(df[y_cols[2]], errors='coerce').fillna(0) if len(y_cols) >= 4 else None

    fig = plt.figure(figsize=(10, 8), dpi=150)
    ax = fig.add_subplot(111, projection='3d')

    has_measure = 'measure' in df.columns
    has_track = 'track_name' in df.columns
    track_colors = {
        'Track_01': '#E74C3C', 'Track_02': '#3498DB',
        'Track_03': '#2ECC71', 'Track_04': '#9B59B6',
    }
    fallback = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']

    def update(frame):
        ax.clear()
        if has_measure:
            mask = df['measure'] <= frame
            if has_track:
                for i, track in enumerate(df['track_name'].unique()):
                    tmask = mask & (df['track_name'] == track)
                    color = track_colors.get(track, fallback[i % len(fallback)])
                    ax.scatter(x_vals[tmask], y_vals[tmask], z_vals[tmask],
                               c=color, s=80, alpha=0.85, label=track, zorder=3)
            else:
                ax.scatter(x_vals[mask], y_vals[mask], z_vals[mask],
                           c='#1f77b4', s=80, alpha=0.85, zorder=3)
        elif sequence is not None:
            mask = sequence <= frame
            ax.scatter(x_vals[mask], y_vals[mask], z_vals[mask],
                       c='#1f77b4', s=80, alpha=0.85, zorder=3)
            ax.scatter(x_vals[~mask], y_vals[~mask], z_vals[~mask],
                       c='lightgray', s=30, alpha=0.3, zorder=2)
        else:
            ax.scatter(x_vals[:frame+1], y_vals[:frame+1], z_vals[:frame+1],
                       c='#1f77b4', s=80, alpha=0.85, zorder=3)
        ax.set_xlabel(x_col.replace("_", " ").title(), fontsize=10, labelpad=8)
        ax.set_ylabel(y_cols[0].replace("_", " ").title(), fontsize=10, labelpad=8)
        ax.set_zlabel(y_cols[1].replace("_", " ").title(), fontsize=10, labelpad=8)
        if has_measure:
            ax.set_title(f"Measure {frame}", fontsize=13, fontweight='bold', pad=20)
        else:
            ax.set_title(f"Frame {frame}", fontsize=13, fontweight='bold', pad=20)

    if has_measure:
        frames = int(df['measure'].max())
    elif sequence is not None:
        frames = int(sequence.max())
    else:
        frames = len(df)

    anim = FuncAnimation(fig, update, frames=frames + 1, interval=500, repeat=True)

    output_filename = Path(args.output).name
    resolved_output = BASE_DIR / "processed_data" / output_filename
    resolved_output.parent.mkdir(parents=True, exist_ok=True)

    try:
        out_path = str(resolved_output)
        if out_path.endswith('.png'):
            out_path = out_path.replace('.png', '.gif')
        writer = PillowWriter(fps=2)
        anim.save(out_path, writer=writer)
        print(f"Successfully saved animation to: {out_path}")
    except Exception as e:
        print(f"Warning: animation save failed ({e}). Saving static frame instead.", file=sys.stderr)
        update(frames)
        plt.savefig(resolved_output)
    finally:
        plt.close()


def _plot_radar(df, x_col, y_cols, args):
    """Radar/spider chart for multi-axis narrative comparison."""
    if len(y_cols) < 3:
        print("Error: radar requires at least 3 Y columns.", file=sys.stderr)
        sys.exit(1)

    labels = df[x_col].astype(str).tolist()
    axes = [c.replace("_", " ").title() for c in y_cols]
    angles = np.linspace(0, 2 * np.pi, len(axes), endpoint=False).tolist()
    angles += angles[:1]

    default_palette = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']
    colors = [c.strip() for c in args.palette.split(",")] if args.palette else default_palette

    fig, ax = plt.subplots(figsize=(8, 8), dpi=150, subplot_kw=dict(polar=True))

    for i, label in enumerate(labels):
        values = []
        for j in range(len(y_cols)):
            vals = pd.to_numeric(df[y_cols[j]], errors='coerce').fillna(0).tolist()
            values.append(vals[i])
        values += values[:1]
        color = colors[i % len(colors)]
        ax.plot(angles, values, 'o-', linewidth=2, label=label, color=color, zorder=3)
        ax.fill(angles, values, alpha=0.1, color=color, zorder=2)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(axes, fontsize=10)
    ax.set_ylim(0, 10)
    ax.set_yticks([2, 4, 6, 8, 10])
    ax.set_yticklabels(['2', '4', '6', '8', '10'], fontsize=8)
    ax.set_title(args.title or "Narrative Fingerprint Radar", fontsize=14, fontweight='bold', pad=25)
    ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1), fontsize=9)


def _plot_network(df, x_col, y_cols, args):
    """2D network graph from node-edge data."""
    try:
        import networkx as nx
    except ImportError:
        print("Error: networkx required for network charts. Install: pip install networkx",
              file=sys.stderr)
        sys.exit(1)

    G = nx.DiGraph()

    labels = df[x_col].astype(str).tolist()
    for label in labels:
        G.add_node(label)

    if len(y_cols) >= 2:
        sources = df[y_cols[0]].astype(str).tolist()
        targets = df[y_cols[1]].astype(str).tolist()
        for s, t in zip(sources, targets):
            if s != t:
                G.add_edge(s, t)

    fig, ax = plt.subplots(figsize=(12, 10), dpi=150)
    pos = nx.spring_layout(G, k=2, iterations=50, seed=42)

    nx.draw_networkx_nodes(G, pos, node_color='#1f77b4', node_size=300,
                           alpha=0.85, ax=ax)
    nx.draw_networkx_edges(G, pos, edge_color='#555555', width=1.0,
                           alpha=0.6, arrows=True, arrowsize=12, ax=ax)
    nx.draw_networkx_labels(G, pos, font_size=6, font_weight='bold', ax=ax)

    ax.set_axis_off()
    title = args.title or "Narrative Network Graph"
    ax.set_title(title, fontsize=14, fontweight='bold', pad=15)


def main():
    parser = argparse.ArgumentParser(description="Universal Dataset-Agnostic Charting Engine")
    parser.add_argument('--input', help="Path to the input data file (CSV or XLSX)")
    parser.add_argument('--db', help="Path to the target SQLite database file (.db)")
    parser.add_argument('--table', help="Name of the SQLite table to load data from")
    parser.add_argument('--output', required=True, help="Path or name to save the output chart image")
    parser.add_argument('--chart-type', required=True, choices=['bar', 'line', 'box', 'narrative', 'scatter3d', 'animate3d', 'network', 'radar'], help="Type of chart to generate")
    parser.add_argument('--x-col', help="Column for X-axis (non-interactive mode)")
    parser.add_argument('--y-col', help="Column(s) for Y-axis, comma-separated (non-interactive mode)")
    parser.add_argument('--title', help="Custom chart title")
    parser.add_argument('--figsize', help="Figure size as WxH (default: 10x6)")
    parser.add_argument('--palette', help="Comma-separated hex colors for grouped bars")
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
        if Path(args.input).suffix.lower() == '.json':
            df = load_midi_density(args.input)
        else:
            df = load_data(args.input)
    else:
        print("Error: Either --input or both --db and --table must be specified.", file=sys.stderr)
        sys.exit(1)
    
    # Resolve column selections
    if args.x_col:
        x_col = args.x_col
        if x_col not in df.columns:
            print(f"Error: X-axis column '{x_col}' not found.", file=sys.stderr)
            sys.exit(1)
    else:
        print("\nAvailable column headers:")
        for idx, col in enumerate(df.columns, start=1):
            print(f"{idx}. {col}")
        print()
        while True:
            x_col = input("Enter the exact name of the column for the X-axis: ").strip()
            if x_col in df.columns:
                break
            print(f"Error: Column '{x_col}' does not exist. Please try again.")

    if args.y_col:
        y_cols = [c.strip() for c in args.y_col.split(",")]
        for c in y_cols:
            if c not in df.columns:
                print(f"Error: Y-axis column '{c}' not found.", file=sys.stderr)
                sys.exit(1)
    else:
        while True:
            y_col_input = input("Enter the exact name of the column for the Y-axis: ").strip()
            if y_col_input in df.columns:
                y_cols = [y_col_input]
                break
            print(f"Error: Column '{y_col_input}' does not exist. Please try again.")

    figsize = (10, 6)
    if args.figsize:
        try:
            w, h = args.figsize.lower().split("x")
            figsize = (float(w), float(h))
        except Exception:
            pass

    plt.figure(figsize=figsize, dpi=150)
    plt.grid(visible=True, linestyle='--', alpha=0.5, zorder=0)

    try:
        if args.chart_type == 'narrative':
            _plot_narrative_fingerprint(df, x_col, y_cols, args)
        elif args.chart_type == 'scatter3d':
            _plot_scatter3d(df, x_col, y_cols, args)
        elif args.chart_type == 'animate3d':
            _plot_animate3d(df, x_col, y_cols, args)
        elif args.chart_type == 'network':
            _plot_network(df, x_col, y_cols, args)
        elif args.chart_type == 'radar':
            _plot_radar(df, x_col, y_cols, args)
        elif args.chart_type in ['bar', 'line']:
            y_col = y_cols[0]
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
