#!/usr/bin/env python3
"""Multi-model search: queries all indexes, merges, Claude reranks."""
import json, sys, os, subprocess, numpy as np, faiss
from concurrent.futures import ThreadPoolExecutor

os.environ.setdefault('HF_HOME', '$HF_HOME')
set_env = {}
with open('~/.config/dsearch/.env') as f:
    for line in f:
        if '=' in line and not line.startswith('#'):
            k, v = line.strip().split('=', 1)
            set_env[k] = v
os.environ.update(set_env)

FAISS_BASE = '$FAISS_BASE'
MODELS = ['cohere-v3', 'e5-base', 'gte']
TOP_PER_MODEL = 10

# Cache loaded models
_st_models = {}

def search_model(model_key, query):
    faiss_dir = f'{FAISS_BASE}/{model_key}'
    index = faiss.read_index(f'{faiss_dir}/index.faiss')
    meta = json.load(open(f'{faiss_dir}/metadata.json'))
    paths = meta['doc_paths']
    cids = meta['chunk_doc_ids']

    if 'cohere' in model_key:
        import cohere
        co = cohere.ClientV2(api_key=os.environ.get('COHERE_API_KEY', ''))
        resp = co.embed(texts=[query], model='embed-multilingual-v3.0',
                       input_type='search_query', embedding_types=['float'])
        qvec = np.array(resp.embeddings.float_, dtype=np.float32)
    else:
        from sentence_transformers import SentenceTransformer
        mname = meta['model']
        if mname not in _st_models:
            _st_models[mname] = SentenceTransformer(mname, trust_remote_code=True)
        m = _st_models[mname]
        qvec = m.encode([query], normalize_embeddings=True).astype(np.float32)

    scores, indices = index.search(qvec, 30)
    results = []
    seen = set()
    for score, idx in zip(scores[0], indices[0]):
        p = paths[cids[idx]]
        if p not in seen:
            seen.add(p)
            results.append({'path': p, 'score': float(score), 'model': model_key})
            if len(results) >= TOP_PER_MODEL:
                break
    return results

def main():
    query = ' '.join(sys.argv[1:]) if len(sys.argv) > 1 else input('Query: ')
    
    # Stage 1: Claude query expansion
    print(f'=== QUERY: {query} ===\n')
    print('Stage 1: Claude expanding query...')
    try:
        cp = subprocess.run(
            ['claude', '-p', '--model', 'haiku',
             '--dangerously-skip-permissions',
             f'Return ONLY a JSON list of 5 alternative search phrases for this query, mix Greek and English. No explanation. Query: {query}'],
            capture_output=True, timeout=30, stdin=subprocess.DEVNULL
        )
        expanded_raw = cp.stdout.decode().strip()
        # Try to parse JSON list from output
        import re
        match = re.search(r'\[.*\]', expanded_raw, re.DOTALL)
        if match:
            expanded = json.loads(match.group())
        else:
            expanded = []
    except Exception as e:
        expanded = []
    
    all_queries = [query] + expanded[:4]
    print(f'  Queries: {all_queries}\n')

    # Stage 2: Search all models × all queries
    print('Stage 2: Searching all models...')
    all_results = {}  # path → {best_score, models, queries}
    
    for q in all_queries:
        for model_key in MODELS:
            try:
                results = search_model(model_key, q)
                for r in results:
                    p = r['path']
                    if p not in all_results:
                        all_results[p] = {'path': p, 'scores': {}, 'found_by': set(), 'queries': set()}
                    key = f"{r['model']}:{q[:30]}"
                    all_results[p]['scores'][key] = r['score']
                    all_results[p]['found_by'].add(r['model'])
                    all_results[p]['queries'].add(q[:40])
            except Exception as e:
                print(f'  [{model_key}] error: {e}')
        print(f'  Searched "{q[:40]}..." → {len(all_results)} unique files so far')

    # Score: number of models that found it + average score
    ranked = []
    for p, info in all_results.items():
        model_count = len(info['found_by'])
        avg_score = sum(info['scores'].values()) / len(info['scores'])
        combined = model_count * 10 + avg_score
        ranked.append((combined, model_count, avg_score, p, info))
    ranked.sort(reverse=True)

    print(f'\n=== TOP 15 MERGED RESULTS ===\n')
    top = ranked[:15]
    for i, (comb, mc, avg, p, info) in enumerate(top):
        models = ','.join(sorted(info['found_by']))
        print(f'{i+1:2d}. [{mc} models, avg={avg:.3f}] {p[-80:]}')
        print(f'     found by: {models}')

    # Stage 3: Claude reranking
    print(f'\n=== Stage 3: Claude reranking top 15 ===\n')
    summaries = []
    for i, (_, _, _, p, _) in enumerate(top):
        fname = os.path.basename(p)
        folder = os.path.basename(os.path.dirname(p))
        summaries.append(f'{i+1}. {folder}/{fname}')
    
    rerank_prompt = (
        f'Original query: "{query}"\n\n'
        f'Rank these files by relevance to the query. Return ONLY a JSON list of numbers '
        f'in order of relevance (most relevant first), e.g. [3,1,7,...]\n\n'
        + '\n'.join(summaries)
    )
    
    try:
        cp = subprocess.run(
            ['claude', '-p', '--model', 'haiku',
             '--dangerously-skip-permissions',
             rerank_prompt],
            capture_output=True, timeout=30, stdin=subprocess.DEVNULL
        )
        rerank_raw = cp.stdout.decode().strip()
        import re
        match = re.search(r'\[[\d,\s]+\]', rerank_raw)
        if match:
            order = json.loads(match.group())
            print('Claude ranking:')
            for rank, idx in enumerate(order[:10]):
                if 1 <= idx <= len(top):
                    _, mc, avg, p, info = top[idx-1]
                    models = ','.join(sorted(info['found_by']))
                    print(f'  {rank+1}. {p[-80:]}')
                    print(f'     [{mc} models, avg={avg:.3f}] {models}')
        else:
            print(f'Could not parse reranking: {rerank_raw[:200]}')
    except Exception as e:
        print(f'Reranking failed: {e}')

if __name__ == '__main__':
    main()
