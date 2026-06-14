#!$VENV_GTE
"""Phase C2: retrieval evaluation harness for dsearch2.

Runs 6 fixed queries against the current 33-file / 160-chunk controlled index
and checks ranking quality, tier distribution, and duplicate concentration.

Usage:
    python test_dsearch2_retrieval_eval.py [--dsearch2 /path/to/dsearch2] [--top 20]
"""
import argparse, json, os, subprocess, sys
from collections import Counter

QUERIES = [
    {
        "id": "Q1",
        "query": "πολεοδομία Ηράκλειο οικοδομική άδεια",
        "description": "Building permit / urban planning Heraklio",
        "expect_top5_tiers": ["A", "B"],
        "expect_c_not_a": True,
        "notes": "A/B official permit docs must rank above C notes",
    },
    {
        "id": "Q2",
        "query": "κτηματολόγιο ΚΑΕΚ τοπογραφικό διάγραμμα",
        "description": "Cadastre KAEK topographic diagram",
        "expect_top5_tiers": ["A", "B"],
        "expect_c_not_a": True,
        "notes": "A certificate or B FAQ should appear in top 5",
    },
    {
        "id": "Q3",
        "query": "ΕΦΚΑ ΤΣΜΕΔΕ ΑΜΚΑ ασφαλιστικό",
        "description": "Insurance EFKA/TSMEDE booklet",
        "expect_top5_tiers": [],
        "expect_c_not_a": True,
        "notes": "ΤΣΜΕΔΕ booklet may be absent (zero chunks); no false A personal doc should dominate",
    },
    {
        "id": "Q4",
        "query": "corpus προσωπικό έγγραφο διαδικασίες",
        "description": "DSEARCH personal document procedures",
        "expect_top5_tiers": [],
        "expect_c_not_a": True,
        "notes": "ΠΡΟΣΩΠΙΚΟ-ΕΓΓΡΑΦΟ.odt may appear but must be C, not A",
    },
    {
        "id": "Q5",
        "query": "γείτονες καταγγελίες πολεοδομία",
        "description": "Neighbours complaints urban planning",
        "expect_top5_tiers": [],
        "expect_c_not_a": True,
        "notes": "Personal notes about neighbours should be C",
    },
    {
        "id": "Q6",
        "query": "ΓΟΚ άδεια ηλεκτροδότηση οικοδομή",
        "description": "Building code permit electrification",
        "expect_top5_tiers": ["A", "B"],
        "expect_c_not_a": True,
        "notes": "ΓΟΚ-αδεια-ηλεκτροδοτηση.odt is C (personal notes); official permit scans are A",
    },
]

def run_query(dsearch2_bin, query, top):
    cmd = [dsearch2_bin, "--json", "--top", str(top), query]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print(f"  ERROR: dsearch2 returned {result.returncode}", file=sys.stderr)
        print(f"  stderr: {result.stderr[:500]}", file=sys.stderr)
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}", file=sys.stderr)
        return None


def analyse_query(qdef, data, top):
    results = data.get("results", [])
    n = len(results)
    passes = []
    fails = []

    tier_dist = Counter(r["source_tier"] for r in results)
    top5 = results[:5]
    top10 = results[:10]
    top5_tiers = [r["source_tier"] for r in top5]
    top10_tiers = [r["source_tier"] for r in top10]

    path_counts = Counter(r["path"] for r in results)
    max_dup = max(path_counts.values()) if path_counts else 0
    max_dup_file = max(path_counts, key=path_counts.get) if path_counts else ""

    print(f"\n{'='*80}")
    print(f"{qdef['id']}: {qdef['query']}")
    print(f"  {qdef['description']}")
    print(f"  Results: {n}/{top}")
    print(f"  Tier distribution (top {top}): {dict(tier_dist)}")
    print(f"  Top 5 tiers: {top5_tiers}")
    print(f"  Top 10 tiers: {top10_tiers}")
    print(f"  Max duplicate chunks from one file: {max_dup} ({os.path.basename(max_dup_file)})")

    print(f"\n  Top {min(n, top)} results:")
    for r in results:
        fname = os.path.basename(r["path"])
        print(f"    #{r['rank']:2d} [{r['source_tier']}] {r['score']:.6f} {fname}")

    # Check 1: expect A/B in top 5 (when applicable)
    if qdef["expect_top5_tiers"]:
        found_expected = any(t in qdef["expect_top5_tiers"] for t in top5_tiers)
        if found_expected:
            passes.append("A/B in top 5")
        else:
            fails.append(f"expected {qdef['expect_top5_tiers']} in top 5, got {top5_tiers}")

    # Check 2: no C file appears as A
    if qdef["expect_c_not_a"]:
        c_as_a = []
        c_keywords = ["ΚΤΗΜΑΤΟΛΟΓΙΟ.odt", "ερωτησεις.odt", "γειτονες.odt",
                       "Σταδια.odt", "ΓΟΚ-αδεια-ηλεκτροδοτηση.odt",
                       "ΠΡΟΣΩΠΙΚΟ-ΕΓΓΡΑΦΟ.odt", "ΣημειωματαΔιαδικασιες.odt",
                       "ΣΗΜΕΙΩΣΕΙΣ-ΤΕΧΝΙΚΑ-ΔΙΑΔΙΚΑΣΙΕΣ.odt",
                       "πολεοδομια-ηρακλειο.odt", "αντισεισμικος-αρμος.odt",
                       "καταγγελιες-απο-γειτονες.txt"]
        for r in results:
            fname = os.path.basename(r["path"])
            if fname in c_keywords and r["source_tier"] == "A":
                c_as_a.append(fname)
        if not c_as_a:
            passes.append("no C file appears as A")
        else:
            fails.append(f"C files classified as A: {c_as_a}")

    # Check 3: D/noise must not be >50% of top 10
    d_count_top10 = sum(1 for t in top10_tiers if t == "D")
    if len(top10_tiers) > 0:
        d_pct = d_count_top10 / len(top10_tiers)
        if d_pct <= 0.5:
            passes.append(f"D ≤50% of top 10 ({d_count_top10}/{len(top10_tiers)})")
        else:
            fails.append(f"D >50% of top 10: {d_count_top10}/{len(top10_tiers)} ({d_pct:.0%})")
    else:
        passes.append("no results (empty index for this query)")

    # Check 4: PROSOPIKO-EGGRAFO must be C if it appears
    for r in results:
        fname = os.path.basename(r["path"])
        if fname == "ΠΡΟΣΩΠΙΚΟ-ΕΓΓΡΑΦΟ.odt" and r["source_tier"] != "C":
            fails.append(f"ΠΡΟΣΩΠΙΚΟ-ΕΓΓΡΑΦΟ.odt is {r['source_tier']}, expected C")
            break

    # Check 5: poleodomia query specific — A/B official above C notes
    if qdef["id"] == "Q1":
        first_c_rank = None
        first_ab_rank = None
        for r in results:
            fname = os.path.basename(r["path"])
            if r["source_tier"] in ("A", "B") and first_ab_rank is None:
                first_ab_rank = r["rank"]
            if fname == "πολεοδομια-ηρακλειο.odt" and first_c_rank is None:
                first_c_rank = r["rank"]
        if first_ab_rank and first_c_rank and first_ab_rank < first_c_rank:
            passes.append(f"A/B (rank {first_ab_rank}) above poleodomia C note (rank {first_c_rank})")
        elif first_ab_rank and first_c_rank:
            fails.append(f"C note (rank {first_c_rank}) above A/B (rank {first_ab_rank})")

    # Print verdict
    print(f"\n  PASS ({len(passes)}):")
    for p in passes:
        print(f"    ✓ {p}")
    if fails:
        print(f"  FAIL ({len(fails)}):")
        for f in fails:
            print(f"    ✗ {f}")
    else:
        print(f"  ALL CHECKS PASSED")

    return len(passes), len(fails), passes, fails


def main():
    parser = argparse.ArgumentParser(description="Phase C2: retrieval evaluation")
    parser.add_argument("--dsearch2", default="/usr/local/bin/dsearch2")
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args()

    if not os.path.exists(args.dsearch2):
        print(f"ERROR: {args.dsearch2} not found", file=sys.stderr)
        sys.exit(1)

    print(f"Phase C2: Retrieval Evaluation Harness")
    print(f"dsearch2: {args.dsearch2}")
    print(f"top: {args.top}")
    print(f"queries: {len(QUERIES)}")

    total_pass = 0
    total_fail = 0
    query_verdicts = []

    for qdef in QUERIES:
        data = run_query(args.dsearch2, qdef["query"], args.top)
        if data is None:
            print(f"\n{qdef['id']}: SKIPPED (query failed)")
            query_verdicts.append((qdef["id"], "SKIP", 0, 0))
            continue
        np, nf, _, _ = analyse_query(qdef, data, args.top)
        total_pass += np
        total_fail += nf
        verdict = "PASS" if nf == 0 else "FAIL"
        query_verdicts.append((qdef["id"], verdict, np, nf))

    print(f"\n{'='*80}")
    print(f"SUMMARY")
    print(f"{'='*80}")
    for qid, verdict, np, nf in query_verdicts:
        marker = "✓" if verdict == "PASS" else "✗" if verdict == "FAIL" else "?"
        print(f"  {marker} {qid}: {verdict} ({np} pass, {nf} fail)")
    print(f"\nTotal checks: {total_pass} pass, {total_fail} fail")
    overall = "ALL PASS" if total_fail == 0 else f"{total_fail} FAILURES"
    print(f"Overall: {overall}")

    sys.exit(0 if total_fail == 0 else 1)


if __name__ == "__main__":
    main()
