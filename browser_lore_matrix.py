#!/usr/bin/env python3
"""browser_lore_matrix.py — Interactive Lore Matrix ETL hub in the browser.

Replaces the manual CLI menu with a single Streamlit dashboard. Run extractors,
load CSV/XLSX into SQLite, visualize data with the chart engine, browse JSON
staging, inspect databases, and export to Obsidian — all in the browser.

Run:
    cd ~/dev/lore-matrix
    streamlit run browser_lore_matrix.py
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pandas as pd
import streamlit as st

from config.settings import ACTIVE_SYSTEM, OUTPUT_CHUNKS_DIR

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR.parent))  # dev/ — shared core (ollama)
sys.path.insert(0, str(BASE_DIR))          # lore-matrix/

# ── page config ───────────────────────────────────────────────────────

st.set_page_config(page_title="Lore Matrix — Browser Hub", layout="wide")
st.title("🌌 Lore Matrix — Browser Edition")
st.caption(f"Offline-first multimodal ETL hub ({ACTIVE_SYSTEM}). Ingest · Visualize · Persist.")

# ── cached helpers ────────────────────────────────────────────────────

@st.cache_data(show_spinner="Scanning databases…")
def _scan_dbs():
    patterns = [
        BASE_DIR / "*.db",
        BASE_DIR / "*.sqlite",
        BASE_DIR / "databases" / "*.db",
        BASE_DIR / "databases" / "*.sqlite",
    ]
    dbs = sorted({str(p) for p in sum((list(p.glob("*.db")) + list(p.glob("*.sqlite")) for p in patterns), [])})
    return dbs


@st.cache_data(show_spinner="Inspecting tables…")
def _inspect_tables(db_path: str):
    try:
        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [r[0] for r in cur.fetchall()]
            result = {}
            for t in tables:
                cur.execute(f"SELECT COUNT(*) FROM [{t}]")
                result[t] = cur.fetchone()[0]
            return result
    except Exception:
        return {}


@st.cache_data(show_spinner="Listing staged JSON…")
def _list_staged_json():
    if not OUTPUT_CHUNKS_DIR.exists():
        return {}
    result = {}
    for subdir in sorted(OUTPUT_CHUNKS_DIR.iterdir()):
        if subdir.is_dir():
            result[subdir.name] = sorted([f.name for f in subdir.iterdir() if f.suffix == ".json"])
    return result


# ── sidebar ───────────────────────────────────────────────────────────

st.sidebar.header("Navigation")
page = st.sidebar.radio(
    "Go to",
    [
        "📊 Dashboard",
        "📈 Visualizer",
        "🗄️ SQL Loader",
        "🗃️ Database",
        "📥 Ingest",
        "📦 JSON Staging",
        "📤 Export",
    ],
)

st.sidebar.divider()
st.sidebar.caption(f"Active System: **{ACTIVE_SYSTEM}**")
st.sidebar.caption("All scripts run standalone — subprocess orchestrated.")

# ═══════════════════════════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════════════════════════

if page == "📊 Dashboard":
    st.header("📊 Lore Matrix Dashboard")

    dbs = _scan_dbs()
    staged = _list_staged_json()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("SQLite Databases", len(dbs))
    with col2:
        total_json = sum(len(v) for v in staged.values())
        st.metric("Staged JSON Files", total_json)
    with col3:
        st.metric("Extractors", 9)

    st.divider()

    st.subheader("Available Databases")
    if dbs:
        for db_path in dbs:
            tables = _inspect_tables(db_path)
            with st.expander(f"📄 `{Path(db_path).name}` — {len(tables)} table(s)"):
                for t, c in tables.items():
                    st.caption(f"  • **{t}**: {c} row(s)")
    else:
        st.info("No SQLite databases found yet. Run the SQL Loader to create one.")

    st.divider()

    st.subheader("Staged JSON Output")
    if staged:
        for category, files in staged.items():
            with st.expander(f"📂 `{category}/` — {len(files)} file(s)"):
                for f in files:
                    st.caption(f"  • `{f}`")
    else:
        st.info("No staged JSON yet. Run the Unified Ingestor or an extractor.")

    st.divider()

    st.subheader("Quick Actions")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("▶ Run Unified Ingestor", use_container_width=True, type="primary"):
            st.session_state._action = "ingest"
    with c2:
        if st.button("📈 Open Visualizer", use_container_width=True):
            st.session_state._action = "visualizer"
    with c3:
        if st.button("🗄️ SQL Loader", use_container_width=True):
            st.session_state._action = "sql_loader"

    if st.session_state.get("_action") == "ingest":
        st.rerun()
    if st.session_state.get("_action") == "visualizer":
        st.session_state._page = "📈 Visualizer"
        st.rerun()
    if st.session_state.get("_action") == "sql_loader":
        st.session_state._page = "🗄️ SQL Loader"
        st.rerun()

# ═══════════════════════════════════════════════════════════════════════
# VISUALIZER
# ═══════════════════════════════════════════════════════════════════════

elif page == "📈 Visualizer":
    st.header("📈 Data Visualizer Engine")
    st.caption("Universal chart engine — CSV, XLSX, or SQLite table → bar / line / box / scatter3d / animate3d / network / radar.")

    col_src, col_chart = st.columns([2, 1])

    with col_src:
        source_type = st.radio(
            "Source", ["CSV / XLSX File", "SQLite Table"], index=0, key="viz_source_type"
        )

        if source_type == "CSV / XLSX File":
            uploaded = st.file_uploader(
                "Upload CSV or XLSX", type=["csv", "xlsx", "xls"],
                key="viz_upload",
            )
            csv_path = None
            if uploaded:
                tmp = tempfile.NamedTemporaryFile(suffix=f".{uploaded.name.split('.')[-1]}", delete=False)
                tmp.write(uploaded.getvalue())
                tmp.close()
                csv_path = tmp.name
                st.success(f"Loaded: `{uploaded.name}` ({uploaded.size:,} bytes)")

            x_col = st.text_input("X column", key="viz_xcol")
            y_cols = st.text_input("Y column(s), comma-separated", key="viz_ycols")
        else:
            dbs = _scan_dbs()
            db_choice = st.selectbox("Database", [""] + dbs, format_func=lambda p: Path(p).name if p else "— select a DB —")
            if db_choice:
                tables = _inspect_tables(db_choice)
                table_choice = st.selectbox("Table", list(tables.keys()))
                # load table into a temp CSV for the chart engine
                with sqlite3.connect(db_choice) as conn:
                    df = pd.read_sql_query(f"SELECT * FROM [{table_choice}]", conn)
                csv_path = str(Path(db_choice).parent / f"_viz_tmp_{table_choice}.csv")
                df.to_csv(csv_path, index=False)
                x_col = st.text_input("X column", key="viz_xcol_db", value=df.columns[0] if len(df.columns) > 0 else "")
                y_cols = st.text_input("Y column(s), comma-separated", key="viz_ycols_db", value=",".join(df.columns[1:6]))
            else:
                csv_path = None
                x_col = ""
                y_cols = ""

        chart_type = st.selectbox(
            "Chart type",
            ["bar", "line", "box", "narrative", "scatter3d", "animate3d", "network", "radar"],
            index=0,
        )
        title = st.text_input("Title (optional)", key="viz_title")

    with col_chart:
        st.subheader("Preview")
        if csv_path and x_col and y_cols:
            if st.button("▶ Generate Chart", type="primary", use_container_width=True):
                out_name = f"viz_{uuid.uuid4().hex[:8]}.png"
                out_path = str(BASE_DIR / "processed_data" / out_name)
                cmd = [
                    sys.executable,
                    str(BASE_DIR / "core" / "visualize-data.py"),
                    "--input", csv_path,
                    "--chart-type", chart_type,
                    "--x-col", x_col,
                    "--y-col", y_cols,
                    "--output", out_path,
                ]
                if title:
                    cmd.extend(["--title", title])
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                    if result.returncode == 0 and Path(out_path).exists():
                        st.image(out_path, caption=f"{chart_type} chart")
                        st.download_button(
                            "📥 Download Image",
                            data=Path(out_path).read_bytes(),
                            file_name=out_name,
                            mime="image/png",
                        )
                    else:
                        st.error(f"Chart generation failed:\n{result.stderr[:500]}")
                except subprocess.TimeoutExpired:
                    st.error("Chart generation timed out.")
                except Exception as e:
                    st.error(f"Error: {e}")
        else:
            st.info("Upload a file or select a SQLite table, then pick columns and chart type.")

# ═══════════════════════════════════════════════════════════════════════
# SQL LOADER
# ═══════════════════════════════════════════════════════════════════════

elif page == "🗄️ SQL Loader":
    st.header("🗄️ SQL Data Loader")
    st.caption("Generic CSV/XLSX → SQLite with idempotent upsert.")

    input_file = st.file_uploader("Upload CSV or XLSX", type=["csv", "xlsx", "xls"], key="sql_upload")
    db_name = st.text_input("Target SQLite database filename", value="game_vault.db")
    table_name = st.text_input("Target table name")
    key_col = st.text_input("Key column (for idempotent upsert)", placeholder="e.g., id")
    if_exists = st.selectbox("If exists", ["replace", "append", "fail"])

    if input_file and table_name:
        st.divider()
        col_load, col_run = st.columns([1, 2])
        with col_run:
            if st.button("▶ Load into SQLite", type="primary", use_container_width=True):
                ext = input_file.name.split(".")[-1]
                tmp = tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False)
                tmp.write(input_file.getvalue())
                tmp.close()

                cmd = [
                    sys.executable,
                    str(BASE_DIR / "sql-loader.py"),
                    "--input", tmp.name,
                    "--db", db_name,
                    "--table", table_name,
                    "--if-exists", if_exists,
                ]
                if key_col:
                    cmd.extend(["--key", key_col])

                try:
                    result = subprocess.run(
                        cmd, capture_output=True, text=True, cwd=str(BASE_DIR), timeout=120
                    )
                    if result.returncode == 0:
                        st.success(f"Loaded into `{db_name}` → table `{table_name}` ✅")
                        st.code(result.stdout[-500:] if result.stdout else "Done.")
                    else:
                        st.error(f"Failed:\n{result.stderr[-500:]}")
                except subprocess.TimeoutExpired:
                    st.error("SQL load timed out.")
                except Exception as e:
                    st.error(f"Error: {e}")

# ═══════════════════════════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════════════════════════

elif page == "🗃️ Database":
    st.header("🗃️ Database Inspector")

    dbs = _scan_dbs()
    if not dbs:
        st.info("No SQLite databases found. Load some data first.")
    else:
        db_choice = st.selectbox("Select database", [""] + dbs, format_func=lambda p: Path(p).name if p else "— select —")
        if db_choice:
            tables = _inspect_tables(db_choice)
            st.subheader(f"`{Path(db_choice).name}` — {len(tables)} table(s)")

            for t, count in tables.items():
                with st.expander(f"📄 **{t}** ({count} rows)"):
                    with sqlite3.connect(db_choice) as conn:
                        cur = conn.cursor()
                        cur.execute(f"SELECT * FROM [{t}] LIMIT 50")
                        rows = cur.fetchall()
                        cols = [d[0] for d in cur.description]
                    if rows:
                        df = pd.DataFrame(rows, columns=cols)
                        st.dataframe(df, use_container_width=True, hide_index=True)
                    else:
                        st.caption("Empty table.")

# ═══════════════════════════════════════════════════════════════════════
# INGEST
# ═══════════════════════════════════════════════════════════════════════

elif page == "📥 Ingest":
    st.header("📥 Ingestion Hub")

    ingest_mode = st.radio(
        "Mode",
        ["Unified Ingestor", "Individual Extractor", "ArchiveBox Frozen Asset"],
        index=0,
    )

    if ingest_mode == "Unified Ingestor":
        st.subheader("Run Unified Ingestor")
        st.caption("Scans all input hoppers (PDFs, web targets, images, manga OCR, JSON) and routes each to its extractor.")
        model = st.text_input("Model override (optional)", placeholder="e.g., gemma4-v2-Q6_K.gguf:latest")
        engine = st.selectbox("Engine", ["local", "gemini", "featherless"])

        if st.button("▶ Run Unified Ingestor", type="primary", use_container_width=True):
            cmd = [sys.executable, str(BASE_DIR / "ingest.py")]
            if model:
                cmd.extend(["--model", model])
            if engine != "local":
                cmd.extend(["--engine", engine])
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(BASE_DIR), timeout=300)
                st.code(result.stdout[-1000:] if result.stdout else result.stderr[-1000:])
                if result.returncode == 0:
                    st.success("Ingestion complete ✅")
                else:
                    st.error(f"Failed with exit code {result.returncode}")
            except subprocess.TimeoutExpired:
                st.error("Ingestion timed out — check running processes.")
            except Exception as e:
                st.error(f"Error: {e}")

    elif ingest_mode == "Individual Extractor":
        st.subheader("Run Individual Extractor")
        extractor = st.selectbox(
            "Extractor",
            [
                "PDF (extract-pdf.py)",
                "Web / ArchiveBox (extract-web.py)",
                "Images / Vision (extract-vision.py)",
                "Manga OCR (extract-manga.py)",
                "Game Dialogue (extract-game-text.py)",
                "Tables — PDF→CSV (extract-tables.py)",
                "Narrative Structure (extract-narrative.py)",
                "OCEAN Profiler (extract-ocean.py)",
                "Launchpad Scorer (extract-launchpad.py)",
                "Institution Meso-Scorer (extract-head.py)",
                "Monsters (extract-monsters.py)",
            ],
        )

        script_map = {
            "PDF (extract-pdf.py)": "extract-pdf.py",
            "Web / ArchiveBox (extract-web.py)": "extract-web.py",
            "Images / Vision (extract-vision.py)": "extract-vision.py",
            "Manga OCR (extract-manga.py)": "extract-manga.py",
            "Game Dialogue (extract-game-text.py)": "extract-game-text.py",
            "Tables — PDF→CSV (extract-tables.py)": "extract-tables.py",
            "Narrative Structure (extract-narrative.py)": "extract-narrative.py",
            "OCEAN Profiler (extract-ocean.py)": "extract-ocean.py",
            "Launchpad Scorer (extract-launchpad.py)": "extract-launchpad.py",
            "Institution Meso-Scorer (extract-head.py)": "extract-head.py",
            "Monsters (extract-monsters.py)": "extract-monsters.py",
        }

        script = script_map[extractor]
        st.info(f"Running **{script}**")

        if st.button("▶ Run Extractor", type="primary", use_container_width=True):
            try:
                result = subprocess.run(
                    [sys.executable, str(BASE_DIR / script)],
                    capture_output=True, text=True, cwd=str(BASE_DIR), timeout=300
                )
                st.code(result.stdout[-1000:] if result.stdout else result.stderr[-1000:])
                if result.returncode == 0:
                    st.success(f"{script} completed ✅")
                else:
                    st.error(f"Failed with exit code {result.returncode}")
            except subprocess.TimeoutExpired:
                st.error("Extractor timed out.")
            except Exception as e:
                st.error(f"Error: {e}")

    else:
        st.subheader("Ingest Frozen ArchiveBox Asset")
        st.caption("Import a saved ArchiveBox snapshot by timestamp ID.")
        ts_id = st.text_input("ArchiveBox Timestamp ID", placeholder="e.g., 1718912345")
        if st.button("▶ Ingest ArchiveBox Asset", type="primary", use_container_width=True):
            if ts_id:
                cmd = [sys.executable, str(BASE_DIR / "extract-web.py"), "--archive", ts_id]
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(BASE_DIR), timeout=300)
                    st.code(result.stdout[-1000:] if result.stdout else result.stderr[-1000:])
                    if result.returncode == 0:
                        st.success("ArchiveBox asset ingested ✅")
                    else:
                        st.error(f"Failed with exit code {result.returncode}")
                except subprocess.TimeoutExpired:
                    st.error("Ingestion timed out.")
                except Exception as e:
                    st.error(f"Error: {e}")
            else:
                st.warning("Enter a timestamp ID.")

# ═══════════════════════════════════════════════════════════════════════
# JSON STAGING
# ═══════════════════════════════════════════════════════════════════════

elif page == "📦 JSON Staging":
    st.header("📦 JSON Staging Area")
    staged = _list_staged_json()

    if not staged:
        st.info("No staged JSON yet. Run the Unified Ingestor or an extractor to populate this area.")
    else:
        for category, files in staged.items():
            with st.expander(f"📂 **{category}/** — {len(files)} file(s)"):
                for f in files:
                    fpath = OUTPUT_CHUNKS_DIR / category / f
                    if fpath.exists():
                        try:
                            data = fpath.read_text(encoding="utf-8")
                            with st.expander(f"📄 `{f}`"):
                                st.code(data[:2000], language="json")
                        except Exception as e:
                            st.caption(f"`{f}` — read error: {e}")
                    else:
                        st.caption(f"`{f}`")

# ═══════════════════════════════════════════════════════════════════════
# EXPORT
# ═══════════════════════════════════════════════════════════════════════

elif page == "📤 Export":
    st.header("📤 Export")

    export_tool = st.selectbox(
        "Export tool",
        [
            "JSON → Obsidian Notes (json_to_obsidian.py)",
            "SQLite → Obsidian Markdown (sql-to-md.py)",
            "Markdown Slicer (md_slicer.py)",
            "TV Tropes → Metadata Archive (meta_archivist.py)",
        ],
    )

    if export_tool == "JSON → Obsidian Notes (json_to_obsidian.py)":
        st.subheader("Compile JSON → Obsidian Notes")
        st.caption("Converts staged JSON into hash-cached, wiki-linked Obsidian notes.")
        phase = st.selectbox(
            "Export phase",
            ["one-shot", "raw (no-LLM)", "compile"],
            index=0,
            help="one-shot: JSON → compiled notes in one pass. raw: JSON → RAW_VAULT_DIR (no LLM). compile: RAW_VAULT_DIR → vault/ (LLM compile).",
        )
        cmd_args = [sys.executable, str(BASE_DIR / "src" / "transformers" / "json_to_obsidian.py")]
        if phase == "raw (no-LLM)":
            cmd_args.append("--phase")
            cmd_args.append("raw")
        elif phase == "compile":
            cmd_args.append("--phase")
            cmd_args.append("compile")
        if st.button("▶ Compile to Obsidian", type="primary", use_container_width=True):
            env = os.environ.copy()
            env["PYTHONPATH"] = str(BASE_DIR) + (os.pathsep + env.get("PYTHONPATH", ""))
            try:
                result = subprocess.run(
                    cmd_args,
                    capture_output=True, text=True, cwd=str(BASE_DIR), env=env, timeout=300
                )
                if result.returncode == 0:
                    st.success(f"Obsidian compilation complete ({phase}) ✅")
                else:
                    st.error(f"Failed: {result.stderr[-500:]}")
            except Exception as e:
                st.error(f"Error: {e}")

    elif export_tool == "SQLite → Obsidian Markdown (sql-to-md.py)":
        st.subheader("Export SQLite → Obsidian Markdown")
        dbs = _scan_dbs()
        db_choice = st.selectbox("Database", [""] + dbs, format_func=lambda p: Path(p).name if p else "— select —")
        if db_choice:
            tables = _inspect_tables(db_choice)
            table_choice = st.selectbox("Table", list(tables.keys()))
            output_dir = st.text_input("Output directory", value="obsidian_vault")
            if st.button("▶ Export to Markdown", type="primary", use_container_width=True):
                cmd = [
                    sys.executable,
                    str(BASE_DIR / "sql-to-md.py"),
                    "--db", db_choice,
                    "--table", table_choice,
                    "--output-dir", output_dir,
                ]
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(BASE_DIR), timeout=120)
                    if result.returncode == 0:
                        st.success("Export complete ✅")
                    else:
                        st.error(f"Failed: {result.stderr[-500:]}")
                except Exception as e:
                    st.error(f"Error: {e}")

    elif export_tool == "Markdown Slicer (md_slicer.py)":
        st.subheader("Slice Monolithic Markdown")
        md_file = st.text_input("Path to monolithic Markdown file")
        output_dir = st.text_input("Output directory", value="obsidian_vault/dialogue_split")
        if st.button("▶ Slice Markdown", type="primary", use_container_width=True):
            cmd = [sys.executable, str(BASE_DIR / "src" / "utils" / "md_slicer.py"), md_file, "--output-dir", output_dir]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(BASE_DIR), timeout=120)
                if result.returncode == 0:
                    st.success("Slicing complete ✅")
                else:
                    st.error(f"Failed: {result.stderr[-500:]}")
            except Exception as e:
                st.error(f"Error: {e}")

    else:
        st.subheader("TV Tropes → Metadata Archive")
        st.caption("Harvest TV Tropes data into the metadata archive.")
        if st.button("▶ Harvest Tropes", type="primary", use_container_width=True):
            env = os.environ.copy()
            env["PYTHONPATH"] = str(BASE_DIR) + (os.pathsep + env.get("PYTHONPATH", ""))
            try:
                result = subprocess.run(
                    [sys.executable, str(BASE_DIR / "src" / "scrapers" / "trope_scraper.py")],
                    capture_output=True, text=True, cwd=str(BASE_DIR), env=env, timeout=300
                )
                if result.returncode == 0:
                    st.success("Trope harvest complete ✅")
                else:
                    st.error(f"Failed: {result.stderr[-500:]}")
            except Exception as e:
                st.error(f"Error: {e}")
