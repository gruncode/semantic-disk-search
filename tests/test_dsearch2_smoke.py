#!/usr/bin/env python3
"""Smoke tests for dsearch2 and dsearch2-answer.
Safe: no indexing, no v1 modifications, no Claude calls.
Run: python3 test_dsearch2_smoke.py
"""
import subprocess, json, sys

passed = 0
failed = 0
errors = []

def run(cmd, timeout=15):
    cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return cp.returncode, cp.stdout, cp.stderr

def check(label, ok, detail=''):
    global passed, failed
    if ok:
        passed += 1
        print(f'  PASS  {label}')
    else:
        failed += 1
        msg = f'  FAIL  {label}: {detail}'
        errors.append(msg)
        print(msg)

# ── dsearch2 tests ──────────────────────────────────────────────────────────

print('=== dsearch2 CLI ===')

rc, out, err = run(['dsearch2', '--help'])
check('--help exits 0', rc == 0)
check('--help shows usage', 'usage: dsearch2' in out)

rc, out, err = run(['dsearch2', '--show-aliases'])
check('--show-aliases exits 0', rc == 0)
check('--show-aliases shows groups', 'alias groups loaded' in out)
check('--show-aliases has poleodomia', 'poleodomia' in out)

rc, out, err = run(['dsearch2', '--json', 'πολεοδομία', 'Ηράκλειο', 'οικοδομική', 'άδεια'])
check('query exits 0', rc == 0)
data = json.loads(out)
check('JSON has query_original', 'query_original' in data)
check('JSON has query_expanded', 'query_expanded' in data)
check('JSON has aliases_used', 'aliases_used' in data)
check('JSON has results', 'results' in data)
check('0 results (empty collection)', data.get('total_results', -1) == 0)

# multi-word alias expansion
aliases = data.get('aliases_used', [])
check('πολεοδομία group expanded', 'poleodomia' in aliases, f'aliases={aliases}')
check('οικ.άδεια group expanded', 'building permit' in aliases, f'aliases={aliases}')
check('aliases sorted (deterministic)', aliases == sorted(aliases), f'aliases={aliases}')

# --no-alias
rc, out, err = run(['dsearch2', '--json', '--no-alias', 'poleodomia'])
data2 = json.loads(out)
check('--no-alias: no aliases', len(data2.get('aliases_used', [])) == 0)

# ── dsearch2-answer tests ──────────────────────────────────────────────────

print('\n=== dsearch2-answer CLI ===')

rc, out, err = run(['dsearch2-answer', '--help'])
check('--help exits 0', rc == 0)
check('--help shows usage', 'usage: dsearch2-answer' in out)

rc, out, err = run(['dsearch2-answer', '--json', 'πολεοδομία'])
check('empty query exits 0', rc == 0)
data3 = json.loads(out)
check('JSON has answer field', 'answer' in data3)
check('JSON has passages field', 'passages' in data3)
check('JSON has passages_used field', 'passages_used' in data3)
check('passages_used = 0', data3.get('passages_used', -1) == 0)
check('answer mentions 0 chunks', '0 chunks' in data3.get('answer', ''))

# ── Summary ─────────────────────────────────────────────────────────────────

print(f'\n{"="*60}')
print(f'RESULTS: {passed} passed, {failed} failed')
if errors:
    print('\nFAILURES:')
    for e in errors:
        print(e)
    sys.exit(1)
else:
    print('ALL TESTS PASSED')
    sys.exit(0)
