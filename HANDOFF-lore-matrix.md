---
project: lore-matrix
date: 2026-09-14
status: complete
test_count: 111
git: local-only
extractors: 9 (web, head, ocean, narrative, launchpad, tables, pdf, vision, monsters)
browser: browser_lore_matrix.py (Streamlit dashboard)
visualization: bar/line/box/scatter3d/animate3d/interactive/network + MIDI JSON
obsidian_export: --phase raw/compile/one-shot with pure no-LLM raw vault builder
json_uploader: streamlit file_uploader for .json / .lorebook.json → input_json/ hopper
vision: easyocr local + L3-8B-Stheno (big rig) synthesis; --vision-model moondream:latest multimodal option
manga_db: manga_db_loader.py — per-series SQLite (Chronos disc layout) + Chroma manga_vault (nomic-embed-text) dual-commit; 86 Mingyun entries loaded
---
# Lore Matrix — Handoff Document

## Current State (2026-09-05)

Lore Matrix V4 is the **central ETL and visualization hub** of the workspace — the ingestion layer that feeds sibling projects (VSPE, NME, HEAD, Choir Cloud). It ingests unstructured sources (PDFs, web pages, ArchiveBox snapshots, manga OCR, images, RPG game text, TV Tropes), normalizes them through strict Pydantic schemas, and persists to SQLite, ChromaDB, and Obsidian. 103 tests all green, `ruff` clean, CI-gated on GitHub Actions (Python 3.11 / 3.12). A Streamlit browser dashboard (`browser_lore_matrix.py`) replaces the CLI menu for interactive use — ingest, visualize, query databases, and export from the browser.

**Recent work (2026-09-02 through 2026-09-05):**
- **Unified Obsidian exporter** — collapsed 3 overlapping exporters into one with `--phase raw/compile/one-shot`; pure `core/raw_vault_builder.py` (zero LLM imports), lazy `ACTIVE_AI` in config.settings; legacy pair deleted. Also fixed a silent alias-drop bug in `map_sillytavern_entry`.
- **Interactive visualizer** — `--chart-type interactive` with matplotlib Slider + Button (manual scrub, fading trail, auto-play, arrow keys); headless falls back to GIF export. `--output` respects absolute/relative paths (bare filenames still go to `processed_data/`).
- **Pipeline validation** — tested end-to-end on 3 real SillyTavern lorebooks (JJK, 1850's Slang, Cyberpunk 2077 — 150+ notes, 0 failures). Fixed subfolder naming (`General_Rules` → `Converted JSON`), YAML validator rejection (quoted arrays), and `.title()` acronym mangling.

**Project complete 2026-09-14** — V4 shipped, validated, and polished; the repo is in maintenance. Only foreseeable work is new extractors or prompt variants on demand.

## Lineage

*Chronological trail of the proposals and journal entries that built this project — lets a design model trace "how did we get here" without narration.*

| Date | Proposal | Journal | What Shipped |
|---|---|---|---|
| 2026-06-28 | — | `2026-06-28-sqlite-pipeline-integration.md`, `2026-06-28-sql-pivot.md` | Centralized SQLite pipeline, local-offline pivot away from BigQuery (predates proposal template) |
| 2026-07-02 | — | `2026-07-02-hopper-output-sorting.md`, `2026-07-02-schema-harmonization.md`, `2026-07-02-vision-harvester-integration.md` | Hierarchical output routing, Pydantic schema enforcement, multimodal Vision Harvester (predates proposal template) |
| 2026-07-09 | — | `2026-07-09-directory-naming-refactor.md`, `2026-07-09-workflow-improvement-tracking.md` | Generic staging dir + centralized config, parallel ThreadPoolExecutor + hash-idempotency (predates proposal template) |
| 2026-08-03 | — | `2026-08-03-git-local-only-setup.md`, `2026-08-03-known-friction-fixes.md` | Local-only git repo, canonical concurrency module, curated requirements.txt (predates proposal template) |
| 2026-08-06 | — | `2026-08-06-lore-matrix-v4.md` | V4 — GitHub-ready portfolio piece, generic hardened SQL loader, CI passing (predates proposal template) |
| 2026-08-10 | `2026-08-10-choir-cloud-lore-matrix-integration.md` | `2026-08-10-choir-cloud-end-to-end.md` | MidiDensityLog JSON support added to visualize-data.py (Choir Cloud sibling integration) |
| 2026-08-11 | `2026-08-11-vspe-ocean-profiler.md` | `2026-08-11-vspe-complete-pipeline.md` | Lore Matrix serves as ingestion hub for VSPE's OCEAN profiler |
| 2026-08-14 | `2026-08-14-head-cli-meso-extractor.md` | `2026-08-14-head-cli-meso-extractor-shipped.md` | **extract-head.py** — cold institutional meso-slider scorer (H.E.A.D. 4-slider taxonomy) via big-rig gemma4-v2, emits head-cli-compatible fixture YAML |
| 2026-08-15 | `digital-dm-project/shota-monsters-digital-dm/besm/world-lore/pipeline-scope.md` | `2026-08-15-shota-monsters-pipeline-verification.md`, `2026-08-15-master-monster-db-import.md`, `2026-08-15-master-db-catalog-import.md` | **extract-monsters.py** — Weebly monster stat block extractor (103 SxM1 monsters, 0 failures). **monsters-to-md.py** — JSON → Obsidian-ready markdown by stratum. New `MonsterProfile` + `MonsterAbility` Pydantic models + `monster-extractor-prompt.md`. New sibling: digital-dm-project |
| 2026-08-15 | — | `2026-08-15-archivebox-preservation-layer.md` | **ArchiveBox remote read path** — `extract-web.py` reads the big-rig vault over Tailscale via `dev/core/archivebox.py` (local vault first, remote fallback, `output.html` ladder). `ARCHIVEBOX_URL` added to config |
| 2026-09-01 | — | — | **browser_lore_matrix.py** — Streamlit browser dashboard (7 tabs: Dashboard, Visualizer, SQL Loader, Database, Ingest, JSON Staging, Export). Follows `browser_aeiou.py` / `browser_nme.py` / `browser_choir_cloud.py` pattern. 91 tests, `ruff` clean. Streamlit + plotly added to requirements. |
| 2026-09-02 | `2026-09-01-lore-matrix-interactive-scrubbing.md` | `2026-09-02-lore-matrix-interactive-scrubbing.md` | **Interactive scrubbing** in `core/visualize-data.py` — new `--chart-type interactive` (matplotlib Slider + Button): manual frame scrub, fading trail, auto-play, arrow-key stepping, headless fallback to GIF. Counterplan `2026-09-02-lore-matrix-interactive-scrubbing.md`. 94 tests. |
| 2026-09-02 | `2026-09-02-lore-matrix-exporter-consolidation.md` | `2026-09-02-lore-matrix-exporter-consolidation.md` | **Unified Obsidian exporter** — pure `core/raw_vault_builder.py` (no-LLM JSON→raw unwrap, SillyTavern world-info preserved), `json_to_obsidian.py --phase raw/compile/one-shot` (lazy `ACTIVE_AI` in config.settings), legacy `json-to-md.py` + `md-to-obsidian.py` deleted. Counterplan `2026-09-02-lore-matrix-exporter-consolidation.md`. 103 tests. |
| 2026-09-05 | — | `2026-09-05-lore-matrix-pipeline-validation.md` | **Pipeline validation** on 3 real lorebooks (JJK, 1850's Slang, Cyberpunk 2077 — 150+ notes, 0 failures). Fixed subfolder naming (`General_Rules` → `Converted JSON`), YAML validator rejection (quoted arrays), `.title()` acronym mangling. Also fixed `--output` path to respect absolute/relative paths instead of forcing `processed_data/`. |
| 2026-09-11 | — | — | **Repo hygiene** — local data + IDE state untracked (`.obsidian/`, `config.json`, completion/targets lists); `.gitignore` extended. Runtime artifacts stay on the thin client, never ship. (Housekeeping — no proposal) |
| 2026-09-14 | — | — | **JSON uploader** — added `st.file_uploader` to the Streamlit Ingest tab's Unified Ingestor mode. `.json` / `.lorebook.json` files drop directly into `input_json/` hopper before ingestion. Added `INPUT_JSON_DIR` to `config/settings.py`. |
| 2026-09-14 | — | — | **PDF uploader** — added `st.file_uploader` for `.pdf` files to the same Unified Ingestor mode. PDFs stage in `input_pdfs/` before extraction via `extract-pdf.py`. Added `INPUT_PDFS_DIR` to the browser app imports. |
| 2026-09-14 | — | — | **Image uploader** — added `st.file_uploader` for `.png`/`.jpg`/`.jpeg`/`.webp`/`.bmp` to the same Unified Ingestor mode. Images stage in `input_images/` before vision extraction via `extract-vision.py`. Added `INPUT_IMAGES_DIR` to the browser app imports. |
| 2026-09-14 | — | — | **Vision direction toggle** — `ingest.py` now accepts `--direction LTR/RTL` (threaded through `classify_and_route` + `run_hopper_scan` into `extract-vision.py`). Streamlit Ingest tab added a "Vision reading direction" selectbox that passes it through. LTR default, RTL for manga. |
| 2026-09-14 | — | — | **Big-rig vision + synthesis wired** — EasyOCR (`easyocr` + `opencv-python-headless`) installed locally for text detection; `LocalProvider` default big-rig synthesis switched to `L3-8B-Stheno` (fast clean structured JSON) via `core/engines.py`. Added `generate_vision()` to `LocalProvider` + `--vision-model` flag to `extract-vision.py` (sends page image to a vision LLM, bypassing EasyOCR; default `moondream:latest`, overridable via `OLLAMA_VISION_MODEL`). Validated end-to-end on the 12-page Mingyun comic: EasyOCR+Stheno = 12/12 clean; moondream direct = reliable to run but degenerate JSON (deferred). |
| 2026-09-14 | `changelog/proposals/2026-09-14-manga-narrative-db-confirmed.md` | — | **Manga narrative DB shipped** — full triangulation (proposal → counter-plan → synthesis; supersedes the Mokuro-path draft). `extract-vision.py --series <name>` stages chunks under `output/json_staging/<slug>/`; `manga_db_loader.py` validates + persists per-series SQLite (Chronos disc layout `manga-data/<series_id>/data/<series_id>.db`, PK `(series_id, page, entry_index)`, derived `entry_id = page*1000 + entry_index`) and dual-commits a `manga_vault` Chroma collection via `nomic-embed-text` (both LAN nodes). `core/utils.slugify()` canonicalized; `vector_vault.get_collection()` gained an optional embedding_function. 6 new tests → **111 total**. Live load: Mingyun Comic 12 pages / 86 entries / 86 vectors, idempotent re-run. persona-etl handoff ready. |
| 2026-09-14 | — | — | **Image uploader** — added `st.file_uploader` for `.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp` files. Images stage in `input_images/` before vision extraction via `extract-vision.py`. |

## Architecture Overview

```
Input Hoppers (PDFs / Web / Images / Manga OCR / Game Text / JSON / Tropes)
    │
    ▼
ingest.py ── Polymorphic Gateway Router (auto-detects input type)
    │
    ├──▶ extract-pdf.py          ── pdfplumber + LLM → LorebookLog
    ├──▶ extract-web.py          ── BeautifulSoup/Jina + LLM → LorebookLog
    ├──▶ extract-vision.py       ── EasyOCR + Union-Find + LLM → NarrativeLog
    ├──▶ extract-manga.py        ── Mokuro OCR parser → NarrativeLog
    ├──▶ extract-game-text.py    ── Deterministic RPG parser (no LLM)
    ├──▶ extract-tables.py       ── Strict pdfplumber → CSV (no LLM)
    ├──▶ extract-narrative.py    ── Prose → LLM → NarrativeStructure (NME graph)
    ├──▶ extract-ocean.py        ── Text → LLM → OceanProfile (VSPE feeder)
    ├──▶ extract-launchpad.py    ── Institution text → LLM → LaunchpadFeatures (VSPE feeder)
    ├──▶ import-json.py          ── SillyTavern lorebook importer
    └──▶ trope_scraper.py        ── TV Tropes harvester → ChromaDB
    │
    ▼
output/json_staging/  ── Hierarchical, category-mirrored staging
    │
    ├──▶ json_to_obsidian.py     ── JSON → Obsidian (--phase raw no-LLM / compile / one-shot)
    ├──▶ json-to-lorebook.py     ── JSON → SillyTavern lorebook (per-universe)
    ├──▶ sql-loader.py           ── CSV/XLSX → SQLite (idempotent upsert)
    ├──▶ dual_commit.py          ── Game dialogue → SQLite + ChromaDB
    └──└▶ sql-to-md.py           ── SQLite → Obsidian Markdown
    │
    ▼
Persistence: Obsidian vault · SQLite · ChromaDB
    │
    └──▶ core/visualize-data.py ── bar/line/box/scatter3d/animate3d/interactive/network charts
```

## File Map

| File | Purpose | Lines | Tests |
|---|---|---|---|
| `browser_lore_matrix.py` | Streamlit browser dashboard (ingest, visualize, query, export) | ~564 | — |
| `lore-matrix.py` | Master CLI menu (15 options, subprocess orchestrator) | ~482 | — |
| `ingest.py` | Polymorphic gateway router (auto-detects input type, routes to extractor) | ~273 | — |
| `extract-pdf.py` | PDF harvester (pdfplumber + LLM → LorebookLog) | ~157 | — |
| `extract-web.py` | Web/ArchiveBox harvester (BeautifulSoup + Jina fallback + LLM). ArchiveBox path reads local vault first, then the big-rig dashboard over Tailscale via `dev/core/archivebox.py` (output.html fallback) | ~298 | 2 |
| `extract-vision.py` | Multimodal image harvester (EasyOCR + Union-Find + LLM; `--series` staging + `--vision-model` multimodal option) | ~475 | — |
| `manga_db_loader.py` | Per-series manga DB loader (NarrativeLog → SQLite Chronos-disc layout + Chroma `manga_vault` dual-commit) | ~200 | 6 |
| `extract-manga.py` | Manga OCR harvester (Mokuro parser) | ~250 | — |
| `extract-game-text.py` | Deterministic RPG dialogue parser (no LLM, no AI) | ~219 | 4 |
| `extract-tables.py` | Strict PDF→CSV table extractor (pdfplumber, no LLM) | ~106 | — |
| `extract-narrative.py` | Narrative structure extractor (prose → NME graph via LLM) | ~358 | 22 |
| `extract-ocean.py` | OCEAN personality profiler (text → LLM → OceanProfile) | ~113 | — |
| `extract-launchpad.py` | Institutional launchpad scorer (text → LLM → LaunchpadFeatures) | ~112 | — |
| `extract-head.py` | Meso-tier institution scorer (text → LLM → MesoTierLLM → head-cli fixture YAML), --schein-only, --overwrite | ~200 | — |
| `import-json.py` | SillyTavern lorebook JSON importer | ~184 | — |
| `json-to-lorebook.py` | Per-universe lorebook compiler | ~120 | — |
| `jsonl-to-prose.py` | JSONL → prose converter | ~138 | — |
| `sql-loader.py` | Generic CSV/XLSX → SQLite (strategy-driven, idempotent upsert) | ~176 | 8 |
| `sql-to-md.py` | SQLite → Obsidian Markdown exporter | ~269 | — |
| `data-profile.py` | Dataset health audit / sanitization gate | ~179 | — |
| `db-migrate.py` | SQLite snapshot & rollback manager | ~171 | — |
| **`core/`** | | | |
| `core/engines.py` | Provider abstraction (LocalProvider / GeminiProvider / FeatherlessProvider) | ~91 | — |
| `core/utils.py` | Schemas (LorebookLog, NarrativeLog), reasoning-tag stripper, chunker, retry | ~228 | 4 |
| `core/concurrency.py` | Canonical RateLimiter + make_safe_print (thread-safe) | ~41 | — |
| `core/image_processing.py` | OCR enhancement (CLAHE, deskew, binarize, bilateral denoise) | ~85 | — |
| `core/visualize-data.py` | Chart engine (bar/line/box/scatter3d/animate3d/interactive/network + MIDI JSON) | ~749 | 11 |
| `core/raw_vault_builder.py` | **Pure JSON → raw markdown unwrapper (no-LLM by construction — no provider imports)** | ~200 | 5 |
| `core/narrative_types.py` | NME-compatible Pydantic models (StoryNode, StoryEdge, Perspective, etc.) | ~53 | 4 |
| `core/ocean_types.py` | OceanProfile Pydantic model (Big Five percentiles) | ~49 | 6 |
| `core/ocean_scalpel.py` | JSON extraction scalpel (defends against reasoning-model noise) | ~63 | 7 |
| `core/launchpad_types.py` | LaunchpadFeatures Pydantic model (institutional features) | ~33 | 5 |
| `core/meso_types.py` | MesoTierLLM + ScheinAudit + ScheinOnly Pydantic models (H.E.A.D. 4-slider) | ~74 | 9 |
| **`src/`** | | | |
| `src/transformers/json_to_obsidian.py` | Obsidian compiler — `--phase raw` (no-LLM) / `--phase compile` / one-shot (hash-cache, parallel, wiki-link, YAML validation) | ~590 | 5 |
| `src/transformers/meta_archivist.py` | Trope ETL → metadata archive | ~277 | — |
| `src/scrapers/trope_scraper.py` | TV Tropes harvester → TropeModel | ~298 | — |
| `src/storage/dual_commit.py` | Game dialogue → SQLite + ChromaDB dual-commit | ~137 | 1 |
| `src/storage/vector_vault.py` | ChromaDB trope vault & query engine | ~230 | — |
| `src/utils/md_slicer.py` | Monolithic MD → frontmatter-inheriting card slicer | ~185 | 4 |
| **`config/`** | | | |
| `config/settings.py` | Central config (BASE_DIR, provider factory, paths, prompts) | ~66 | — |
| `config/extractor-prompt.md` | Lorebook extraction system prompt | — | — |
| `config/compiler-prompt.md` | Obsidian compilation system prompt | — | — |
| `config/vision-extractor-prompt.md` | Vision/manga narrative extraction prompt | — | — |
| `config/narrative-extractor-prompt.md` | NME narrative structure extraction prompt | — | — |
| `config/ocean-profiler-prompt.md` | OCEAN personality profiling prompt | — | — |
| `config/launchpad-scorer-prompt.md` | Institutional launchpad scoring prompt | — | — |
| `config/meso-profiler-prompt.md` | H.E.A.D. meso-slider scoring prompt (BRC/IRT/IND/SRI + quadrant + Schein) | — | — |
| `config/trope_settings.json` | TV Tropes scraper config | — | — |

## Schema

```python
class LorebookEntry(BaseModel):
    id: int                          # Unique integer (from 1)
    name: str                        # Entity/mechanic name
    keys: list[str]                  # 3-6 trigger strings
    content: str                     # Dense description + bracketed metadata tags
    insertion_order: int = 50
    priority: int = 50

class LorebookLog(BaseModel):
    entries: list[LorebookEntry]

class NarrativeEntry(BaseModel):
    Speaker: str                     # CamelCase mirrors LLM JSON keys
    Dialogue: str
    Scene_Description: str           # serialization_alias="Scene Description"

class NarrativeLog(BaseModel):
    entries: list[NarrativeEntry]

class OceanProfile(BaseModel):       # VSPE feeder
    Openness: float                  # 0-100 percentile
    Conscientiousness: float
    Extraversion: float
    Agreeableness: float
    Neuroticism: float

class LaunchpadFeatures(BaseModel):  # VSPE feeder
    Faults: list[str]
    Levers: list[str]
    Scarcities: list[str]
    Guard_Pressure: float            # 0.0-1.0

class MesoTierLLM(BaseModel):        # HEAD feeder
    BehaviorRegulation: float         # 0-10 BRC
    InformationRouting: float         # 0-10 IRT
    IdeologicalNormalization: float   # 0-10 IND
    SomaticInsulation: float          # 0-10 SRI
    HeadQuadrant: Literal["Closed Society", "Open Society", "Predatory State", "Social Democratic Corporatist State"]
    Schein: ScheinAudit | None        # optional cultural audit

class StoryNode(BaseModel):          # NME feeder
    id: str
    label: str
    act: int | None = None
    pov: str | None = None

class StoryEdge(BaseModel):
    source: str
    target: str
    weight: float = 1.0              # 0.0-1.0
```

**SQLite tables:** `game_dialogue` (dual-commit, actively used), plus any table created via `sql-loader.py`. Legacy `cannabinoid_results` and `ice_cream_sales` tables in `coursework.db` were archived to `archives/` on 2026-09-06.

**ChromaDB collections:** `game_dialogue`, `trope_vault`

## Key Design Decisions

| Decision | Rationale |
|---|---|
| **Provider factory** (`get_ai_provider()`) | One uniform `generate(system_prompt, user_content, response_format)` interface across Ollama/Gemini/Featherless — swap engines without touching extractors |
| **Pydantic v2 as validation backbone** | `response_format=<Model>` on every LLM call + `model_validate_json()` re-validation — schema deviations crash loudly, not silently |
| **CamelCase fields mirror LLM JSON keys** | `Speaker`, `Scene_Description` — no alias translation layer between LLM output and Pydantic model |
| **Externalized prompts in `config/*.md`** | System prompts are markdown files loaded at runtime — edit prompts without touching code |
| **Hierarchical output staging** | Input folder structure mirrored into `output/json_staging/` — universes stay isolated, no naming collisions |
| **`--if-exists fail` default** | Non-destructive by default; `replace` and `--key` upsert are explicit opt-in |
| **Atomic writes everywhere** | `tempfile` + `os.replace` — no half-written files on crash |
| **Hash-cached Obsidian compilation** | SHA-256 content cache — re-compile only changed entries |
| **Canonical concurrency module** | `core/concurrency.py` — single source of truth for RateLimiter + safe_print |
| **Reasoning-tag stripping** | `clean_reasoning_response()` strips `<think>...</think>` before JSON parsing — works across DeepSeek, Llama, Gemini |
| **Path-agnostic resolution** | `BASE_DIR = Path(__file__).resolve().parent.parent` — no hardcoded absolute paths |
| **Subprocess orchestration** | Master CLI spawns scripts as subprocesses — each tool runs/tests independently |

## Compiled Data / Assets

| Source | Count | Location |
|---|---|---|
| Sample lorebooks (PDF, JSON) | varies | `output/json_staging/` |
| Web targets (targets.txt) | varies | `output/json_staging/{category}/` |
| Game dialogue exports | varies | `output/json_staging/game_text_*.json` |
| TV Tropes | varies | ChromaDB `trope_vault` collection |
| Legacy cannabinoid lab data | 3 strains | `cannabis_lab.db` |
| Game vault | varies | `game_vault.db` + ChromaDB `game_dialogue` |

## What Works

- PDF ingestion (pdfplumber + LLM → LorebookLog)
- Web ingestion (BeautifulSoup + Jina fallback + LLM, ArchiveBox snapshot support)
- Vision ingestion (EasyOCR local + Union-Find clustering + LTR/RTL + image enhancement; big-rig L3-8B-Stheno synthesis)
- Manga OCR ingestion (Mokuro parser)
- Game text ingestion (deterministic, no LLM)
- Strict table extraction (pdfplumber → CSV, no LLM)
- Narrative structure extraction (prose → NME graph via LLM)
- OCEAN personality profiling (text → LLM → OceanProfile → VSPE handoff)
- Launchpad scoring (institution text → LLM → LaunchpadFeatures → VSPE handoff)
- Institution meso-slider scoring (text → LLM → MesoTierLLM → head-cli fixture YAML, big-rig gemma4-v2, cold toolchain)
- JSON import (SillyTavern lorebooks)
- TV Tropes scraping + ChromaDB vault
- Obsidian compilation (parallel, hash-cached, wiki-linked, YAML-validated)
- JSON → Obsidian export with `--phase` (raw no-LLM unwrap / compile / one-shot)
- SillyTavern lorebook compilation (per-universe)
- SQL loading (CSV/XLSX → SQLite, idempotent upsert)
- SQLite → Obsidian Markdown export
- Data profiling / sanitization
- Database snapshot & rollback
- Markdown slicer (monolithic → frontmatter-inheriting cards)
- Dual-commit (game dialogue → SQLite + ChromaDB)
- Visualization engine (bar, line, box, scatter3d, animate3d, interactive, network + MIDI JSON support) — interactive adds manual frame scrubbing, fading trail, auto-play, arrow-key stepping
- Polymorphic gateway router (auto-detects input type)
- Master CLI menu (15 options)
- Streamlit browser dashboard (interactive ingest, visualize, query, export)
- JSON lorebook uploader (Streamlit file_uploader → `input_json/` → `import-json.py`)
- PDF uploader (Streamlit file_uploader → `input_pdfs/` → `extract-pdf.py`)
- Image uploader (Streamlit file_uploader → `input_images/` → `extract-vision.py`)
- Vision reading-direction toggle (LTR/RTL via `ingest.py --direction`, surfaced in the Streamlit Ingest tab)
- Manga narrative DB (`manga_db_loader.py` — per-series SQLite, PK `(series_id, page, entry_index)`, series_meta provenance, idempotent upsert) + Chroma `manga_vault` dual-commit (nomic-embed-text)
- Git local-only (9 commits, no remote — `origin` removed 2026-09-01 per the remote policy; portfolio display lives on the big rig)

## What Doesn't Work Yet

- **moondream multimodal extraction (deferred)** — `--vision-model moondream:latest` runs reliably on the big rig but yields degenerate `NarrativeLog` JSON (empty placeholders + truncation). The quality path is EasyOCR (local) + L3-8B-Stheno synthesis. Moondream scene-level understanding is a later task.
- **Launchpad "Levers" excluded from SHDA math** — agent opportunities ≠ institutional stability (by design)
- **`--output` path quirk** — bare filenames still resolve to `processed_data/` by design (backward compat); absolute/relative paths with directories are respected as-is

## Known Frictions

| Friction | Impact | Fix Effort |
|---|---|---|
| `requirements.txt` is curated but optional layers commented out | Vision/Gemini deps must be manually uncommented + installed | Low — uncomment + pip install |
| ~~`extract-vision.py` can't run on thin client~~ | Vision ingestion was big-rig-only | ✅ Resolved 2026-09-14 — EasyOCR + opencv installed locally; synthesis on big rig (Stheno) |
| ~~GitHub badge has `YOUR-USERNAME` placeholder~~ | Cosmetic | ✅ Fixed 2026-09-01 — replaced with `EmCargi` |
| ~~Git has a GitHub remote (portfolio) but AGENTS.md says "no remote"~~ | Tension between portfolio display and local-first mandate | ✅ Resolved 2026-09-01 — remotes now reserved for big-rig-hosted, production-ready projects only. `origin` removed from thin-client lore-matrix repo. AGENTS.md updated with formal remote policy. |
| Multiple SQLite DBs | `coursework.db`, `data_lab.db`, `db/narratives.db` archived to `archives/` (Sept 2026). Only `game_vault.db` remains active. | ✅ Resolved 2026-09-06 |

## How to Extend

### Run the master CLI
```bash
venv/bin/python lore-matrix.py
```

### Run the unified ingestor (sweeps all hoppers)
```bash
venv/bin/python ingest.py
```

### Run a specific extractor standalone
```bash
venv/bin/python extract-pdf.py
venv/bin/python extract-web.py
venv/bin/python extract-vision.py --direction RTL --preprocess --deskew --workers 4
venv/bin/python extract-narrative.py --input story.txt --engine local
venv/bin/python extract-ocean.py profile --input bio.txt --model "gemma2:2b"

# Meso-tier institution profiler (HEAD feeder — big-rig gemma4-v2 recommended)
OLLAMA_PRIMARY_MODEL="gemma4-v2-Q6_K.gguf:latest" venv/bin/python extract-head.py profile -i institution.txt --out sparta --overwrite
OLLAMA_PRIMARY_MODEL="gemma4-v2-Q6_K.gguf:latest" venv/bin/python extract-head.py profile -i detail.txt --out sparta --schein-only --overwrite
```

### Run the browser dashboard
```bash
streamlit run browser_lore_matrix.py
```
Replaces the CLI menu with an interactive Streamlit dashboard — ingest, visualize, query databases, browse JSON staging, and export to Obsidian from the browser.

### Load data into SQLite
```bash
venv/bin/python sql-loader.py --input data.csv --db library.db --table characters --key id
```

### Export JSON → Obsidian (unified exporter, three modes)
```bash
# raw: JSON chunks → RAW_VAULT_DIR (TTRPG_Vault) — NO LLM, pure unwrap
venv/bin/python src/transformers/json_to_obsidian.py --phase raw

# compile: RAW_VAULT_DIR → COMPILED_VAULT_DIR (vault) — LLM compile
venv/bin/python src/transformers/json_to_obsidian.py --phase compile

# one-shot: JSON → compiled (default, unchanged behavior)
venv/bin/python src/transformers/json_to_obsidian.py
```

### Visualize
```bash
venv/bin/python core/visualize-data.py --input data.csv --chart-type scatter3d --x-col x --y-col y,z --output cloud.png
venv/bin/python core/visualize-data.py --input midi.json --chart-type animate3d --x-col note_density --y-col active_polyphony,average_velocity --output anim.gif

# Interactive scrubbing (GUI window; --trail-length 8 matches choir_cloud trails)
venv/bin/python core/visualize-data.py --input data.csv --chart-type interactive --x-col label --y-col x,y,z,sequence --trail-length 8 --fps 15
# Headless / CI-safe: falls back to GIF export
venv/bin/python core/visualize-data.py --input data.csv --chart-type interactive --x-col label --y-col x,y,z,sequence --output scrub.gif
```

### Add a new extractor
1. Create `extract-<source>.py` at root
2. Import from `config.settings` and `core.utils`
3. Define a Pydantic schema in `core/utils.py` (or a new `core/<source>_types.py`)
4. Use `generate_with_retry()` for LLM calls with `response_format=<Model>`
5. Write to `OUTPUT_CHUNKS_DIR` with atomic writes
6. Add a menu option in `lore-matrix.py` and a route in `ingest.py`
7. Add tests in `tests/`

### Add a new LLM provider
1. Add a class in `core/engines.py` with `generate(system_prompt, user_content, response_format=None)`
2. Add a branch in `get_ai_provider()` in `config/settings.py`
3. Done — all extractors pick it up automatically

## Operational Notes

- **Big rig (100.73.250.56)** is never touched by tooling. It hosts the synthesis LLM (L3-8B-Stheno) and the optional vision model (moondream); Megane manages big-rig model installs. EasyOCR/opencv now run on the thin client (installed 2026-09-14).
- **Git** is local-only (9 commits, no remote since 2026-09-01 — remotes are reserved for big-rig-hosted production projects).
- **venv** is at `/home/megane/dev/venv/` (shared across workspace). Python is 3.12.3.
- **Ollama fallback chain:** big-rig (`100.73.250.56:11434`, primary) → thin-client (`localhost:11434`, fallback). Big-rig hosts `gemma4-v2-Q6_K.gguf` + `qwen2.5-coder:14b`. Override primary model via `OLLAMA_PRIMARY_MODEL` env; fallback model via extractor `--model`. Chain is in `core/ollama.py` (canonical copy).
- **CI**: `.github/workflows/ci.yml` runs `ruff check .` + `pytest` on Python 3.11 / 3.12.
- **`requirements.txt`** is curated (not a raw pip freeze). Optional layers (easyocr, opencv, google-genai) are commented out.

## Sibling Architecture (Lore Matrix as ingestion hub)

| Sibling | Substrate | What Lore Matrix feeds it | Feeder script |
|---|---|---|---|
| SHDA | Civilizations | (direct — no LM dependency) | — |
| PAVE | Sound | (direct — no LM dependency) | — |
| NME | Narratives | NarrativeStructure JSON (prose → graph) | `extract-narrative.py` (NME now at `dev/nme-cli/`) |
| VSPE | Personality × Institutions | OceanProfile + LaunchpadFeatures JSON | `extract-ocean.py` + `extract-launchpad.py` |
| HEAD | Hegemonic friction | MesoTierLLM fixture YAML (institution sliders + quadrant + Schein) | `extract-head.py` |
| Choir Cloud | Polyphonic music | MidiDensityLog JSON (visualization) | `core/visualize-data.py` |
| Digital DM | RPG game data | MonsterProfile JSON (SxM1 mechs from Weebly, SxM2 from DB export) | `extract-monsters.py` + `monsters-to-md.py` |

## Next Session Priorities

**Project complete — V4 shipped, validated, polished.** Items below are explicitly optional or intentionally deferred; there is no required work:

1. ~~**Browser Export tab phase selector**~~ — ✅ Done 2026-09-06: `st.selectbox` for one-shot / raw / compile phases in `browser_lore_matrix.py`
2. ~~**Edge cases in raw vault builder**~~ — ✅ Done 2026-09-06: empty-string alias filtering, leading `-`/`.` filename stripping, both locked with tests
3. **Subfolder auto-differentiation** — intentionally not implemented. Source SillyTavern JSON entries carry no `type`/`category` field. `Converted JSON` is the correct default — the human-in-the-loop review of raw notes before compiling is a feature, not a limitation. Lorebooks span slang, tutorials, districts, characters, items — automated classification would require heuristics or LLM calls that violate the pure no-LLM raw unwrap guarantee.
4. **Unified DB schema** — multiple ad-hoc SQLite DBs (cannabis_lab, coursework, game_vault) could share a migration framework

---

*Handoff updated 2026-09-14. Lore Matrix V4 — the ingestion hub feeding all 7 siblings. Final polish session: unified exporter (Sept 2), interactive visualizer (Sept 2), pipeline validated on 3 real lorebooks (Sept 5), `--output` path fix. 103 tests, ruff clean, PyQt5 installed for GUI rendering. Everything ships.*
