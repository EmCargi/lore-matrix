# Changelog

All notable changes to the **Lore Matrix** are documented here, oriented to the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) style.

The repo is currently at a single squashed **V4** save-state (V3 → V4 release notes below).

---

## [4.0.0] — 2026-08-06

### Executive summary

V4 turns the Lore Matrix from a working-but-scrappy internal suite into a **GitHub-ready,
hardened, consolidated data-engineering portfolio piece**. It merges two overlapping CSV→SQLite
readers into one hardened general-purpose loader, repairs reasoning-model output across every
multimodal extractor, makes serialization uniform and genuinely non-destructive, and wraps the whole
thing in lint + test gates that run in CI.

### Added

- **`pyproject.toml`** — modern PEP 621 build metadata: dynamic dependencies (from
  `requirements.txt`), `ruff` + `pytest` config consolidated here, project version **`4.0.0`**.
- **`LICENSE`** — MIT.
- **Continuous integration** — `.github/workflows/ci.yml` runs `ruff check .` + `pytest` on
  **Python 3.11 / 3.12** for every push/PR.
- **Hardenings in `sql-loader.py`** — generic CSV/XLSX → SQLite:
  - `--if-exists fail|replace|append` — non-destructive strategy, **`fail` is the new default**
    (was always `replace`).
  - `--key COLUMN` — optional idempotent UPSERT (`INSERT … ON CONFLICT DO UPDATE`) backed by a
    guaranteed unique index, so re-runs update instead of duplicating.
  - Column sanitization now also **deduplicates** headers (dupe headers no longer crash SQLite).
  - Atomic transaction + summary ledger.
- **New tests** — `tests/test_sql_loader.py` (fail/append/replace + idempotent keyed upsert +
  column sanitize), `tests/test_reasoning.py`, `tests/test_narrative_uniform.py`.

### Changed

- **Loader consolidation** — the two overlapping CSV→SQLite tools are now one:
  `templates/sql_loader.py` was promoted to the root `sql-loader.py`, and the domain-specific
  POC `load-to-sql.py` was retired.
- **Master menu (`lore-matrix.py`)** — removed the old "Load CSVs via `load-to-sql.py`" option 6;
  renumbered the menu **7–15 → 6–14**; the SQL Data Loader wizard (option 4) now passes
  `--if-exists replace` to preserve its prior behavior.
- **Uniform serialization** — every producer now dumps Pydantic models with `by_alias=True` for
  canonical `"Scene Description"` keys; `json_to_obsidian.py` keeps a backward-compatible fallback.
- **`config/settings.py`** — `ARCHIVEBOX_VAULT_DIR` is now environment-overridable (fallback
  `BASE_DIR / archivebox`), removing a hardcoded legacy path → true two-node portability.
- **README** — rewritten for V4 (`README.md`, renamed from `Lore-matrix-README.md`): accurate V4
  tool map, 14-option menu, architecture diagram, and Testing/CI section.

### Fixed

- **Reasoning-model output** — all extractors now run `core/utils.clean_reasoning_response()` before
  `model_validate_json()`, fixing crashes caused by JSON wrapped in ` response` thinking blocks
  (`extract-pdf.py`, `extract-web.py`, `extract-vision.py`, `extract-manga.py`).
- **Archive-after-parse** — the PDF extractor only archives processed sources when chunks were actually
  saved (`saved_chunks > 0`), so empty files are no longer archived.

### Hardening & repo hygiene

- **`ruff check .`** is now a CI gate; critical bare-`except` resilience/fallback paths are annotated
  with `# noqa: BLE001` and intent comments (deliberate — not blanket suppression).
- **`.gitignore`** expanded: `.ruff_cache/`, `.eggs/`, `*.egg-info/`, `.coverage`, `htmlcov/`,
  `*.bak`, Obsidian session-state `**/.obsidian/workspace.json`, and LibreOffice `~lock*` files.
- Untracked Obsidian `workspace.json` session state (3 files) walked back out of git.
- Removed redundant root shims and dead code: `visualize-data.py` (→ `core/visualize-data.py`) and
  `test_pandas.py`.
- Obsolete `pytest.ini` removed (config moved to `pyproject.toml`).

### Removed

- `load-to-sql.py` (domain-specific POC superseded by `sql-loader.py`).
- `templates/sql_loader.py` (promoted to root `sql-loader.py`).
- `tests/test_mappings.py` (tested the removed `load-to-sql` module).
- `visualize-data.py` (root shim), `test_pandas.py` (scratch), `pytest.ini`.

### Tests

- **26 passing** across the deterministic subsystems (game-text, dual-commit, slicer, archive,
  reasoning, narrative-uniformity, sql-loader).
- `ruff check .` clean.

### Breaking / migration notes

- The specialized, mapping-driven ETL (`load-to-sql.py` + its mappings file) and the one-off
  comparison tool were domain-specific proof-of-concept add-ons; they are **gone**, fully orphaned
  and removed. Use the generic `sql-loader.py` for any future CSV→SQLite work.
- `sql-loader.py` defaults to **`--if-exists fail`** (non-destructive) — a CLI call that used to
  silently replace an existing table will now refuse; pass `--if-exists replace` (or `--key`) intentionally.

---

## [V3] — 2026-08-06 (baseline)

The single squashed V4 commit re-settles the previously-committed V3 source, config, docs, and
tests. V3 featured the ArchiveBox offline ingest, the deterministic RPG game-dialogue harvester
`extract-game-text.py`, the dual-commit loader, and the Markdown slicer. Those capabilities are
preserved (and where needed, hardened) in V4; see the `[4.0.0]` entry above for what changed on top.

---

## Unreleased

- Swap `YOUR-USERNAME` in `README.md` badge to the real GitHub handle once the repo is final.