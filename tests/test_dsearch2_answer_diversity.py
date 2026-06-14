#!$VENV_GTE
"""Phase C3: answer-context diversity tests for dsearch2-answer.

Tests that --max-per-file limits chunk concentration from single files
and that --no-diversity bypasses the cap.

Usage:
    python test_dsearch2_answer_diversity.py [--dsearch2-answer /path/to/dsearch2-answer]
"""
import argparse, json, os, re, subprocess, sys
from collections import Counter

DSEARCH2_ANSWER = '/usr/local/bin/dsearch2-answer'
KTIMATOLOGIO_QUERY = "κτηματολόγιο ΚΑΕΚ τοπογραφικό διάγραμμα"


def run_dry_run(binary, query, top=20, extra_args=None):
    cmd = [binary, query, '--top', str(top), '--dry-run']
    if extra_args:
        cmd.extend(extra_args)
    cp = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return cp.stdout, cp.stderr, cp.returncode


def parse_distribution(output, section_header):
    lines = output.split('\n')
    in_section = False
    dist = {}
    for line in lines:
        if section_header in line:
            in_section = True
            continue
        if in_section:
            line = line.strip()
            if not line or line.startswith('[') or line.startswith('=') or line.startswith('File distribution') or line.startswith('Prompt') or line.startswith('Query') or line.startswith('Aliases') or line.startswith('Raw') or line.startswith('After') or line.startswith('Passages') or line.startswith('Diversity'):
                if dist:
                    break
                continue
            m = re.match(r'(.+?):\s+(\d+)', line)
            if m:
                dist[m.group(1).strip()] = int(m.group(2))
            else:
                break
    return dist


def main():
    parser = argparse.ArgumentParser(description='C3 diversity tests')
    parser.add_argument('--dsearch2-answer', default=DSEARCH2_ANSWER)
    args = parser.parse_args()

    binary = args.dsearch2_answer
    passes = []
    fails = []

    print("Phase C3: Answer-Context Diversity Tests")
    print(f"Binary: {binary}")
    print()

    # Test 1: default diversity limits KTHMATOLOGIO.odt to <=4
    print("Test 1: default diversity (max 4/file)")
    out, err, rc = run_dry_run(binary, KTIMATOLOGIO_QUERY)
    if rc != 0:
        fails.append(f"T1: dsearch2-answer returned {rc}")
    else:
        before = parse_distribution(out, "BEFORE diversity")
        after = parse_distribution(out, "AFTER diversity")
        kthm_before = before.get('ΚΤΗΜΑΤΟΛΟΓΙΟ.odt', 0)
        kthm_after = after.get('ΚΤΗΜΑΤΟΛΟΓΙΟ.odt', 0)

        if kthm_before > 4:
            passes.append(f"T1a: ΚΤΗΜΑΤΟΛΟΓΙΟ.odt raw has {kthm_before} chunks (>4, needs filtering)")
        else:
            passes.append(f"T1a: ΚΤΗΜΑΤΟΛΟΓΙΟ.odt raw has {kthm_before} chunks (already <=4)")

        if kthm_after <= 4:
            passes.append(f"T1b: ΚΤΗΜΑΤΟΛΟΓΙΟ.odt after diversity = {kthm_after} (<=4)")
        else:
            fails.append(f"T1b: ΚΤΗΜΑΤΟΛΟΓΙΟ.odt after diversity = {kthm_after} (>4, expected <=4)")

        if 'Diversity: ON' in out:
            passes.append("T1c: diversity mode ON by default")
        else:
            fails.append("T1c: diversity mode not ON by default")

        cert_after = after.get('ΠΙΣΤΟΠΟΙΗΤΙΚΟ-ΚΤΗΜΑΤΟΓΡΑΦΟΥΜΕΝΟΥ-ΑΚΙΝΗΤΟΥ-320410714006.pdf', 0)
        if cert_after > 0:
            passes.append(f"T1d: A certificate still in filtered results ({cert_after} chunks)")
        else:
            fails.append("T1d: A certificate missing from filtered results")

    # Test 2: --no-diversity preserves raw top 20
    print("\nTest 2: --no-diversity bypass")
    out2, err2, rc2 = run_dry_run(binary, KTIMATOLOGIO_QUERY, extra_args=['--no-diversity'])
    if rc2 != 0:
        fails.append(f"T2: dsearch2-answer returned {rc2}")
    else:
        before2 = parse_distribution(out2, "BEFORE diversity")
        after2 = parse_distribution(out2, "AFTER diversity")

        if before2 == after2:
            passes.append("T2a: before == after (no filtering applied)")
        else:
            fails.append(f"T2a: before != after with --no-diversity (before={before2}, after={after2})")

        if 'Diversity: OFF' in out2:
            passes.append("T2b: diversity mode OFF when --no-diversity")
        else:
            fails.append("T2b: diversity mode not showing OFF")

    # Test 3: custom --max-per-file 2
    print("\nTest 3: --max-per-file 2")
    out3, err3, rc3 = run_dry_run(binary, KTIMATOLOGIO_QUERY, extra_args=['--max-per-file', '2'])
    if rc3 != 0:
        fails.append(f"T3: dsearch2-answer returned {rc3}")
    else:
        after3 = parse_distribution(out3, "AFTER diversity")
        max_any = max(after3.values()) if after3 else 0
        if max_any <= 2:
            passes.append(f"T3: all files <=2 chunks after --max-per-file 2 (max was {max_any})")
        else:
            fails.append(f"T3: max chunks = {max_any} (expected <=2, dist={after3})")

    # Test 4: Q1 poleodomia with diversity still has A in results
    print("\nTest 4: poleodomia query with diversity preserves A docs")
    out4, err4, rc4 = run_dry_run(binary, "πολεοδομία Ηράκλειο οικοδομική άδεια")
    if rc4 != 0:
        fails.append(f"T4: dsearch2-answer returned {rc4}")
    else:
        after4 = parse_distribution(out4, "AFTER diversity")
        a_files = ['PICT0090.jpg', 'ΟικοδομικηΑδεια2016b.pdf']
        found_a = any(f in after4 for f in a_files)
        if found_a:
            passes.append("T4: A-tier files still present after diversity filter")
        else:
            fails.append(f"T4: no A-tier files in filtered results: {after4}")

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for p in passes:
        print(f"  ✓ {p}")
    for f in fails:
        print(f"  ✗ {f}")
    print(f"\nTotal: {len(passes)} pass, {len(fails)} fail")
    overall = "ALL PASS" if not fails else f"{len(fails)} FAILURES"
    print(f"Overall: {overall}")
    sys.exit(0 if not fails else 1)


if __name__ == '__main__':
    main()
