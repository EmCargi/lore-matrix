---
project: lore-matrix
date: 2026-08-15
status: active
test_count: 88
git: local-only
extractors: 9 (web, head, ocean, narrative, launchpad, tables, pdf, vision, monsters)
---
# Lore Matrix — Handoff Document

## Current State (2026-08-15)

Lore Matrix V4 is the **central ETL and visualization hub** of the workspace — the ingestion layer that feeds sibling projects (VSPE, NME, HEAD, Choir Cloud). It ingests unstructured sources (PDFs, web pages, ArchiveBox snapshots, manga OCR, images, RPG game text, TV Tropes), normalizes them through strict Pydantic schemas, and persists to SQLite, ChromaDB, and Obsidian. 88 tests (86 green + 2 pre-existing), `ruff` clean, CI-gated on GitHub Actions (Python 3.11 / 3.12).

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
    ├──▶ json_to_obsidian.py     ── JSON → Obsidian notes (hash-cached, parallel, wiki-linked)
    ├──▶ json-to-lorebook.py     ── JSON → SillyTavern lorebook (per-universe)
    ├──▶ json-to-md.py           ── JSON → Markdown
    ├──▶ sql-loader.py           ── CSV/XLSX → SQLite (idempotent upsert)
    ├──▶ dual_commit.py          ── Game dialogue → SQLite + ChromaDB
    └──└▶ sql-to-md.py           ── SQLite → Obsidian Markdown
    │
    ▼
Persistence: Obsidian vault · SQLite · ChromaDB
    │
    └──▶ core/visualize-data.py ── bar/line/box/scatter3d/animate3d/network charts
```

## File Map

| File | Purpose | Lines | Tests |
|---|---|---|---|
| `lore-matrix.py` | Master CLI menu (15 options, subprocess orchestrator) | ~482 | — |
| `ingest.py` | Polymorphic gateway router (auto-detects input type, routes to extractor) | ~273 | — |
| `extract-pdf.py` | PDF harvester (pdfplumber + LLM → LorebookLog) | ~157 | — |
| `extract-web.py` | Web/ArchiveBox harvester (BeautifulSoup + Jina fallback + LLM). ArchiveBox path reads local vault first, then the big-rig dashboard over Tailscale via `dev/core/archivebox.py` (output.html fallback) | ~298 | 2 |
| `extract-vision.py` | Multimodal image harvester (EasyOCR + Union-Find + LLM) | ~475 | — |
| `extract-manga.py` | Manga OCR harvester (Mokuro parser) | ~250 | — |
| `extract-game-text.py` | Deterministic RPG dialogue parser (no LLM, no AI) | ~219 | 4 |
| `extract-tables.py` | Strict PDF→CSV table extractor (pdfplumber, no LLM) | ~106 | — |
| `extract-narrative.py` | Narrative structure extractor (prose → NME graph via LLM) | ~358 | 22 |
| `extract-ocean.py` | OCEAN personality profiler (text → LLM → OceanProfile) | ~113 | — |
| `extract-launchpad.py` | Institutional launchpad scorer (text → LLM → LaunchpadFeatures) | ~112 | — |
| `extract-head.py` | Meso-tier institution scorer (text → LLM → MesoTierLLM → head-cli fixture YAML), --schein-only, --overwrite | ~200 | — |
| `import-json.py` | SillyTavern lorebook JSON importer | ~184 | — |
| `json-to-lorebook.py` | Per-universe lorebook compiler | ~120 | — |
| `json-to-md.py` | JSON → Markdown exporter | ~117 | — |
| `md-to-obsidian.py` | Markdown → Obsidian vault syncer | ~83 | — |
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
| `core/visualize-data.py` | Chart engine (bar/line/box/scatter3d/animate3d/network + MIDI JSON) | ~521 | 8 |
| `core/narrative_types.py` | NME-compatible Pydantic models (StoryNode, StoryEdge, Perspective, etc.) | ~53 | 4 |
| `core/ocean_types.py` | OceanProfile Pydantic model (Big Five percentiles) | ~49 | 6 |
| `core/ocean_scalpel.py` | JSON extraction scalpel (defends against reasoning-model noise) | ~63 | 7 |
| `core/launchpad_types.py` | LaunchpadFeatures Pydantic model (institutional features) | ~33 | 5 |
| `core/meso_types.py` | MesoTierLLM + ScheinAudit + ScheinOnly Pydantic models (H.E.A.D. 4-slider) | ~74 | 9 |
| **`src/`** | | | |
| `src/transformers/json_to_obsidian.py` | Obsidian compiler (hash-cache, parallel, wiki-link, YAML validation) | ~682 | 4 |
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

**SQLite tables:** `cannabinoid_results` (legacy lab data), `game_dialogue` (dual-commit), plus any table created via `sql-loader.py`

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
| BFRPG rulebook (PDF) | ~200 entries | `output/json_staging/BFRPG/` |
| Web targets (targets.txt) | varies | `output/json_staging/{category}/` |
| Game dialogue exports | varies | `output/json_staging/game_text_*.json` |
| TV Tropes | varies | ChromaDB `trope_vault` collection |
| Legacy cannabinoid lab data | 3 strains | `cannabis_lab.db` |
| Game vault | varies | `game_vault.db` + ChromaDB `game_dialogue` |

## What Works

- PDF ingestion (pdfplumber + LLM → LorebookLog)
- Web ingestion (BeautifulSoup + Jina fallback + LLM, ArchiveBox snapshot support)
- Vision ingestion (EasyOCR + Union-Find clustering + LTR/RTL + image enhancement)
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
- SillyTavern lorebook compilation (per-universe)
- SQL loading (CSV/XLSX → SQLite, idempotent upsert)
- SQLite → Obsidian Markdown export
- Data profiling / sanitization
- Database snapshot & rollback
- Markdown slicer (monolithic → frontmatter-inheriting cards)
- Dual-commit (game dialogue → SQLite + ChromaDB)
- Visualization engine (bar, line, box, scatter3d, animate3d, network + MIDI JSON support)
- Polymorphic gateway router (auto-detects input type)
- Master CLI menu (15 options)
- 88 tests green (86 pass + 2 pre-existing failures: test_network_chart, test_dual_commit collection error), `ruff` clean, CI on GitHub Actions
- Git local-only (2 commits, no remote by design — though a GitHub remote exists for portfolio)

## What Doesn't Work Yet

- **Vision harvester on thin client** — EasyOCR/opencv not installed (optional layer, ~2GB torch pull). Big rig has them.
- **No interactive scrubbing in visualizer** — matplotlib slider exists but is basic
- ~~**OCEAN profiler used subprocess**~~ — **Fixed 2026-08-14**: `profile_text()` and `score_text()` extracted to `core/ocean_profiler_engine.py` and `core/launchpad_scorer_engine.py`; vspe-cli imports directly, zero subprocess overhead. Extractors still run standalone.
- **Launchpad "Levers" excluded from SHDA math** — agent opportunities ≠ institutional stability (by design)

## Known Frictions

| Friction | Impact | Fix Effort |
|---|---|---|
| `requirements.txt` is curated but optional layers commented out | Vision/Gemini deps must be manually uncommented + installed | Low — uncomment + pip install |
| `extract-vision.py` can't run on thin client | Vision ingestion is big-rig-only | By design (optional layer) |
| GitHub badge has `YOUR-USERNAME` placeholder | Cosmetic | 1-line fix |
| Git has a GitHub remote (portfolio) but AGENTS.md says "no remote" | Tension between portfolio display and local-first mandate | Megane's call — remote is read-only portfolio, not a workflow remote |
| Multiple SQLite DBs (cannabis_lab.db, coursework.db, game_vault.db) | No unified schema — each loader creates its own | By design (sandbox pattern) |

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

### Load data into SQLite
```bash
venv/bin/python sql-loader.py --input data.csv --db library.db --table characters --key id
```

### Visualize
```bash
venv/bin/python core/visualize-data.py --input data.csv --chart-type scatter3d --x-col x --y-col y,z --output cloud.png
venv/bin/python core/visualize-data.py --input midi.json --chart-type animate3d --x-col note_density --y-col active_polyphony,average_velocity --output anim.gif
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

- **Big rig (100.73.250.56)** is never touched by tooling. Vision deps (EasyOCR, opencv, google-genai) are installed there by Megane personally.
- **Git** is local-only with 2 commits. A GitHub remote exists (`origin`) for portfolio display, but the workflow is not push/pull — it's save states + two-node promotion.
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

1. **ChromaDB index for digital-dm** — `build_chromadb.py` exists in digital-dm-project, needs duplicate-ID fix (level-appended ability IDs) and clean run (~3,975 documents, ~30 min via big-rig nomic-embed-text)
2. **Fix the `YOUR-USERNAME` placeholder** in `README.md` badge (1-line cosmetic)
3. **Resolve the git remote tension** — either remove `origin` to fully honor "no remote by design," or document it as read-only portfolio display
4. **Interactive scrubbing** in `core/visualize-data.py` — matplotlib slider is basic
5. **Consolidate `json-to-md.py` and `md-to-obsidian.py`** — overlapping functionality, may merge
6. **Consider a unified DB schema** — multiple ad-hoc SQLite DBs (cannabis_lab, coursework, game_vault) could share a migration framework

---

*Handoff updated 2026-08-15. Lore Matrix V4 — the ingestion hub feeding all 6 siblings. extract-head.py ships the cold institution scoring toolchain: foreign governance text → big-rig gemma4-v2 → MesoTierLLM → head-cli fixture YAML. 2026-08-15 additions: extract-monsters.py (103 SxM1 monsters → digital-dm-project) and the ArchiveBox remote read path (big-rig vault over Tailscale). 88 tests. Gorbachev out-of-sample rerun: ΔF 0.595 → Subversion Catalyst.*
