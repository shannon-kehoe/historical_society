"""
Fetches object records from museum-digital, normalized into a flat dict
regardless of whether they came from the public frontend API or the
authenticated musdb API.

Frontend API pattern (public, read-only, no auth) -- confirmed against
museum-digital's own Nov 2025 blog post ("Making Interoperability Easy",
https://blog.museum-digital.org/2025/11/24/making-interoperability-easy/):

    Single object:  https://hessen.museum-digital.de/json/object/<id>
    Batch/search:   https://hessen.museum-digital.de/export/json/<query>?limit=100&offset=0
                    (query uses the same "s=" search syntax as the site's
                    search bar, e.g. institution:1 for one museum's objects)

    NOTE: this replaces the older ?output=json pattern from museum-digital's
    2022-era docs, which may still work on some instances but is not what
    the current blog documents as the supported approach.

musdb API pattern (authenticated, once you have credentials):
    See the OpenAPI/Swagger docs at https://<instance>.museum-digital.de/musdb/swagger/
    for the exact object-listing and object-detail routes and required
    headers. The musdb OpenAPI spec (https://hessen.museum-digital.de/musdb/api)
    confirms /object/read/{id} and /object/search/{searchQuery} as the
    relevant read endpoints -- MUSDB_DETAIL_PATH / MUSDB_LIST_PATH below
    reflect that.

Field names in _normalize() were VERIFIED against live responses on
2026-08-24 (objects 172986, 103759, 5868 on the hessen instance):

  - Single object (/json/object/<id>) and batch entries share the same
    core fields: object_id, object_name, object_description, object_type,
    object_material_technique, object_dimensions, object_images.
  - The single-object endpoint additionally resolves object_tags,
    object_relation_times / _places / _people (each with nested
    time.time_name / place.place_name / people.displayname dicts).
    Batch entries omit those, so batch-indexed text is slightly leaner.
  - The batch endpoint wraps everything as
    {"results": {"total": N, "objects": {"<id>": {...}, ...}}}
    -- note `objects` is a DICT keyed by id, not a list. Past the end it
    returns {"results": {"total": N, "objects": []}}.
  - Images: instance-root-relative, i.e.
    {FRONTEND_BASE_URL}/data/{md_subset}/{folder}/{preview}
"""

import time
import requests

import config

MUSDB_DETAIL_PATH = "/object/read/{id}"          # confirmed via musdb OpenAPI spec
MUSDB_LIST_PATH = "/object/search/{searchQuery}"  # confirmed via musdb OpenAPI spec


def _relation_names(raw: dict, relation_key: str, nested_key: str, name_key: str) -> str:
    """
    Flatten one of the object_relation_* lists into comma-joined names,
    e.g. object_relation_places -> [{"place": {"place_name": ...}}, ...].
    Only present on single-object responses; batch entries just yield "".
    """
    names = []
    for entry in raw.get(relation_key) or []:
        nested = entry.get(nested_key)
        if isinstance(nested, dict) and nested.get(name_key):
            names.append(nested[name_key])
    return ", ".join(names)


def _main_image_url(raw: dict):
    """Prefer the image flagged is_main; fall back to the first one."""
    images = raw.get("object_images") or []
    if not images:
        return None
    main = next((im for im in images if im.get("is_main") == "j"), images[0])
    filename = main.get("preview") or main.get("filename_loc")
    folder = main.get("folder")
    if not (folder and filename):
        return None
    subset = raw.get("md_subset") or config.INSTANCE_SLUG
    return f"{config.FRONTEND_BASE_URL}/data/{subset}/{folder}/{filename}"


def _normalize(raw: dict) -> dict:
    """
    Flatten a museum-digital object record into the fields we care about
    for text embedding. Field names verified against live hessen-instance
    responses -- see module docstring.
    """
    title = raw.get("object_name") or ""
    description = raw.get("object_description") or ""
    category_name = raw.get("object_type") or ""
    mattech = raw.get("object_material_technique") or ""

    keywords = ", ".join(
        t["tag_name"] for t in raw.get("object_tags") or [] if t.get("tag_name")
    )
    date_text = _relation_names(raw, "object_relation_times", "time", "time_name")
    place = _relation_names(raw, "object_relation_places", "place", "place_name")
    people = _relation_names(raw, "object_relation_people", "people", "displayname")

    obj_id = raw.get("object_id")
    image_url = _main_image_url(raw)

    text_parts = [title, description, category_name, mattech, keywords, date_text, place, people]
    text = " | ".join(str(p) for p in text_parts if p)

    return {
        "id": obj_id,
        "title": title,
        "text": text,
        "category": category_name,
        "date_text": date_text,
        "place": place,
        "url": f"{config.FRONTEND_BASE_URL}/object/{obj_id}",
        "image_url": image_url,
        "_raw": raw,  # kept for debugging during the first live test; drop later if noisy
    }


def fetch_object(object_id: int) -> dict:
    if config.READ_MODE == "frontend":
        url = f"{config.FRONTEND_BASE_URL}/json/object/{object_id}"
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return _normalize(resp.json())
    else:
        fields = (
            "objekt_inventarnr,objektart,objekt_name,objekt_beschreibung,"
            "objekt_material_technik,objekt_masse"
        )
        headers = {"Authorization": f"Bearer {config.MUSDB_API_KEY}"}
        url = config.MUSDB_BASE_URL + MUSDB_DETAIL_PATH.format(id=object_id)
        resp = requests.get(url, headers=headers, params={"fields": fields}, timeout=30)
        resp.raise_for_status()
        return _normalize(resp.json())


def fetch_all_objects(page_size: int = 50, sleep_between: float = 0.5, max_pages: int | None = None,
                       search_query: str | None = None):
    """
    Generator that yields normalized object dicts, one at a time, paging
    through the catalog. `sleep_between` is a polite delay so we don't
    hammer a volunteer-run instance's server.

    `search_query` uses museum-digital's search syntax (the same "s="
    parameter used on the site's search page) -- e.g. "institution:33" for
    one museum's objects, or "collection:49" for one collection. Defaults
    to config.SEARCH_QUERY (the society's own institution).
    """
    search_query = search_query or config.SEARCH_QUERY
    if config.READ_MODE == "frontend":
        offset = 0
        page = 0
        while True:
            url = f"{config.FRONTEND_BASE_URL}/export/json/{search_query}"
            resp = requests.get(
                url, params={"limit": page_size, "offset": offset}, timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            # verified live shape: {"results": {"total": N, "objects": {"<id>": {...}}}}
            # (an empty page comes back as "objects": [])
            objects = (data.get("results") or {}).get("objects") or {}
            if not objects:
                break
            raws = objects.values() if isinstance(objects, dict) else objects
            for raw in raws:
                yield _normalize(raw)
            offset += page_size
            page += 1
            if max_pages is not None and page >= max_pages:
                break
            time.sleep(sleep_between)
    else:
        headers = {"Authorization": f"Bearer {config.MUSDB_API_KEY}"}
        page = 0
        position = 0
        while True:
            url = config.MUSDB_BASE_URL + MUSDB_LIST_PATH.format(searchQuery=search_query)
            resp = requests.get(headers=headers, url=url, params={"position": position}, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            results = (data.get("results") or {})
            objects = results.get("objects") or []
            if not objects:
                break
            for raw in objects:
                yield _normalize(raw)
            position += len(objects)
            page += 1
            if max_pages is not None and page >= max_pages:
                break
            time.sleep(sleep_between)
