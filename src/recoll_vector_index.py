#!/usr/bin/env python3
"""
Build FAISS vector index with document chunking.
Splits docs into overlapping chunks, embeds with multilingual-e5-small.

Usage:
    VENV/python3 /tmp/recoll_vector_index.py --build [--conf DIR] [--limit 500]
    VENV/python3 /tmp/recoll_vector_index.py --query "search" [--conf DIR] [--top 20]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import zipfile
import numpy as np
from pathlib import Path

os.environ.setdefault('HF_HOME', '$HF_HOME')

DEFAULT_FAISS_DIR = '$FAISS_BASE/gte'
MODEL_NAME = 'Alibaba-NLP/gte-multilingual-base'
# Models that need "query:"/"passage:" prefixes (e5 family)
E5_PREFIX_MODELS = {'intfloat/multilingual-e5-small', 'intfloat/multilingual-e5-base', 'intfloat/multilingual-e5-large'}
DEFAULT_RECOLL_CONF = os.path.expanduser('~/.recoll')

# Named index presets: name → (faiss_dir, model, venv_python)
INDEX_PRESETS = {
    'e5': ('$FAISS_BASE/e5-base', 'intfloat/multilingual-e5-base',
           '$VENV_TF'),
    'gte': ('$FAISS_BASE/gte', 'Alibaba-NLP/gte-multilingual-base',
            '$VENV_GTE'),
}

# Chunking parameters
CHUNK_SIZE = 500       # chars per chunk
CHUNK_OVERLAP = 100    # overlap between chunks
MAX_TEXT_CHARS = 30000 # max text to extract per doc (covers ~15 pages)
MIN_CHUNK_LEN = 30     # skip tiny chunks
BATCH_SIZE = 64

TEXT_EXTS = {'.txt', '.md', '.rtf', '.html', '.htm', '.csv', '.log'}
OFFICE_EXTS = {'.odt', '.ods', '.docx', '.xlsx'}
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp'}
SKIP_EXTS = {'.webp', '.gif', '.mp3', '.mp4', '.avi', '.mkv', '.zip', '.gz',
             '.tar', '.7z', '.rar', '.iso', '.bin', '.exe', '.dll',
             '.so', '.o', '.pyc', '.class', '.whl', '.egg', '.svg'}


def get_all_doc_paths(conf_dir):
    """Scan indexed directories for documents."""
    topdirs = []
    conf_file = os.path.join(conf_dir, 'recoll.conf')
    if os.path.exists(conf_file):
        with open(conf_file) as f:
            for line in f:
                if line.strip().startswith('topdirs'):
                    topdirs = line.split('=', 1)[1].strip().split()
                    break
    if not topdirs:
        topdirs = [os.path.expanduser('~/DATA')]

    indexable_exts = TEXT_EXTS | OFFICE_EXTS | IMAGE_EXTS | {'.pdf', '.doc', '.ppt', '.pptx', '.xls'}
    paths = []
    for topdir in topdirs:
        for root, dirs, files in os.walk(topdir, followlinks=True):
            dirs[:] = [d for d in dirs if d not in
                       {'.git', '.svn', 'node_modules', '__pycache__',
                        '.cache', '.thumbnails', '.Trash-0', '.Trash-1000'}]
            for fname in files:
                # Skip .ocr.txt cache files — the parent image reads them
                if fname.endswith('.ocr.txt'):
                    continue
                ext = Path(fname).suffix.lower()
                if ext in indexable_exts:
                    full = os.path.join(root, fname)
                    try:
                        if os.path.getsize(full) > 100:
                            paths.append(full)
                    except OSError:
                        pass
    return paths


def extract_text(path):
    """Extract full text from a document."""
    p = Path(path)
    if not p.exists() or not p.is_file():
        return ''
    ext = p.suffix.lower()
    try:
        if ext in TEXT_EXTS:
            return p.read_text(errors='ignore')[:MAX_TEXT_CHARS]
        if ext in OFFICE_EXTS:
            z = zipfile.ZipFile(path)
            txt = []
            for n in z.namelist():
                if n.endswith(('content.xml', 'document.xml', 'sharedStrings.xml')):
                    txt.append(z.read(n).decode('utf-8', 'ignore'))
            return re.sub(r'<[^>]+>', ' ', ' '.join(txt))[:MAX_TEXT_CHARS]
        if ext == '.pdf':
            cp = subprocess.run(
                ['pdftotext', '-q', '-nopgbrk', path, '-'],
                capture_output=True, timeout=30
            )
            text = cp.stdout.decode('utf-8', errors='replace').strip()
            if len(text) >= MIN_CHUNK_LEN:
                return text[:MAX_TEXT_CHARS]
            return ''  # skip image-only PDFs (no Tesseract fallback)
        if ext == '.doc':
            cp = subprocess.run(['antiword', path], capture_output=True, timeout=15)
            return cp.stdout.decode('utf-8', errors='replace')[:MAX_TEXT_CHARS]
        if ext in IMAGE_EXTS:
            # Use Claude Vision OCR cache (.ocr.txt) only — skip if no cache
            ocr_cache = path + '.ocr.txt'
            if os.path.exists(ocr_cache):
                text = Path(ocr_cache).read_text(errors='ignore').strip()
                if len(text) >= MIN_CHUNK_LEN:
                    return text[:MAX_TEXT_CHARS]
            return ''  # skip images without OCR cache
    except Exception:
        pass
    return f'{p.stem} {p.parent.name}'


def chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Split text into overlapping chunks."""
    text = text.strip()
    if len(text) <= chunk_size:
        return [text] if len(text) >= MIN_CHUNK_LEN else []
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if len(chunk) >= MIN_CHUNK_LEN:
            chunks.append(chunk)
        start += chunk_size - overlap
    return chunks


def build_index(conf_dir, faiss_dir, limit=None, model_name=None):
    """Build chunked FAISS index."""
    import faiss
    from sentence_transformers import SentenceTransformer

    model_name = model_name or MODEL_NAME
    use_prefix = model_name in E5_PREFIX_MODELS

    index_file = os.path.join(faiss_dir, 'index.faiss')
    meta_file = os.path.join(faiss_dir, 'metadata.json')
    os.makedirs(faiss_dir, exist_ok=True)

    print(f'Loading embedding model: {model_name}...')
    model = SentenceTransformer(model_name, trust_remote_code=True)

    print(f'Scanning {conf_dir} for documents...')
    all_paths = get_all_doc_paths(conf_dir)
    if limit:
        all_paths = all_paths[:limit]
    print(f'Found {len(all_paths)} documents')

    # Extract text and chunk
    chunk_texts = []     # "passage: chunk_text"
    chunk_doc_ids = []   # index into doc_paths
    doc_paths = []       # unique document paths
    doc_idx = {}         # path → index

    skipped = 0
    for i, path in enumerate(all_paths):
        if i % 200 == 0:
            sys.stderr.write(f'\r  Extracting+chunking: {i}/{len(all_paths)} ({len(chunk_texts)} chunks)...')
            sys.stderr.flush()
        try:
            text = extract_text(path)
            text = text.encode('utf-8', errors='ignore').decode('utf-8').strip()
            if len(text) < MIN_CHUNK_LEN:
                skipped += 1
                continue

            # Register document
            if path not in doc_idx:
                doc_idx[path] = len(doc_paths)
                doc_paths.append(path)
            did = doc_idx[path]

            # Chunk and add
            chunks = chunk_text(text)
            for ch in chunks:
                chunk_texts.append(f'passage: {ch}' if use_prefix else ch)
                chunk_doc_ids.append(did)
        except Exception:
            skipped += 1

    sys.stderr.write(f'\r  Done: {len(doc_paths)} docs → {len(chunk_texts)} chunks (skipped {skipped})\n')

    if not chunk_texts:
        print('No chunks generated. Aborting.')
        return

    print(f'Embedding {len(chunk_texts)} chunks (batch={BATCH_SIZE})...')
    t0 = time.time()
    embeddings = model.encode(
        chunk_texts, batch_size=BATCH_SIZE, show_progress_bar=True,
        normalize_embeddings=True
    )
    elapsed = time.time() - t0
    print(f'Embedding done: {elapsed:.0f}s ({len(chunk_texts)/max(elapsed,1):.1f} chunks/sec)')

    print('Building FAISS index...')
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(np.array(embeddings).astype('float32'))
    faiss.write_index(index, index_file)

    meta = {
        'model': model_name,
        'dim': dim,
        'num_docs': len(doc_paths),
        'num_chunks': len(chunk_texts),
        'chunk_size': CHUNK_SIZE,
        'chunk_overlap': CHUNK_OVERLAP,
        'doc_paths': doc_paths,
        'chunk_doc_ids': chunk_doc_ids,
        'build_time': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    with open(meta_file, 'w') as f:
        json.dump(meta, f, ensure_ascii=False)

    idx_size = os.path.getsize(index_file) / 1e6
    print(f'Done! {index_file} ({idx_size:.1f} MB)')
    print(f'  {len(doc_paths)} docs, {len(chunk_texts)} chunks, {dim} dims')


def search(query, faiss_dir, top_k=20, model_name=None):
    """Search: find top chunks, aggregate to document level."""
    import faiss
    from sentence_transformers import SentenceTransformer

    index_file = os.path.join(faiss_dir, 'index.faiss')
    meta_file = os.path.join(faiss_dir, 'metadata.json')

    # Auto-detect model from metadata if not specified
    with open(meta_file) as f:
        meta = json.load(f)
    model_name = model_name or meta.get('model', MODEL_NAME)
    use_prefix = model_name in E5_PREFIX_MODELS

    model = SentenceTransformer(model_name, trust_remote_code=True)
    index = faiss.read_index(index_file)

    doc_paths = meta['doc_paths']
    chunk_doc_ids = meta['chunk_doc_ids']

    # Search more chunks than needed, then aggregate per document
    q_emb = model.encode([f'query: {query}' if use_prefix else query], normalize_embeddings=True)
    D, I = index.search(np.array(q_emb).astype('float32'), min(top_k * 3, index.ntotal))

    # Aggregate: best chunk score per document
    doc_scores = {}
    for score, idx in zip(D[0], I[0]):
        if 0 <= idx < len(chunk_doc_ids):
            did = chunk_doc_ids[idx]
            if did not in doc_scores or score > doc_scores[did]:
                doc_scores[did] = float(score)

    # Sort by score, return top_k documents
    ranked = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    results = []
    for did, score in ranked:
        if 0 <= did < len(doc_paths):
            results.append({'path': doc_paths[did], 'score': score})
    return results


def main():
    presets = ', '.join(INDEX_PRESETS.keys())
    ap = argparse.ArgumentParser(description='Chunked FAISS Vector Index for Recoll')
    ap.add_argument('--build', action='store_true')
    ap.add_argument('--conf', default=DEFAULT_RECOLL_CONF, help='Recoll config dir')
    ap.add_argument('--faiss-dir', default=None, help='FAISS output dir (overrides --index)')
    ap.add_argument('--index', choices=list(INDEX_PRESETS.keys()), default=None,
                    help=f'Use a named index preset: {presets}')
    ap.add_argument('--limit', type=int, help='Limit docs (for testing)')
    ap.add_argument('--query', help='Search query')
    ap.add_argument('--top', type=int, default=20)
    ap.add_argument('--model', default=None, help='Override embedding model (auto-detected from index metadata on search)')
    args = ap.parse_args()

    # Resolve index preset
    faiss_dir = args.faiss_dir
    model_name = args.model
    if args.index and args.index in INDEX_PRESETS:
        preset = INDEX_PRESETS[args.index]
        faiss_dir = faiss_dir or preset[0]
        model_name = model_name or preset[1]
    faiss_dir = faiss_dir or DEFAULT_FAISS_DIR

    if args.build:
        build_index(args.conf, faiss_dir, limit=args.limit, model_name=model_name)
    elif args.query:
        results = search(args.query, faiss_dir, args.top, model_name=model_name)
        for r in results:
            print(f'  {r["score"]:.4f}  {r["path"]}')
    else:
        ap.print_help()
        print(f'\nAvailable index presets: {presets}')


if __name__ == '__main__':
    main()
