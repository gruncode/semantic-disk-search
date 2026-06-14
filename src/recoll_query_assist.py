#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

DEFAULT_RECOLL_CONF = os.path.expanduser('~/.recoll')
TEXT_EXTS = {'.txt', '.md', '.rtf', '.html', '.htm', '.csv', '.json', '.xml', '.log'}
OFFICE_EXTS = {'.odt', '.docx', '.doc', '.ods', '.xlsx', '.xls'}
PDF_EXT = {'.pdf'}
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp', '.webp', '.gif'}
NOISE_PATH_BITS = ['demo', 'guide', 'οδηγ', 'notes-on', 'taxnews', 'sample', 'παραδειγ', 'εικονικ', 'προσοριν', '/.trash-', '/.trash-1000/', '/.trash-0/', 'removedpathspaces', 'fileschanged', '/messages2', '/mesages', '/spaces2.txt', '/spaces3.txt', 'tokenizer.json', 'cachedextension', 'tor-browser', 'node_modules']
PAYMENT_HINTS = ['payment', 'paid', 'receipt', 'proof', 'bank', 'charge', 'πληρω', 'καταβολ', 'εκκαθαρισ', 'οφειλ', 'δοση', 'βεβαιωση']
AMOUNT_HINTS = ['amount', 'value', 'price', 'tax', 'φόρος', 'φορος', 'ευρώ', 'euro', '€']
STOPWORDS = {
    'the','a','an','about','where','what','whats','is','it','my','me','to','for','of','and','or','in','on','with','find','file','files','says','say','how','much',
    'did','was','has','had','been','are','were','do','does','not','but','can','will','just','than','then','so','if',
    # Greek stopwords — articles, pronouns, prepositions, common verbs
    'το','τα','τη','τις','τον','την','τους','τους','της','του','των',
    'ο','η','οι','ένα','μια','ένας',
    'και','ή','αλλά','αλλα','ούτε','ουτε','μα',
    'σε','στο','στη','στα','στον','στην','στους','στις',
    'από','απο','για','με','μου','σου','του','της','μας','σας','τους',
    'που','πως','πώς','πότε','ποτε','πόσο','ποσο','πού','που',
    'είναι','ειναι','ήταν','ηταν','έχω','εχω','έχει','εχει',
    'αυτό','αυτο','αυτά','αυτα','αυτή','αυτη','αυτός','αυτος',
    'εγώ','εγω','εσύ','εσυ','εμείς','εμεις','εσείς','εσεις',
    'τι','ποιο','ποια','ποιος',
    'δεν','μην','θα','να','αν',
}
QUERY_FLUFF = {'wrt', 'what', 'where', 'when', 'who', 'why', 'how', 'much', 'happened', 'happen', 'result', 'results', 'status', 'about', 'regarding', 'tell', 'show',
    'πότε', 'ποτε', 'πόσο', 'ποσο', 'πού', 'είναι', 'ειναι', 'ήταν', 'ηταν', 'τι',
}
TIME_WORDS = {'last', 'year', 'this', 'next', 'previous', 'today', 'yesterday', 'tomorrow'}

DOMAIN_TERMS = {
    'property': {
        'triggers': ['sell','sale','selling','buyer','seller','broker','commission','deed','transfer','land','plot','property','parcel','estate','πωλ','αγορα','μεσιτ','συμβολ','μεταβιβ','οικοπ','αγροτ','κτημα','κτήμα','περιουσ','κτηματολογ','αντικειμενικ','πολεοδομ','αυθαιρετ'],
        'prefix_triggers': ['πωλ', 'αγορα', 'μεσιτ', 'συμβολ', 'μεταβιβ', 'οικοπ', 'αγροτ', 'περιουσ', 'κτηματολογ', 'αντικειμενικ', 'πολεοδομ'],
        'queries': [
            'sale OR sell OR buyer OR seller OR broker OR contract OR deed OR transfer',
            'land OR property OR plot OR parcel OR estate',
            'πώληση OR πωληση OR μεταβίβαση OR συμβόλαιο OR συμβολαιο OR μεσίτης OR μεσιτης',
            'οικόπεδο OR οικοπεδο OR αγροτεμάχιο OR αγροτεμαχιο OR κτήμα OR κτημα',
            'value OR price OR estimate OR αξία OR αξια OR τιμή OR τιμη OR εκτίμηση OR εκτιμηση',
        ],
        'folder_boosts': {'periousia': 3.0, 'κριτη': 1.8, 'νομικα': 1.5},
        'dir_scopes': ['RealEstate'],
    },
    'tax': {
        'triggers': ['tax','taxes','paid','payment','receipt','vat','income','declaration','irs','enfia','ενφια','φορο','φόρο','εφορι','πληρω','καταβολ','εκκαθαριστ','δηλωσ'],
        'prefix_triggers': ['φορο', 'εφορι', 'πληρω', 'καταβολ', 'εκκαθαριστ', 'δηλωσ'],
        'queries': [
            'tax OR taxes OR payment OR paid OR receipt OR declaration OR income',
            'φόρος OR φορος OR εφορία OR εφορια OR πληρωμή OR πληρωμη OR καταβολή OR καταβολη',
            'ΕΝΦΙΑ OR ενφια OR εκκαθαριστικό OR εκκαθαριστικο OR δήλωση OR δηλωση',
        ],
        'folder_boosts': {'finance': 3.0, 'tax': 2.0},
        'dir_scopes': ['Finance/Tax'],
    },
    'rent': {
        'triggers': ['rent','rental','lease','tenant','landlord','μισθωσ','μισθωτ','ενοικ'],
        'prefix_triggers': ['μισθωσ', 'ενοικ', 'μισθωτ'],
        'queries': [
            'rent OR rental OR lease OR tenant OR landlord',
            'μίσθωση OR μισθωση OR ενοίκιο OR ενοικιο OR μισθωτήριο OR μισθωτηριο',
        ],
        'folder_boosts': {'periousia': 1.5, 'accommodation': 1.5},
        'dir_scopes': ['RealEstate', 'Accommodation'],
    },
    'health': {
        'triggers': ['health','medical','doctor','hospital','blood','scan','mri','ct','xray','ultrasound','surgery','diagnosis','αιμα','αιματ','εξεταση','εξετασ','υπερηχ','αξονικ','μαγνητικ','νευρολογ','καρδιο','ορθοπεδ','ουρολογ','οστικ','ατυχημ','χειρουργ','γιατρ','φαρμακ','προστατ','δερμα','ωμος','μεση','πλατη','αυχεν'],
        'prefix_triggers': ['αιματ', 'εξετασ', 'υπερηχ', 'αξονικ', 'μαγνητικ', 'νευρολογ', 'καρδιο', 'ορθοπεδ', 'ουρολογ', 'χειρουργ', 'γιατρ', 'φαρμακ', 'προστατ'],
        'queries': [
            'blood OR test OR scan OR MRI OR ultrasound OR diagnosis',
            'αίμα OR αιμα OR εξέταση OR εξεταση OR υπέρηχος OR υπερηχος',
            'MRI OR αξονική OR αξονικη OR μαγνητική OR μαγνητικη',
        ],
        'folder_boosts': {'health': 3.0, 'γιωργοσ': 2.0, 'πατερασ': 1.5, 'μαμα': 1.5},
        'dir_scopes': ['Health'],
    },
    'work': {
        'triggers': ['corpus','corpus','salary','payslip','μισθολογ','εργασιακ','μισθοδοσ','υπηρεσι','scada','grid','switch','substation','τεχνικ','λογιστικ','οδοιπορ'],
        'prefix_triggers': ['μισθολογ', 'εργασιακ', 'μισθοδοσ', 'λογιστικ', 'οδοιπορ'],
        'queries': [
            'salary OR payslip OR corpus',
            'μισθολογικά OR μισθολογικα OR εργασιακά OR εργασιακα',
            'SCADA OR grid OR switch OR substation',
        ],
        'folder_boosts': {'corpus': 3.0, 'work_docs': 2.0, 'τεχνικ': 1.5},
        'dir_scopes': ['corpus'],
    },
    'teaching': {
        'triggers': ['teaching','teacher','iek','ινεδιβιμ','αλγοριθμ','algorithm','python','course','lecture','syllabus','exam','student','μαθημα','εξεταστ','βαθμο','διδασκ','εκπαιδ','πληρωμ'],
        'prefix_triggers': ['αλγοριθμ', 'μαθημα', 'εξεταστ', 'βαθμο', 'διδασκ', 'εκπαιδ'],
        'queries': [
            'teaching OR IEK OR ΙΝΕΔΙΒΙΜ OR algorithm OR python',
            'αλγοριθμική OR αλγοριθμικη OR μάθημα OR μαθημα OR εξετάσεις OR εξετασεις',
        ],
        'folder_boosts': {'teaching': 3.0, 'iek': 2.0, 'αλγοριθμ': 1.5},
        'dir_scopes': ['Teaching'],
    },
    'legal': {
        'triggers': ['legal','law','court','κωδικ','νομος','νόμος','συνταγμα','δικαστ','δικηγορ','αστικ','ποινικ','αγωγ','εξωδικ'],
        'prefix_triggers': ['κωδικ', 'δικαστ', 'δικηγορ', 'αστικ', 'ποινικ', 'εξωδικ'],
        'queries': [
            'law OR legal OR court OR code OR constitution',
            'νόμος OR νομος OR κώδικας OR κωδικας OR σύνταγμα OR συνταγμα',
        ],
        'folder_boosts': {'legal': 3.0, 'νομικα': 2.0},
        'dir_scopes': ['Finance/Legal', 'RealEstate/Legal'],
    },
    'banking': {
        'triggers': ['bank','banking','account','deposit','τραπεζ','λογαριασμ','καταθεσ','alpha','eurobank','εθνικη','πειραιω'],
        'prefix_triggers': ['τραπεζ', 'λογαριασμ', 'καταθεσ'],
        'queries': [
            'bank OR banking OR account OR deposit',
            'τράπεζα OR τραπεζα OR λογαριασμός OR λογαριασμος OR κατάθεση OR καταθεση',
        ],
        'folder_boosts': {'banking': 3.0, 'ελλαδα': 1.5, 'εξωτερικο': 1.5},
        'dir_scopes': ['Finance/Banking'],
    },
    'investment': {
        'triggers': ['invest','stock','fund','mutual','bond','shares','portfolio','dividend','μετοχ','επενδ','αμοιβαι','ομολογ','μερισμ','χρηματιστ','παραγωγ','derivative'],
        'prefix_triggers': ['μετοχ', 'επενδ', 'αμοιβαι', 'ομολογ', 'χρηματιστ', 'παραγωγ'],
        'queries': [
            'stock OR fund OR invest OR bond OR shares OR portfolio',
            'μετοχή OR μετοχη OR επένδυση OR επενδυση OR αμοιβαίο OR αμοιβαιο',
        ],
        'folder_boosts': {'invest': 3.0, 'stocks': 2.0},
        'dir_scopes': ['Finance/Invest'],
    },
}


def run(cmd, why):
    print(f'[{why}] $ {shlex.join(cmd)}', file=sys.stderr)
    cp = subprocess.run(cmd, capture_output=True)
    stdout = cp.stdout.decode('utf-8', errors='replace') if isinstance(cp.stdout, (bytes, bytearray)) else str(cp.stdout)
    stderr = cp.stderr.decode('utf-8', errors='replace') if isinstance(cp.stderr, (bytes, bytearray)) else str(cp.stderr)
    return cp.returncode, stdout, stderr


def tokenize(text):
    parts = re.findall(r"[\w\-Ά-ώΑ-Ωάέήίόύώϊϋΐΰ]+", text.lower(), flags=re.UNICODE)
    return [p for p in parts if p not in STOPWORDS and len(p) > 1]


def anchor_terms(query):
    toks = tokenize(query)
    anchors = [t for t in toks if t not in QUERY_FLUFF]
    uniq = []
    seen = set()
    for t in anchors:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    uniq.sort(key=lambda t: (len(t) < 4, t.isascii(), len(t)))
    return uniq


def detect_domains(query_tokens):
    found = []
    token_set = set(query_tokens)
    for name, cfg in DOMAIN_TERMS.items():
        matched = False
        prefix_triggers = set(cfg.get('prefix_triggers', []))
        for trig in cfg['triggers']:
            if trig in token_set:
                matched = True
                break
            if trig in prefix_triggers and len(trig) >= 4 and any(tok.startswith(trig) for tok in query_tokens):
                matched = True
                break
        if matched:
            found.append(name)
    return found


def heuristic_query_plan(query):
    toks = tokenize(query)
    anchors = anchor_terms(query)
    domains = detect_domains(toks)
    now = dt.datetime.now()
    resolved_year = now.year - 1 if 'last year' in query.lower() else None
    must_terms = []
    preferred_terms = []
    negative_terms = []
    if 'tax' in domains:
        # Use anchors as must_terms to preserve user-specific terms like ENFIA, E1
        tax_anchors = [a for a in anchors if a not in TIME_WORDS and a not in QUERY_FLUFF]
        must_terms = tax_anchors[:3] if tax_anchors else ['tax', 'paid']
        preferred_terms += ['tax', 'taxes', 'payment', 'paid', 'receipt', 'εκκαθαριστικό', 'φόρος', 'πληρωμή', 'δήλωση', 'ΕΝΦΙΑ']
        negative_terms += ['warranty', 'fund', 'investment', 'constitution', 'parking', 'tutorial', 'manual']
        if resolved_year:
            preferred_terms += [str(resolved_year), str(resolved_year - 1)]
    if 'property' in domains:
        must_terms = must_terms or [t for t in anchors if t not in TIME_WORDS][:2]
        preferred_terms += ['land', 'property', 'plot', 'parcel', 'οικόπεδο', 'αγροτεμάχιο', 'κτήμα']
        negative_terms += ['tenant', 'lease', 'notice', 'terminate']
    if 'rent' in domains:
        must_terms = must_terms or ['rent']
        preferred_terms += ['rent', 'lease', 'tenant', 'landlord', 'ενοίκιο', 'μίσθωση']
    if 'health' in domains:
        must_terms = must_terms or [t for t in anchors if t not in TIME_WORDS][:3]
        preferred_terms += ['εξέταση', 'εξεταση', 'αίμα', 'αιμα', 'diagnosis']
    if 'work' in domains:
        must_terms = must_terms or [t for t in anchors if t not in TIME_WORDS][:3]
        preferred_terms += ['corpus', 'corpus', 'μισθολογικά', 'εργασιακά']
    if 'teaching' in domains:
        must_terms = must_terms or [t for t in anchors if t not in TIME_WORDS][:3]
        preferred_terms += ['teaching', 'IEK', 'ΙΝΕΔΙΒΙΜ', 'αλγοριθμική']
    if 'legal' in domains:
        must_terms = must_terms or [t for t in anchors if t not in TIME_WORDS][:3]
        preferred_terms += ['νόμος', 'κώδικας', 'σύνταγμα', 'law']
    if 'banking' in domains:
        must_terms = must_terms or [t for t in anchors if t not in TIME_WORDS][:3]
        preferred_terms += ['τράπεζα', 'λογαριασμός', 'bank']
    if 'investment' in domains:
        must_terms = must_terms or [t for t in anchors if t not in TIME_WORDS][:3]
        preferred_terms += ['μετοχή', 'επένδυση', 'stock', 'fund']
    if not must_terms:
        must_terms = [t for t in anchors if t not in TIME_WORDS][:3]
    needs_amount = any(t in query.lower() for t in ['how much', 'amount', 'value', 'price', 'paid', 'tax', 'φόρος', 'φορος', 'πληρω'])
    plan = {
        'query': query,
        'domains': domains,
        'anchors': anchors,
        'must_terms': must_terms,
        'preferred_terms': list(dict.fromkeys(preferred_terms)),
        'negative_terms': list(dict.fromkeys(negative_terms)),
        'needs_amount': needs_amount,
        'resolved_year': resolved_year,
        'search_strategy': 'strict_then_broaden',
        'planner': 'heuristic',
    }
    return plan


def llm_query_plan(query):
    """Use claude -p (Claude subscription) for intelligent query planning."""
    claude_bin = which_local('claude')
    if not claude_bin:
        return None
    now = dt.datetime.now()
    schema_hint = {
        'domains': ['tax|property|rent|health|work|teaching|legal|banking|investment|generic'],
        'anchors': ['key entities from query'],
        'must_terms': ['terms that MUST appear in results'],
        'preferred_terms': ['related terms in BOTH Greek and English'],
        'filename_terms': ['likely filename fragments to search with filename: prefix'],
        'negative_terms': ['terms indicating false positives'],
        'needs_amount': False,
        'resolved_year': None,
        'search_strategy': 'strict_then_broaden',
    }
    prompt = (
        'You are a search-query planner for a bilingual Greek/English local desktop file index (Recoll/Xapian). '
        'The index has NO Greek stemmer — different word endings do NOT match. '
        'Return ONLY valid JSON, no markdown, no explanation. '
        'Extract anchors, must_terms, preferred_terms (include BOTH Greek and English variants), '
        'filename_terms (likely filename fragments — Greek filenames often use unaccented greeklish or mixed), '
        'negative_terms, needs_amount, resolved_year. '
        f'Current year: {now.year}. "Last year" = {now.year - 1}. '
        f'JSON schema: {json.dumps(schema_hint, ensure_ascii=False)}\n\n'
        f'USER QUERY: {query}'
    )
    try:
        # --strict-mcp-config blocks MCP server spawning (fast startup)
        empty_mcp = '/tmp/empty-mcp-planner.json'
        if not os.path.exists(empty_mcp):
            with open(empty_mcp, 'w') as ef:
                ef.write('{"mcpServers":{}}')
        cp = subprocess.run(
            [claude_bin, '-p',
             '--dangerously-skip-permissions',
             '--strict-mcp-config', '--mcp-config', empty_mcp,
             '--model', 'sonnet',
             '--output-format', 'stream-json', '--verbose',
             prompt],
            capture_output=True, timeout=30,
            stdin=subprocess.DEVNULL
        )
        # Parse stream-json: extract first text content from assistant message
        text = ''
        for line in cp.stdout.decode('utf-8', errors='replace').splitlines():
            try:
                d = json.loads(line.strip())
                if d.get('type') == 'assistant':
                    for c in d.get('message', {}).get('content', []):
                        if isinstance(c, dict) and c.get('type') == 'text':
                            text = c['text'].strip()
                            break
                if text:
                    break
            except Exception:
                pass
        # Strip markdown code fences if present
        if text.startswith('```'):
            text = re.sub(r'^```\w*\n?', '', text)
            text = re.sub(r'\n?```$', '', text)
        plan = json.loads(text)
        plan['query'] = query
        plan['planner'] = 'claude'
        return plan
    except Exception as e:
        print(f'[claude planner failed: {e}]', file=sys.stderr)
        return None


def build_query_plan(query):
    llm_plan = llm_query_plan(query)
    if llm_plan:
        return llm_plan
    return heuristic_query_plan(query)


def build_queries_from_plan(plan):
    query = plan['query']
    queries = [query]
    anchors = [a for a in plan.get('anchors', []) if a not in QUERY_FLUFF]
    must_terms = [m for m in plan.get('must_terms', []) if m]
    preferred_terms = [p for p in plan.get('preferred_terms', []) if p]
    domains = plan.get('domains', [])
    # filename: queries for anchors (high precision for known-item search)
    for a in anchors[:4]:
        if len(a) >= 3:
            queries.append(f'filename:{a}')
    # filename: queries from LLM-suggested filename terms (Claude knows Greek morphology)
    for ft in plan.get('filename_terms', [])[:4]:
        ft = ft.strip()
        if len(ft) >= 3 and f'filename:{ft}' not in queries:
            queries.append(f'filename:{ft}')
    # dir:-scoped queries when domain detected
    dir_scopes = []
    for d in domains:
        if d in DOMAIN_TERMS:
            dir_scopes.extend(DOMAIN_TERMS[d].get('dir_scopes', []))
    for ds in dir_scopes[:2]:
        if anchors:
            queries.append(f'dir:{ds} ' + ' '.join(anchors[:3]))
        if must_terms:
            queries.append(f'dir:{ds} ' + ' OR '.join(must_terms[:3]))
    # Use plan anchors as dir: scopes (person names, place names are often folder names)
    raw_anchors = plan.get('anchors', [])
    for ra in raw_anchors[:5]:
        if len(ra) >= 4 and not ra.isascii():
            other = [x for x in raw_anchors if x != ra][:2]
            if other:
                q = f'dir:{ra} ' + ' '.join(other)
                if q not in queries:
                    queries.append(q)
    # must-term AND combinations
    if must_terms:
        queries.append(' AND '.join(must_terms[:min(3, len(must_terms))]))
    if plan.get('resolved_year') and must_terms:
        queries.append(' AND '.join([str(plan['resolved_year'])] + must_terms[:2]))
    if plan.get('resolved_year') and preferred_terms:
        queries.append(' AND '.join([str(plan['resolved_year']), preferred_terms[0]]))
    # anchor combinations
    if len(anchors) >= 2:
        queries.append(' AND '.join(anchors[:2]))
    if len(anchors) >= 3:
        queries.append(' AND '.join(anchors[:3]))
    # cross anchor+preferred
    if anchors and preferred_terms:
        for pref in preferred_terms[:3]:
            queries.append(' AND '.join(([pref] + anchors[:2])[:3]))
    # OR fallbacks
    if anchors:
        queries.append(' OR '.join(anchors[:min(6, len(anchors))]))
    if preferred_terms:
        queries.append(' OR '.join(preferred_terms[:6]))
    out, seen = [], set()
    for q in queries:
        q = q.strip()
        if q and q not in seen:
            seen.add(q)
            out.append(q)
    return out[:16]


def parse_recoll_lines(stdout, query_tag):
    results, current = [], None
    for line in stdout.splitlines():
        if re.match(r'^(application/|text/|image/|message/)', line):
            if current:
                results.append(current)
            parts = line.split('\t')
            mime = parts[0].strip()
            m_path = re.search(r'\[file://([^\]]+)\]', line)
            m_title = re.search(r'\]\s+\[([^\]]+)\]', line)
            current = {'mime': mime, 'path': m_path.group(1) if m_path else None, 'title': m_title.group(1) if m_title else '', 'snippets': [], 'queries': [query_tag]}
        elif current and re.match(r'^\d+\s*:\s', line):
            current['snippets'].append(re.sub(r'^\d+\s*:\s*', '', line))
    if current:
        results.append(current)
    return results


def recoll_search(query, conf):
    rc, out, err = run(['recollq', '-c', conf, '-A', '-g', '3', '-n', '20', query], f'recoll search: {query[:60]}')
    if rc != 0:
        return []
    return parse_recoll_lines(out, query)


def recoll_search_basic(query, conf):
    """Search using -b (basic) output — returns just paths. Used for filename: and dir: queries."""
    rc, out, err = run(['recollq', '-c', conf, '-b', '-n', '15', query], f'recoll basic: {query[:60]}')
    if rc != 0:
        return []
    results = []
    for line in out.splitlines():
        line = line.strip()
        if line.startswith('file://'):
            path = line[7:]  # strip file://
            if path:
                results.append({
                    'mime': 'unknown', 'path': path, 'title': Path(path).name,
                    'snippets': [], 'queries': [query]
                })
    return results


FAISS_DIR = '$FAISS_BASE/gte'
VENV_PYTHON = '$VENV_GTE'
VECTOR_INDEX_SCRIPT = '$PROJECT_DIR/src/recoll_vector_index.py'


def vector_search(query, top_k=30, faiss_dir=None):
    """Run vector search via subprocess (uses transformers venv with sentence-transformers)."""
    fdir = faiss_dir or FAISS_DIR
    index_file = os.path.join(fdir, 'index.faiss')
    if not Path(index_file).exists() or not Path(VECTOR_INDEX_SCRIPT).exists():
        return []
    try:
        env = os.environ.copy()
        env['HF_HOME'] = '$HF_HOME'
        cp = subprocess.run(
            [VENV_PYTHON, VECTOR_INDEX_SCRIPT, '--query', query, '--faiss-dir', fdir, '--top', str(top_k)],
            capture_output=True, timeout=60, env=env
        )
        results = []
        for line in cp.stdout.decode('utf-8', errors='replace').splitlines():
            line = line.strip()
            parts = line.split(None, 1)
            if len(parts) == 2:
                try:
                    score, path = float(parts[0]), parts[1]
                    results.append({
                        'mime': 'unknown', 'path': path, 'title': Path(path).name,
                        'snippets': [], 'queries': ['vector_search']
                    })
                except ValueError:
                    pass
        return results
    except Exception:
        return []


def vector_augment(bm25_ranked, vector_results):
    """Add vector-only results to BM25 list without re-ranking existing BM25 results.
    BM25 ranking is preserved. Vector results that BM25 missed are appended."""
    bm25_paths = {item.get('path', '') for item in bm25_ranked}
    augmented = list(bm25_ranked)
    for item in vector_results:
        path = item.get('path', '')
        if path and path not in bm25_paths:
            item['queries'] = ['vector_search']
            augmented.append(item)
            bm25_paths.add(path)
    return augmented


def score_result(item, plan, folder=None):
    domains = plan.get('domains', [])
    score = 0.0
    reasons = []
    anchors = plan.get('anchors', [])
    must_terms = plan.get('must_terms', [])
    preferred_terms = plan.get('preferred_terms', [])
    negative_terms = plan.get('negative_terms', [])
    path = (item.get('path') or '').lower()
    title = (item.get('title') or '').lower()
    text = ' '.join(item.get('snippets') or []).lower()
    query_l = plan.get('query', '').lower()
    asks_amount = bool(plan.get('needs_amount'))
    for part in tokenize(plan.get('query', '')):
        if part in path:
            score += 2.0
            reasons.append(f'path:{part}')
        if part in title:
            score += 2.0
            reasons.append(f'title:{part}')
        if part in text:
            score += 1.2
            reasons.append(f'text:{part}')
    if folder and folder.lower() in path:
        score += 4.0
        reasons.append(f'folder:{folder.lower()}')
    for d in domains:
        if d not in DOMAIN_TERMS:
            continue
        for k, boost in DOMAIN_TERMS[d].get('folder_boosts', {}).items():
            if k in path:
                score += boost
                reasons.append(f'domain_folder:{d}:{k}')
    ext = Path(path).suffix.lower()
    if ext in PDF_EXT:
        score += 1.0
        reasons.append('ext:pdf')
    if ext in OFFICE_EXTS:
        score += 1.2
        reasons.append('ext:office')
    if ext in TEXT_EXTS:
        score += 0.8
        reasons.append('ext:text')
    if ext in IMAGE_EXTS:
        score -= 0.5
        reasons.append('ext:image_penalty')
    score += min(len(item.get('snippets') or []), 3) * 0.5
    # Boost for being found via filename: or dir: queries (high precision signals)
    fn_queries = [q for q in (item.get('queries') or []) if q.startswith('filename:')]
    dir_queries = [q for q in (item.get('queries') or []) if q.startswith('dir:')]
    if fn_queries:
        score += 5.0
        reasons.append(f'filename_query_boost:{len(fn_queries)}')
    if dir_queries:
        score += 3.0
        reasons.append(f'dir_query_boost:{len(dir_queries)}')
    # dir_scope match — if domain detected and file is in expected directory
    for d in domains:
        for ds in DOMAIN_TERMS.get(d, {}).get('dir_scopes', []):
            if ds.lower() in path:
                score += 2.5
                reasons.append(f'dir_scope:{d}:{ds}')
                break
    score += len(item.get('queries') or []) * 0.25
    if query_l in text or query_l in title:
        score += 2.0
        reasons.append('exact_query_match')
    if any(bit in path for bit in NOISE_PATH_BITS):
        score -= 5.0
        reasons.append('noise_penalty')
    must_hits = sum(1 for t in must_terms if t.lower() in path or t.lower() in title or t.lower() in text)
    if must_hits:
        score += must_hits * 2.5
        reasons.append(f'must_hits:{must_hits}')
    else:
        score -= 2.0
        reasons.append('missing_must_hits')
    pref_hits = sum(1 for t in preferred_terms[:8] if t.lower() in path or t.lower() in title or t.lower() in text)
    if pref_hits:
        score += min(4.0, pref_hits * 0.8)
        reasons.append(f'preferred_hits:{pref_hits}')
    neg_hits = sum(1 for t in negative_terms[:10] if t.lower() in path or t.lower() in title or t.lower() in text)
    if neg_hits:
        score -= min(6.0, neg_hits * 1.5)
        reasons.append(f'negative_hits:{neg_hits}')
    if anchors:
        coverage = sum(1 for a in anchors[:4] if a in path or a in title or a in text)
        score += coverage * 2.0
        reasons.append(f'anchor_coverage:{coverage}')
        if coverage == 0:
            score -= 4.0
            reasons.append('missing_anchor_coverage')
    if 'tax' in domains:
        if any(h in path or h in text or h in title for h in PAYMENT_HINTS):
            score += 3.5
            reasons.append('tax_payment_hint')
        if asks_amount and any(h in text or h in title for h in AMOUNT_HINTS):
            score += 2.0
            reasons.append('tax_amount_hint')
        year_hits = re.findall(r'20\d\d', path + ' ' + title + ' ' + text[:1000])
        now = dt.datetime.now()
        if str(now.year - 1) in year_hits:
            score += 2.5
            reasons.append(f'year:{now.year - 1}')
        elif str(now.year - 2) in year_hits:
            score += 1.2
            reasons.append(f'year:{now.year - 2}')
    return round(score, 3), reasons


def merge_results(results, plan, folder=None):
    merged = {}
    for item in results:
        path = item.get('path')
        if not path:
            continue
        if folder and folder.lower() not in path.lower():
            continue
        if path not in merged:
            merged[path] = item
        else:
            merged[path]['queries'] = sorted(set(merged[path].get('queries', []) + item.get('queries', [])))
            merged[path]['snippets'] = list(dict.fromkeys((merged[path].get('snippets', []) + item.get('snippets', []))))[:8]
    for item in merged.values():
        item['score'], item['score_reasons'] = score_result(item, plan, folder=folder)
    return sorted(merged.values(), key=lambda x: x['score'], reverse=True)


def which_local(name):
    for d in os.environ.get('PATH', '').split(':'):
        p = Path(d) / name
        if p.exists() and os.access(p, os.X_OK):
            return str(p)
    return None


def extract_text(path):
    p = Path(path)
    ext = p.suffix.lower()
    if not p.exists() or not p.is_file():
        return ''
    try:
        if ext in TEXT_EXTS:
            return p.read_text(errors='ignore')[:12000]
        if ext in {'.odt', '.ods', '.docx', '.xlsx'}:
            code = (
                'import sys, zipfile, re\n'
                'z=zipfile.ZipFile(sys.argv[1])\n'
                'txt=[]\n'
                'for n in z.namelist():\n'
                '    if n.endswith(("content.xml","document.xml","sharedStrings.xml")):\n'
                '        txt.append(z.read(n).decode("utf-8","ignore"))\n'
                'print(re.sub(r"<[^>]+>"," "," ".join(txt))[:12000])\n'
            )
            _, out, _ = run(['python3', '-c', code, path], f'extract zipped office xml text from {path}')
            return out[:12000]
        if ext in PDF_EXT:
            pdftotext = which_local('pdftotext')
            if pdftotext:
                _, out, _ = run([pdftotext, '-q', '-nopgbrk', path, '-'], f'extract PDF text from {path}')
                return out[:12000]
        if ext == '.doc':
            antiword = which_local('antiword')
            if antiword:
                _, out, _ = run([antiword, path], f'extract DOC text from {path}')
                return out[:12000]
        if ext == '.rtf':
            code = (
                'import re,sys\n'
                't=open(sys.argv[1],errors="ignore").read()\n'
                't=re.sub(r"\\\\[a-z]+-?\\d* ?"," ",t)\n'
                't=re.sub(r"[{}]"," ",t)\n'
                'print(t[:12000])\n'
            )
            _, out, _ = run(['python3', '-c', code, path], f'extract RTF-ish text from {path}')
            return out[:12000]
    except Exception:
        return ''
    return ''


def build_context(candidates, topn):
    out = []
    for item in candidates[:topn]:
        text = extract_text(item['path'])
        out.append({'path': item['path'], 'title': item.get('title', ''), 'mime': item.get('mime', ''), 'score': item.get('score', 0), 'score_reasons': item.get('score_reasons', []), 'queries': item.get('queries', []), 'snippets': item.get('snippets', [])[:4], 'extracted_text': text[:5000] if text else ''})
    return out


def score_context_match(plan, context):
    query = plan.get('query', '')
    q_tokens = set(tokenize(query))
    anchors = plan.get('anchors', [])
    if not context:
        return {'good': False, 'reason': 'no_context', 'score': 0.0}
    top = context[:5]
    total = 0.0
    bad = 0
    payment_hits = 0
    amount_hits = 0
    asks_amount = bool(plan.get('needs_amount'))
    anchor_hits = 0
    for item in top:
        hay = ' '.join(item.get('snippets', [])) + '\n' + item.get('extracted_text', '')
        hay_l = hay.lower()
        overlap = sum(1 for t in q_tokens if t in hay_l)
        total += overlap + float(item.get('score', 0))
        path_l = item.get('path', '').lower()
        if any(bit in path_l for bit in NOISE_PATH_BITS):
            bad += 1
        if anchors and sum(1 for a in anchors[:4] if a in hay_l or a in path_l) >= max(1, min(2, len(anchors[:4]))):
            anchor_hits += 1
        if any(bit in hay_l or bit in path_l for bit in PAYMENT_HINTS):
            payment_hits += 1
        if asks_amount and (re.search(r'(€\s?\d|\d[\d\.,]*\s?€|\d[\d\.,]*\s?(ευρώ|euro|euros))', hay, re.I) or any(bit in hay_l for bit in AMOUNT_HINTS)):
            amount_hits += 1
    avg = total / max(len(top), 1)
    good = avg >= 6.0 and bad < max(3, len(top)) and (not asks_amount or payment_hits >= 1 or amount_hits >= 1) and (not anchors or anchor_hits >= 1)
    if bad >= max(3, len(top) // 2 + 1):
        reason = 'too_noisy'
    elif anchors and anchor_hits == 0:
        reason = 'missing_anchor_evidence'
    elif asks_amount and payment_hits == 0 and amount_hits == 0:
        reason = 'missing_amount_evidence'
    else:
        reason = 'ok' if good else 'low_match'
    return {'good': good, 'reason': reason, 'score': round(avg, 3), 'payment_hits': payment_hits, 'amount_hits': amount_hits, 'anchor_hits': anchor_hits}


def refine_queries_for_retry(plan, queries):
    refined = []
    q_tokens = tokenize(plan.get('query', ''))
    anchors = plan.get('anchors', [])
    domains = plan.get('domains', [])
    preferred_terms = plan.get('preferred_terms', [])
    if anchors:
        refined.extend([
            ' AND '.join(anchors[:min(3, len(anchors))]),
            ' AND '.join(anchors[:min(2, len(anchors))]),
            ' OR '.join(anchors[:min(6, len(anchors))]),
        ])
    if preferred_terms:
        refined.append(' OR '.join(preferred_terms[:8]))
    if 'tax' in domains:
        years = [t for t in q_tokens if re.fullmatch(r'20\d\d', t)]
        if not years:
            now = dt.datetime.now()
            years = [str(now.year - 1)]
        refined.extend([
            'tax OR paid OR payment OR receipt',
            'φόρος OR πληρωμή OR καταβολή OR εκκαθαριστικό',
            'ΕΝΦΙΑ OR δήλωση OR εκκαθαριστικό',
            ' OR '.join(years + ['tax', 'payment', 'φόρος', 'πληρωμή']),
        ])
    if 'property' in domains:
        refined.extend([
            'sale OR seller OR buyer OR contract OR deed',
            'πώληση OR μεταβίβαση OR συμβόλαιο OR μεσίτης',
            'οικόπεδο OR αγροτεμάχιο OR κτήμα OR αξία',
        ])
    if 'rent' in domains:
        refined.extend([
            'rent OR lease OR tenant OR landlord',
            'ενοίκιο OR μίσθωση OR μισθωτήριο',
        ])
    for q in queries[:3]:
        refined.append(q)
    out = []
    seen = set()
    for q in refined:
        q = q.strip()
        if q and q not in seen:
            seen.add(q)
            out.append(q)
    return out[:8]


def call_openai_answer(query, context):
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        return None
    try:
        from openai import OpenAI
    except Exception:
        return None
    prompt = (
        'Answer the user query using ONLY the provided files/snippets. '
        'Return JSON with keys: answer, confidence, values_found, best_files. '
        'best_files must be a list of objects with path and why. '
        'If a value/price/amount is not explicitly present, say not found. '
        'Do not invent facts.\n\n'
        f'USER QUERY: {query}\n\nFILES:\n{json.dumps(context, ensure_ascii=False)}'
    )
    client = OpenAI(api_key=api_key)
    resp = client.responses.create(model=os.environ.get('OPENAI_MODEL', 'gpt-5-mini'), input=prompt)
    text = getattr(resp, 'output_text', '') or ''
    try:
        return json.loads(text)
    except Exception:
        return {'answer': text.strip(), 'confidence': 'unknown', 'values_found': [], 'best_files': []}


def local_answer(plan, context):
    query = plan.get('query', '')
    q_tokens = set(tokenize(query))
    scored, value_hits = [], []
    asks_amount = bool(plan.get('needs_amount'))
    money_re = re.compile(r'(€\s?\d[\d\.,]*|\d[\d\.,]*\s?€|\d[\d\.,]*\s?(ευρώ|euro|euros)|\d[\d\.,]*\s?(usd|dollars))', re.I)
    for item in context:
        hay = ' '.join(item.get('snippets', [])) + '\n' + item.get('extracted_text', '')
        hay_l = hay.lower()
        overlap = sum(1 for t in q_tokens if t in hay_l)
        scored.append((overlap + item.get('score', 0), item))
        if asks_amount:
            for m in money_re.finditer(hay[:8000]):
                snippet = hay[max(0, m.start()-80):m.end()+80].replace('\n', ' ')
                value_hits.append({'path': item['path'], 'match': m.group(0), 'snippet': snippet})
    scored.sort(key=lambda x: x[0], reverse=True)
    best = [it for _, it in scored[:5]]
    ans = []
    if best:
        ans.append('Most relevant files found:')
        for item in best[:3]:
            ans.append(f'- {item["path"]}')
    else:
        ans.append('No strong candidate files found.')
    if asks_amount and value_hits:
        ans.append('Possible amount/value mentions found:')
        for vh in value_hits[:5]:
            ans.append(f'- {vh["match"]} in {vh["path"]}')
    elif asks_amount:
        ans.append('No explicit amount/value found in the extracted top-file text.')
    return {'answer': '\n'.join(ans), 'confidence': 'medium' if best else 'low', 'values_found': value_hits[:10] if asks_amount else [], 'best_files': [{'path': b['path'], 'why': '; '.join(b.get('snippets', [])[:2])[:300]} for b in best]}


def answer_quality(plan, final_answer):
    query = plan.get('query', '')
    answer_text = (final_answer.get('answer') or '').lower()
    files = final_answer.get('best_files') or []
    noisy = 0
    anchors = plan.get('anchors', [])
    anchor_ok = False
    for bf in files[:5]:
        path_l = bf.get('path', '').lower()
        if any(bit in path_l for bit in NOISE_PATH_BITS):
            noisy += 1
        why_l = (bf.get('why') or '').lower()
        if anchors and sum(1 for a in anchors[:4] if a in path_l or a in why_l) >= max(1, min(2, len(anchors[:4]))):
            anchor_ok = True
    asks_amount = bool(plan.get('needs_amount'))
    has_amount = bool(final_answer.get('values_found')) or bool(re.search(r'(€\s?\d|\d[\d\.,]*\s?€|\d[\d\.,]*\s?(ευρώ|euro|euros))', answer_text, re.I))
    good = bool(files) and noisy < max(3, len(files[:5])) and (not asks_amount or has_amount) and (not anchors or anchor_ok)
    if noisy >= max(3, len(files[:5]) // 2 + 1):
        reason = 'answer_noisy'
    elif anchors and not anchor_ok:
        reason = 'answer_missing_anchor_coverage'
    elif asks_amount and not has_amount:
        reason = 'answer_missing_amount'
    else:
        reason = 'ok' if good else 'answer_weak'
    return {'good': good, 'reason': reason, 'noisy_files': noisy, 'has_amount': has_amount, 'anchor_ok': anchor_ok}


def maybe_retry_search(plan, conf, folder, queries, ranked, top):
    first_context = build_context(ranked, top)
    quality = score_context_match(plan, first_context)
    if quality['good']:
        return ranked, first_context, None, quality
    retry_queries = refine_queries_for_retry(plan, queries)
    retry_raw = []
    for q in retry_queries:
        retry_raw.extend(recoll_search(q, conf))
    retry_ranked = merge_results(retry_raw, plan, folder=folder)
    retry_context = build_context(retry_ranked, top)
    retry_quality = score_context_match(plan, retry_context)
    used_retry = {
        'reason': quality['reason'],
        'first_pass_score': quality['score'],
        'retry_queries': retry_queries,
        'retry_score': retry_quality['score'],
        'retry_kept': retry_quality['good'] or retry_quality['score'] >= quality['score'],
    }
    if used_retry['retry_kept']:
        return retry_ranked, retry_context, used_retry, retry_quality
    return ranked, first_context, used_retry, quality


def maybe_retry_after_answer(plan, conf, folder, queries, ranked, context, final_answer, top):
    aq = answer_quality(plan, final_answer)
    if aq['good']:
        return ranked, context, final_answer, None, aq
    retry_queries = refine_queries_for_retry(plan, queries)
    if 'tax' in plan.get('domains', []):
        retry_queries = [
            'payment OR paid OR receipt OR εκκαθαριστικό OR πληρωμή OR καταβολή',
            'ΕΝΦΙΑ OR πληρωμή OR δόση OR οφειλή',
            'φόρος OR πληρωμή OR βεβαίωση OR εκκαθαριστικό',
        ] + retry_queries
    retry_raw = []
    for q in retry_queries[:8]:
        retry_raw.extend(recoll_search(q, conf))
    retry_ranked = merge_results(retry_raw, plan, folder=folder)
    retry_context = build_context(retry_ranked, top)
    retry_answer = local_answer(plan, retry_context)
    retry_aq = answer_quality(plan, retry_answer)
    info = {'reason': aq['reason'], 'retry_queries': retry_queries[:8], 'retry_kept': retry_aq['good']}
    if retry_aq['good']:
        return retry_ranked, retry_context, retry_answer, info, retry_aq
    return ranked, context, final_answer, info, aq


def main():
    ap = argparse.ArgumentParser(description='Recoll-assisted local file finder with optional LLM synthesis')
    ap.add_argument('query', help='Natural language question')
    ap.add_argument('--conf', default=DEFAULT_RECOLL_CONF, help='Recoll config dir')
    ap.add_argument('--top', type=int, default=12, help='Top candidate files to inspect')
    ap.add_argument('--folder', help='Keep only results whose path contains this folder string, e.g. Finance or RealEstate')
    ap.add_argument('--faiss-dir', default=FAISS_DIR, help='FAISS index directory')
    ap.add_argument('--debug', action='store_true', help='Print candidate scores/reasons for debugging')
    ap.add_argument('--json', action='store_true', help='Emit JSON only')
    args = ap.parse_args()

    plan = build_query_plan(args.query)
    queries = build_queries_from_plan(plan)
    raw = []
    # Use basic search for filename: and dir: queries, full search for others
    for q in queries[:14]:
        if q.startswith('filename:') or q.startswith('dir:'):
            raw.extend(recoll_search_basic(q, args.conf))
        else:
            raw.extend(recoll_search(q, args.conf))
    ranked = merge_results(raw, plan, folder=args.folder)
    # Hybrid: merge BM25 results with vector search via RRF
    vec_results = vector_search(args.query, top_k=30, faiss_dir=args.faiss_dir)
    if vec_results:
        ranked = vector_augment(ranked, vec_results)
        # Re-score merged results with plan-based scoring
        for item in ranked:
            if 'score' not in item or item.get('queries') == ['vector_search']:
                item['score'], item['score_reasons'] = score_result(item, plan, folder=args.folder)
    ranked, context, retry_info, quality = maybe_retry_search(plan, args.conf, args.folder, queries[:14], ranked, args.top)
    llm = call_openai_answer(args.query, context)
    final_answer = llm or local_answer(plan, context)
    # Only do answer-retry if first pass was truly poor (skip to avoid timeouts)
    answer_retry = None
    answer_quality_info = answer_quality(plan, final_answer)
    if not answer_quality_info['good'] and len(ranked) > 0:
        ranked, context, final_answer, answer_retry, answer_quality_info = maybe_retry_after_answer(plan, args.conf, args.folder, queries[:14], ranked, context, final_answer, args.top)
    result = {'query': args.query, 'plan': plan, 'queries_run': queries[:14], 'folder_filter': args.folder, 'quality': quality, 'retry': retry_info, 'answer_quality': answer_quality_info, 'answer_retry': answer_retry, 'candidates': context, 'final': final_answer}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(f'QUERY: {args.query}\n')
    print(f'PLAN: {json.dumps(plan, ensure_ascii=False)}')
    if args.folder:
        print(f'FOLDER FILTER: {args.folder}')
    print(f'QUALITY: {quality}')
    if retry_info:
        print(f'RETRY: {retry_info}')
    print(f'ANSWER_QUALITY: {answer_quality_info}')
    if answer_retry:
        print(f'ANSWER_RETRY: {answer_retry}')
    print('QUERIES RUN:')
    for q in queries[:10]:
        print(f'- {q}')
    print('\nANSWER:')
    print(result['final'].get('answer', ''))
    print('\nBEST FILES:')
    for bf in result['final'].get('best_files', [])[:5]:
        print(f'- {bf["path"]}')
        if bf.get('why'):
            print(f'  why: {bf["why"]}')
    if result['final'].get('values_found'):
        print('\nVALUES FOUND:')
        for vh in result['final']['values_found'][:10]:
            print(f'- {vh["match"]} :: {vh["path"]}')
            print(f'  snippet: {vh["snippet"]}')
    print('\nTOP CANDIDATE SNIPPETS:')
    for item in context[:5]:
        print(f'\n* {item["path"]}')
        if args.debug:
            print(f'  score: {item.get("score")} reasons: {item.get("score_reasons", [])}')
        for sn in item.get('snippets', [])[:3]:
            print(f'  - {sn}')


if __name__ == '__main__':
    main()
