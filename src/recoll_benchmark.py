#!/usr/bin/env python3
"""
Recoll Query Assist Benchmark Harness

Runs a golden set of queries against recoll_query_assist.py,
measures retrieval quality with MRR, Recall@K, Precision@K,
and produces a per-query + aggregate scorecard.

Usage:
    python3 /tmp/recoll_benchmark.py [--golden /tmp/recoll_golden_set.json] [--top 12] [--verbose]
    python3 /tmp/recoll_benchmark.py --compare baseline.json improved.json
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPT = '$PROJECT_DIR/src/recoll_query_assist.py'
DEFAULT_GOLDEN = '$PROJECT_DIR/golden_sets/full_38q.json'
RESULTS_DIR = '$PROJECT_DIR/benchmark_results'


def run_query(query, top=12, conf=None, faiss_dir=None):
    """Run recoll_query_assist.py with --json and return parsed result."""
    cmd = [sys.executable, SCRIPT, query, '--json', '--top', str(top)]
    if conf:
        cmd.extend(['--conf', conf])
    if faiss_dir:
        cmd.extend(['--faiss-dir', faiss_dir])
    try:
        cp = subprocess.run(cmd, capture_output=True, timeout=120)
        stdout = cp.stdout.decode('utf-8', errors='replace')
        stderr = cp.stderr.decode('utf-8', errors='replace')
        if cp.returncode != 0:
            return None, stderr
        # Find the JSON object in stdout (skip any stderr lines that leaked)
        # The JSON output starts with {
        json_start = stdout.find('{')
        if json_start == -1:
            return None, f'No JSON in output: {stdout[:500]}'
        return json.loads(stdout[json_start:]), stderr
    except subprocess.TimeoutExpired:
        return None, 'TIMEOUT'
    except json.JSONDecodeError as e:
        return None, f'JSON parse error: {e}'
    except Exception as e:
        return None, str(e)


def evaluate_query(test_case, result):
    """Evaluate a single query result against expected patterns.

    Returns dict with:
      - hit_at: rank (1-based) of first matching file, or None
      - matched_pattern: which pattern matched
      - matched_file: the file path that matched
      - top_files: list of top result paths
      - folder_hit: whether any result is in expected folder
      - noise_count: how many top-5 results look noisy
    """
    expected_patterns = test_case.get('expected_patterns', []) or test_case.get('acceptable_patterns', [])
    expected_folders = test_case.get('expected_folders', [])

    # Extract file paths from candidates and best_files
    candidates = result.get('candidates', [])
    best_files = (result.get('final', {}) or {}).get('best_files', [])

    # Build ordered list of result paths (candidates are already ranked by score)
    result_paths = []
    for c in candidates:
        p = c.get('path', '')
        if p and p not in result_paths:
            result_paths.append(p)
    # Also check best_files
    for bf in best_files:
        p = bf.get('path', '')
        if p and p not in result_paths:
            result_paths.append(p)

    # Find first hit
    hit_at = None
    matched_pattern = None
    matched_file = None
    for rank, path in enumerate(result_paths, 1):
        path_lower = path.lower()
        for pat in expected_patterns:
            pat_lower = pat.lower()
            if pat_lower in path_lower:
                hit_at = rank
                matched_pattern = pat
                matched_file = path
                break
        if hit_at is not None:
            break

    # Folder hit check
    folder_hit = False
    for path in result_paths[:5]:
        for folder in expected_folders:
            if folder.lower() in path.lower():
                folder_hit = True
                break
        if folder_hit:
            break

    # Noise check (top-5)
    noise_bits = ['.trash-', 'demo', 'guide', 'sample', 'removedpath',
                  'fileschanged', '/messages2', '/spaces2', '/spaces3']
    noise_count = 0
    for path in result_paths[:5]:
        path_lower = path.lower()
        if any(nb in path_lower for nb in noise_bits):
            noise_count += 1

    return {
        'hit_at': hit_at,
        'matched_pattern': matched_pattern,
        'matched_file': matched_file,
        'top_files': result_paths[:5],
        'folder_hit': folder_hit,
        'noise_count': noise_count,
        'num_results': len(result_paths),
    }


def compute_metrics(evaluations):
    """Compute aggregate metrics from all evaluations."""
    n = len(evaluations)
    if n == 0:
        return {}

    recall_at = {1: 0, 3: 0, 5: 0, 10: 0}
    mrr_sum = 0.0
    noise_total = 0
    folder_hits = 0
    total_results = 0

    for ev in evaluations:
        hit = ev['hit_at']
        if hit is not None:
            mrr_sum += 1.0 / hit
            for k in recall_at:
                if hit <= k:
                    recall_at[k] += 1
        if ev['folder_hit']:
            folder_hits += 1
        noise_total += ev['noise_count']
        total_results += ev['num_results']

    metrics = {
        'num_queries': n,
        'MRR': round(mrr_sum / n, 4),
        'Recall@1': round(recall_at[1] / n, 4),
        'Recall@3': round(recall_at[3] / n, 4),
        'Recall@5': round(recall_at[5] / n, 4),
        'Recall@10': round(recall_at[10] / n, 4),
        'folder_hit_rate': round(folder_hits / n, 4),
        'avg_noise_top5': round(noise_total / n, 4),
        'avg_results': round(total_results / n, 2),
        'hits': recall_at[10],
        'misses': n - recall_at[10],
    }
    return metrics


def compute_domain_metrics(evaluations, test_cases):
    """Compute metrics broken down by domain."""
    by_domain = {}
    for ev, tc in zip(evaluations, test_cases):
        domain = tc.get('domain', 'unknown')
        if domain not in by_domain:
            by_domain[domain] = []
        by_domain[domain].append(ev)
    return {d: compute_metrics(evs) for d, evs in by_domain.items()}


def print_scorecard(metrics, domain_metrics, evaluations, test_cases, verbose=False):
    """Print a human-readable scorecard."""
    print('\n' + '=' * 70)
    print('  RECOLL QUERY ASSIST BENCHMARK SCORECARD')
    print('=' * 70)
    print(f'  Date:       {dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'  Queries:    {metrics["num_queries"]}')
    print(f'  MRR:        {metrics["MRR"]:.4f}')
    print(f'  Recall@1:   {metrics["Recall@1"]:.1%} ({int(metrics["Recall@1"] * metrics["num_queries"])}/{metrics["num_queries"]})')
    print(f'  Recall@3:   {metrics["Recall@3"]:.1%}')
    print(f'  Recall@5:   {metrics["Recall@5"]:.1%}')
    print(f'  Recall@10:  {metrics["Recall@10"]:.1%}')
    print(f'  Folder hit: {metrics["folder_hit_rate"]:.1%}')
    print(f'  Avg noise:  {metrics["avg_noise_top5"]:.2f} per query (top-5)')
    print(f'  Hits/Miss:  {metrics["hits"]}/{metrics["misses"]}')
    print('-' * 70)

    # Domain breakdown
    print('\n  DOMAIN BREAKDOWN:')
    for domain, dm in sorted(domain_metrics.items()):
        print(f'    {domain:12s}  MRR={dm["MRR"]:.3f}  R@1={dm["Recall@1"]:.0%}  R@3={dm["Recall@3"]:.0%}  R@5={dm["Recall@5"]:.0%}  n={dm["num_queries"]}')

    # Per-query results
    print('\n  PER-QUERY RESULTS:')
    print(f'  {"ID":<35s} {"Hit@":<6s} {"Domain":<12s} {"Diff":<6s} {"Status"}')
    print('  ' + '-' * 70)
    for ev, tc in zip(evaluations, test_cases):
        hit = ev['hit_at']
        status = f'@{hit}' if hit else 'MISS'
        icon = '✓' if hit and hit <= 3 else ('~' if hit else '✗')
        print(f'  {tc["id"]:<35s} {status:<6s} {tc["domain"]:<12s} {tc.get("difficulty", tc.get("tier","?")):<6s} {icon}')
        if verbose and hit is None:
            print(f'    Expected: {(tc.get("expected_patterns") or tc.get("acceptable_patterns", []))[:3]}')
            print(f'    Got:      {[os.path.basename(p) for p in ev["top_files"][:3]]}')

    # Failures detail
    failures = [(ev, tc) for ev, tc in zip(evaluations, test_cases) if ev['hit_at'] is None]
    if failures:
        print(f'\n  FAILURES ({len(failures)}):')
        for ev, tc in failures:
            print(f'    {tc["id"]}: query="{tc["query"][:60]}"')
            print(f'      expected: {(tc.get("expected_patterns") or tc.get("acceptable_patterns", []))[:2]}')
            top3 = [os.path.basename(p) for p in ev['top_files'][:3]]
            print(f'      got top3: {top3}')

    # Late hits (found but not in top-3)
    late_hits = [(ev, tc) for ev, tc in zip(evaluations, test_cases) if ev['hit_at'] and ev['hit_at'] > 3]
    if late_hits:
        print(f'\n  LATE HITS (found but rank > 3):')
        for ev, tc in late_hits:
            print(f'    {tc["id"]}: rank={ev["hit_at"]} file={os.path.basename(ev["matched_file"] or "")}')

    print('\n' + '=' * 70)


def compare_runs(file1, file2):
    """Compare two benchmark result files."""
    with open(file1) as f:
        r1 = json.load(f)
    with open(file2) as f:
        r2 = json.load(f)

    m1 = r1['metrics']
    m2 = r2['metrics']

    print('\n' + '=' * 70)
    print('  BENCHMARK COMPARISON')
    print('=' * 70)
    print(f'  {"Metric":<20s} {"Before":<12s} {"After":<12s} {"Delta":<12s}')
    print('  ' + '-' * 56)
    for key in ['MRR', 'Recall@1', 'Recall@3', 'Recall@5', 'Recall@10', 'folder_hit_rate', 'avg_noise_top5']:
        v1 = m1.get(key, 0)
        v2 = m2.get(key, 0)
        delta = v2 - v1
        sign = '+' if delta > 0 else ''
        better = '↑' if (delta > 0 and key != 'avg_noise_top5') or (delta < 0 and key == 'avg_noise_top5') else ('↓' if delta != 0 else '=')
        print(f'  {key:<20s} {v1:<12.4f} {v2:<12.4f} {sign}{delta:<10.4f} {better}')

    # Per-query comparison
    ev1 = {e['id']: e for e in r1.get('per_query', [])}
    ev2 = {e['id']: e for e in r2.get('per_query', [])}
    improved = []
    regressed = []
    for qid in ev1:
        if qid in ev2:
            h1 = ev1[qid].get('hit_at')
            h2 = ev2[qid].get('hit_at')
            if h1 is None and h2 is not None:
                improved.append((qid, h1, h2))
            elif h1 is not None and h2 is None:
                regressed.append((qid, h1, h2))
            elif h1 is not None and h2 is not None and h2 < h1:
                improved.append((qid, h1, h2))
            elif h1 is not None and h2 is not None and h2 > h1:
                regressed.append((qid, h1, h2))

    if improved:
        print(f'\n  IMPROVED ({len(improved)}):')
        for qid, h1, h2 in improved:
            print(f'    {qid}: {h1 or "MISS"} → {h2}')
    if regressed:
        print(f'\n  REGRESSED ({len(regressed)}):')
        for qid, h1, h2 in regressed:
            print(f'    {qid}: {h1} → {h2 or "MISS"}')
    if not improved and not regressed:
        print('\n  No per-query changes detected.')
    print('=' * 70)


def run_benchmark(golden_path, top=12, conf=None, faiss_dir=None, verbose=False, tag=None):
    """Run full benchmark and return results dict."""
    with open(golden_path) as f:
        test_cases = json.load(f)

    evaluations = []
    errors = []
    total = len(test_cases)

    for i, tc in enumerate(test_cases, 1):
        qid = tc['id']
        query = tc['query']
        sys.stderr.write(f'\r  [{i}/{total}] {qid:<40s}')
        sys.stderr.flush()

        t0 = time.time()
        result, stderr = run_query(query, top=top, conf=conf, faiss_dir=faiss_dir)
        elapsed = time.time() - t0

        if result is None:
            errors.append({'id': qid, 'error': stderr})
            ev = {
                'hit_at': None, 'matched_pattern': None, 'matched_file': None,
                'top_files': [], 'folder_hit': False, 'noise_count': 0,
                'num_results': 0,
            }
        else:
            ev = evaluate_query(tc, result)

        ev['id'] = qid
        ev['elapsed'] = round(elapsed, 2)
        evaluations.append(ev)

    sys.stderr.write('\r' + ' ' * 60 + '\r')
    sys.stderr.flush()

    metrics = compute_metrics(evaluations)
    domain_metrics = compute_domain_metrics(evaluations, test_cases)

    print_scorecard(metrics, domain_metrics, evaluations, test_cases, verbose=verbose)

    if errors:
        print(f'\n  ERRORS ({len(errors)}):')
        for err in errors:
            print(f'    {err["id"]}: {err["error"][:200]}')

    # Save results
    os.makedirs(RESULTS_DIR, exist_ok=True)
    tag_str = f'_{tag}' if tag else ''
    ts = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
    result_file = f'{RESULTS_DIR}/benchmark_{ts}{tag_str}.json'
    result_data = {
        'timestamp': ts,
        'tag': tag,
        'golden_file': golden_path,
        'metrics': metrics,
        'domain_metrics': domain_metrics,
        'per_query': evaluations,
        'errors': errors,
    }
    with open(result_file, 'w') as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)
    print(f'\n  Results saved: {result_file}')

    return result_data, result_file


def main():
    ap = argparse.ArgumentParser(description='Recoll Query Assist Benchmark Harness')
    sub = ap.add_subparsers(dest='cmd')

    # Run benchmark
    run_p = sub.add_parser('run', help='Run benchmark')
    run_p.add_argument('--golden', default=DEFAULT_GOLDEN, help='Golden set JSON file')
    run_p.add_argument('--top', type=int, default=12, help='Top-N for recoll_query_assist.py')
    run_p.add_argument('--conf', help='Recoll config dir')
    run_p.add_argument('--faiss-dir', help='FAISS index directory')
    run_p.add_argument('--verbose', '-v', action='store_true', help='Show failure details')
    run_p.add_argument('--tag', help='Tag for this run (e.g. baseline, v2)')

    # Compare
    cmp_p = sub.add_parser('compare', help='Compare two benchmark results')
    cmp_p.add_argument('file1', help='First (before) result JSON')
    cmp_p.add_argument('file2', help='Second (after) result JSON')

    # List past results
    sub.add_parser('list', help='List past benchmark results')

    args = ap.parse_args()

    if args.cmd == 'compare':
        compare_runs(args.file1, args.file2)
    elif args.cmd == 'list':
        rdir = Path(RESULTS_DIR)
        if rdir.exists():
            for f in sorted(rdir.glob('benchmark_*.json')):
                with open(f) as fh:
                    data = json.load(fh)
                m = data.get('metrics', {})
                tag = data.get('tag', '')
                print(f'  {f.name:<45s} MRR={m.get("MRR", 0):.4f}  R@1={m.get("Recall@1", 0):.1%}  R@3={m.get("Recall@3", 0):.1%}  tag={tag}')
        else:
            print('  No benchmark results yet.')
    elif args.cmd == 'run' or args.cmd is None:
        golden = getattr(args, 'golden', DEFAULT_GOLDEN)
        top = getattr(args, 'top', 12)
        conf = getattr(args, 'conf', None)
        faiss_dir = getattr(args, 'faiss_dir', None)
        verbose = getattr(args, 'verbose', False)
        tag = getattr(args, 'tag', None)
        run_benchmark(golden, top=top, conf=conf, faiss_dir=faiss_dir, verbose=verbose, tag=tag)
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
