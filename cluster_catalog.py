"""
Clusters the whole indexed catalog using HDBSCAN (handles an unknown
number of clusters and leaves genuine one-offs unclustered rather than
forcing them into a group). Run this after build_index.py, and re-run
periodically as the catalog grows.

Optionally asks Claude to write a short human-readable label for each
cluster, based on a sample of its member items.

Usage:
    python cluster_catalog.py
    python cluster_catalog.py --no-label   # skip the LLM labeling step
"""

import argparse
import json

import numpy as np

import config

try:
    import hdbscan
except ImportError:
    hdbscan = None


def label_cluster(sample_texts: list[str]) -> str:
    if not config.USE_LLM_EXPLANATIONS:
        return "(unlabeled)"
    try:
        import anthropic
        client = anthropic.Anthropic()
        joined = "\n".join(f"- {t[:200]}" for t in sample_texts[:8])
        prompt = (
            "Here are sample items from one group of related museum objects "
            f"in a local historic society's collection:\n\n{joined}\n\n"
            "In 3-6 words, name the shared theme connecting these items "
            "(e.g. 'farm tools, early 20th century' or 'wartime household items'). "
            "Just the label, nothing else."
        )
        msg = client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=30,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        return f"(labeling unavailable: {e})"


def main(do_label: bool):
    if hdbscan is None:
        raise SystemExit("Install hdbscan first: pip install hdbscan")

    with open(config.INDEX_PATH, "r", encoding="utf-8") as f:
        records = json.load(f)
    embeddings = np.load(config.EMBEDDINGS_PATH)

    print(f"Clustering {len(records)} objects...")
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=config.MIN_CLUSTER_SIZE,
        min_samples=config.MIN_SAMPLES,
        metric="euclidean",
    )
    cluster_labels = clusterer.fit_predict(embeddings)  # -1 = noise / no cluster

    n_clusters = len(set(cluster_labels)) - (1 if -1 in cluster_labels else 0)
    n_noise = int((cluster_labels == -1).sum())
    print(f"Found {n_clusters} clusters ({n_noise} items didn't fit any cluster)")

    centroids = []
    text_labels = {}
    for cluster_id in sorted(set(cluster_labels)):
        if cluster_id == -1:
            continue
        member_idxs = np.where(cluster_labels == cluster_id)[0]
        centroid = embeddings[member_idxs].mean(axis=0)
        centroid = centroid / np.linalg.norm(centroid)
        centroids.append(centroid)

        sample_texts = [records[i]["text"] for i in member_idxs[:8]]
        label = label_cluster(sample_texts) if do_label else f"cluster {cluster_id}"
        text_labels[str(len(centroids) - 1)] = f"{label} ({len(member_idxs)} items)"
        print(f"  cluster {cluster_id}: {len(member_idxs)} items -> {label}")

    with open("data/clusters.json", "w", encoding="utf-8") as f:
        json.dump({"centroids": np.array(centroids).tolist(), "labels": text_labels}, f, indent=2)

    # Also save per-object cluster assignment for browsing/debugging
    for rec, label in zip(records, cluster_labels):
        rec["cluster_id"] = int(label)
    with open(config.INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print("Saved data/clusters.json and updated cluster_id in the index.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-label", dest="do_label", action="store_false")
    args = parser.parse_args()
    main(do_label=args.do_label)
