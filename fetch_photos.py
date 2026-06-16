#!/usr/bin/env python3
"""
fetch_photos.py - pull a photo for each Limber stretch from liftmanual.com
and save it under the correct filename in ./photos/.

How it works
------------
1. Reads photo-filenames.txt (the Limber cheat-sheet): filename -> stretch name.
2. Fetches liftmanual.com's full A-Z index once and builds two lookups:
      title -> page URL   (authoritative; handles liftmanual's own slug typos)
      slug  -> page URL
3. For each stretch it tries, in order:
      a) an entry in OVERRIDES below (you pin these by hand)
      b) exact title match
      c) filename-as-slug match (e.g. "pigeon" / "pigeon-hip-stretch" / "pigeon-pose")
      d) fuzzy title match (kept only above a confidence cutoff)
4. For each match it opens the page, reads the og:image (the clean static photo),
   downloads it, and saves it as photos/<filename>.
5. Writes fetch-report.csv: status, confidence, what it matched, what failed.

Idempotent: a stretch that already has photos/<id>.* is skipped unless --force.

Usage
-----
    python3 fetch_photos.py                # match + download everything missing
    python3 fetch_photos.py --dry-run      # match only, write report, download nothing
    python3 fetch_photos.py --force        # re-download even if a photo exists
    python3 fetch_photos.py --limit 20     # only the first 20 (for testing)
    python3 fetch_photos.py --min-confidence 0.90

Standard library only, no pip installs needed.

RIGHTS: liftmanual.com content is "(c) Lift Manual, all rights reserved." This
downloads their images for your app. That's your call; the script is polite
(normal User-Agent, rate-limited) but gives you no licence.
"""

import argparse
import csv
import difflib
import html
import os
import re
import sys
import time
import urllib.request
import urllib.error

INDEX_URL = "https://liftmanual.com/exercises/"
UA = "Mozilla/5.0 (compatible; LimberPhotoFetch/1.0; personal use)"
DELAY = 1.0  # seconds between network requests

HERE = os.path.dirname(os.path.abspath(__file__))
CHEATSHEET = os.path.join(HERE, "photo-filenames.txt")
PHOTOS_DIR = os.path.join(HERE, "photos")
REPORT = os.path.join(HERE, "fetch-report.csv")
IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp")

# --- Manual overrides -------------------------------------------------------
# If a stretch matches the wrong page (or none), pin it here:
#     "<filename>": "<full liftmanual URL>"
# Find the right URL by searching the stretch on liftmanual.com.
OVERRIDES = {
    "fire-log.jpg": "https://liftmanual.com/double-pigeon-pose/",
}
# ---------------------------------------------------------------------------


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def normalize(s):
    s = html.unescape(s).lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_cheatsheet(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"\s+(\S+\.(?:jpg|jpeg|png|webp))\s*(.+?)\s*$", line)
            if not m:
                continue
            fname = m.group(1)
            name = re.sub(r"\s*\[[^\]]*\]\s*$", "", m.group(2)).strip()
            out.append((fname, name))
    return out


def build_index(page):
    """Parse the A-Z page (real HTML, or markdown) into name_index + slug_index.
    Only single-segment exercise URLs match, so /muscle/.. and /equipment/.. are
    excluded automatically."""
    name_index, slug_index = {}, {}
    pairs = []

    # real HTML: <a href="https://liftmanual.com/slug/" ...>Title</a>
    for url, text in re.findall(
        r'<a\s[^>]*href=["\'](https://liftmanual\.com/[a-z0-9\-]+/)["\'][^>]*>(.*?)</a>',
        page, flags=re.I | re.S,
    ):
        title = re.sub(r"<[^>]+>", "", text)  # strip any inner tags
        pairs.append((title, url))

    # markdown fallback: [Title](https://liftmanual.com/slug/)
    for title, url in re.findall(
        r"\[([^\]]+)\]\((https://liftmanual\.com/[a-z0-9\-]+/)\)", page
    ):
        pairs.append((title, url))

    for title, url in pairs:
        n = normalize(title)
        if not n:
            continue
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        name_index.setdefault(n, url)   # first occurrence wins (skips -2 dupes)
        slug_index.setdefault(slug, url)
    return name_index, slug_index


def find_match(filename, name, name_index, slug_index, min_conf):
    if filename in OVERRIDES:
        return OVERRIDES[filename], "override", name

    base = filename.rsplit(".", 1)[0]
    nm = normalize(name)

    if nm in name_index:
        return name_index[nm], "exact-title", name

    for cand in (base, base + "-stretch", base + "-pose", base + "-yoga-pose"):
        if cand in slug_index:
            return slug_index[cand], "filename-slug", cand

    close = difflib.get_close_matches(nm, list(name_index.keys()), n=1, cutoff=min_conf)
    if close:
        ratio = difflib.SequenceMatcher(None, nm, close[0]).ratio()
        return name_index[close[0]], f"fuzzy-{ratio:.2f}", close[0]

    return None, "UNMATCHED", ""


def existing_photo(base):
    for ext in IMG_EXTS:
        p = os.path.join(PHOTOS_DIR, base + ext)
        if os.path.exists(p):
            return p
    return None


def extract_og_image(page):
    for pat in (
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'meta-og:image:\s*(\S+)',
        r'(https://liftmanual\.com/wp-content/uploads/[^\s"\'<>]+\.(?:jpg|jpeg|png|webp))',
    ):
        m = re.search(pat, page, flags=re.I)
        if m:
            return m.group(1)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--min-confidence", type=float, default=0.86)
    args = ap.parse_args()

    if not os.path.exists(CHEATSHEET):
        sys.exit(f"Can't find {CHEATSHEET} - run from repo root (next to photo-filenames.txt).")
    os.makedirs(PHOTOS_DIR, exist_ok=True)

    stretches = parse_cheatsheet(CHEATSHEET)
    if args.limit:
        stretches = stretches[: args.limit]
    print(f"Loaded {len(stretches)} stretches from cheat-sheet.")

    print("Fetching liftmanual A-Z index ...")
    index_html = get(INDEX_URL).decode("utf-8", "replace")
    name_index, slug_index = build_index(index_html)
    print(f"Indexed {len(name_index)} titles / {len(slug_index)} slugs.")
    if len(name_index) < 100:
        print("WARNING: index looks too small - the page format may have changed. "
              "Check before trusting results.")
    print()

    rows = []
    downloaded = skipped = unmatched = failed = 0

    for i, (filename, name) in enumerate(stretches, 1):
        base = filename.rsplit(".", 1)[0]
        url, conf, matched = find_match(filename, name, name_index, slug_index, args.min_confidence)
        row = {"filename": filename, "stretch_name": name, "status": "",
               "confidence": conf, "matched_title": matched,
               "page_url": url or "", "image_url": ""}

        if url is None:
            unmatched += 1
            row["status"] = "UNMATCHED"
            rows.append(row)
            print(f"[{i:3}/{len(stretches)}] {filename:34s} NO MATCH")
            continue

        if existing_photo(base) and not args.force:
            skipped += 1
            row["status"] = "SKIP_EXISTS"
            rows.append(row)
            print(f"[{i:3}/{len(stretches)}] {filename:34s} skip (already have)")
            continue

        if args.dry_run:
            row["status"] = "WOULD_FETCH"
            rows.append(row)
            tag = "" if conf in ("exact-title", "filename-slug", "override") else "  <-- REVIEW"
            print(f"[{i:3}/{len(stretches)}] {filename:34s} -> {url}  [{conf}]{tag}")
            continue

        try:
            time.sleep(DELAY)
            page = get(url).decode("utf-8", "replace")
            img_url = extract_og_image(page)
            if not img_url:
                failed += 1
                row["status"] = "NO_IMAGE_ON_PAGE"
                rows.append(row)
                print(f"[{i:3}/{len(stretches)}] {filename:34s} matched but no image found")
                continue
            row["image_url"] = img_url
            ext = os.path.splitext(img_url.split("?")[0])[1].lower()
            if ext not in IMG_EXTS:
                ext = ".jpg"
            time.sleep(DELAY)
            data = get(img_url)
            with open(os.path.join(PHOTOS_DIR, base + ext), "wb") as fh:
                fh.write(data)
            downloaded += 1
            row["status"] = "DOWNLOADED"
            tag = "" if conf in ("exact-title", "filename-slug", "override") else "  <-- REVIEW"
            print(f"[{i:3}/{len(stretches)}] {filename:34s} saved {base}{ext}  [{conf}]{tag}")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            failed += 1
            row["status"] = f"ERROR:{e}"
            print(f"[{i:3}/{len(stretches)}] {filename:34s} ERROR {e}")
        rows.append(row)

    with open(REPORT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print("\n" + "=" * 50)
    print(f"downloaded : {downloaded}")
    print(f"skipped    : {skipped} (already had a photo)")
    print(f"unmatched  : {unmatched}")
    print(f"failed     : {failed}")
    fuzzy = sum(1 for r in rows if r["confidence"].startswith("fuzzy"))
    print(f"fuzzy guesses to review: {fuzzy}  (see fetch-report.csv)")
    print(f"report     : {REPORT}")


if __name__ == "__main__":
    main()
