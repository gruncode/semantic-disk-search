#!/usr/bin/env python3
"""Regression tests for classify_source_tier() in search-ai-10agents.
Tests strong/weak A split, C-override, a_effective discount, downgrade-only.
Run: python3 test_source_tiers.py

Extracts only the classifier code from search-ai-10agents (avoids heavy deps).
"""
import sys, os, re, unicodedata, ast

# Extract classifier source from the live script
SRC_PATH = '/usr/local/bin/search-ai-10agents'
with open(SRC_PATH) as f:
    full_src = f.read()

# Extract from the tier comment block to end of classify_source_tier function
start_marker = "# C = personal notes/drafts/plans"
end_marker = "    return 'D', 'no strong markers'"
start_idx = full_src.index(start_marker)
end_idx = full_src.index(end_marker, start_idx) + len(end_marker)
classifier_src = full_src[start_idx:end_idx]

# Build execution namespace with needed imports
ns = {'re': re, 'unicodedata': unicodedata, 'os': os}
exec(classifier_src, ns)
classify = ns['classify_source_tier']
TIER_ORDER = ns['TIER_ORDER']

passed = 0
failed = 0
errors = []

def check(label, path, filename, ext, text, expected_tier, must_not_tier=None):
    global passed, failed
    tier, evidence = classify(path, filename, ext, text)
    ok = (tier == expected_tier)
    if must_not_tier and tier == must_not_tier:
        ok = False
    if ok:
        passed += 1
        print(f'  PASS  {label}: tier={tier} ev="{evidence[:60]}"')
    else:
        failed += 1
        msg = f'  FAIL  {label}: got={tier} expected={expected_tier} ev="{evidence[:80]}"'
        errors.append(msg)
        print(msg)

print('=== Test Group 1: Strong A markers → tier A ===')
check('Official doc ΕΛΛΗΝΙΚΗ ΔΗΜΟΚΡΑΤΙΑ + Αρ.Πρωτ',
      '~/Πολεοδομια/βεβαιωση-χρησης.pdf', 'βεβαιωση-χρησης.pdf', '.pdf',
      'ΕΛΛΗΝΙΚΗ ΔΗΜΟΚΡΑΤΙΑ\nΥΠΟΥΡΓΕΙΟ ΠΕΡΙΒΑΛΛΟΝΤΟΣ\nΑρ. Πρωτ: 12345/2024\nΒεβαιώνεται ότι...',
      'A')

check('ΦΕΚ document',
      '~/legal/fek.pdf', 'fek.pdf', '.pdf',
      'ΦΕΚ Α 123/2024\nΕΛΛΗΝΙΚΗ ΔΗΜΟΚΡΑΤΙΑ\nΝ. 5678/2024\nΆρθρο 1',
      'A')

check('Gov email',
      '~/emails/ypourgeio.eml', 'ypourgeio.eml', '.eml',
      'From: info@ypeka.gov.gr\nSubject: Απάντηση\nΑρ. Πρωτ: 999/2024',
      'A')

print('\n=== Test Group 2: Weak A markers only → NOT tier A ===')
check('Notes with Άρθρο+Ν.law+C-markers → not A',
      '~/notes/legal-research.odt', 'legal-research.odt', '.odt',
      'Σύμφωνα με Ν. 4495/2017 Άρθρο 12 και Άρθρο 15\nΠρέπει να ελέγξω τι ισχύει\nΝα ρωτήσω δικηγόρο',
      'D', must_not_tier='A')

check('Phone dir with ΔΗΜΟΣ + C-markers → C not A',
      '~/σημειωσεις/τηλεφωνα.odt', 'τηλεφωνα.odt', '.odt',
      'ΔΗΜΟΣ ΗΡΑΚΛΕΙΟΥ\nΤηλ: 2813-409XXX\nΡώτησα τον Γιάννη\nΜου είπε ότι πρέπει να πάω',
      'C', must_not_tier='A')

print('\n=== Test Group 3: C-markers override weak A ===')
check('Weak A + heavy C → C',
      '~/notes/draft-poleodomia.odt', 'draft-poleodomia.odt', '.odt',
      'Ν. 4495/2017 Άρθρο 12\nΊσως χρειάζεται αυτοψία\nΝα ρωτήσω τον μηχανικό\nΙδέα: να κάνω ένσταση\nTODO: τηλέφωνο',
      'C')

check('ρώτησα + πήρα τηλ + μου είπε → C',
      '~/Περιουσία/σημειωσεις.odt', 'σημειωσεις.odt', '.odt',
      'Ρώτησα στην πολεοδομία\nΠήρα τηλ τον Παπαδόπουλο\nΜου είπε ότι χρειάζεται βεβαίωση\nΆρθρο 12',
      'C', must_not_tier='A')

print('\n=== Test Group 4: Strong A + C markers → A survives ===')
check('ΕΛΛΗΝ.ΔΗΜΟΚΡ + ΠΕΡΙΦΕΡΕΙΑ + Αρ.Πρωτ + Αποφασίζουμε + σημειώσεις',
      '~/Πολεοδομια/αποφαση.pdf', 'αποφαση.pdf', '.pdf',
      'ΕΛΛΗΝΙΚΗ ΔΗΜΟΚΡΑΤΙΑ\nΠΕΡΙΦΕΡΕΙΑ ΑΤΤΙΚΗΣ\nΑρ. Πρωτ: 555/2024\nΑποφασίζουμε\nΣημειώσεις: ...',
      'A')

print('\n=== Test Group 5: B-tier ===')
check('Invoice + IBAN',
      '~/finance/invoice.pdf', 'invoice.pdf', '.pdf',
      'ΤΙΜΟΛΟΓΙΟ ΠΑΡΟΧΗΣ ΥΠΗΡΕΣΙΩΝ\nΑΦΜ: 123456789\nIBAN: GR1234567890',
      'B')

check('Bank contract',
      '~/finance/ethniki.pdf', 'ethniki.pdf', '.pdf',
      'Εθνική Τράπεζα\nΣύμβαση δανείου\nIBAN: GR9876543210',
      'B')

print('\n=== Test Group 6: C-tier ===')
check('Draft with planning language',
      '~/notes/ideas.txt', 'ideas.txt', '.txt',
      'Ιδέα: να αλλάξω δικηγόρο\nΊσως πρέπει να κάνω ένσταση\nΘα πρέπει να ρωτήσω',
      'C')

check('TODO+FIXME+σκοπεύω',
      '/tmp/draft-notes.odt', 'draft-notes.odt', '.odt',
      'TODO: ελέγξω ημερομηνίες\nFIXME: λάθος αρίθμηση\nΝα τσεκάρω τα χαρτιά\nΣκοπεύω να πάω αύριο',
      'C')

print('\n=== Test Group 7: D-tier (no markers) ===')
check('Bare text',
      '~/misc/random.txt', 'random.txt', '.txt',
      'Κάποιο κείμενο χωρίς ιδιαίτερα στοιχεία.',
      'D')

print('\n=== Test Group 8: Filename/path signals ===')
check('A-path + weak fname, no content markers → B',
      '~/Πολεοδομια/βεβαιωση.txt', 'βεβαιωση.txt', '.txt',
      'Κάποιο απλό κείμενο χωρίς institutional markers',
      'B', must_not_tier='A')

check('C-filename (notes) + C-content → C',
      '~/Πολεοδομια/notes-meeting.txt', 'notes-meeting.txt', '.txt',
      'Πήρα τηλ τον μηχανικό\nΜου είπε ότι θα πρέπει\nΝα ρωτήσω αύριο',
      'C')

print('\n=== Test Group 9: TIER_ORDER + downgrade-only logic ===')
for t, val in [('A',3), ('B',2), ('C',1), ('D',0)]:
    if TIER_ORDER[t] == val:
        passed += 1
        print(f'  PASS  TIER_ORDER[{t}]={val}')
    else:
        failed += 1
        msg = f'  FAIL  TIER_ORDER[{t}] expected {val} got {TIER_ORDER[t]}'
        errors.append(msg)
        print(msg)

def sim_propagation(heuristic, agent):
    """Simulates _parse_rankings downgrade-only logic."""
    if TIER_ORDER.get(agent, 0) <= TIER_ORDER.get(heuristic, 0):
        return agent
    return heuristic

for h, a, exp in [('A','C','C'), ('A','A','A'), ('C','A','C'), ('B','D','D'), ('D','B','D'), ('B','A','B')]:
    result = sim_propagation(h, a)
    label = f'heuristic={h} agent={a} → expected={exp}'
    if result == exp:
        passed += 1
        print(f'  PASS  {label}')
    else:
        failed += 1
        msg = f'  FAIL  {label} got={result}'
        errors.append(msg)
        print(msg)

print('\n=== Test Group 10: New C-patterns ===')
check('ρώτησα + πρέπει-να → C (needs ≥2 distinct C-patterns for score≤-3)',
      '/tmp/test.txt', 'test.txt', '.txt',
      'Ρώτησα στο ΚΕΠ αν χρειάζεται\nΠρέπει να πάω Δευτέρα\nΡώτησα πόσο κοστίζει',
      'C')

check('πήρα τηλ alone → C signal',
      '/tmp/test2.txt', 'test2.txt', '.txt',
      'Πήρα τηλ τον Νίκο\nΠήρα τηλ την πολεοδομία\nΘα πρέπει να ξαναπάρω',
      'C')

check('μου είπε alone → C signal',
      '/tmp/test3.txt', 'test3.txt', '.txt',
      'Μου είπε ο Γιάννης ότι δεν γίνεται\nΜου είπε να πάω Τρίτη\nίσως αλλάξει γνώμη',
      'C')

check('πρέπει-να action → C signal',
      '/tmp/test4.txt', 'test4.txt', '.txt',
      'Πρέπει να πάω στο Κτηματολόγιο\nΠρέπει να πάρω βεβαίωση\nΠρέπει να ρωτήσω',
      'C')

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
