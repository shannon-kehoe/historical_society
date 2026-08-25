"""
Configuration for the museum-digital neighbor/cluster-finder pipeline.

Two data-access modes are supported, since your society doesn't have
musdb API credentials yet:

  READ_MODE = "frontend"  -> uses the public, unauthenticated frontend
                              JSON API (https://hessen.museum-digital.de/...)
                              Only sees objects that are already PUBLISHED
                              on the public portal.

  READ_MODE = "musdb"     -> uses the authenticated musdb API, once you
                              have credentials. Sees everything in the
                              catalog, published or not (useful for
                              newly-entered items still being reviewed).

Once you get musdb credentials, flip READ_MODE to "musdb" and fill in
MUSDB_API_KEY / MUSDB_BASE_URL below. Nothing else in the pipeline needs
to change -- data_source.py abstracts over both.
"""

import os

# --- Instance ---------------------------------------------------------
INSTANCE_SLUG = "hessen"
FRONTEND_BASE_URL = f"https://{INSTANCE_SLUG}.museum-digital.de"

# --- Data source mode ---------------------------------------------------
READ_MODE = "frontend"  # "frontend" or "musdb"

# --- Which catalog to index ---------------------------------------------
# museum-digital search syntax. institution:33 is the
# Verein für Geschichte- und Altertumskunde e.V. Frankfurt-Höchst
# (https://hessen.museum-digital.de/institution/33).
SEARCH_QUERY = "institution:33"

# --- musdb (authenticated) API — fill in once you have credentials ------
MUSDB_BASE_URL = f"https://{INSTANCE_SLUG}.museum-digital.de/musdb"
MUSDB_API_KEY = os.environ.get("MUSDB_API_KEY", "")

# --- Embeddings -----------------------------------------------------
# Local, free, no API key needed. Good default for a volunteer-run project.
# Multilingual model since object descriptions will mostly be in German.
EMBEDDING_MODEL = "paraphrase-multilingual-mpnet-base-v2"

# --- Storage ---------------------------------------------------------
DATA_DIR = "data"
INDEX_PATH = os.path.join(DATA_DIR, "object_index.json")   # id -> metadata + text
EMBEDDINGS_PATH = os.path.join(DATA_DIR, "embeddings.npy")  # aligned array

# --- Neighbor search ---------------------------------------------------
TOP_K_NEIGHBORS = 8
MIN_SIMILARITY = 0.35  # below this, don't bother suggesting a "neighbor"

# --- Clustering ---------------------------------------------------------
# Tuned for a small catalog (~34 items): min_samples=1 keeps HDBSCAN from
# being too conservative in high-dimensional embedding space (the default,
# min_samples = min_cluster_size, found 0 clusters). Worth revisiting
# (raising both) as the catalog grows into the hundreds.
MIN_CLUSTER_SIZE = 3  # HDBSCAN: smallest group that counts as a cluster
MIN_SAMPLES = 1       # HDBSCAN: lower = less conservative clustering

# --- LLM explanation step (optional) -------------------------------------
# Uses the Anthropic API to explain *why* two objects are related, in
# plain language a volunteer archivist can read and act on.
USE_LLM_EXPLANATIONS = True
ANTHROPIC_MODEL = "claude-sonnet-4-6"
