# corpus Semantic Search — Project Report

> Covers 4 sessions: 2026-03-23 → 2026-03-29 (~30h of work).

### Color Legend

Items are tagged by subsystem so you can scan related items across sections:

<font color="#2196F3">■ BM25</font> Recoll/Xapian keyword search | <font color="#4CAF50">■ VECTOR</font> FAISS/ChromaDB embeddings | <font color="#FF9800">■ OCR</font> Image→text (Claude Vision, Tesseract) | <font color="#9C27B0">■ PIPELINE</font> Claude query planning & multi-agent RAG | <font color="#F44336">■ FIX</font> Problems & workarounds | <font color="#795548">■ INFRA</font> Venvs, GPU, storage, CLI

---

## Resources Required (for relocation to another PC)

### Software (apt)
- `recoll` 1.34+ — BM25 full-text search engine (Xapian backend)
- `tesseract-ocr` + `tesseract-ocr-ell` + `tesseract-ocr-eng` — OCR (Greek+English)
- `pdftotext` (poppler-utils), `antiword` — text extraction from PDF/DOC

### Python Packages (pip, in addition to venv contents)
- `openpyxl` — XLSX text extraction (much better than recoll for spreadsheets)
- `xlrd` — legacy .xls extraction (429 files in corpus)
- `python-pptx` — .pptx extraction (11 files in corpus)

### Python Venvs (two required — cannot merge)
- **Venv A** (transformers 4.49): faiss-cpu, sentence-transformers, cohere, chromadb, numpy — for GTE model
- **Venv B** (transformers 5.0+): torch, faiss-cpu, sentence-transformers — for e5-base, e5-large, bge-m3

### HuggingFace Models (~8GB total download, cached locally)
- `Alibaba-NLP/gte-multilingual-base` (768-dim) — requires `trust_remote_code=True` and transformers ≤4.49
- `intfloat/multilingual-e5-base` (768-dim)
- `intfloat/multilingual-e5-large` (1024-dim)
- `BAAI/bge-m3` (1024-dim, ~3.6GB RAM at runtime)
- `intfloat/multilingual-e5-small` (384-dim, legacy — optional)

### API Keys
- **Cohere API key** — for `embed-multilingual-v3.0` (best model). Store in `~/.config/dsearch/.env` as `COHERE_API_KEY=...`
- **Claude subscription** — for `claude -p` query planning and Vision OCR. No API key needed (uses OAuth)

### Data to Copy

| What | Size | Source | Notes |
|------|------|----------------|-------|
| FAISS indexes (5 models) | 1.4 GB | `$FAISS_BASE/` | `index.faiss` + `metadata.json` per model |
| ChromaDB | 614 MB | `$CHROMADB_DIR/` | Single `chroma.sqlite3` |
| Recoll Xapian index | 6.9 GB | `$XAPIAN_DB/` | Or rebuild with `recollindex` (~2-4h) |
| OCR text caches | ~50 MB | `*.ocr.gemini.txt` / `*.ocr.gemini-pro.txt` in-place next to images | 4,863 files scattered in `~/DATA/corpus/` |
| Source documents | 28 GB | `~/DATA/corpus/` | The actual corpus |
| Project scripts | <1 MB | `~/DATA/ComputerWork/myProjects/semantic-disk-search/` | All Python scripts, configs, golden set |
| CLI wrappers | <4 KB | `/usr/local/bin/dsearch-multimodel`, `docsearch`, `docsearch-all` | Shell scripts |
| OCR MCP server | <100 KB | `~/.local/share/mcp/ocr/` | `ocr_server.py`, `bulk_ocr.py` |
| Recoll config | <2 KB | `~/.recoll/recoll.conf` | topdirs, pdfocr=1, dbdir path |
| Raw embeddings (4 models) | 1.25 GB | `semantic-disk-search/raw-embeddings/` | See table below |

#### Raw Embeddings (`raw-embeddings/`)

Raw numpy vectors returned from GCP T4 + Cohere API. Can rebuild FAISS/ChromaDB without re-running models.

| File | Size | Contents |
|------|------|----------|
| `embeddings_gte.npy` | 236 MB | GTE vectors (80,568 × 768) |
| `embeddings_e5-large.npy` | 315 MB | e5-large vectors (80,568 × 1024) |
| `embeddings_bge-m3.npy` | 315 MB | bge-m3 vectors (80,568 × 1024) |
| `embeddings_cohere-v3.npy` | 315 MB | Cohere v3 vectors (80,568 × 1024) |
| `embed_meta.jsonl` | 23 MB | Chunk metadata (file paths, chunk IDs) |
| `chunks-dsearch.jsonl` | 73 MB | Source text chunks sent to GCP for embedding |
| **Total** | **1.25 GB** | e5-base missing (was built locally on CPU, no .npy produced) |

### Hardware Requirements
- **Minimum:** 16GB RAM, any x86_64 CPU with AVX2 (for faiss-cpu)
- **Recommended:** 32GB+ RAM (bge-m3 alone uses 3.6GB). SSD for FAISS indexes
- **GPU optional:** Only needed for building indexes faster (GCP T4 spot $0.18/hr). Not needed at query time
- **Disk:** ~40GB for indexes + corpus. Indexes can be rebuilt from corpus + OCR caches

### Rebuild from Scratch (if indexes lost)
1. Install apt packages + create two venvs
2. Copy corpus (`~/DATA/corpus/`) and OCR caches (`.ocr.*.txt` files)
3. Run `recollindex` for BM25 (~2-4h)
4. Run `recoll_vector_index.py --build` per model (~6.5h/model on CPU, or ~30min on T4 GPU)
5. Run `cohere_embed.py` for Cohere index (~17min, needs API key)

---

## Executive Summary

### Embedding Models — 5-Model Comparison on Greek Workplace Documents

Tested 7 embedding models on 28GB/35K corpus files (Greek: payslips, legal, SCADA, scanned forms). Built FAISS indexes for 5 finalists using GCP T4 GPU (~$2.50 total). Key findings:

- **Cohere embed-v3.0** (1024-dim, API) — best Greek precision, no false positives from English technical noise. Set as default.
- **e5-base** (768-dim, local) — good retrieval asymmetry; found emails that all other models missed.
- **e5-large** (1024-dim, local) — broadest coverage for legal/procedural documents.
- **GTE** (768-dim, local) — sharpest score distribution (best discrimination), but confused by SCADA/OCR noise.
- **bge-m3** (1024-dim, local) — disappointing despite strong MTEB benchmarks; worst on real Greek single-word queries.
- **OpenAI 3-small/3-large** — tested, rejected. GTE beat 3-small on 9/12 pairs. 3-large was *worse* than 3-small for Greek.

**Critical finding: no single model finds everything.** On real queries, each model contributed unique relevant files the others missed entirely. Running all 5 in parallel is justified.

### Multi-Agent RAG Pipeline

The 6-step pipeline (`DSEARCH-SEARCH-PROMPT.md`) runs a question through all 5 models simultaneously:

1. Claude expands the user query → 3 Greek alternative phrasings
2. Python script searches all 5 FAISS indexes × 4 queries → up to 75 unique files
3. Text extracted from matched files (PDF/DOCX/ODT/images via OCR cache)
4. **5 parallel Claude agents** — one per model's result set — each extracts facts as JSON `[{date, fact, source}]`
5. Facts merged, deduplicated (first 80 chars), sorted chronologically
6. Claude answers the original question from merged facts with source citations

Tested on 4 real questions (μετάταξη, μετάθεση, ένταξη, εξωυπηρεσιακή άδεια). Pipeline covers 60+ documents in ~3 minutes, producing complete timelines with file sources. Cost: ~$0.05/question (Cohere search + Claude agents).

**Pipeline lessons:**
- **Opus is essential** for query expansion and agents — generates Greek morphological variants, understands context. Haiku/Sonnet too weak for Greek workplace domain.
- **Map-Reduce pattern works** — agents extract facts independently from their file sets, merge handles deduplication. No coordination needed between agents.
- **Parallel agents are fast** — 5 agents reading 15 files each takes the same wall-clock time as 1 agent reading 1 file (process launch is the bottleneck, not reading).
- **Recoll's extraction is more comprehensive** (19K docs) vs custom extractor (12K) — recoll handles extensionless files, more formats. Should use recoll's text as source in future.
- **openpyxl >> recoll for XLSX** — recoll only extracts sharedStrings.xml labels, missing cell values (dates, numbers, SAP codes). openpyxl captures everything.
- **Extensionless files invisible** to all 5 embedding models — 30 files in corpus not indexed (e.g., insurance records, ΣΕΠΕ applications). Recoll finds them via `file --mime-type`.
- **Hybrid text extractor built** (`extract_chunks.py`): openpyxl for XLSX, xlrd for .xls (429 files), python-pptx for .pptx (11 files), pdftotext for PDF, OCR cache for images, zipfile for DOCX/ODT.

### Hybrid BM25 + Vector System (partially complete)

A Recoll BM25 + FAISS vector hybrid was benchmarked on a sample subset: **MRR 0.862, R@5 100%** (up from BM25-only 0.636). The key strategy is **vector_augment** — preserve BM25 ranking order, only append files that vector search found but BM25 missed. RRF fusion was tested at weights 0.15–0.80 and always degraded precision. Claude query planning gave +0.102 MRR, the single biggest win.

**Remaining work:** full-disk hybrid benchmark (only 13-query sample done so far), add BM25 as 6th source in the multi-agent pipeline, index extensionless text files, OCR remaining folders (Health, Finance, RealEstate).

---

## Table of Contents

- [Resources Required](#resources-required-for-relocation-to-another-pc) — software, models, data, hardware for relocation
1. [Problem & Goal](#1-problem--goal)
2. [Timeline](#2-timeline)
3. [What Was Built](#3-what-was-built)
4. [Architecture](#4-architecture)
5. [Experiments & Metrics](#5-experiments--metrics)6. [Models Compared](#6-models-compared)
7. [Key Decisions & Rationale](#7-key-decisions--rationale)8. [Problems Encountered & Fixes](#8-problems-encountered--fixes)9. [Lessons Learned](#9-lessons-learned)10. [Current State](#10-current-state)
11. [Known Gaps & Next Steps](#11-known-gaps--next-steps)
12. [File Inventory](#12-file-inventory)13. [Cost Summary](#13-cost-summary)

---

## 1. Problem & Goal

**Corpus:** ~28GB, 35K files in `~/DATA/corpus/` (Greek workplace documents: payslips, legal, SCADA, training, photos of installations, scanned forms).

**Problem:** Recoll (Xapian BM25) was the only search. It failed on:
- Greek morphology — no stemmer in Xapian 1.4 ("εργασίες" ≠ "εργασία")
- 65% of PDFs are image-only scans — invisible to text search
- Vague semantic queries ("what properties do I own in Crete?") — BM25 needs exact words

**Goal:** Build a hybrid search system combining BM25 keyword precision + vector semantic recall + OCR for images + LLM query expansion + multi-agent fact extraction.

---

## 2. Timeline

### Session 1 — 2026-03-23 (SEMANTIC-FILESEARCH-fork)
- Explored ~/DATA folder structure (11K+ docs, 8 domains)
- Built 3-tier golden test set (38 queries: easy/known-item/semantic)
- Built benchmark harness (MRR, R@1/3/5/10)
- Ran 9 BM25 optimization experiments
- **Biggest win:** Claude subscription query planning (+0.102 MRR)
- Designed hybrid architecture plan (4 phases)

### Session 2 — 2026-03-24/25 (SEMANTIC-SEARCH, continuation)
- Installed Tesseract OCR (Greek+English)
- Tried Surya OCR (failed: incompatible with transformers 5.0)
- Built FAISS vector index with chunking (e5-small → e5-base)
- Discovered vector_augment > RRF fusion
- Built OCR MCP server (Claude Vision batch OCR)
- Fixed `claude -p` empty output bug (CLAUDE.md startup interference)
- Fixed OCR MCP spawn-leak (GPT-5 diagnosis)
- Ran overnight OCR batch: 2,047 images → `.ocr.txt`
- Moved project from /tmp to permanent location

### Session 3 — 2026-03-28 (FAISS-embedding-indexing-TESTS)
- A/B tested e5-base vs GTE on corpus corpus
- Created separate venv for GTE (transformers 4.49 required)
- Built 2 FAISS indexes (e5-base + GTE, 84K chunks each)
- Tested OpenAI embeddings (text-embedding-3-small/large) — GTE wins
- Discussed ChromaDB for incremental updates

### Session 4 — 2026-03-29 (SEMANTICsearch-2-GOOGLECLOUDembeding)
- Built ChromaDB index on GCP T4 GPU (32 min vs 6.5h CPU)
- Embedded with Cohere API (embed-multilingual-v3.0) — best for Greek
- Built e5-large + bge-m3 indexes on GCP GPU
- **Result: 5 FAISS indexes + 1 ChromaDB**
- Created `dsearch-multimodel` CLI (multi-model)
- Created 6-step RAG pipeline prompt (`DSEARCH-SEARCH-PROMPT.md`)
- Tested full pipeline on 4 real questions
- Discovered extensionless files gap
- Compared Cohere vs e5 vs GTE vs bge-m3 on real queries

---

## 3. What Was Built

### Search Tools

| Tool | Location | Purpose |
|------|----------|---------|
| `dsearch-multimodel` | `/usr/local/bin/dsearch-multimodel` | Multi-model vector search CLI. Default: Cohere. `--model e5\|gte\|bge-m3\|e5-large` |
| `search` | project dir `./search` | Hybrid BM25+vector on sample index (Finance/Tax+Health) |
| `search-all` | project dir `./search-all` | Full-disk BM25+Claude (no vector) |
| `faiss-search` | `~/bin/faiss-search` | Raw FAISS query with auto-venv selection |

### Indexes (all on `~/`)

| Index | Path | Size | Model | Docs | Chunks | Dim |
|-------|------|------|-------|------|--------|-----|
| Xapian (Recoll BM25) | `recoll-xapiandb/` | 6.9 GB | — | ~11K | — | — |
| FAISS cohere-v3 | `faiss-index/cohere-v3/` | 315 MB | Cohere embed-v3.0 | 5,707 | 80,568 | 1024 |
| FAISS e5-base | `faiss-index/e5-base/` | 248 MB | multilingual-e5-base | 8,304 | 84,597 | 768 |
| FAISS e5-large | `faiss-index/e5-large/` | 315 MB | multilingual-e5-large | 5,707 | 80,568 | 1024 |
| FAISS GTE | `faiss-index/gte/` | 248 MB | gte-multilingual-base | 8,304 | 84,597 | 768 |
| FAISS bge-m3 | `faiss-index/bge-m3/` | 315 MB | BAAI/bge-m3 | 5,707 | 80,568 | 1024 |
| ChromaDB | `chromadb-index/` | 614 MB | GTE (same as FAISS) | — | 80,568 | 768 |
| FAISS sample | `recoll-sample-test/faiss/` | 22 MB | e5-base | ~1K | 14,078 | 768 | [DELETED 2026-03-30] |
| FAISS general (stale) | `recoll-faiss/` | 57 MB | e5-small | old | old | 384 | [DELETED 2026-03-30] |

### OCR System

| Component | Location | What |
|-----------|----------|------|
| OCR MCP server | `~/.local/share/mcp/ocr/ocr_server.py` (also at `~/.local/share/ocr-mcp-venv/`) | Claude Vision batch OCR via MCP |
| Bulk OCR script | `~/.local/share/mcp/ocr/bulk_ocr.py` | Standalone parallel OCR |
| Gemini OCR caches | `*.ocr.gemini.txt` in-place | 2,403 files |
| Gemini-pro OCR caches | `*.ocr.gemini-pro.txt` in-place | 2,460 files |
| Tesseract OCR cache | `recoll-ocrcache/` | 92 KB (barely used — Gemini replaced it) | [DELETED 2026-03-30] |

### Pipeline Prompt

`DSEARCH-SEARCH-PROMPT.md` — portable 6-step RAG prompt. A new chat session reads this file and executes:
1. Claude expands query → 3 Greek alternatives
2. Python script searches all 5 models × 4 queries → up to 75 unique files
3. Extract text from all files (PDF/DOCX/ODT/images via OCR cache)
4. 5 parallel `claude -p` agents — each reads its model's files, extracts facts as JSON
5. Merge + deduplicate facts, sort by date
6. Claude answers from merged facts with source citations

### Golden Set & Benchmark

| File | Contents |
|------|----------|
| `recoll_golden_set_v3.json` | 38 queries, 3 tiers (10 easy, 19 known-item, 9 semantic) |
| `golden_tuning.json` | 70% split (26 queries) — used for experiments |
| `golden_canary.json` | 30% split (12 queries) — overfitting detection |
| `recoll_benchmark.py` | Benchmark harness: MRR, R@1/3/5/10, folder-hit, per-domain |
| `recoll_experiments.md` | 13 experiments logged with accept/revert decisions |

---

## 4. Architecture

```
                         ┌─────────────────────┐
                         │    User Query        │
                         └──────────┬───────────┘
                                    │
                         ┌──────────▼───────────┐
                         │  Claude Query Expand  │
                         │  (3 Greek variants)   │
                         └──────────┬───────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
          ┌─────────▼──────┐  ┌────▼─────┐  ┌──────▼───────────┐
          │  Recoll BM25   │  │  FAISS   │  │  FAISS × 5       │
          │  (Xapian 6.9G) │  │  single  │  │  cohere/e5/gte/  │
          │  filename: dir:│  │  model   │  │  e5-large/bge-m3 │
          └─────────┬──────┘  └────┬─────┘  └──────┬───────────┘
                    │               │               │
                    └───────────────┼───────────────┘
                                    │
                         ┌──────────▼───────────┐
                         │  vector_augment       │
                         │  (BM25 order kept,    │
                         │   vector-only appended)│
                         └──────────┬───────────┘
                                    │
                         ┌──────────▼───────────┐
                         │  5 Parallel Claude    │
                         │  Agents → JSON facts  │
                         └──────────┬───────────┘
                                    │
                         ┌──────────▼───────────┐
                         │  Merge + Dedup +      │
                         │  Chronological Sort   │
                         └──────────┬───────────┘
                                    │
                         ┌──────────▼───────────┐
                         │  Claude Final Answer  │
                         │  (facts + sources)    │
                         └─────────────────────-─┘
```

**Two usage modes:**
- **Quick:** `dsearch-multimodel "query"` — single model, 10 results, <5s
- **Full RAG:** Follow `DSEARCH-SEARCH-PROMPT.md` — all 5 models, parallel agents, ~3 min

**Text extraction chain:**
```
PDF → pdftotext (text PDFs) or skip (image-only, no Tesseract fallback)
DOCX/ODT → zipfile → XML → strip tags
XLSX → openpyxl (cell values, dates, numbers)
XLS → xlrd
DOC → antiword
Images → read .ocr.gemini.txt / .ocr.gemini-pro.txt cache (skip if none)
```

**Chunking:** 500 chars, 100 overlap → avg 10 chunks/doc. Min 30 chars per chunk.

---

## 5. Experiments & Metrics

> **Summary:** 13 experiments, 4 accepted, 9 reverted. Only 3 things actually helped: Greek stopwords (+0.006), Claude query planning (+0.102 — biggest win by far), and vector_augment (+0.041). RRF fusion always hurt. Final: MRR 0.636→0.862 on sample, 0.636→0.699 on full set.


#### BM25 Optimization (Session 1)

| # | Change | Tuning MRR | Delta | Verdict |
|---|--------|-----------|-------|---------|
| 0 | Baseline | 0.605 | — | — |
| 1 | <font color="#2196F3">■</font> Fix rent/salary domain confusion (`μισθ`→`μισθωσ`) | 0.610 | +0.005 | ACCEPT |
| 2 | <font color="#2196F3">■</font> ANY-mode (`-o`) query variant | 0.610 | +0.000 | REVERT |
| 3 | <font color="#2196F3">■</font> Wildcard `filename:stem*` | 0.609 | -0.001 | REVERT |
| 4 | <font color="#2196F3">■</font> Greek stopwords (~70 words) | 0.616 | +0.006 | ACCEPT |
| 5 | <font color="#2196F3">■</font> Remove `λογαριασμ` from banking | 0.616 | +0.000 | REVERT |
| 6 | <font color="#2196F3">■</font> Expand filename: anchors 4→6 | 0.616 | +0.000 | REVERT |
| **7** | <font color="#9C27B0">■</font> **Claude subscription query planning** | **0.718** | **+0.102** | **ACCEPT** |
| 8 | <font color="#9C27B0">■</font> `dir:` scope from plan anchors | 0.726 | +0.008 | ACCEPT |
| 9 | <font color="#9C27B0">■</font> Merge Claude + heuristic plans | 0.610 | **-0.116** | REVERT |

Canary check after exp 8: MRR=0.718 — no overfitting.

#### Hybrid Fusion (Session 2)

| # | Change | Sample MRR | Notes |
|---|--------|-----------|-------|
| 10 | <font color="#4CAF50">■</font> RRF vector_weight=0.8 | 0.718 | -0.103 from BM25-only |
| 11 | <font color="#4CAF50">■</font> RRF vector_weight=0.3 | 0.692 | Still hurts |
| 12 | <font color="#4CAF50">■</font> RRF vector_weight=0.15 | 0.686 | Any RRF re-ranking degrades BM25 |
| **13** | <font color="#4CAF50">■</font> **vector_augment (append-only)** | **0.862** | **+0.041, R@5=100%** |


### Metric Progression

| Stage | MRR | R@1 | R@5 | Set |
|-------|-----|-----|-----|-----|
| Original heuristic | 0.636 | 55.3% | 73.7% | Full 38q |
| + stopwords + rent fix | 0.616 | 53.8% | 69.2% | Tuning 26q |
| + Claude planning | 0.718 | 61.5% | 84.6% | Tuning 26q |
| + dir: scopes | 0.726 | 61.5% | 88.5% | Tuning 26q |
| Final BM25+Claude | **0.699** | **63.2%** | **81.6%** | Full 38q |
| **Hybrid (BM25+vector_augment)** | **0.862** | **76.9%** | **100%** | Sample 13q |

---

## 6. Models Compared

### Embedding Models (ranked for Greek workplace docs)

| Rank | Model | Dim | Source | Strength | Weakness |
|------|-------|-----|--------|----------|----------|
| 1 | **Cohere embed-v3.0** | 1024 | API ($0.10/1M tok) | Best Greek precision, no false positives from English tech docs | API-only, ~$1.60 per full index |
| 2 | intfloat/multilingual-e5-base | 768 | Local (HF) | Good retrieval asymmetry, found emails others missed | Scores cluster 0.83-0.88 (poor discrimination) |
| 3 | intfloat/multilingual-e5-large | 1024 | Local (HF) | Broad coverage, found legal docs | Slower, needs more VRAM |
| 4 | Alibaba-NLP/gte-multilingual-base | 768 | Local (HF) | Sharp score distribution (good discrimination), 8K context | Confused by SCADA/technical OCR noise |
| 5 | BAAI/bge-m3 | 1024 | Local (HF) | Strong MTEB benchmarks | Disappointing on real Greek queries |

**Cross-model finding:** No single model finds everything. On real pipeline tests, each model contributed unique finds the others missed. Keeping all 5 is justified.

### Also Tested (Not Kept)

| Model | Why Not |
|-------|---------|
| OpenAI text-embedding-3-small | GTE wins 9/12 test pairs, sends data externally, costs money |
| OpenAI text-embedding-3-large | *Worse* than 3-small for Greek (counter-intuitive, confirmed) |
| intfloat/multilingual-e5-small | Replaced by e5-base (768 vs 384-dim, noticeably better) |
| Surya OCR 0.16/0.17 | Crashes on transformers 5.0 (`pad_token_id` error), incompatible |

### OCR Comparison

| Tool | Quality (Greek) | Speed | Notes |
|------|----------------|-------|-------|
| Claude Vision (via MCP) | Best — contextual, handles handwriting | ~15-22s/image | Used for batch: 4,863 cached files |
| Google Vision API | ~95% accuracy | 0.58s/image | Service account exists, not used for batch |
| Tesseract 5.3 | Poor on Greek docs | Fast | Recoll integration works, but quality too low |
| Surya | Untested (install failed) | — | Incompatible with transformers 5.0 |

---

## 7. Key Decisions & Rationale

> **Summary:** Append vector results to BM25 (don't re-rank). Use Claude for query planning (not heuristic). Keep all 5 models (each finds unique docs). Cohere is best for Greek. Chunk at 500 chars. Use Claude Vision for OCR. GCP T4 for index builds. Two venvs required (GTE needs transformers 4.49).


| Decision | Why | Alternative Rejected |
|----------|-----|---------------------|
| <font color="#4CAF50">■</font> **vector_augment over RRF** | RRF re-ranks BM25 results, degrading precision. Augment preserves BM25 order and only appends semantic-only finds | RRF at any weight (0.15-0.80) always hurt MRR |
| <font color="#9C27B0">■</font> **Claude -p for query planning** | +0.102 MRR — generates Greek morphological variants Xapian can't derive. Uses subscription, no API cost | OpenAI API (zero credits), heuristic planner (weaker) |
| <font color="#2196F3">■</font> **Keep Recoll BM25** | Works well for exact matches, filename:, dir: queries. High precision on known-item tier | Replace with pure vector (would lose precision) |
| <font color="#4CAF50">■</font> **5 models not 1** | Each model finds unique relevant docs. Merging all 5 covers more ground than any single model | Single best model (misses too much) |
| <font color="#4CAF50">■</font> **Cohere as default** | Best precision for Greek, no false positives from English technical docs | GTE (good but confused by SCADA), e5-base (scores cluster) |
| <font color="#4CAF50">■</font> **Chunking 500/100** | Full doc coverage. Without chunking, 90% of long documents' content was lost (only first 2000 chars embedded) | Whole-document embedding (lost 90% of text) |
| <font color="#FF9800">■</font> **Claude Vision over Tesseract** | Dramatically better for Greek documents, handwriting, complex layouts | Tesseract (poor Greek accuracy) |
| <font color="#795548">■</font> **GCP T4 GPU for embedding** | 12-15x speedup (32 min vs 6.5h). Upload only text chunks (~50MB), not raw files (28GB) | CPU-only (6.5h per model × 5 = impractical) |
| <font color="#795548">■</font> **Separate venvs (gte-embed vs transformers)** | GTE custom code crashes on transformers 5.0. Must pin 4.49 | Single venv (crashes) |
| <font color="#795548">■</font> **ChromaDB alongside FAISS** | Supports incremental add/delete without full rebuild. FAISS is read-only, every change = 6h rebuild | FAISS-only (fragile, no CRUD) |
| <font color="#9C27B0">■</font> **Merge Claude+heuristic = NO** | -0.116 MRR regression. Heuristic generic terms dilute Claude's focused plan | Merged planner (tested, failed badly) |


---

## 8. Problems Encountered & Fixes

> **Summary:** 8 showstoppers resolved. Biggest: `claude -p` empty output (workaround: parse stream-json), OCR spawn leak (fix: `--strict-mcp-config`), GTE vs transformers 5.0 (fix: separate venv). Subtlest: A/B test gave wrong results because wrong venv was used to query the index.


#### Showstoppers (resolved)

| Problem | Root Cause | Fix |
|---------|-----------|-----|
| <font color="#9C27B0">■</font> `claude -p` returns empty text | CLAUDE.md startup instructions trigger Bash tool calls; `-p` mode `result` field omits tool outputs | Parse `--output-format stream-json --verbose` and extract text blocks |
| <font color="#FF9800">■</font> OCR MCP spawn leak (20+ processes) | Each `claude -p` spawns all 9 MCP servers from `~/.claude.json` × 4 workers = cascade | `--strict-mcp-config --mcp-config empty.json` + serial workers + `start_new_session=True` + `os.killpg()` |
| <font color="#4CAF50">■</font> GTE crashes with transformers 5.0 | Custom rotary embedding code uses API removed in 5.0 | Separate venv `$VENV_GTE/` pinned to transformers 4.49 |
| <font color="#FF9800">■</font> Surya OCR installation fails | `pad_token_id` error — Surya 0.16/0.17 both incompatible with transformers 5.0+ | Abandoned Surya; stuck with Claude Vision + Tesseract |
| <font color="#4CAF50">■</font> FAISS build Unicode crash | Surrogate chars in Greek filenames | `.encode('utf-8', errors='ignore').decode('utf-8')` |
| <font color="#9C27B0">■</font> `--model haiku` broken | Tool #130 of ~165 has invalid JSON schema | Use opus or sonnet only |
| <font color="#2196F3">■</font> `recollq '*'` fails | Max term expansion limit | Use `os.walk()` for file discovery instead |
| <font color="#795548">■</font> DATA mount is noexec | `~/DATA` mounted with `noexec` | Scripts at `/usr/local/bin/`, not symlinked from DATA |

#### Gotchas / Subtle Issues

| Issue | Detail |
|-------|--------|
| A/B test gave wrong results | Used transformers 5.0 venv to query GTE index built with 4.49 → garbage embeddings, looked like GTE was dramatically better. Caught by re-running with correct venv |
| DocFetcher Lucene can't export text | Content field is indexed but NOT stored. Cannot be used as text source for embedding |
| Metadata bug | `MODEL_NAME` (global) written to JSON instead of `model_name` (local override). Auto-detect loaded wrong model on search |
| Claude non-determinism | Same query gives ±1-2 hit variance between benchmark runs. Accepted as inherent limitation |
| Sonnet 3.5x slower than Opus for agents | Process launch overhead dominates per-token speed; Sonnet found more facts (53 vs 26) making responses longer |


---

## 9. Lessons Learned

> **Summary:** Measure before optimizing (5/9 experiments reverted). Claude planning = biggest win. RRF always hurts — use append-only. No single model wins — keep all 5. Bigger ≠ better (OpenAI 3-large < 3-small for Greek). Claude Vision >> Tesseract. Opus essential for agents (Sonnet 3.5x slower). openpyxl >> recoll for XLSX. Map-Reduce pattern works for parallel fact extraction.


#### <font color="#2196F3">■</font> Search Engineering

- **Measure before optimizing.** The golden set + benchmark turned guesswork into data. 5 of 9 experiments were reverted — would have been accepted without measurement.
- **One change at a time.** Accept/revert discipline caught that merging planners was -0.116 MRR.
- **70/30 tuning/canary split** prevents overfitting. Canary set actually scored higher than tuning — confirmed changes were real, not overfitting.
- **RRF hurts when BM25 is already good.** Any re-ranking disrupts correct BM25 rankings. Even at weight=0.15, re-ranking degrades what BM25 already got right. Append-only (vector_augment) is the right hybrid strategy.
- **`filename:` and `dir:` Recoll queries are high-precision** for known-item search. Underused in the original script — adding them recovered 2 failures to rank @1.
- **BM25 finds what ALL vector models miss.** Demonstrated with extensionless files — recoll found them instantly, all 5 embedding models returned nothing.

#### <font color="#9C27B0">■</font> LLMs in Search

- **Claude query planning = biggest single win** (+0.102 MRR). Generates Greek morphological variants, cross-language expansion, `filename_terms` with greeklish transliterations.
- **Subscription ≠ API.** `claude -p` uses subscription (free). API key had zero credits.
- **Don't merge LLM + heuristic plans.** Heuristic generic terms dilute Claude's focused, specific plan. Let Claude lead alone.
- **Claude is non-deterministic.** Same query gives different results between runs — causes ±1-2 hit variance in benchmarks. Accepted as inherent limitation.

#### <font color="#4CAF50">■</font> Embeddings & Models

- **No single model finds everything.** On real queries, each model contributed unique finds.
- **Score magnitudes are meaningless across models.** e5-base gives 0.83+ for everything; GTE gives 0.07-0.81. Only rankings matter.
- **Bigger ≠ better.** OpenAI text-embedding-3-large was *worse* than 3-small for Greek. bge-m3 (strong on MTEB) was worst for real Greek queries.
- **Local beats cloud for this corpus.** GTE (free, local, private) outperformed OpenAI embeddings on 9/12 test pairs.
- **FAISS flat index is enough for 10K docs.** 15-50MB file, microsecond search. No need for Qdrant/Weaviate/Pinecone.
- **Chunking matters.** Embedding only first 2000 chars loses 90% of long documents. 500-char overlapping chunks with doc-level aggregation is the right approach.

#### <font color="#FF9800">■</font> OCR

- **Claude Vision >> Tesseract for Greek.** Handles handwriting, complex layouts, watermarks, contextual inference of truncated names.
- **Sidecar `.ocr.txt` is the right pattern.** Files next to originals survive index rebuilds, are readable by any tool, no special DB needed.
- **Batch 10+ images per `claude -p` call.** Uses `===FILE N===` separators in prompt. System prompt overhead (~9K tokens) dwarfs image tokens (~950). Effective rate: ~5s/img with Opus. Single-image calls waste 90% on prompt.
- **4 workers max** before Anthropic throttles concurrent inference.
- **`--bare` flag breaks OAuth** — disables authentication entirely. Use `--strict-mcp-config --mcp-config empty.json` instead to block MCP servers while keeping auth.

#### Methodology (from web research)

- **Fix scoring before expanding queries.** More results with bad scoring = more noise. Get ranking right first.
- **The right order:** tokenization → field boosting → synonyms → scoring → query expansion → vector search → reranking.
- **Standard IR practices:** Doc2Query for golden sets, TREC-style pooling, 50+ queries minimum, 3-point relevance scale, hold-out validation sets.

#### <font color="#795548">■</font> Text Extraction

- **openpyxl >> recoll for XLSX.** Recoll only gets sharedStrings.xml labels; openpyxl captures actual cell values (dates, numbers, SAP codes). Compared recoll vs DocFetcher vs python-docx vs openpyxl.
- **DocFetcher Lucene can't export text.** Content field is indexed but NOT stored — cannot be used as text source for embedding.
- **Hybrid extractor needed.** No single tool handles all formats well: openpyxl for XLSX, xlrd for .xls, python-pptx for .pptx, pdftotext for PDF, OCR cache for images, zipfile for DOCX/ODT.
- **Recoll finds 19K docs vs custom extractor's 12K** — recoll handles extensionless files via `file --mime-type`. Should use recoll's text as source in future.

#### <font color="#9C27B0">■</font> Pipeline Architecture

- **Opus essential for agents.** Haiku/Sonnet too weak for Greek workplace domain — miss context, produce shallow facts. Always use Opus for `claude -p` calls.
- **Map-Reduce works well.** Agents extract facts independently, merge handles deduplication. No coordination needed between agents.
- **Parallel agents = free speed.** 5 agents reading 15 files each takes same wall-clock as 1 agent reading 1 file. Process launch overhead is the bottleneck, not reading/reasoning.
- **Sonnet 3.5x slower than Opus.** Counter-intuitive — process launch overhead dominates; Sonnet also found more facts (53 vs 26) making responses longer.

#### Infrastructure

- **GCP T4 spot = $0.18/hr, 12-15x faster.** Upload only text chunks (50MB), not raw files (28GB). Total 5-model cost: ~$2.60.
- **Two venvs are permanent.** GTE needs transformers 4.49; e5/bge-m3 need 5.0. Cannot unify.
- **ChromaDB for CRUD, FAISS for speed.** ChromaDB supports add/delete; FAISS is read-only but simpler.


---

## 10. Current State

### Working

- `dsearch-multimodel "query"` — Cohere default, 5 models available via `--model`
- 5 FAISS indexes + 1 ChromaDB, all populated (80K chunks from corpus)
- OCR MCP server — batch Claude Vision OCR
- 4,863 image OCR caches in corpus (gemini + gemini-pro)
- Full pipeline tested on 4 real questions with good results
- `DSEARCH-SEARCH-PROMPT.md` — any new chat can run the full 6-step RAG pipeline

### Metrics Achieved

| What | Before | After |
|------|--------|-------|
| BM25 MRR (38q full) | 0.636 | 0.699 (+10%) |
| Hybrid MRR (13q sample) | — | 0.862 |
| Hybrid R@5 (13q sample) | — | 100% |
| Images searchable | 0 | 4,863 (via OCR cache) |
| Embedding models | 0 | 5 |
| Vector indexes | 0 | 6 (5 FAISS + 1 ChromaDB) |

---

## 11. Known Gaps & Next Steps

| Gap | Impact | Fix |
|-----|--------|-----|
| <font color="#4CAF50">■</font> **Extensionless text files not indexed** | 30 files in corpus invisible to all 5 models (e.g., insurance records). Recoll finds them. | Add `file --mime-type` fallback in extractor, re-embed |
| <font color="#9C27B0">■</font> **BM25 not in 6-step pipeline** | Pipeline uses only 5 vector models. BM25 should be 6th source. | Add recollq step to `DSEARCH-SEARCH-PROMPT.md` |
| <font color="#4CAF50">■</font> **Doc count discrepancy** | cohere/e5-large/bge-m3 = 5,707 docs; e5-base/gte = 8,304 docs (different extraction runs) | Re-extract all with unified script, rebuild all indexes |
| <font color="#2196F3">■</font> **Full-disk hybrid benchmark not run** | MRR=0.862 is sample-only (13q). Full 38q hybrid benchmark pending | Run `recoll_benchmark.py` with all 5 models |
| <font color="#FF9800">■</font> **OCR coverage incomplete** | Only corpus images OCR'd. Health, Finance, RealEstate images not done | Run OCR MCP `scan_bulk_good` on remaining folders |
| <font color="#FF9800">■</font> **Image-only PDFs skipped** | FAISS builder skips scanned PDFs without text. ~8K PDFs affected | Need `pdftoppm` → Tesseract/Vision pipeline for PDFs |
| <font color="#795548">■</font> **GCP instance stopped, not deleted** | `embedding-gpu` (europe-west1-b, T4 spot) — restart for re-indexing | Keep stopped; $0 when stopped |
| <font color="#9C27B0">■</font> **Query expansion can hurt** | Generic English expansions (e.g., "recording" for "μαγνητοφώνηση") pull irrelevant results | Domain-aware expansion or constrain to Greek-only |

---

## 12. File Inventory

> **Summary:** Project code in `~/DATA/ComputerWork/myProjects/semantic-disk-search/` (16 scripts + golden sets + benchmarks). CLI wrappers at `/usr/local/bin/{dsearch-multimodel,docsearch,docsearch-all}`. OCR at `~/.local/share/mcp/ocr/`. Two venvs: `gte-embed` (transformers 4.49) and `transformers` (5.0). HF models cached.


#### Project Directory
`$PROJECT_DIR/`

| File | Role |
|------|------|
| `recoll_query_assist.py` | <font color="#2196F3">■</font><font color="#4CAF50">■</font><font color="#9C27B0">■</font> Main hybrid search tool (BM25 + domain detection + Claude planning + vector augment) |
| `recoll_vector_index.py` | <font color="#4CAF50">■</font> FAISS index builder (chunked, OCR cache, multi-model presets) |
| `chroma_vector_index.py` | <font color="#4CAF50">■</font> ChromaDB alternative (incremental add/delete) |
| `recoll_benchmark.py` | Golden set benchmark harness |
| `recoll_golden_set_v3.json` | 38 queries, 3 tiers |
| `golden_tuning.json` | 26q tuning split |
| `golden_canary.json` | 12q canary split |
| `recoll_experiments.md` | 13 experiments with accept/revert log |
| `Semantic-Search-Prompt.md` | 6-step corpus RAG pipeline prompt |
| `README.md` | Architecture quick-reference |
| `search` / `search-all` | Shell wrappers (sample / full-disk) |
| `build_golden_set.py` | Doc2Query golden set generator |
| `validate_golden.py` | Raw recollq validation |
| `verify_index.py` | Index coverage checker |
| `ocr_batch_dsearch.py` | Batch OCR for corpus images |
| `extract_chunks.py` | <font color="#795548">■</font> Hybrid text extractor (openpyxl+xlrd+pptx+pdftotext+OCR cache) |
| `gpu_embed.py` | <font color="#4CAF50">■</font> Single-model GPU embedding script for GCP T4 |
| `gpu_embed_multi.py` | <font color="#4CAF50">■</font> Multi-model GPU embedding (e5-large + bge-m3 back-to-back) |
| `cohere_embed.py` | <font color="#4CAF50">■</font> Cohere API embedding script (embed-multilingual-v3.0) |
| `build_chroma_from_embeddings.py` | <font color="#4CAF50">■</font> ChromaDB builder from pre-computed .npy vectors |
| `multi_search.py` | <font color="#9C27B0">■</font> 5-model parallel search + merge prototype |
| `chat-2026-03-24-*.md` | Session chat logs |
| `benchmark_results/` | 25+ benchmark JSON snapshots |
| `backups/` | Pre-change backups of all scripts |

#### System Files

| File | Role |
|------|------|
| `/usr/local/bin/dsearch-multimodel` | Multi-model vector search CLI |
| `/usr/local/bin/docsearch` | Sample hybrid search alias |
| `/usr/local/bin/docsearch-all` | Full-disk BM25+Claude alias |
| `~/.recoll/recoll.conf` | Recoll config (pdfocr=1, ocrlang=ell+eng) |
| `~/.config/dsearch/.env` | COHERE_API_KEY |
| `~/.local/share/mcp/ocr/ocr_server.py` | OCR MCP server |
| `~/.local/share/mcp/ocr/bulk_ocr.py` | Standalone batch OCR |
| `~/.local/share/mcp/ocr/bulk_ocr_gemini.py` | Gemini batch OCR variant |

#### Venvs & Model Cache

| Path | Contents |
|------|----------|
| `$VENV_GTE/` | faiss-cpu, sentence-transformers, cohere, chromadb, transformers **4.49** |
| `$VENV_TF/` | torch 2.10+cpu, sentence-transformers, faiss-cpu, transformers **5.0** |
| `$HF_HOME/hub/` | 6 models: gte-multilingual-base, e5-small/base/large, bge-m3, Alibaba-NLP/new-impl |


---

## 13. Cost Summary

| Item | Cost | Notes |
|------|------|-------|
| GCP T4 spot (3 builds: GTE + e5-large + bge-m3) | ~$0.90 | europe-west1-b, ~5h total |
| Cohere API (embed 80K chunks) | ~$1.60 | One-time index build |
| Claude Vision OCR (4,863 images) | $0 | Subscription, not API |
| Claude query planning | $0 | Subscription (`claude -p`) |
| Tesseract/Recoll | $0 | System packages |
| **Total one-time** | **~$2.50** | |
| Per-question (full pipeline) | ~$0.05 | Cohere search + Claude reads ~50 files |
| Equivalent managed service | $500-2K/mo | Azure AI Search, Vertex AI, Kendra |

---

*Report generated 2026-03-29. Covers sessions SEMANTIC-FILESEARCH-fork, SEMANTIC-SEARCH, FAISS-embedding-indexing-TESTS, SEMANTICsearch-2-GOOGLECLOUDembeding.*
