"""
Given a new (or existing) object, find its nearest neighbors in the
already-indexed catalog, and report which cluster it falls into.

Usage:
    python find_neighbors.py --object-id 173953
    python find_neighbors.py --object-id 173953 --explain   # add LLM writeup

Run build_index.py at least once before this.
"""

import argparse
import json

import numpy as np
from sentence_transformers import SentenceTransformer

import config
import data_source


def load_index():
    with open(config.INDEX_PATH, "r", encoding="utf-8") as f:
        records = json.load(f)
    embeddings = np.load(config.EMBEDDINGS_PATH)
    return records, embeddings


def find_neighbors(new_text: str, records, embeddings, model, top_k=None, exclude_id=None):
    top_k = top_k or config.TOP_K_NEIGHBORS
    query_vec = model.encode([new_text], normalize_embeddings=True)[0]

    # cosine similarity, since embeddings are normalized this is just a dot product
    sims = embeddings @ query_vec

    ranked = np.argsort(-sims)
    results = []
    for idx in ranked:
        rec = records[idx]
        if exclude_id is not None and rec["id"] == exclude_id:
            continue
        score = float(sims[idx])
        if score < config.MIN_SIMILARITY:
            break
        results.append({**rec, "similarity": round(score, 3)})
        if len(results) >= top_k:
            break
    return results


def assign_cluster(new_vec, records, embeddings):
    """
    Lightweight cluster assignment: requires clusters.json produced by
    cluster_catalog.py. Finds the cluster whose centroid is closest to
    the new item. Returns None if clustering hasn't been run yet.
    """
    try:
        with open("data/clusters.json", "r", encoding="utf-8") as f:
            cluster_data = json.load(f)
    except FileNotFoundError:
        return None

    centroids = np.array(cluster_data["centroids"])  # shape (n_clusters, dim)
    if centroids.size == 0:  # clustering ran but found no clusters
        return None
    labels = cluster_data["labels"]  # cluster id -> short description
    sims = centroids @ new_vec
    best = int(np.argmax(sims))
    return {
        "cluster_id": best,
        "label": labels.get(str(best), f"cluster {best}"),
        "similarity": round(float(sims[best]), 3),
    }


def explain_relationship(new_obj_text: str, neighbor: dict) -> str:
    """Optional: ask Claude to explain *why* two objects might be related."""
    if not config.USE_LLM_EXPLANATIONS:
        return ""
    try:
        import anthropic
        client = anthropic.Anthropic()
        prompt = (
            "You catalog artifacts for a small volunteer-run historical society.\n\n"
            f"New item: {new_obj_text}\n\n"
            f"Possibly related existing item: {neighbor['text']}\n\n"
            "In 1-2 plain sentences, suggest a concrete, specific reason these two "
            "items might be related (e.g. same maker, same era and region, same "
            "household/donor, same craft technique, part of a set). If there's no "
            "good specific reason beyond surface similarity, say so plainly instead "
            "of inventing a connection."
        )
        msg = client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        return f"(explanation unavailable: {e})"


def main(object_id: int, explain: bool):
    records, embeddings = load_index()
    model = SentenceTransformer(config.EMBEDDING_MODEL)

    new_obj = data_source.fetch_object(object_id)
    print(f"\nNew item: {new_obj['title']}  ({new_obj['url']})\n")

    neighbors = find_neighbors(new_obj["text"], records, embeddings, model, exclude_id=object_id)

    if not neighbors:
        print("No neighbors found above the similarity threshold.")
    else:
        print(f"Top {len(neighbors)} related items:\n")
        for n in neighbors:
            print(f"  [{n['similarity']}] {n['title']}  ({n['url']})")
            if explain:
                explanation = explain_relationship(new_obj["text"], n)
                print(f"      -> {explanation}")
        print()

    query_vec = model.encode([new_obj["text"]], normalize_embeddings=True)[0]
    cluster = assign_cluster(query_vec, records, embeddings)
    if cluster:
        print(f"Closest cluster: #{cluster['cluster_id']} — {cluster['label']} "
              f"(similarity {cluster['similarity']})")
    else:
        print("No cluster data yet — run cluster_catalog.py first.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--object-id", type=int, required=True)
    parser.add_argument("--explain", action="store_true", help="Add an LLM-written explanation for each neighbor")
    args = parser.parse_args()
    main(object_id=args.object_id, explain=args.explain)
