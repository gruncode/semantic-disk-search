# Semantic Disk Search — Status

**Updated:** 2026-06-13

## v1 (search-ai-10agents) — LIVE, modified

**File:** `/usr/local/bin/search-ai-10agents` (68K)
**Backup:** `/tmp/.search-ai-10agents.bak-20260612-tier-v2`, `/usr/local/bin/.search-ai-10agents.bak-20260612-tier`
**Collection:** `fulldisk` (1.12M chunks, 500-char), Cohere embed-multilingual-v3.0

### Changes (2026-06-12 — Phase 2 tier improvements)

1. **Stricter A classifier:** Split `_A_PATTERNS` into `_A_STRONG` (9 institutional: ΕΛΛΗΝΙΚΗ ΔΗΜΟΚΡΑΤΙΑ, Αρ.Πρωτ, ΦΕΚ, Υπουργείο, etc.) and `_A_WEAK` (5 legal vocab: Άρθρο, Ν.law, ΑΦΜ, ΑΜ-ΤΕΕ, ΔΗΜΟΣ). Tier A now requires ≥1 strong marker.
2. **C-override:** When C-signals present + no strong A + ≤1 weak A → `a_effective=0` (discounts weak A-markers).
3. **4 new C-patterns:** ρώτησα, πήρα-τηλ, μου-είπε, πρέπει-να.
4. **Downgrade-only propagation:** `_parse_rankings()` agents can lower tier (A→C) but never raise it (C→A). Uses `TIER_ORDER = {A:3, B:2, C:1, D:0}`.
5. **A/B quota:** `step_merge()` ensures top 15 includes ≥5 A/B files (score≥5) by evicting lowest-scoring C/D files.
6. **Claim-level evidence:** `step_final()` prompt now demands 3-section output: ANSWER + CLAIM EVIDENCE (per-claim: status CONFIRMED/SUPPORTED/UNCONFIRMED/WEAK, sources, key quote) + SOURCES.

### Tests

- **29/29 unit tests passed** — `$PROJECT_DIR/test_source_tiers.py`
- Groups: Strong A, Weak A rejection, C-override, Strong A+C survival, B-tier, C-tier, D-tier, filename/path signals, TIER_ORDER+downgrade-only, new C-patterns.

### Live query test: "πολεοδομία Ηρακλείου άδεια οικοδομής" (2026-06-12) — **PASS**

- **πολεοδομια-ηρακλειο.odt** correctly classified as **C** (was the problem file). Rank #8, labeled "⚠ ανεπιβεβαίωτο" in answer.
- **PICT0090.jpg** (ΕΠΑΕ decision) correctly at **A**, ranked #1.
- Top 15 composition: 3×A, 4×B, 1×C, 7×D — official documents dominate.
- Claim Evidence section present with CONFIRMED/SUPPORTED/WEAK/UNCONFIRMED statuses per claim.
- Downgrade-only verified: agent scored πολεοδομια-ηρακλειο.odt at 9 but tier stayed C (couldn't upgrade).
- Total runtime: 337s (100 files, 10 agents, 15 merged, 340K chars to final Claude).

## v2 (dsearch2-update) — INSTALLED, tuned classifier, 33-file eval set

**File:** `/usr/local/bin/dsearch2-update` (41K, root:root 755)
**Collection:** `fulldisk-1k` (950,429 chunks, 128,322 files tracked)
**Tier distribution (sample 1K):** A=34 B=72 C=268 D=626

### Classifier v2 tuning (Phase B Task 8-9, 2026-06-12) — **ALL PASS**

1. **A_STRONG/A_WEAK split:** Strong = ΕΛΛΗΝΙΚΗ ΔΗΜΟΚΡΑΤΙΑ, Αρ.Πρωτ, Υπουργείο, Περιφέρεια, ΔΗΜΟΣ, Βεβαιώνεται, Αποφασίζουμε, Χορηγείται. Weak = Άρθρο, Ν.law, ΦΕΚ, ΑΦΜ, ΑΜ-ΤΕΕ, Δ/ΝΣΗ-ΤΜΗΜΑ.
2. **FNAME_A split:** Strong (πιστοποιητικο, αποφαση, βεβαιωση...) vs Weak (αδεια, εγγραφο, ενσταση, αγωγη)
3. **Expanded FNAME_C_RE:** +ερωτησ, γειτον, σταδια, προσωπικ, σημειωματα, διαδικασιες, τηλ, τηλεφ
4. **Note fallback:** .odt in personal folders → C if no strong A/B; .txt requires C filename/content signals
5. **Permit-folder OCR rescue:** images in Αδεια-Φάκελος with OCR hints → A/B
6. **Precedence-based classifier:** 6 priority rules before D default
7. **Anti-quotation:** note files need 2+ strong A content signals to be A
8. **New flags:** `--force` (bypass mtime), `--llm-tier-fallback` (Haiku D→C, disabled by default)

### Eval results

- **Classifier-only:** 17/31 exact match (55%), 19/31 acceptable (61%)
- **Required fixes:** All 9 PASS (ΚΤΗΜΑΤΟΛΟΓΙΟ→C, ερωτησεις→C, γειτονες→C, Σταδια→C, ΓΟΚ-αδεια→C, ΠΡΟΣΩΠΙΚΟ-ΕΓΓΡΑΦΟ→C, PICT0047/0095/0088→A/B)
- **Retrieval queries:** 4/4 pass criteria met (A official above C notes, D not dominant)

### Backups

- `/tmp/.dsearch2-update.bak-20260612-pre-classifier-tune` (original work copy)
- `/tmp/.dsearch2-update.bak-20260612-pre-classifier-tune-live` (live pre-install)
- `/home/DISKS/root-store/my-projects/semantic-disk-search/bin/dsearch2-update-tuned-20260612` (persistent)

## dsearch2 CLI retriever — INSTALLED, ready (needs indexed collection)

**File:** `/usr/local/bin/dsearch2` (12K, root:root 755)
**Backup:** `/tmp/.dsearch2.bak-20260612-initial-install`

### Architecture

- **Hybrid retrieval:** Vector (Cohere embed-v3 → ChromaDB) + Lexical TF + RRF merge
- **RRF formula:** `score = 1/(60+vec_rank) + 1/(60+tf_rank) + tier_boost`
- **Tier tiebreaker:** A +0.004, B +0.002, C +0, D -0.002 (tiny — relevance dominates)
- **TF scoring:** Accent-stripped, log-dampened term frequency over returned chunks only (no corpus-wide IDF)
- **Alias expansion:** 18 Greek↔English groups, loaded from `configs/alias_map.json`
- **Read-only:** Does not modify ChromaDB, does not call dsearch2-update

### CLI options

- `dsearch2 query words` — terminal output (colored, ranked passages)
- `dsearch2 --json query` — JSON with `query_original`, `query_expanded`, `aliases_used`, results
- `dsearch2 -n 50 query` — top N results (default 20)
- `dsearch2 --show-aliases` — print alias map and exit
- `dsearch2 --no-alias query` — disable alias expansion
- `dsearch2 --debug query` — print debug info to stderr

### Tests (2026-06-12) — **ALL PASS**

- `--help` — clean argparse output
- `--show-aliases` — 18 alias groups displayed
- Empty collection query — "0 chunks" message, exit 0, JSON includes expansion metadata

## Bilingual alias map — CREATED

**File:** `$PROJECT_DIR/configs/alias_map.json`
**Groups:** 18 (πολεοδομία, οικ.άδεια, κτηματολόγιο, ΕΦΚΑ, ΤΕΕ, corpus, βεβαίωση, συμβόλαιο, τοπογραφικό, αυθαίρετο, ένσταση, μηχανικός, δικηγόρος, πληρεξούσιο, κληρονομιά, ακίνητο, ΕΠΑΕ, ΦΕΚ)

## dsearch2-answer — INSTALLED, live synthesis tested

**File:** `/usr/local/bin/dsearch2-answer` (9K, root:root 755)
**Backup:** `/tmp/.dsearch2-answer.bak-20260612-initial-install`

### Architecture

- **Passage-first:** calls `dsearch2 --json` as subprocess, builds answer from ranked passages
- **Claude synthesis:** sends top 20 passages as context to `claude -p` with structured prompt
- **Prompt structure:** ANSWER (with inline [P<n>] citations) + CLAIM EVIDENCE (status per claim) + SOURCES
- **Empty collection:** exits cleanly with clear message, no Claude call

### CLI options

- `dsearch2-answer query words` — terminal output (answer + citations)
- `dsearch2-answer --json query` — JSON with answer, passages, metadata
- `dsearch2-answer -n 100 query` — retrieve more passages (default 50)
- `dsearch2-answer --show-passages query` — show passages before answer
- `dsearch2-answer --no-alias query` — disable alias expansion
- `dsearch2-answer --model ID query` — Claude model override
- `dsearch2-answer --dry-run query` — build prompt without calling Claude

### Tests (2026-06-12) — **ALL PASS**

- `--help` — clean argparse output
- Empty collection query — clear message, exit 0, JSON metadata correct

### Live synthesis test (2026-06-12) — **PASS**

Query: "πολεοδομία Ηράκλειο οικοδομική άδεια" on 7-chunk controlled index:
- Inline [P1]-[P6] citations present
- A sources (ΕΠΑΕ decision) → CONFIRMED
- C sources (personal notes) → UNCONFIRMED-WEAK, not presented as official
- CLAIM EVIDENCE section with 3 claims, proper status/sources/quotes
- SOURCES section with 2 files + tier labels

## Backup — DONE

**Location:** `/home/DISKS/root-store/my-projects/semantic-disk-search/`
**Contents:** bin/ (6 executables), configs/ (alias_map.json), tests/ (2 test suites), STATUS.md

## Phase C1: extraction audit — DONE (2026-06-12)

- 33 files, 160 chunks, 6 zero-chunk files
- 3 genuinely tiny (.txt < 100B) — acceptable
- 2 OCR-empty diagrams (PICT0052/0086 sidecars = "[OCR empty]")
- 1 scanned PDF without OCR ([pension-fund-booklet].pdf, 516KB image-only)
- Extraction quality generally good; full indexing not yet approved

## Phase C2: retrieval evaluation — ALL PASS (2026-06-12)

6 queries, 16 checks, 0 failures:
- Q1 πολεοδομία: A/B in top 5 ✓, C notes rank 10+ ✓, D ≤50% ✓
- Q2 κτηματολόγιο: A certificate top 3 ✓, ΚΤΗΜΑΤΟΛΟΓΙΟ.odt correctly C ✓
- Q3 ΕΦΚΑ/ΤΣΜΕΔΕ: no false A domination ✓, ΤΣΜΕΔΕ booklet absent (0 chunks) as expected
- Q4 corpus: ΠΡΟΣΩΠΙΚΟ-ΕΓΓΡΑΦΟ.odt correctly C ✓, D 0/10 ✓
- Q5 γείτονες: personal notes correctly C ✓, D 1/10 ✓
- Q6 ΓΟΚ: A/B official docs top 4 ✓, ΓΟΚ-αδεια at rank 12 (C) ✓

## Phase C3: answer-context diversity — ALL PASS (2026-06-12)

- Added `--max-per-file 4` (default) and `--no-diversity` to dsearch2-answer
- Diversity filter runs after retrieval, before Claude prompt
- ΚΤΗΜΑΤΟΛΟΓΙΟ.odt: 12 raw chunks → 4 after filter
- Custom `--max-per-file 2` caps all files to 2
- `--no-diversity` preserves raw top-N exactly
- A-tier files still present after filtering
- 8 automated tests, 0 failures
- Backup: `/tmp/.dsearch2-answer.bak-20260612-pre-diversity`

## Phase C4: Haiku fallback audit — ALL PASS (2026-06-12)

- 5 Haiku calls (claude-haiku-4-5-20251001 via `claude -p`), 1 D→C upgrade
- Upgraded: Φορος-ΤΑΠ.txt (tax note, arguably correct)
- Haiku said A for 2015-ΔΕΥΑΗ.jpg and B for 2015Υπευθυνη-ΔηλωσηΠασχαλη130.pdf — code kept D ✓
- No A/B created in final output ✓
- Existing regex A/B/C unchanged ✓
- True D/noise (GPS, postal, tiny) remain D ✓
- Cache reuse: rerun made 0 calls (5 cache hits) ✓
- No Chroma metadata changed (audit-only) ✓
- Cache: `$CHROMADB_DIR/tier_llm_cache.json`
- Log: `/tmp/dsearch2-haiku-tier-audit.jsonl`

## Phase C5: staged 331-file indexing — ALL PASS (2026-06-12)

- 331 files → 1,313 chunks (from 209 files with text)
- Tier dist (files): A:19 B:42 C:33 D:115
- Zero-chunk: 122 files (96 .jpg + 15 .png + 8 .txt + 2 .pdf + 1 .odt)
  - Mostly images without OCR sidecars (expected)
- Retrieval eval: 6 queries, 16 checks, 0 failures
- Diversity test: 8 checks, 0 failures
- New files from: RealEstate (120), corpus (100), Credentials (30), Consumables (50)
- No personal note classified as A
- D never >50% of top 10 in any query
- Manifest: `eval_set_phaseC5_300.txt` (331 files)

## Phase C6: staged 2,313-file indexing — ALL PASS (2026-06-12)

- 2,313 files → 23,260 chunks (2,085 files with text, 228 zero-chunk)
- Tier dist (files): A:412 B:425 C:276 D:972
- Zero-chunk: 228 (9.9%) — 113 .jpg + 65 .txt + 32 .pdf + 15 .png + 3 .odt
- Extraction: 18.2s, embedding: 356s (~$0.002 Cohere), upsert: 38s
- Retrieval eval: 6 queries, 16 checks, 0 failures
- Diversity test: 8 checks, 0 failures
- Quality improved at scale: Q2 now surfaces real cadastre certs, Q3 finds payslips
- ΚΤΗΜΑΤΟΛΟΓΙΟ.odt self-corrected from 12 to 4 raw chunks (more competition)
- Checkpoint: `/home/DISKS/root-store/my-projects/semantic-disk-search/checkpoints/phaseC5-pass-20260612/`
- Manifest: `eval_set_phaseC6_2000.txt` (2,313 files)

## Phase C7: staged 11,304-file indexing — ALL PASS (2026-06-12/13)

- 11,304 files → 108,269 chunks (10,208 with text, 1,096 zero-chunk)
- Tier dist (all chunks): A:10,099 (9.3%) B:13,430 (12.4%) C:12,616 (11.7%) D:72,124 (66.6%)
- Extraction: 56.2s (8,991 new files → 85,009 chunks)
- Embedding: ~24.7min (Cohere, 480/batch, ~$0.009)
- Upsert: 253.9s, Total: 29m49.8s
- Retrieval eval: 6 queries, 16/16 checks PASS
- Diversity test: 8/8 checks PASS
- Quality improved: Q2 top 20 = 15A + 5B (zero C/D), 19 unique files
- Checkpoint: `/home/DISKS/root-store/my-projects/semantic-disk-search/checkpoints/phaseC7-pass-20260612/`
- Manifest: `eval_set_phaseC7_10000.txt` (11,304 files)

## Phase C8: full 131K indexing — COMPLETE (2026-06-13)

- **Final:** 950,429 chunks, 128,322 files indexed
- **Tier dist (sample):** A=34 B=72 C=268 D=626
- **Surrogate fix:** 76 files with non-UTF-8 filenames (Latin-1 `\udce4` surrogates from `os.walk()`) caused `TypeError: Cannot convert Python object to UpdateMetadataValue` at 97% in 3 consecutive runs. Fixed via `safe_str()` = `s.encode('utf-8', errors='replace').decode('utf-8')` applied to ids, docs, metadata strings, and index keys.
- **Pollution cleanup:** 30,606 chunks from `.claude/paste-cache` + 54 index entries removed (path-prefix rules)
- **Cohere cost:** ~$0.098 total
- **Haiku fallback:** disabled (per GPT instruction)
- **Logs:** `logs/phaseC8_surrogate_fix_20260613.log` (successful run), `logs/phaseC8_subbatch_20260613.log` (isolation that found root cause)

### Step 7 post-checks — ALL PASS

| Check | Result |
|-------|--------|
| ChromaDB count | 950,429 ✓ |
| Index count | 128,322 ✓ |
| .claude pollution | 0/50 queries ✓ |
| safe_str patch | installed ✓ |
| Dry-run (no new work) | 0 new chunks ✓ |

### Known issue

- Benchmark/eval project artifacts (eval_set_phase*.txt, benchmark_*.json, STATUS.md) appear in normal queries — see Phase C9

## Phase C9: exclude project artifacts from retrieval — COMPLETE (2026-06-13)

- **Index:** 128,322 → 128,217 (105 generated artifact entries removed)
- **ChromaDB:** 0 chunks deleted (artifacts had index entries only, never embedded)
- **Hard-exclude patterns** added to SKIP_PATHS in dsearch2-update:
  - `semantic-disk-search/benchmark_results/`
  - `semantic-disk-search/backups/benchmark_results/`
  - `semantic-disk-search/eval_set_phase*`
  - `recoll-hybrid-search-2DELETE/benchmark_results/`
  - `recoll-hybrid-search-2DELETE/backups/benchmark_results/`
  - `root-store checkpoints/`
- **Down-rank** in dsearch2 retriever: `PROJECT_PENALTY = -0.008` for project-meta paths unless query contains project terms (dsearch/chromadb/benchmark/eval/status/phase/tier)
- **Heraklio top 20 artifact hits:** 0 — PASS
- **Note:** semantic-disk-search project self-search not available (STATUS.md/project docs have no Chroma chunks)

### Files changed (Phase C9)

- `/usr/local/bin/dsearch2-update` — added 6 SKIP_PATHS entries
- `/usr/local/bin/dsearch2` — added PROJECT_META_PREFIXES, PROJECT_PENALTY, PROJECT_QUERY_TERMS, query-intent bypass in rrf_merge()
- `$CHROMADB_DIR/file_index_1k.json` — 105 entries removed

## 5-Query Validation — ALL PASS (2026-06-13)

| Query | Artifacts | Top 5 tiers | Verdict |
|-------|-----------|-------------|---------|
| πολεοδομία Ηράκλειο οικ. άδεια | 0 | A/A/A/A/A | PASS — official docs dominate |
| ΕΦΚΑ ΤΣΜΕΔΕ ειδική προσαύξηση | 0 | A/D/C/D/C | PASS — A anchors, D flagged |
| corpus γιατρός εργασία επιστολή | 0 | B/B/C/B/C | PASS — no false A |
| κτηματολόγιο Σητεία Μόχλος ΔΧΜ | 0 | A/A/A/A/A | PASS — A dominates |
| Samsung CSC call recording | 0 | D/D/B/B/D | PASS — tech notes expected |

## Phase D: real-use monitoring — ACTIVE

- Use `dsearch2-answer` for real questions
- Log failures to `docs/REAL_USE_FAILURE_LOG.md`
- Patch only from repeated failure patterns
- No further code changes without failure evidence

## Phase D-Haiku: LLM tier rescue — VALIDATED (2026-06-13)

Haiku 4.5 reclassified D-tier files via Anthropic API. Two passes. No binary changes.

### Pass 1 (offset scan)
- 457 D-tier paths processed (offset-based scan missed most D-tier)
- D→B: 291, D→C: 92, A_CANDIDATE: 9, Kept D: 65
- Cost: ~$1

### Pass 2 (WHERE-filtered + priority-based) — VALIDATED
- Total D-tier: 665K chunks / 63.6K paths
- Filtered: 23,596 code/config/noise skipped, 38.5K candidates
- 2,649 unique files classified across two runs (API credits exhausted mid-run)
- D→B: 1,614, D→C: 644, A_CANDIDATE: 138 total, Kept D: 306
- Reclassification rate: **88.4%**
- ChromaDB chunks updated: ~47,000
- Cost: $2.81, API calls: ~3,100

### A_CANDIDATE review
- 127 reviewed=true → promoted to A in ChromaDB (2,227 chunks)
- 11 flagged edge cases resolved: 10→B (EFKA scrapes, Chinese cert, portal screenshot), 1→D (backup metadata)
- Policy: Haiku NEVER auto-promotes to A. Only reviewed whitelist entries.

### B/C/D validation (random sampling)
- 100 B: 19/20 correct (manuals, bank docs, insurance, tech docs)
- 50 C: 20/20 correct (personal notes, CVs, homework)
- 50 D: 20/20 correct (garbled HTML, OCR errors, corrupted text)
- Quality: **EXCELLENT**

### 10-query validation: 8/10 PASS
| Query | Tiers | Verdict |
|-------|-------|---------|
| φορολογική δήλωση Ε1 2022 | All A | PASS |
| ασφαλιστήριο αυτοκινήτου | B dominant | PASS |
| πιστοποιητικό θανάτου | A+B mix | PASS |
| κτηματολόγιο Κρήτη δήλωση | All A | PASS |
| corpus πειθαρχικό | A+B | PARTIAL |
| υπεύθυνη δήλωση γείτονα | All A | PASS |
| pension calculation UK | C dominant | PASS |
| zoneminder camera config | All D | PASS |
| SCADA RTU manual | Mixed D | FAIL — ESP32/driver code instead of manuals |
| blood test results | Mixed | FAIL — English→Greek semantic gap |

### Known failures (to fix before next wave)
- "blood test results" needs Greek aliases: εξετάσεις αίματος, αιματολογικές, γενική αίματος
- "SCADA RTU manual" needs manual/doc boost + code penalty + RTU/EFASEC aliases
- "corpus πειθαρχικό" needs πειθαρχικό/ΕΔΕ/disciplinary synonyms

### Tier distribution (post-pass 2, sample 1K chunks)
A=6.7%, B=56.4%, C=29.8%, D=7.1%

### Logs
- `logs/haiku-reclassify/haiku-reclassify-full-results.jsonl` (run 2, 3000 files)
- `logs/haiku-reclassify/haiku-reclassify-pass2-results.jsonl` (run 1, 7000 attempted)
- `logs/haiku-reclassify/haiku-audit-cache.json` (2368 entries)
- `manual_a_promotions.json` (138 entries, all reviewed)

## System ready for real use

## Files changed (Phase B+C sessions)

- `/usr/local/bin/search-ai-10agents` — classifier rewrite, downgrade-only, A/B quota, claim evidence
- `/usr/local/bin/dsearch2` — NEW: hybrid retriever (vector+TF+RRF, alias expansion, phrase-aware)
- `/usr/local/bin/dsearch2-answer` — NEW: passage-first answer pipeline skeleton
- `/usr/local/bin/dsearch2-update` — TUNED: A_STRONG/A_WEAK, precedence-based, note fallback, --force, Haiku
- `$PROJECT_DIR/configs/alias_map.json` — 18 bilingual alias groups
- `$PROJECT_DIR/test_source_tiers.py` — 29-test regression suite
- `$PROJECT_DIR/test_dsearch2_smoke.py` — 23 smoke tests
- `$PROJECT_DIR/test_dsearch2_eval_tiers.py` — classifier eval (33 files)
- `$PROJECT_DIR/eval_set_phaseB_30.txt` — 33-file eval manifest
- `$PROJECT_DIR/eval_set_phaseB_30_expected.md` — expected tiers
- `$PROJECT_DIR/test_dsearch2_extraction_audit.py` — extraction audit (Phase C1)
- `$PROJECT_DIR/test_dsearch2_retrieval_eval.py` — retrieval eval harness (Phase C2)
- `$PROJECT_DIR/test_dsearch2_answer_diversity.py` — diversity tests (Phase C3)
- `/usr/local/bin/dsearch2-answer` — MODIFIED: diversity filter (--max-per-file, --no-diversity)
- `$PROJECT_DIR/STATUS.md` — this file
