# 🌌 Lore Matrix (V4)

[![CI](https://github.com/EmCargi/lore-matrix/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR-USERNAME/lore-matrix/actions/workflows/ci.yml)
![Python 3.11 | 3.12](https://img.shields.io/badge/python-3.11%20%7C%203.12-3776AB?logo=python&logoColor=white)
![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Lint: ruff](https://img.shields.io/badge/lint-ruff-D7FF64.svg)

**An offline-first, multimodal ETL pipeline, cognitive knowledge graph generator, and deterministic game-dialogue harvester.**

Lore Matrix is a data-engineering portfolio suite: it ingests unstructured sources — PDFs, web pages/ArchiveBox snapshots, RPG text exports, Manga OCR timelines, and images — normalizes them through strict Pydantic schemas, and persists them as relational rows (SQLite), vector embeddings (ChromaDB), and single-note repositories (Obsidian). It is built for **resilience (idempotent, schema-validated, retry-hardened), portability (provider-agnostic LLM adapter, path-agnostic resolution), and decoupling (central config, externalized prompts)**.

### ⚡ At a Glance

| Property | Detail |
| :--- | :--- |
| **Ingest** | PDF · web / ArchiveBox · Manga OCR · images · RPG game text · TV Tropes |
| **Validation** | Strict Pydantic v2 schemas · reasoning-tag & code-fence cleaning |
| **Persist** | SQLite (relational) · ChromaDB (vector) · Obsidian (notes) |
| **Resilience** | Idempotent writes · tenacity retries · provider-agnostic LLM adapter · deterministic parsers |
| **Quality** | `ruff` lint + `pytest` suite gated in CI (Python 3.11 / 3.12) |

```mermaid
graph TD
    A[Unstructured Sources: PDF, Web, Manga, Vision, Game] --> B[Extractors + LLM Adapters]
    B -->|Pydantic Validation| C[Clean Normalised JSON Chunks]
    C --> D[json_to_obsidian Committer / sql-loader / dual_commit]
    D --> E[Obsidian Vault / SQLite / ChromaDB]
```

---

## 🛠️ Systems Architecture

The pipeline follows a modular, decoupled ETL pattern — every stage is a standalone CLI script orchestrated from a master menu (`lore-matrix.py`), so each subsystem can run, test, and scale independently.

```mermaid
graph TD
    %% Inputs
    subgraph Hoppers[Input Hoppers]
        H_PDF[input_pdfs/ *.pdf]
        H_WEB[targets.txt URLs / ArchiveBox vault]
        H_GAME[input_game_text/ *.txt]
        H_IMG[input_images/ *.png *.jpg]
        H_MNG[input_manga_ocr/ *_ocr/*.json]
        H_TROPE[TV Tropes / web]
    end

    %% Gateway
    GW[ingest.py Gateway Router]

    %% Engines
    subgraph Engines[Extraction & Transformation]
        E_PDF[extract-pdf.py]
        E_WEB[extract-web.py]
        E_VIS[extract-vision.py]
        E_MNG[extract-manga.py]
        E_GAME[extract-game-text.py · deterministic]
        E_TAB[extract-tables.py · strict PDF→CSV]
        E_TROPE[src/scrapers/trope_scraper.py]
        E_META[src/transformers/meta_archivist.py]
        E_SLICE[src/utils/md_slicer.py]
    end

    subgraph Providers[LLM Adapters]
        P_OLLAMA[Ollama · default]
        P_GEMINI[Gemini]
        P_FEATH[Featherless]
    end

    subgraph Persist[Persistence]
        S_SQL[SQLite via sql-loader/dual_commit]
        S_CHROMA[ChromaDB vector vault]
        S_OBS[Obsidian vault]
    end

    H_PDF --> GW
    H_WEB --> GW
    H_MNG --> GW
    H_IMG --> GW
    H_GAME --> E_GAME

    GW --> E_PDF
    GW --> E_WEB
    GW --> E_VIS
    GW --> E_MNG

    E_PDF --> Providers
    E_WEB --> Providers
    E_VIS --> Providers
    E_MNG --> Providers

    E_GAME --> S_SQL
    E_GAME --> S_CHROMA
    E_TROPE --> E_META --> S_CHROMA
    S_SQL --> E_SLICE --> S_OBS
```

> **Note:** every box is a runnable script; the menu is a thin orchestrator that spawns them as subprocesses.

---

## 📦 What's in V4

V4 consolidates the suite and makes it GitHub-ready as a portfolio artifact:

1. **Packaging & continuous integration** — `pyproject.toml` (dynamic deps, lint/test config), MIT license, and a GitHub Actions workflow (`ruff` lint + `pytest`) on Python 3.11 / 3.12.
2. **One general-purpose SQL loader** — the two overlapping CSV→SQLite tools were merged into `sql-loader.py`: a non-destructive `--if-exists fail|replace|append` default and an optional `--key` idempotent UPSERT (`ON CONFLICT DO UPDATE`) with an enforced unique index. The domain-specific POC was retired.
3. **Reasoning-output correctness** — every extractor now strips model `thinking` tags via `core.utils.clean_reasoning_response()` before Pydantic validation, fixing JSON-in-`response` validation crashes.
4. **Uniform serialization** — all producers emit canonical aliased keys (`by_alias=True`), with a backward-compatible fallback in the Obsidian compiler.
5. **Non-destructive defaults** — the PDF extractor archives only when chunks are actually saved; destructive-db strategy defaults to `fail`; every critical `except` path is annotated with intent.

> The design history of the loader merge is captured in the repo `CHANGELOG.md`.

---

## 🚀 Installation & Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# optional but recommended, run from repo root:
ruff check .
python -m pytest
```

### External Dependencies
- **Ollama** — local reasoning models (`deepseek-r1:7b`, `qwen2.5-coder`), the default `local` provider.
- **EasyOCR** — vision engine for the multimodal harvester.
- **ChromaDB** — vector store for trope-RAG and dual-commit subsystems.

### Configuration (`config/settings.py`)
Everything central lives in one place — engines, prompt paths, and the pipeline's directory layout. Key settings:

| Setting | Purpose |
| :--- | :--- |
| `DEFAULT_ENGINE` | Provider engine: `local` · `gemini` · `featherless` |
| `ACTIVE_VISION_MODEL` | Default local model name (`deepseek-r1:7b`) |
| `IS_REASONING_MODEL` / `REASONING_TAG_NAME` | Auto-strip model `thinking` blocks before validation |
| `OUTPUT_CHUNKS_DIR` | Central JSON staging dir (`output/json_staging`) |
| `ARCHIVEBOX_VAULT_DIR` | Local ArchiveBox snapshot root for offline web ingest (env-overridable) |
| `EXTRACTOR_SYSTEM_PROMPT` | Loaded from `config/extractor-prompt.md` |

### LLM Providers (`core/engines.py`)
A uniform factory exposing `generate(system_prompt, user_content, response_format=None)` over three interchangeable backends, all enforcing Pydantic structured output:
- **`LocalProvider`** — Ollama (default).
- **`GeminiProvider`** — Google Gemini.
- **`FeatherlessProvider`** — OpenAI-compatible.

---

## 🧭 Interactive CLI (`lore-matrix.py`)

```bash
./venv/bin/python lore-matrix.py
```

| Option | Action |
| :--- | :--- |
| 1 | Run **Unified Ingestor** (`ingest.py`) |
| 2 | Compile JSON → Obsidian notes (`json_to_obsidian.py`) |
| 3 | **Data Visualizer** wizard |
| 4 | **SQL Data Loader** wizard (`sql-loader.py`) |
| 5 | Extract Data Tables — strict PDF→CSV (`extract-tables.py`) |
| 6 | Profile & Sanitize raw datasets (`data-profile.py`) |
| 7 | Database Backup & Rollback manager (`db-migrate.py`) |
| 8 | Export SQLite queries → Obsidian Markdown (`sql-to-md.py`) |
| 9 | Harvest narrative tropes (`trope_scraper.py`) |
| 10 | Vault & Query Tropes submenu (`vector_vault.py`) |
| 11 | **Advanced: Run Individual Ingestors** submenu |
| 12 | Ingest a frozen ArchiveBox asset (by Timestamp ID) |
| 13 | Slice a monolithic Markdown file (`md_slicer.py`) |
| 14 | Exit |

> Run any script standalone too — e.g. `./venv/bin/python sql-loader.py --input data.csv --db library.db --table characters --key id`.

---

## 🗺️ Module Cross-Reference

### Root scripts
| Script | Role |
| :--- | :--- |
| `lore-matrix.py` | Master CLI menu (orchestrator) |
| `ingest.py` | Unified gateway router for the main harvesters |
| `extract-pdf.py` · `extract-web.py` · `extract-vision.py` · `extract-manga.py` | Multimodal harvesters (PDF / web+ArchiveBox / images / manga OCR) |
| `extract-game-text.py` | Deterministic RPG dialogue parser |
| `extract-tables.py` | Strict PDF→CSV table extractor |
| `sql-loader.py` | Generic CSV/XLSX → SQLite loader (strategy-driven) |
| `sql-to-md.py` | SQLite → Obsidian Markdown exporter |
| `data-profile.py` | Dataset health audit / sanitization gate |
| `db-migrate.py` | SQLite snapshot & rollback manager |
| `json-to-lorebook.py` · `json-to-md.py` · `import-json.py` · `md-to-obsidian.py` | SillyTavern / Obsidian compilers & importers |

### `core/`, `src/`
| Path | Role |
| :--- | :--- |
| `core/engines.py` | Provider abstraction (local / gemini / featherless) |
| `core/utils.py` | Reasoning-tag stripper + `info()/error()` & Pydantic schemas |
| `core/image_processing.py` | OCR enhancement (CLAHE, deskew, binarize) |
| `core/visualize-data.py` | Data visualizer engine |
| `src/scrapers/trope_scraper.py` | TV Tropes harvester |
| `src/transformers/meta_archivist.py` · `json_to_obsidian.py` | Trope ETL & Obsidian compiler |
| `src/storage/dual_commit.py` | Game dialogue → SQLite + ChromaDB dual-commit |
| `src/storage/vector_vault.py` | ChromaDB trope vault & query |
| `src/utils/md_slicer.py` | Monolithic MD → frontmatter-inheriting card slicer |

---

## 🧪 Testing & CI

The `pytest` suite (`testpaths = tests`) covers the deterministic subsystems:

```bash
venv/bin/ruff check .   # lint
venv/bin/python -m pytest   # tests
```

A GitHub Actions workflow (`.github/workflows/ci.yml`) runs **ruff lint** and **pytest** on every push/PR against Python 3.11 and 3.12.

---

## 🧂 Quality Philosophy

- **Idempotency everywhere**: hash caches, `ON CONFLICT DO UPDATE` upserts, unique-constraint migrations, atomic writes (`tempfile` + `os.replace`).
- **Never destroy data** — merge into the source vaults are forbidden; artifacts are regenerable; destructive ops are snapshot-backed.
- **Humans and machines both** — rich console feedback for operators, and structured Pydantic models for downstream tools.

---

## 📄 License

[MIT](LICENSE)