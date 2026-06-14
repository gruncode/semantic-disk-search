#!$VENV_GTE
"""Classifier-only evaluation test for dsearch2-update tier system.
Reads eval_set_phaseB_30.txt + eval_set_phaseB_30_expected.md,
runs classify_source_tier() on each file, compares actual vs expected.
Prints confusion matrix and per-file results.

Usage:
    python test_dsearch2_eval_tiers.py [--dsearch2-update /path/to/dsearch2-update]
"""
import argparse, importlib.machinery, importlib.util, json, os, re, sys

EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
EVAL_FILES = os.path.join(EVAL_DIR, 'eval_set_phaseB_30.txt')
EVAL_EXPECTED = os.path.join(EVAL_DIR, 'eval_set_phaseB_30_expected.md')

def load_dsearch2_update(path):
    """Import dsearch2-update as a module to access its functions."""
    loader = importlib.machinery.SourceFileLoader('dsearch2_update', path)
    spec = importlib.util.spec_from_loader('dsearch2_update', loader, origin=path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules['dsearch2_update'] = mod
    # prevent main() from running during import
    old_argv = sys.argv
    sys.argv = ['dsearch2-update', '--status']
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass
    finally:
        sys.argv = old_argv
    return mod

def parse_expected_tiers(md_path):
    """Parse eval_set_phaseB_30_expected.md → {filename: expected_tier}."""
    expected = {}
    current_tier = None
    with open(md_path) as f:
        for line in f:
            m = re.match(r'^## ([ABCD]) —', line)
            if m:
                current_tier = m.group(1)
                continue
            m = re.match(r'^\| ([ABCD]) \|.*\|\s*(\S+)\s*\|', line)
            if m and current_tier:
                tier = m.group(1)
                fname = m.group(2)
                expected[fname] = tier
    return expected

def main():
    parser = argparse.ArgumentParser(description='Classifier-only eval test')
    parser.add_argument('--dsearch2-update', default='/tmp/dsearch2-update',
                        help='path to dsearch2-update script (default: /tmp/dsearch2-update)')
    parser.add_argument('--debug', action='store_true', help='show classifier debug output')
    parser.add_argument('--llm-tier-fallback', action='store_true',
                        help='enable Haiku LLM fallback for D-tier files')
    parser.add_argument('--llm-tier-log', type=str, default=None,
                        help='JSONL log path for LLM tier calls')
    parser.add_argument('--llm-tier-cache', type=str, default=None,
                        help='JSON cache path for LLM tier results')
    args = parser.parse_args()

    if args.debug:
        os.environ['DSEARCH2_DEBUG'] = '1'

    mod = load_dsearch2_update(args.dsearch2_update)

    if args.llm_tier_fallback:
        if args.llm_tier_cache and os.path.exists(args.llm_tier_cache):
            with open(args.llm_tier_cache) as f:
                mod._LLM_TIER_CACHE.update({k: tuple(v) for k, v in json.load(f).items()})
            print(f'Loaded LLM cache: {len(mod._LLM_TIER_CACHE)} entries from {args.llm_tier_cache}')
        mod._LLM_TIER_LOG.clear()

    with open(EVAL_FILES) as f:
        paths = [line.strip() for line in f if line.strip()]

    expected = parse_expected_tiers(EVAL_EXPECTED)

    tiers = ['A', 'B', 'C', 'D']
    confusion = {e: {a: 0 for a in tiers} for e in tiers}
    results = []
    match = 0
    total = 0
    skip = 0

    for path in paths:
        fname = os.path.basename(path)
        if fname not in expected:
            print(f'  SKIP (no expected tier): {fname}')
            skip += 1
            continue
        exp = expected[fname]
        ext = os.path.splitext(fname)[1].lower()

        if not os.path.exists(path):
            print(f'  SKIP (file missing): {path}')
            skip += 1
            continue

        text = mod.extract_text(path)
        text = text.encode('utf-8', errors='ignore').decode('utf-8').strip()

        actual, evidence = mod.classify_source_tier(path, fname, ext, text,
                                                     llm_fallback=args.llm_tier_fallback)
        ok = actual == exp
        # accept A or B for permit-folder scans expected as A
        acceptable = ok or (exp == 'A' and actual == 'B')
        if ok:
            match += 1
        total += 1
        confusion[exp][actual] += 1
        mark = '  OK' if ok else (' ~OK' if acceptable else ' FAIL')
        results.append((fname, exp, actual, evidence, mark))

    print(f'\n{"="*72}')
    print(f'CLASSIFIER EVAL: {match}/{total} exact match ({match/total*100:.0f}%)')
    acceptable_count = sum(1 for _, e, a, _, _ in results if e == a or (e == 'A' and a == 'B'))
    print(f'ACCEPTABLE (A↔B ok): {acceptable_count}/{total} ({acceptable_count/total*100:.0f}%)')
    if skip:
        print(f'SKIPPED: {skip}')

    print(f'\n{"─"*72}')
    print(f'{"File":<45} {"Exp":>3} {"Act":>3} {"":>5}  Evidence')
    print(f'{"─"*72}')
    for fname, exp, actual, evidence, mark in sorted(results, key=lambda x: x[1]):
        print(f'{fname[:44]:<45} {exp:>3} {actual:>3} {mark:>5}  {evidence[:40]}')

    print(f'\n{"─"*72}')
    print('Confusion matrix (rows=expected, cols=actual):')
    print(f'{"":>8}', end='')
    for t in tiers:
        print(f'{t:>6}', end='')
    print()
    for exp in tiers:
        print(f'{exp:>8}', end='')
        for act in tiers:
            v = confusion[exp][act]
            print(f'{v:>6}', end='')
        print()

    # required fixes check
    print(f'\n{"─"*72}')
    print('Required fixes:')
    required = {
        'ΚΤΗΜΑΤΟΛΟΓΙΟ.odt': 'C',
        'ερωτησεις.odt': 'C',
        'γειτονες.odt': 'C',
        'Σταδια.odt': 'C',
        'ΓΟΚ-αδεια-ηλεκτροδοτηση.odt': 'C',
        'ΠΡΟΣΩΠΙΚΟ-ΕΓΓΡΑΦΟ.odt': 'C',
    }
    required_ab = ['PICT0047.jpg', 'PICT0095.jpg', 'PICT0088.jpg']
    all_pass = True
    for fname, req_tier in required.items():
        found = [r for r in results if r[0] == fname]
        if found:
            actual = found[0][2]
            ok = actual == req_tier
            print(f'  {fname:<45} need={req_tier} got={actual} {"PASS" if ok else "FAIL"}')
            if not ok:
                all_pass = False
        else:
            print(f'  {fname:<45} NOT FOUND')
            all_pass = False
    for fname in required_ab:
        found = [r for r in results if r[0] == fname]
        if found:
            actual = found[0][2]
            ok = actual in ('A', 'B')
            print(f'  {fname:<45} need=A/B got={actual} {"PASS" if ok else "FAIL"}')
            if not ok:
                all_pass = False
        else:
            print(f'  {fname:<45} NOT FOUND')
            all_pass = False

    print(f'\n{"="*72}')
    print(f'REQUIRED FIXES: {"ALL PASS" if all_pass else "SOME FAIL"}')

    if args.llm_tier_fallback:
        print(f'\n{"─"*72}')
        print('LLM TIER FALLBACK AUDIT:')
        log = mod._LLM_TIER_LOG
        cache = mod._LLM_TIER_CACHE
        d_files = [r for r in results if r[2] == 'D' or 'llm-upgrade' in r[3]]
        upgraded = [r for r in results if 'llm-upgrade' in r[3]]
        haiku_ab = [r for r in results if r[3].startswith('llm-upgrade') and r[2] in ('A', 'B')]
        print(f'  D-tier files (regex): {len([r for r in results if "no strong markers" in r[3] or "llm-upgrade" in r[3]])}')
        print(f'  Haiku calls made: {len(log)}')
        print(f'  D→C upgrades: {len(upgraded)}')
        print(f'  Cache entries: {len(cache)}')
        if haiku_ab:
            print(f'  WARNING: Haiku produced A/B in final: {[(r[0], r[2]) for r in haiku_ab]}')
        else:
            print(f'  No A/B from Haiku (correct)')
        for r in upgraded:
            print(f'    UPGRADED: {r[0]} → {r[2]} ({r[3]})')
        for entry in log:
            print(f'    LOG: {os.path.basename(entry.get("path","?"))} '
                  f'haiku={entry.get("llm_tier","?")} '
                  f'excerpt={entry.get("excerpt_len",0)} chars')

        if args.llm_tier_cache:
            serializable = {k: list(v) for k, v in cache.items()}
            with open(args.llm_tier_cache, 'w') as f:
                json.dump(serializable, f, ensure_ascii=False, indent=2)
            print(f'  Cache saved: {len(cache)} entries → {args.llm_tier_cache}')

        if args.llm_tier_log:
            with open(args.llm_tier_log, 'a') as f:
                for entry in log:
                    entry['final_tier'] = 'C' if entry.get('llm_tier') == 'C' else 'D'
                    f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            print(f'  Log saved: {len(log)} entries → {args.llm_tier_log}')

    return 0 if all_pass else 1

if __name__ == '__main__':
    sys.exit(main())
