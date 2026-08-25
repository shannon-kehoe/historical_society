"""
Builds (or fully rebuilds) the local embedding index from the whole
catalog. Run this once to start, then periodically (e.g. weekly, via a
cron job or GitHub Action) to pick up items added directly in
museum-digital rather than through this pipeline.

Usage:
    python build_index.py            # full rebuild
    python build_index.py --max-pages 2   # quick test run, ~100 objects
"""

import argparse
import json
import os

import numpy as np
from sentence_transformers import SentenceTransformer

import config
import data_source


def main(max_pages=None):
    os.makedirs(config.DATA_DIR, exist_ok=True)

    print(f"Loading embedding model: {config.EMBEDDING_MODEL} (first run downloads it, ~1GB)")
    model = SentenceTransformer(config.EMBEDDING_MODEL)

    print(f"Fetching objects from {config.INSTANCE_SLUG} instance (mode={config.READ_MODE})...")
    records = []
    texts = []
    for obj in data_source.fetch_all_objects(max_pages=max_pages):
        if not obj["text"].strip():
            continue  # skip empty/unpublished stubs
        records.append(obj)
        texts.append(obj["text"])
        if len(records) % 100 == 0:
            print(f"  ...{len(records)} objects fetched")

    print(f"Fetched {len(records)} objects total. Embedding...")
    embeddings = model.encode(texts, show_progress_bar=True, normalize_embeddings=True)

    np.save(config.EMBEDDINGS_PATH, embeddings)
    with open(config.INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(records)} records to {config.INDEX_PATH}")
    print(f"Saved embeddings ({embeddings.shape}) to {config.EMBEDDINGS_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=None, help="Limit pages fetched, for a quick test run")
    args = parser.parse_args()
    main(max_pages=args.max_pages)
