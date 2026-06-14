#!/usr/bin/env python3
"""
ChromaDB vector index with incremental updates.
Replaces FAISS with persistent ChromaDB — supports add/delete/update without full rebuild.

Usage:
    VENV/python3 chroma_vector_index.py --build [--conf DIR] [--limit N]
    VENV/python3 chroma_vector_index.py --update            # incremental: new/changed files only
    VENV/python3 chroma_vector_index.py --query "search"    [--top N] [--folder X]
    VENV/python3 chroma_vector_index.py --delete-path "/path/to/file"
    VENV/python3 chroma_vector_index.py --stats
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

os.environ.setdefault('HF_HOME', '$HF_HOME')

DEFAULT_CHROMA_DIR = '$CHROMADB_DIR'
DEFAULT_COLLECTION = 'dsearch'
MODEL_NAME = 'Alibaba-NLP/gte-multilingual-base'
DEFAULT_RECOLL_CONF = os.path.expanduser('~/.recoll')

CHUNK_SIZE = 500
CHUNK_OVERLAP = 100
MAX_TEXT_CHARS = 30000
MIN_CHUNK_LEN = 30
BATCH_SIZE = 64

TEXT_EXTS = {'.txt', '.md', '.rtf', '.html', '.htm', '.csv', '.log'}
OFFICE_EXTS = {'.odt', '.ods', '.docx', '.xlsx'}
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp'}


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
                if fname.endswith('.ocr.txt') or fname.endswith('.ocr.gemini.txt') or fname.endswith('.ocr.gemini-pro.txt'):
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
            return ''
        if ext == '.doc':
            cp = subprocess.run(['antiword', path], capture_output=True, timeout=15)
            return cp.stdout.decode('utf-8', errors='replace')[:MAX_TEXT_CHARS]
        if ext in IMAGE_EXTS:
            # Check all OCR cache variants
            for suffix in ['.ocr.txt', '.ocr.gemini.txt', '.ocr.gemini-pro.txt']:
                ocr_cache = path + suffix
                if os.path.exists(ocr_cache):
                    text = Path(ocr_cache).read_text(errors='ignore').strip()
                    if len(text) >= MIN_CHUNK_LEN:
                        return text[:MAX_TEXT_CHARS]
            return ''
    except Exception:
        pass
    return ''


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


def make_chunk_id(path, chunk_idx):
    """Deterministic chunk ID from path + index."""
    h = hashlib.md5(path.encode('utf-8', errors='ignore')).hexdigest()[:12]
    return f"{h}_{chunk_idx}"


def get_file_mtime(path):
    """Get file modification time as string."""
    try:
        return str(int(os.path.getmtime(path)))
    except OSError:
        return '0'


def get_folder(path, conf_dir):
    """Extract top-level subfolder relative to topdirs."""
    topdirs = []
    conf_file = os.path.join(conf_dir, 'recoll.conf')
    if os.path.exists(conf_file):
        with open(conf_file) as f:
            for line in f:
                if line.strip().startswith('topdirs'):
                    topdirs = line.split('=', 1)[1].strip().split()
                    break
    for td in topdirs:
        if path.startswith(td):
            rel = path[len(td):].lstrip('/')
            parts = rel.split('/')
            return parts[0] if parts else ''
    return ''


def get_collection(chroma_dir, collection_name, model_name=None):
    """Get or create ChromaDB collection with GTE embedding function."""
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

    model_name = model_name or MODEL_NAME
    client = chromadb.PersistentClient(path=chroma_dir)
    ef = SentenceTransformerEmbeddingFunction(
        model_name=model_name,
        trust_remote_code=True,
    )
    collection = client.get_or_create_collection(
        name=collection_name,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"}
    )
    return client, collection


def build_index(conf_dir, chroma_dir, collection_name, limit=None, model_name=None):
    """Full build: clear and rebuild ChromaDB collection."""
    import chromadb

    client, collection = get_collection(chroma_dir, collection_name, model_name)

    # Clear existing
    if collection.count() > 0:
        print(f'Clearing existing collection ({collection.count()} chunks)...')
        # ChromaDB delete all
        all_ids = collection.get()['ids']
        if all_ids:
            for i in range(0, len(all_ids), 5000):
                collection.delete(ids=all_ids[i:i+5000])

    print(f'Scanning {conf_dir} for documents...')
    all_paths = get_all_doc_paths(conf_dir)
    if limit:
        all_paths = all_paths[:limit]
    print(f'Found {len(all_paths)} documents')

    added = 0
    skipped = 0
    total_chunks = 0

    for i, path in enumerate(all_paths):
        if i % 200 == 0:
            sys.stderr.write(f'\r  Processing: {i}/{len(all_paths)} ({total_chunks} chunks, {skipped} skipped)...')
            sys.stderr.flush()

        try:
            text = extract_text(path)
            text = text.encode('utf-8', errors='ignore').decode('utf-8').strip()
            if len(text) < MIN_CHUNK_LEN:
                skipped += 1
                continue

            chunks = chunk_text(text)
            if not chunks:
                skipped += 1
                continue

            ext = Path(path).suffix.lower()
            folder = get_folder(path, conf_dir)
            mtime = get_file_mtime(path)

            chunk_ids = [make_chunk_id(path, ci) for ci in range(len(chunks))]
            metadatas = [{
                'path': path,
                'folder': folder,
                'ext': ext,
                'mtime': mtime,
                'chunk_idx': ci,
                'total_chunks': len(chunks),
            } for ci in range(len(chunks))]

            # Add in batches (ChromaDB limit)
            for b in range(0, len(chunks), BATCH_SIZE):
                collection.add(
                    ids=chunk_ids[b:b+BATCH_SIZE],
                    documents=chunks[b:b+BATCH_SIZE],
                    metadatas=metadatas[b:b+BATCH_SIZE],
                )

            added += 1
            total_chunks += len(chunks)
        except Exception as e:
            skipped += 1

    sys.stderr.write(f'\r  Done: {added} docs, {total_chunks} chunks, {skipped} skipped\n')
    print(f'Collection "{collection_name}" has {collection.count()} chunks')


def update_index(conf_dir, chroma_dir, collection_name, model_name=None):
    """Incremental update: add new/changed files, remove deleted."""
    client, collection = get_collection(chroma_dir, collection_name, model_name)

    # Get all currently indexed paths and their mtimes
    existing = {}  # path → mtime
    if collection.count() > 0:
        # Fetch all metadata (paginated)
        offset = 0
        batch = 5000
        while True:
            result = collection.get(limit=batch, offset=offset, include=['metadatas'])
            if not result['ids']:
                break
            for meta in result['metadatas']:
                existing[meta['path']] = meta['mtime']
            offset += batch

    print(f'Currently indexed: {len(existing)} unique files')

    # Scan disk
    all_paths = get_all_doc_paths(conf_dir)
    disk_set = set(all_paths)
    existing_set = set(existing.keys())

    new_files = disk_set - existing_set
    deleted_files = existing_set - disk_set
    # Changed = same path but different mtime
    changed_files = set()
    for path in disk_set & existing_set:
        if get_file_mtime(path) != existing.get(path, '0'):
            changed_files.add(path)

    print(f'New: {len(new_files)}, Changed: {len(changed_files)}, Deleted: {len(deleted_files)}')

    # Delete removed/changed files' chunks
    to_remove = deleted_files | changed_files
    if to_remove:
        print(f'Removing {len(to_remove)} files from index...')
        # Get IDs for these paths
        for path in to_remove:
            results = collection.get(where={"path": path})
            if results['ids']:
                collection.delete(ids=results['ids'])

    # Add new + changed files
    to_add = new_files | changed_files
    if to_add:
        print(f'Adding {len(to_add)} files...')
        added = 0
        total_chunks = 0
        for i, path in enumerate(sorted(to_add)):
            if i % 100 == 0 and i > 0:
                sys.stderr.write(f'\r  Adding: {i}/{len(to_add)} ({total_chunks} chunks)...')
                sys.stderr.flush()
            try:
                text = extract_text(path)
                text = text.encode('utf-8', errors='ignore').decode('utf-8').strip()
                if len(text) < MIN_CHUNK_LEN:
                    continue
                chunks = chunk_text(text)
                if not chunks:
                    continue
                ext = Path(path).suffix.lower()
                folder = get_folder(path, conf_dir)
                mtime = get_file_mtime(path)
                chunk_ids = [make_chunk_id(path, ci) for ci in range(len(chunks))]
                metadatas = [{
                    'path': path, 'folder': folder, 'ext': ext,
                    'mtime': mtime, 'chunk_idx': ci, 'total_chunks': len(chunks),
                } for ci in range(len(chunks))]
                for b in range(0, len(chunks), BATCH_SIZE):
                    collection.add(
                        ids=chunk_ids[b:b+BATCH_SIZE],
                        documents=chunks[b:b+BATCH_SIZE],
                        metadatas=metadatas[b:b+BATCH_SIZE],
                    )
                added += 1
                total_chunks += len(chunks)
            except Exception:
                pass
        sys.stderr.write(f'\r  Added: {added} files, {total_chunks} chunks\n')
    else:
        print('Nothing to update.')

    print(f'Collection total: {collection.count()} chunks')


def search(query, chroma_dir, collection_name, top_k=20, folder=None, model_name=None):
    """Search ChromaDB collection. Returns doc-level results (best chunk per doc)."""
    client, collection = get_collection(chroma_dir, collection_name, model_name)

    where_filter = {"folder": folder} if folder else None

    results = collection.query(
        query_texts=[query],
        n_results=min(top_k * 5, collection.count()),  # get more chunks, aggregate to docs
        where=where_filter,
    )

    # Aggregate: best chunk score per document path
    doc_scores = {}
    for dist, meta in zip(results['distances'][0], results['metadatas'][0]):
        path = meta['path']
        # ChromaDB returns distances (lower=closer for cosine), convert to similarity
        sim = 1.0 - dist
        if path not in doc_scores or sim > doc_scores[path]:
            doc_scores[path] = sim

    ranked = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    return [{'path': p, 'score': s} for p, s in ranked]


def delete_path(path, chroma_dir, collection_name, model_name=None):
    """Delete all chunks for a specific file path."""
    client, collection = get_collection(chroma_dir, collection_name, model_name)
    results = collection.get(where={"path": path})
    if results['ids']:
        collection.delete(ids=results['ids'])
        print(f'Deleted {len(results["ids"])} chunks for: {path}')
    else:
        print(f'Not found: {path}')


def stats(chroma_dir, collection_name, model_name=None):
    """Show collection statistics."""
    client, collection = get_collection(chroma_dir, collection_name, model_name)
    count = collection.count()
    print(f'Collection: {collection_name}')
    print(f'Chunks: {count}')
    if count == 0:
        return

    # Sample to get unique paths and folder distribution
    sample = collection.get(limit=min(count, 50000), include=['metadatas'])
    paths = set()
    folders = {}
    exts = {}
    for meta in sample['metadatas']:
        paths.add(meta['path'])
        f = meta.get('folder', '?')
        folders[f] = folders.get(f, 0) + 1
        e = meta.get('ext', '?')
        exts[e] = exts.get(e, 0) + 1

    print(f'Documents: {len(paths)}')
    print(f'Avg chunks/doc: {count / max(len(paths), 1):.1f}')
    print(f'\nFolders:')
    for f, c in sorted(folders.items(), key=lambda x: -x[1])[:10]:
        print(f'  {f}: {c} chunks')
    print(f'\nExtensions:')
    for e, c in sorted(exts.items(), key=lambda x: -x[1])[:10]:
        print(f'  {e}: {c} chunks')


def main():
    ap = argparse.ArgumentParser(description='ChromaDB Vector Index (replaces FAISS)')
    ap.add_argument('--build', action='store_true', help='Full rebuild')
    ap.add_argument('--update', action='store_true', help='Incremental update (new/changed/deleted)')
    ap.add_argument('--query', help='Search query')
    ap.add_argument('--delete-path', help='Delete a file from the index')
    ap.add_argument('--stats', action='store_true', help='Show collection stats')
    ap.add_argument('--conf', default=DEFAULT_RECOLL_CONF, help='Recoll config dir')
    ap.add_argument('--chroma-dir', default=DEFAULT_CHROMA_DIR, help='ChromaDB persistent dir')
    ap.add_argument('--collection', default=DEFAULT_COLLECTION, help='Collection name')
    ap.add_argument('--top', type=int, default=20)
    ap.add_argument('--folder', default=None, help='Filter by folder (e.g. Εργασιακα_ΜΟΥ)')
    ap.add_argument('--model', default=None, help='Override embedding model')
    ap.add_argument('--limit', type=int, help='Limit docs (for testing)')
    args = ap.parse_args()

    model = args.model or MODEL_NAME

    if args.build:
        build_index(args.conf, args.chroma_dir, args.collection, limit=args.limit, model_name=model)
    elif args.update:
        update_index(args.conf, args.chroma_dir, args.collection, model_name=model)
    elif args.query:
        results = search(args.query, args.chroma_dir, args.collection, args.top, folder=args.folder, model_name=model)
        for r in results:
            print(f'  {r["score"]:.4f}  {r["path"]}')
    elif args.delete_path:
        delete_path(args.delete_path, args.chroma_dir, args.collection, model_name=model)
    elif args.stats:
        stats(args.chroma_dir, args.collection, model_name=model)
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
