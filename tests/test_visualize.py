# Tests for the extended visualization engine.

import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

SCRIPT_PATH = PROJECT_ROOT / "core" / "visualize-data.py"


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def sample_narrative_csv(tmp_path):
    """A small CSV with NME fingerprint data for two stories."""
    csv = tmp_path / "narratives.csv"
    csv.write_text(
        "name,agency,reliability,convergence,divergence\n"
        "Ciel,10.0,2.0,5.3,2.6\n"
        "Sora,4.5,10.0,5.2,2.7\n"
        "Linear,5.0,8.0,3.0,1.5\n"
        "Branching,6.0,7.0,8.0,7.5\n",
        encoding="utf-8",
    )
    return csv


@pytest.fixture
def sample_graph_csv(tmp_path):
    """A small CSV with node-edge data for network charts."""
    csv = tmp_path / "graph.csv"
    csv.write_text(
        "source,target,weight\n"
        "A,B,1.0\n"
        "B,C,0.8\n"
        "C,D,0.9\n"
        "A,D,0.5\n"
        "D,E,0.7\n",
        encoding="utf-8",
    )
    return csv


@pytest.fixture
def sample_3d_csv(tmp_path):
    """A small CSV with 3D coordinates and a sequence column."""
    csv = tmp_path / "points3d.csv"
    csv.write_text(
        "label,x,y,z,sequence\n"
        "A,1.0,2.0,3.0,1\n"
        "B,4.0,5.0,6.0,2\n"
        "C,7.0,8.0,9.0,3\n"
        "D,2.0,3.0,4.0,4\n",
        encoding="utf-8",
    )
    return csv


# ── Smoke Tests (subprocess) ──────────────────────────────


def test_visualizer_help():
    """Script returns 0 on --help."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        capture_output=True,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0


def test_narrative_chart(sample_narrative_csv):
    """Narrative fingerprint chart generates without error."""
    result = subprocess.run(
        [
            sys.executable, str(SCRIPT_PATH),
            "--input", str(sample_narrative_csv),
            "--chart-type", "narrative",
            "--x-col", "name",
            "--y-col", "agency,reliability,convergence,divergence",
            "--output", "test_narrative.png",
        ],
        capture_output=True,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0, result.stderr.decode()
    out = PROJECT_ROOT / "processed_data" / "test_narrative.png"
    assert out.exists()
    out.unlink(missing_ok=True)


def test_scatter3d_chart(sample_3d_csv):
    """3D scatter chart generates without error."""
    result = subprocess.run(
        [
            sys.executable, str(SCRIPT_PATH),
            "--input", str(sample_3d_csv),
            "--chart-type", "scatter3d",
            "--x-col", "label",
            "--y-col", "x,y,z",
            "--output", "test_scatter3d.png",
        ],
        capture_output=True,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0, result.stderr.decode()
    out = PROJECT_ROOT / "processed_data" / "test_scatter3d.png"
    assert out.exists()
    out.unlink(missing_ok=True)


def test_scatter3d_with_color(sample_3d_csv):
    """3D scatter chart with 4th column as color."""
    result = subprocess.run(
        [
            sys.executable, str(SCRIPT_PATH),
            "--input", str(sample_3d_csv),
            "--chart-type", "scatter3d",
            "--x-col", "label",
            "--y-col", "x,y,z,sequence",
            "--output", "test_scatter3d_color.png",
        ],
        capture_output=True,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0, result.stderr.decode()
    out = PROJECT_ROOT / "processed_data" / "test_scatter3d_color.png"
    assert out.exists()
    out.unlink(missing_ok=True)


def test_animate3d_chart(sample_3d_csv):
    """3D animation generates (or falls back to static)."""
    result = subprocess.run(
        [
            sys.executable, str(SCRIPT_PATH),
            "--input", str(sample_3d_csv),
            "--chart-type", "animate3d",
            "--x-col", "label",
            "--y-col", "x,y,z,sequence",
            "--output", "test_animate3d.gif",
        ],
        capture_output=True,
        cwd=str(PROJECT_ROOT),
        timeout=30,
    )
    assert result.returncode == 0, result.stderr.decode()
    out_gif = PROJECT_ROOT / "processed_data" / "test_animate3d.gif"
    out_png = PROJECT_ROOT / "processed_data" / "test_animate3d.png"
    assert out_gif.exists() or out_png.exists()
    out_gif.unlink(missing_ok=True)
    out_png.unlink(missing_ok=True)


def test_network_chart(sample_graph_csv):
    """Network graph generates without error."""
    result = subprocess.run(
        [
            sys.executable, str(SCRIPT_PATH),
            "--input", str(sample_graph_csv),
            "--chart-type", "network",
            "--x-col", "source",
            "--y-col", "source,target",
            "--output", "test_network.png",
            "--title", "Test Graph",
        ],
        capture_output=True,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0, result.stderr.decode()
    out = PROJECT_ROOT / "processed_data" / "test_network.png"
    assert out.exists()
    out.unlink(missing_ok=True)


def test_missing_column_error(sample_narrative_csv):
    """Script exits non-zero when column doesn't exist."""
    result = subprocess.run(
        [
            sys.executable, str(SCRIPT_PATH),
            "--input", str(sample_narrative_csv),
            "--chart-type", "narrative",
            "--x-col", "nonexistent",
            "--y-col", "agency",
            "--output", "test_error.png",
        ],
        capture_output=True,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode != 0


def test_scatter3d_needs_3_columns():
    """scatter3d requires at least 3 Y columns."""
    csv_path = Path("/tmp/test_2col.csv")
    csv_path.write_text("label,x,y\nA,1,2\nB,3,4\n", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable, str(SCRIPT_PATH),
            "--input", str(csv_path),
            "--chart-type", "scatter3d",
            "--x-col", "label",
            "--y-col", "x,y",
            "--output", "test_error.png",
        ],
        capture_output=True,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode != 0
    csv_path.unlink(missing_ok=True)


def test_interactive_headless_fallback(sample_3d_csv):
    """--chart-type interactive under Agg falls back to GIF export, no crash."""
    env = dict(os.environ, MPLBACKEND="Agg")
    result = subprocess.run(
        [
            sys.executable, str(SCRIPT_PATH),
            "--input", str(sample_3d_csv),
            "--chart-type", "interactive",
            "--x-col", "label",
            "--y-col", "x,y,z,sequence",
            "--output", "test_interactive.gif",
            "--trail-length", "4",
            "--fps", "15",
        ],
        capture_output=True,
        cwd=str(PROJECT_ROOT),
        env=env,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr.decode()
    out = PROJECT_ROOT / "processed_data" / "test_interactive.gif"
    assert out.exists()
    out.unlink(missing_ok=True)


def test_interactive_headless_no_output_fails(sample_3d_csv):
    """Interactive without --output must not hang headless — argparse rejects it."""
    env = dict(os.environ, MPLBACKEND="Agg")
    result = subprocess.run(
        [
            sys.executable, str(SCRIPT_PATH),
            "--input", str(sample_3d_csv),
            "--chart-type", "interactive",
            "--x-col", "label",
            "--y-col", "x,y,z,sequence",
        ],
        capture_output=True,
        cwd=str(PROJECT_ROOT),
        env=env,
    )
    assert result.returncode != 0


def test_interactive_key_stepping(sample_3d_csv):
    """Arrow-key handler clamps the frame index within [0, frames]."""
    import argparse
    import importlib.util

    spec = importlib.util.spec_from_file_location("visualize_data", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    df = pd.read_csv(sample_3d_csv)
    args = argparse.Namespace(
        trail_length=4, fps=15, title=None, palette=None, output=None, auto_play=False
    )
    ctrl = mod._plot_interactive3d(df, "label", ["x", "y", "z", "sequence"], args)

    frames = ctrl["frames"]
    try:
        assert frames >= 1
        for _ in range(frames * 3):
            ctrl["on_key"](argparse.Namespace(key="right"))
        assert ctrl["state"]["frame"] == frames

        ctrl["on_key"](argparse.Namespace(key="left"))
        assert ctrl["state"]["frame"] == frames - 1

        for _ in range(frames * 3):
            ctrl["on_key"](argparse.Namespace(key="left"))
        assert ctrl["state"]["frame"] == 0

        ctrl["on_key"](argparse.Namespace(key="up"))
        assert ctrl["state"]["frame"] == 0
    finally:
        mod.plt.close(ctrl["fig"])
