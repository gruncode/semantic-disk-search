# Recoll Query Assist — Experiment Log

## Setup
- Golden set: `/tmp/recoll_golden_set_v3.json` (38 queries, 3 tiers)
- Tuning set: `/tmp/golden_tuning.json` (26 queries, 70%)
- Canary set: `/tmp/golden_canary.json` (12 queries, 30%)
- Code: `/tmp/recoll_query_assist.py`
- Benchmark: `/tmp/recoll_benchmark.py`

## Baseline (current code with all prior changes)
- Date: 2026-03-23
- Tuning MRR: 0.605, R@1=53.8%, R@5=69.2%, Hits=20/26
- Canary MRR: 0.718, R@1=58.3%, R@3=83.3%, R@10=91.7%, Hits=11/12 (checked after exp6)

## Experiments

| # | Change | Tuning MRR | Tuning R@1 | Delta | Accept? |
|---|--------|-----------|-----------|-------|---------|
| 1 | Fix rent domain: `μισθ`→`μισθωσ` prefix to avoid salary false match | 0.610 | 53.8% | +0.005 MRR, +1 hit (salary_corpus MISS→@7) | YES |
| 2 | Add `-o` (ANY term) recollq variant for raw query | 0.610 | 53.8% | +0.000 (poleodomia still not surfaced — ANY finds it but scorer ranks others higher) | NO — reverted |
| 3 | Wildcard `filename:stem*` for Greek words ≥6 chars | 0.609 | 53.8% | -0.001 (wildcards bring too many irrelevant matches) | NO — reverted |
| 4 | Add Greek stopwords (articles, pronouns, prepositions, common verbs) | 0.616 | 53.8% | +0.006 MRR, +1 hit (teaching_schedule MISS→@7), R@10 80.8→84.6% | YES |
| 5 | Remove `λογαριασμ` from banking prefix triggers (ambiguous word) | 0.616 | 53.8% | +0.000 (deh_2ari still fails — no domain → generic handler also misses) | NO — reverted |
| 6 | Expand filename: queries to 6 anchors (was 4) | 0.616 | 53.8% | +0.000 (filename:δεη returns ΔΕΗ files but not the specific one) | NO — reverted |
| 7 | Claude subscription (`claude -p`) for query planning — replaces OpenAI, adds filename_terms, Greek/English expansion | **0.718** | **61.5%** | **+0.102 MRR, +7.7% R@1, +15.4% R@3**, tax→1.0, health→0.89 | **YES** |
| 8 | Use plan anchors as `dir:` scopes (names/places are often folder names) | **0.726** | 61.5% | +0.008 MRR, R@5→88.5%, R@10→92.3%, poleodomia MISS→@1, antikimenikes MISS→@1 | **YES** |
| 9 | Merge Claude + heuristic plans (absorb heuristic terms into LLM plan) | 0.610 | 50.0% | **-0.116 MRR** regression — heuristic generic terms dilute Claude's focused plan | **NO — reverted** |
| 10 | RRF fusion with vector_weight=0.8 (sample set) | 0.718 | 53.8% | -0.103 MRR — vector re-ranking hurts BM25 precision | NO |
| 11 | RRF with vector_weight=0.3 (sample set) | 0.692 | 46.2% | Still hurts — RRF itself reorders regardless of weight | NO |
| 12 | RRF with vector_weight=0.15 (sample set) | 0.686 | 46.2% | Same issue — any RRF re-ranking degrades BM25 | NO |
| 13 | **vector_augment** (append vector-only results, don't re-rank BM25) | **0.862** | **76.9%** | **+0.041 MRR, +7.7% R@1, R@5=100%** — preserves BM25 precision, adds semantic recall | **YES** |
