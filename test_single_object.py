"""
Smoke test: fetch ONE known object and print what comes back.

Run this first to confirm the instance is reachable and the field
mappings in data_source.py still match the live API (see that module's
docstring for the response shapes verified on 2026-08-24).

Usage:
    python test_single_object.py
    python test_single_object.py --object-id 12345   # test a different object

Object 5868 is the default: a real, published painting record
("Verkuendigung", Freies Deutsches Hochstift / Frankfurter Goethe-Museum)
at https://hessen.museum-digital.de/object/5868 -- good for checking the
fetch actually returns the fields we expect.

What to check in the output:
1. Did it run without an HTTP error?
2. Does `text` contain something recognizable (the object should mention
   "Verkuendigung" and an angel/Mary/annunciation scene if using the
   default test object)?
3. Compare the printed `_raw` dict's keys against what _normalize() in
   data_source.py is looking for (title, description, material, etc.)
   -- if the real field names differ, that's the one place to fix.
"""

import argparse
import json

import data_source


def main(object_id: int):
    print(f"Fetching object {object_id} from {data_source.config.FRONTEND_BASE_URL} ...")
    try:
        obj = data_source.fetch_object(object_id)
    except Exception as e:
        print(f"FAILED: {e}")
        print("\nIf this is a 404, double check the object ID exists and is published.")
        print("If this is a connection error, check the instance is reachable from here.")
        return

    print("\n--- Normalized fields (what the pipeline will actually use) ---")
    for key in ("id", "title", "text", "category", "date_text", "place", "url", "image_url"):
        print(f"{key}: {obj.get(key)}")

    print("\n--- Raw response (for comparing field names against _normalize()) ---")
    print(json.dumps(obj.get("_raw"), indent=2, ensure_ascii=False)[:3000])

    if not obj.get("text", "").strip():
        print("\nWARNING: `text` came back empty. _normalize()'s field-name guesses")
        print("probably don't match the real API response -- check the raw JSON above")
        print("and update the key names _normalize() reads in data_source.py.")
    else:
        print("\nLooks OK -- `text` has content. Ready to try build_index.py.")


if __name__ == "__main__":
    import config  # noqa: F401 -- surfaces import errors early
    parser = argparse.ArgumentParser()
    parser.add_argument("--object-id", type=int, default=5868)
    args = parser.parse_args()
    main(object_id=args.object_id)
