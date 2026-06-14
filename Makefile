# Semantic Disk Search — Build & Run Commands
# All targets use explicit python3 paths (~/DATA is noexec)

SRC     := $(shell dirname $(realpath $(lastword $(MAKEFILE_LIST))))/src
SCRIPTS := $(shell dirname $(realpath $(lastword $(MAKEFILE_LIST))))/scripts
GOLDEN  := $(shell dirname $(realpath $(lastword $(MAKEFILE_LIST))))/golden_sets

VENV_GTE := $VENV_GTE
VENV_TF  := $VENV_TF
FAISS_BASE := $FAISS_BASE

# ── Search ──────────────────────────────────────────────
.PHONY: search search-cohere search-gte search-all

search:  ## Quick search (Cohere default): make search Q="μετάταξη"
	dsearch-multimodel "$(Q)"

search-cohere:  ## Search with Cohere model
	dsearch-multimodel --model cohere "$(Q)"

search-gte:  ## Search with GTE model
	dsearch-multimodel --model gte "$(Q)"

search-all:  ## Full-disk BM25+Claude (no vector)
	python3 $(SRC)/recoll_query_assist.py "$(Q)"

# ── Benchmark ───────────────────────────────────────────
.PHONY: benchmark benchmark-sample benchmark-tuning benchmark-canary

benchmark:  ## Full 38-query golden set benchmark
	python3 $(SRC)/recoll_benchmark.py run \
		--golden $(GOLDEN)/full_38q.json --tag full --verbose

benchmark-sample:  ## 13-query sample (Finance/Tax+Health)
	python3 $(SRC)/recoll_benchmark.py run \
		--golden $(GOLDEN)/sample_13q.json --tag sample --verbose

benchmark-tuning:  ## 26-query tuning set
	python3 $(SRC)/recoll_benchmark.py run \
		--golden $(GOLDEN)/tuning_26q.json --tag tuning --verbose

benchmark-canary:  ## 12-query canary (overfitting check)
	python3 $(SRC)/recoll_benchmark.py run \
		--golden $(GOLDEN)/canary_12q.json --tag canary --verbose

# ── Index Building ──────────────────────────────────────
.PHONY: rebuild-gte rebuild-e5 rebuild-cohere rebuild-all

rebuild-gte:  ## Rebuild GTE FAISS index (~6.5h CPU)
	$(VENV_GTE) $(SRC)/recoll_vector_index.py --build --index gte

rebuild-e5:  ## Rebuild e5-base FAISS index
	$(VENV_TF) $(SRC)/recoll_vector_index.py --build --index e5

rebuild-cohere:  ## Rebuild Cohere index (API, ~17min, costs ~$1.60)
	set -a && source ~/.config/dsearch/.env && set +a && \
	$(VENV_GTE) $(SCRIPTS)/cohere_embed.py

rebuild-all: rebuild-gte rebuild-e5 rebuild-cohere  ## Rebuild all indexes

# ── OCR ─────────────────────────────────────────────────
.PHONY: ocr-batch ocr-status

ocr-batch:  ## Batch OCR on corpus images (Claude Vision)
	$(VENV_GTE) $OCR_SERVER/bulk_ocr.py \
		$CORPUS_DIR/ --exclude Ασυρματοι

ocr-status:  ## Count OCR cache files
	@echo "Gemini OCR:"; find $CORPUS_DIR -name '*.ocr.gemini.txt' | wc -l
	@echo "Gemini-pro:"; find $CORPUS_DIR -name '*.ocr.gemini-pro.txt' | wc -l

# ── Jupyter ─────────────────────────────────────────────
.PHONY: jupyter

jupyter:  ## Launch Jupyter notebook server
	cd notebooks && $(VENV_GTE) -m jupyter notebook --no-browser

# ── Recoll ──────────────────────────────────────────────
.PHONY: recoll-reindex recoll-status

recoll-reindex:  ## Full Recoll reindex with OCR (2-4h, runs in background)
	nohup recollindex -c ~/.recoll > /tmp/recoll-reindex.log 2>&1 &
	@echo "PID: $$(cat /tmp/recoll-reindex.log 2>/dev/null || echo 'started')"

recoll-status:  ## Show Recoll index stats
	@du -sh $XAPIAN_DB/
	@recollq -c ~/.recoll -b '*' 2>/dev/null | wc -l | xargs echo "Documents:"

# ── Info ────────────────────────────────────────────────
.PHONY: help status

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

status:  ## Show index sizes and model info
	@echo "=== FAISS Indexes ==="
	@for m in cohere-v3 e5-base e5-large gte bge-m3; do \
		size=$$(du -sh $(FAISS_BASE)/$$m/index.faiss 2>/dev/null | cut -f1); \
		docs=$$(python3 -c "import json; m=json.load(open('$(FAISS_BASE)/$$m/metadata.json')); print(f'{m.get(\"num_docs\",\"?\")}')" 2>/dev/null); \
		printf "  %-12s %s  %s docs\n" "$$m" "$$size" "$$docs"; \
	done
	@echo "=== Xapian BM25 ==="
	@du -sh $XAPIAN_DB/
	@echo "=== ChromaDB ==="
	@du -sh $CHROMADB_DIR/
	@echo "=== OCR Caches ==="
	@find $CORPUS_DIR -name '*.ocr.*.txt' 2>/dev/null | wc -l | xargs echo "  files:"

.DEFAULT_GOAL := help
