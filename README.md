# museum-digital neighbor & cluster finder

For a volunteer-run historic society using museum-digital (Hessen instance)
to catalog artifacts. Given a new item, this finds related older items
("neighbors") and shows which thematic cluster it falls into.

## How it works

1. **`build_index.py`** — pulls every published object from the catalog,
   turns each into a text passage (title + description + materials +
   date + place, etc.), and embeds all of them with a local, free,
   multilingual sentence-embedding model. Saves the embeddings + metadata
   to `data/`.
2. **`cluster_catalog.py`** — groups the whole catalog into thematic
   clusters (HDBSCAN), and asks Claude to write a short label for each
   cluster ("farm tools, early 20th century", etc.).
3. **`find_neighbors.py`** — the main tool. Give it a new item's object ID;
   it embeds that item, finds its nearest neighbors in the existing
   catalog, tells you which cluster it's closest to, and (optionally) asks
   Claude to explain *why* each neighbor might be related.

## Setup

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...   # only needed for the LLM explanation/labeling steps
```

## First run

Sanity-check the API connection first:

```bash
python test_single_object.py                      # known painting, object 5868
python test_single_object.py --object-id 103759   # a Höchst society object
```

This fetches one known, real, published object and prints both the
fields the pipeline extracted and the raw JSON museum-digital returned.
Check that it runs without an HTTP error and that the `text` field has
content.

`data_source.py`'s field mappings were verified against live responses
from the hessen instance on 2026-08-24 (see the module docstring there
for the confirmed JSON shapes). If museum-digital changes its schema and
`test_single_object.py` starts printing an empty `text` field, compare
the raw JSON it prints against the key names in `_normalize()` — that's
the one function that should need adjusting.

Then:

```bash
# Quick test with a small slice of the catalog
python build_index.py --max-pages 2
python cluster_catalog.py
python find_neighbors.py --object-id <some_id> --explain

# Once that looks right, do the full build (may take a while for a large catalog)
python build_index.py
python cluster_catalog.py
```

`build_index.py` / `data_source.fetch_all_objects()` indexes
`config.SEARCH_QUERY`, which is set to `institution:33` — the
Verein für Geschichte- und Altertumskunde e.V. Frankfurt-Höchst
(https://hessen.museum-digital.de/institution/33). To index a different
museum, change `SEARCH_QUERY` (the institution ID is visible in the URL
of its page on the portal, `/institution/<id>`).

## Ongoing use

Re-run `build_index.py` periodically (weekly is plenty for a volunteer
project) to pick up new items added directly through museum-digital.
Re-run `cluster_catalog.py` after each rebuild so cluster themes stay
current.

For a specific newly-added item, run:

```bash
python find_neighbors.py --object-id <new_item_id> --explain
```

## Important limitations right now

- **Batch entries carry slightly less text than single fetches.** The
  batch export omits `object_tags` and the resolved time/place/people
  relations that the single-object endpoint includes, so indexed text is
  a bit leaner than the query text `find_neighbors.py` builds. Fine in
  practice; fetching each object individually during indexing would
  close the gap at the cost of one request per object.
- **No musdb credentials yet.** The pipeline currently reads from the
  *public frontend* API, so it only sees items that have already been
  published on the portal — not items sitting in musdb still being
  entered/reviewed. Once your society gets musdb API credentials:
  1. The endpoint paths (`MUSDB_LIST_PATH` / `MUSDB_DETAIL_PATH` in
     `data_source.py`) are already set from the musdb OpenAPI spec, but
     the response field names haven't been tested against real musdb
     output — check the swagger docs at
     `https://hessen.museum-digital.de/musdb/swagger/` and update the
     field mappings in `_normalize()` to match.
  2. Set `READ_MODE = "musdb"` in `config.py` and set the `MUSDB_API_KEY`
     environment variable.
  This is the only place that needs to change — `build_index.py`,
  `find_neighbors.py`, and `cluster_catalog.py` don't care which mode
  you're in.
- **Nothing writes back to museum-digital.** By design — this only
  *suggests* neighbors/clusters for a volunteer to review, it never
  auto-edits or auto-publishes records. Once you're comfortable with the
  suggestions, wiring the musdb API's write endpoints to attach
  "related object" links is a natural next step.
- **Image similarity isn't included yet.** Right now everything is
  text-only. Adding a CLIP-based image embedding (many objects are more
  visually than textually distinctive — tools, textiles, uniforms) is a
  good follow-up once the text-based version is working well.
