#!$VENV_GTE
"""Extraction audit for dsearch2-update.
Reads eval_set_phaseB_30.txt, extracts text from each file, reports:
- text length, chunk count, OCR sidecar presence, classifier tier
- flags files with 0 chunks and explains why

Usage:
    python test_dsearch2_extraction_audit.py [--dsearch2-update /path/to/dsearch2-update]
"""
import argparse, importlib.machinery, importlib.util, os, sys

EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
EVAL_FILES = os.path.join(EVAL_DIR, 'eval_set_phaseB_30.txt')

def load_mod(path):
    loader = importlib.machinery.SourceFileLoader('dsearch2_update', path)
    spec = importlib.util.spec_from_loader('dsearch2_update', loader, origin=path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules['dsearch2_update'] = mod
    old_argv = sys.argv
    sys.argv = ['dsearch2-update', '--status']
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass
    finally:
        sys.argv = old_argv
    return mod

def main():
    parser = argparse.ArgumentParser(description='Extraction audit')
    parser.add_argument('--dsearch2-update', default='/usr/local/bin/dsearch2-update')
    args = parser.parse_args()

    mod = load_mod(args.dsearch2_update)

    with open(EVAL_FILES) as f:
        paths = [line.strip() for line in f if line.strip()]

    print(f'{"File":<55} {"Ext":>5} {"Size":>8} {"TextLen":>8} {"Chunks":>6} {"OCR":>4} {"Tier":>4}  Reason')
    print('─' * 130)

    zero_chunk_files = []
    total = 0
    total_chunks = 0

    for path in paths:
        fname = os.path.basename(path)
        ext = os.path.splitext(fname)[1].lower()
        total += 1

        if not os.path.exists(path):
            print(f'{fname[:54]:<55} {ext:>5} {"MISSING":>8} {"":>8} {"":>6} {"":>4} {"":>4}  FILE NOT FOUND')
            continue

        fsize = os.path.getsize(path)

        has_ocr = False
        for suf in mod.OCR_SIDECAR_PATTERNS:
            if os.path.exists(path + suf):
                has_ocr = True
                break

        text = mod.extract_text(path)
        text = text.encode('utf-8', errors='ignore').decode('utf-8').strip()
        text_len = len(text)

        if text_len < mod.MIN_CHUNK_LEN:
            chunks = []
        else:
            chunks = mod.chunk_text(text)
        n_chunks = len(chunks)
        total_chunks += n_chunks

        tier = ''
        reason = ''
        if n_chunks > 0:
            tier, evidence = mod.classify_source_tier(path, fname, ext, text)
            reason = evidence[:50]
        else:
            if fsize < 100:
                reason = f'file too small ({fsize}B, min 100)'
            elif text_len == 0:
                if ext in ('.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp', '.gif'):
                    reason = 'no OCR sidecar' if not has_ocr else 'OCR text empty'
                elif ext == '.pdf':
                    reason = 'PDF text extraction returned empty'
                else:
                    reason = 'text extraction returned empty'
            elif text_len < mod.MIN_CHUNK_LEN:
                reason = f'text too short ({text_len} chars, min {mod.MIN_CHUNK_LEN})'
            else:
                reason = 'chunk_text() returned empty (unexpected)'

            zero_chunk_files.append((path, fname, ext, fsize, text_len, has_ocr, reason))

        ocr_mark = 'Y' if has_ocr else '-'
        print(f'{fname[:54]:<55} {ext:>5} {fsize:>8,} {text_len:>8,} {n_chunks:>6} {ocr_mark:>4} {tier:>4}  {reason}')

    print(f'\n{"="*130}')
    print(f'TOTAL: {total} files, {total_chunks} chunks')
    print(f'ZERO-CHUNK FILES: {len(zero_chunk_files)}')

    if zero_chunk_files:
        print(f'\n{"─"*130}')
        print('ZERO-CHUNK DETAIL:')
        for path, fname, ext, fsize, text_len, has_ocr, reason in zero_chunk_files:
            print(f'  {fname}')
            print(f'    path:     {path}')
            print(f'    size:     {fsize:,} bytes')
            print(f'    text_len: {text_len:,} chars')
            print(f'    OCR:      {"exists" if has_ocr else "MISSING"}')
            print(f'    reason:   {reason}')
            if ext in ('.jpg', '.jpeg', '.png', '.tif', '.tiff') and not has_ocr:
                print(f'    FIX:      needs OCR sidecar ({path}.ocr.gemini-pro.txt)')
            elif ext == '.pdf' and text_len == 0:
                print(f'    FIX:      PDF may need OCR (scanned image-only PDF?)')
            elif fsize < 100:
                print(f'    FIX:      genuinely too small — acceptable as 0 chunks')
            print()

if __name__ == '__main__':
    main()
