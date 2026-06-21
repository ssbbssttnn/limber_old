#!/usr/bin/env python3
"""
fetch_photos.py — auto-source stretch photos for Float (or any Limber-family app)

What it does
------------
1. Reads photo-filenames.txt (the cheat-sheet) to learn every stretch's
   filename (= stretch id) and display name.
2. Pulls liftmanual's exercise index once.
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
    "seated-shoulder-flexor-depressor-retractor.jpg": "https://liftmanual.com/seated-shoulder-flexor-depresor-retractor-stretch-bent-knee/",
    "90-90.jpg": "https://liftmanual.com/90-to-90-stretch/",
    "above-head-chest.jpg": "https://liftmanual.com/above-head-chest-stretch/",
    "adductor.jpg": "https://liftmanual.com/adductor-stretch/",
    "all-fours-quad.jpg": "https://liftmanual.com/all-fours-squad-stretch/",
    "animal-resting.jpg": "https://liftmanual.com/animal-resting-yoga-pose/",
    "arm-up-rotator.jpg": "https://liftmanual.com/arm-up-rotator-stretch/",
    "back-pec.jpg": "https://liftmanual.com/back-pec-stretch/",
    "behind-head-chest.jpg": "https://liftmanual.com/behind-head-chest-stretch/",
    "bent-arm-chest.jpg": "https://liftmanual.com/bent-arm-chest-stretch/",
    "bent-over-pendulum.jpg": "https://liftmanual.com/bent-over-shoulder-pendulum/",
    "big-turn-back.jpg": "https://liftmanual.com/standing-reach-up-back-rotation-stretch/",
    "boat-pose.jpg": "https://liftmanual.com/boat-yoga-pose/",
    "bow-pose.jpg": "https://liftmanual.com/bow-yoga-pose/",
    "bridge.jpg": "https://liftmanual.com/bridge-pose-setu-bandhasana/",
    "butterfly.jpg": "https://liftmanual.com/butterfly-yoga-pose/",
    "butterfly-flaps.jpg": "https://liftmanual.com/butterfly-yoga-flaps/",
    "calf-wall.jpg": "https://liftmanual.com/calf-stretch-with-hands-against-wall/",
    "camel.jpg": "https://liftmanual.com/camel-pose/",
    "cat-cow.jpg": "https://liftmanual.com/cat-cow-stretch/",
    "ceiling-look.jpg": "https://liftmanual.com/ceiling-look-stretch/",
    "chair-pose.jpg": "https://liftmanual.com/chair-pose-i-utkatasana-i/",
    "chest-front-shoulder.jpg": "https://liftmanual.com/chest-and-front-of-shoulder-stretch/",
    "child-to-cobra.jpg": "https://liftmanual.com/child-to-cobra-pose/",
    "chin-to-chest.jpg": "https://liftmanual.com/chin-to-chest-stretch/",
    "cobra.jpg": "https://liftmanual.com/cobra-yoga-pose/",
    "corpse.jpg": "https://liftmanual.com/corpse-pose-savasana/",
    "cossack-squat.jpg": "https://liftmanual.com/cossack-squats/",
    "crab.jpg": "https://liftmanual.com/crab-pose/",
    "crescent-moon.jpg": "https://liftmanual.com/crescent-moon-pose/",
    "crocodile.jpg": "https://liftmanual.com/crocodile-yoga-pose/",
    "cross-over-shoulder.jpg": "https://liftmanual.com/cross-over-shoulder-stretch/",
    "crossover-kneeling-hip-flexor.jpg": "https://liftmanual.com/crossover-kneeling-hip-flexor-stretch/",
    "dancer.jpg": "https://liftmanual.com/dancer-pose-natarajasana/",
    "dead-hang.jpg": "https://liftmanual.com/dead-hang-stretch/",
    "deep-squat.jpg": "https://liftmanual.com/prayer-squat-yoga-pose/",
    "dolphin.jpg": "https://liftmanual.com/dolphin-pose/",
    "double-knee-to-chest.jpg": "https://liftmanual.com/pavanamuktasana-yoga-pose/",
    "double-pigeon.jpg": "https://liftmanual.com/double-pigeon-pose/",
    "downward-dog.jpg": "https://liftmanual.com/downward-facing-dog/",
    "dynamic-90-90.jpg": "https://liftmanual.com/dynamic-90-90-hip-twist/",
    "eagle-pose.jpg": "https://liftmanual.com/eagle-pose-garudasana/",
    "elbow-flexor.jpg": "https://liftmanual.com/elbow-flexor-stretch/",
    "elbow-out-rotator.jpg": "https://liftmanual.com/elbow-out-rotator-stretch/",
    "elbows-back.jpg": "https://liftmanual.com/elbows-back-stretch/",
    "extended-side-angle.jpg": "https://liftmanual.com/extended-side-angle-yoga-pose/",
    "external-shoulder-rotation.jpg": "https://liftmanual.com/external-shoulder-rotation-stretch/",
    "feet-ankles-rotation.jpg": "https://liftmanual.com/feet-and-ankles-rotation-stretch/",
    "figure-four.jpg": "https://liftmanual.com/standing-figure-four-pose/",
    "finger-extension.jpg": "https://liftmanual.com/finger-extension-stretch/",
    "finger-flexor.jpg": "https://liftmanual.com/finger-flexor-stretch/",
    "fire-log.jpg": "https://liftmanual.com/double-pigeon-pose/",
    "fish.jpg": "https://liftmanual.com/fish-pose-matsyasana/",
    "flexion-extension-hip.jpg": "https://liftmanual.com/flexion-and-extension-hip-stretch/",
    "forearm-pronator.jpg": "https://liftmanual.com/forearm-pronator-stretch/",
    "forward-flexion-neck.jpg": "https://liftmanual.com/forward-flexion-neck-stretch/",
    "frog.jpg": "https://liftmanual.com/frog-pose-mandukasana/",
    "frog-rock.jpg": "https://liftmanual.com/rocking-ankle-stretch/",
    "front-back-neck.jpg": "https://liftmanual.com/front-and-back-neck-stretch/",
    "front-hamstring.jpg": "https://liftmanual.com/front-hamstring-stretch/",
    "garland.jpg": "https://liftmanual.com/garland-pose-malasana/",
    "half-moon.jpg": "https://liftmanual.com/half-moon-pose-ardha-chandrasana/",
    "half-pigeon.jpg": "https://liftmanual.com/half-pigeon-hip-stretch/",
    "hands-to-feet.jpg": "https://liftmanual.com/hands-to-feet-pada-hastasana/",
    "happy-baby.jpg": "https://liftmanual.com/happy-baby-pose/",
    "hero.jpg": "https://liftmanual.com/hero-pose-virasana/",
    "hip-circles.jpg": "https://liftmanual.com/standing-hip-circle/",
    "hip-extension.jpg": "https://liftmanual.com/hip-extension-stretch/",
    "hip-external-rotator.jpg": "https://liftmanual.com/hip-external-rotator-stretch/",
    "humble-warrior.jpg": "https://liftmanual.com/humble-warrior-pose/",
    "inchworm.jpg": "https://liftmanual.com/bodyweight-front-plank-to-downward-dog/",
    "internal-shoulder-rotation.jpg": "https://liftmanual.com/internal-shoulder-rotation-stretch/",
    "knee-to-chest.jpg": "https://liftmanual.com/knee-to-chest-stretch/",
    "kneeling-back-rotation.jpg": "https://liftmanual.com/kneeling-back-rotation-stretch/",
    "kneeling-chest.jpg": "https://liftmanual.com/kneeling-chest-stretch/",
    "kneeling-iliopsoas.jpg": "https://liftmanual.com/kneeling-iliopsoas-stretch/",
    "kneeling-lat.jpg": "https://liftmanual.com/kneeling-lat-stretch/",
    "kneeling-neck.jpg": "https://liftmanual.com/kneeling-neck-stretch/",
    "kneeling-sartorius.jpg": "https://liftmanual.com/kneeling-sartorius-stretch/",
    "kneeling-tspine.jpg": "https://liftmanual.com/kneeling-t-spine-mobility/",
    "kneeling-wrist-flexor.jpg": "https://liftmanual.com/kneeling-wrist-flexor-stretch/",
    "leg-swings-front.jpg": "https://liftmanual.com/back-forward-leg-swings/",
    "leg-swings-side.jpg": "https://liftmanual.com/side-to-side-leg-swings/",
    "leg-up-hamstring.jpg": "https://liftmanual.com/leg-up-hamstring-stretch/",
    "legs-up-wall.jpg": "https://liftmanual.com/legs-up-the-wall-yoga-pose/",
    "lizard.jpg": "https://liftmanual.com/lizard-pose/",
    "lotus.jpg": "https://liftmanual.com/lotus-yoga-pose-padmasana/",
    "lunging-calf.jpg": "https://liftmanual.com/lunging-straight-leg-calf-stretch/",
    "lying-abductor.jpg": "https://liftmanual.com/lying-abductor-stretch/",
    "lying-calf.jpg": "https://liftmanual.com/lying-calf-stretch/",
    "lying-crossover.jpg": "https://liftmanual.com/lying-crossover-stretch/",
    "lying-glute.jpg": "https://liftmanual.com/lying-glute-stretch/",
    "lying-knee-roll.jpg": "https://liftmanual.com/lying-knee-roll-over-stretch/",
    "lying-knee-to-chest.jpg": "https://liftmanual.com/lying-knee-to-chest-stretch/",
    "lying-lower-back.jpg": "https://liftmanual.com/lying-lower-back-stretch/",
    "lying-quad.jpg": "https://liftmanual.com/quadriceps-lying-stretch/",
    "middle-back.jpg": "https://liftmanual.com/middle-back-stretch/",
    "neck-circle.jpg": "https://liftmanual.com/neck-circle-stretch/",
    "neck-extensor.jpg": "https://liftmanual.com/neck-extensor-stretch/",
    "neck-flexor.jpg": "https://liftmanual.com/neck-flexor-stretch/",
    "neck-side.jpg": "https://liftmanual.com/neck-side-stretch/",
    "one-arm-lat.jpg": "https://liftmanual.com/one-arm-lat-stretch/",
    "open-book.jpg": "https://liftmanual.com/open-book-stretch/",
    "overhead-triceps.jpg": "https://liftmanual.com/overhead-triceps-stretch/",
    "peroneals.jpg": "https://liftmanual.com/peroneals-stretch/",
    "pigeon.jpg": "https://liftmanual.com/pigeon-hip-stretch/",
    "plantar-flexion.jpg": "https://liftmanual.com/plantar-flexion-stretch/",
    "plow.jpg": "https://liftmanual.com/plow-yoga-pose/",
    "posterior-tibialis.jpg": "https://liftmanual.com/posterior-tibialis-stretch/",
    "prayer-squat.jpg": "https://liftmanual.com/prayer-squat-yoga-pose/",
    "pretzel.jpg": "https://liftmanual.com/pretzel-stretch/",
    "pyramid.jpg": "https://liftmanual.com/pyramid-pose/",
    "reaching-up-shoulder.jpg": "https://liftmanual.com/reaching-up-shoulder-stretch/",
    "reaching-upper-back.jpg": "https://liftmanual.com/reaching-upper-back-stretch/",
    "rear-deltoid.jpg": "https://liftmanual.com/rear-deltoid-stretch/",
    "recumbent-hip.jpg": "https://liftmanual.com/recumbent-hip-external-rotator-and-hip-extensor-stretch/",
    "reverse-chest.jpg": "https://liftmanual.com/reverse-chest-stretch/",
    "reverse-shoulder.jpg": "https://liftmanual.com/reverse-shoulder-stretch/",
    "reverse-warrior.jpg": "https://liftmanual.com/reverse-warrior-pose/",
    "revolved-side-angle.jpg": "https://liftmanual.com/revolved-side-angle-pose/",
    "revolved-triangle.jpg": "https://liftmanual.com/revolved-triangle-pose/",
    "rocker-open-legs.jpg": "https://liftmanual.com/rocker-with-open-legs/",
    "rocking-frog.jpg": "https://liftmanual.com/rocking-frog-stretch/",
    "rotating-neck.jpg": "https://liftmanual.com/rotating-neck-stretch/",
    "rotating-stomach.jpg": "https://liftmanual.com/rotating-stomach-stretch/",
    "rotator-cuff.jpg": "https://liftmanual.com/rotator-cuff-stretch/",
    "scapula-elevation.jpg": "https://liftmanual.com/scapula-elevation-depression/",
    "scapula-retraction.jpg": "https://liftmanual.com/scapula-retraction-protraction/",
    "scorpion.jpg": "https://liftmanual.com/scorpion-stretch/",
    "seated-ankle.jpg": "https://liftmanual.com/seated-ankle-stretch/",
    "seated-calf.jpg": "https://liftmanual.com/seated-calf-stretch/",
    "seated-glute.jpg": "https://liftmanual.com/seated-glute-stretch/",
    "seated-groin.jpg": "https://liftmanual.com/seated-groin-stretch/",
    "seated-lower-back.jpg": "https://liftmanual.com/seated-lower-back-stretch/",
    "seated-neck-side.jpg": "https://liftmanual.com/seated-neck-side-stretch/",
    "seated-piriformis.jpg": "https://liftmanual.com/seated-piriformis-stretch/",
    "seated-quad.jpg": "https://liftmanual.com/seated-quadriceps-stretch/",
    "seated-rotation.jpg": "https://liftmanual.com/seated-rotation-stretch/",
    "seated-single-hamstring.jpg": "https://liftmanual.com/seated-single-leg-hamstring-stretch/",
    "seated-spinal-twist.jpg": "https://liftmanual.com/ardha-matsyendrasana-yoga-pose/",
    "seated-straight-calf.jpg": "https://liftmanual.com/seated-straight-leg-calf-stretch/",
    "side-lat.jpg": "https://liftmanual.com/side-lat-stretch/",
    "side-lunge-adductor.jpg": "https://liftmanual.com/side-lunge-adductor-stretch/",
    "side-push-neck.jpg": "https://liftmanual.com/side-push-neck-stretch/",
    "single-straight-leg.jpg": "https://liftmanual.com/single-straight-leg-stretch/",
    "sitting-wide-adductor.jpg": "https://liftmanual.com/sitting-wide-leg-adductor-stretch/",
    "split-sprinter-lunge.jpg": "https://liftmanual.com/split-sprinter-low-lunge/",
    "spread-leg-fold.jpg": "https://liftmanual.com/spread-leg-forward-fold-upavista-konasana/",
    "stand-spread-fold.jpg": "https://liftmanual.com/stand-spread-leg-forward-fold/",
    "standing-abs-rotation.jpg": "https://liftmanual.com/standing-abs-rotation-stretch/",
    "standing-achilles.jpg": "https://liftmanual.com/standing-achilles-stretch/",
    "standing-back-extension-flexion.jpg": "https://liftmanual.com/standing-back-extension-and-flexion/",
    "standing-back-rotation.jpg": "https://liftmanual.com/standing-back-rotation-stretch/",
    "standing-balance-outer-hip.jpg": "https://liftmanual.com/standing-balance-outer-hip-stretch/",
    "standing-balance-quad.jpg": "https://liftmanual.com/standing-balance-quadriceps-stretch/",
    "standing-figure-four.jpg": "https://liftmanual.com/standing-figure-four-pose/",
    "standing-forward-bend.jpg": "https://liftmanual.com/standing-forward-bend-uttanasana/",
    "standing-gastroc.jpg": "https://liftmanual.com/standing-gastrocnemius-calf-stretch/",
    "standing-hamstring.jpg": "https://liftmanual.com/standing-hamstring-stretch/",
    "standing-hamstrings-back.jpg": "https://liftmanual.com/standing-hamstrings-and-back-stretch/",
    "standing-high-hamstring.jpg": "https://liftmanual.com/standing-high-leg-bent-knee-hamstring-stretch/",
    "standing-hip-flexor.jpg": "https://liftmanual.com/standing-hip-flexor-stretch/",
    "standing-iliotibial.jpg": "https://liftmanual.com/standing-iliotibial-stretch/",
    "standing-knee-to-chest.jpg": "https://liftmanual.com/standing-knee-to-chest-stretch/",
    "standing-lateral.jpg": "https://liftmanual.com/standing-lateral-stretch/",
    "standing-lateral-side.jpg": "https://liftmanual.com/standing-lateral-side-stretch/",
    "standing-leg-cross-abductor.jpg": "https://liftmanual.com/standing-leg-cross-abductor-stretch/",
    "standing-one-arm-chest.jpg": "https://liftmanual.com/standing-one-arm-chest-stretch/",
    "standing-outer-hip.jpg": "https://liftmanual.com/standing-outer-hip-stretch/",
    "standing-quad.jpg": "https://liftmanual.com/standing-quadriceps-stretch/",
    "standing-shin.jpg": "https://liftmanual.com/standing-shin-stretch/",
    "standing-tibialis.jpg": "https://liftmanual.com/standing-tibialis-anterior-stretch/",
    "standing-toe-up-calf.jpg": "https://liftmanual.com/standing-toe-up-calf-stretch/",
    "standing-wring-towel.jpg": "https://liftmanual.com/standing-wring-the-towel/",
    "superman-chest.jpg": "https://liftmanual.com/superman-chest-stretch/",
    "supine-twist.jpg": "https://liftmanual.com/supine-spinal-twist-yoga-pose/",
    "thread-the-needle.jpg": "https://liftmanual.com/thread-the-needle-pose/",
    "toy-soldier.jpg": "https://liftmanual.com/toy-soldier-dynamic-stretch/",
    "tree-pose.jpg": "https://liftmanual.com/tree-pose-vrksasana/",
    "triangle.jpg": "https://liftmanual.com/triangle-pose-trikonasana/",
    "twist-step.jpg": "https://liftmanual.com/twist-step-stretch/",
    "twisted-leg-lunge.jpg": "https://liftmanual.com/twisted-leg-lunge-pose/",
    "upper-back.jpg": "https://liftmanual.com/upper-back-stretch/",
    "upward-dog.jpg": "https://liftmanual.com/upward-facing-dog/",
    "warrior-1.jpg": "https://liftmanual.com/warrior-pose-i-virabhadrasana/",
    "warrior-2.jpg": "https://liftmanual.com/warrior-ii-yoga-pose/",
    "warrior-3.jpg": "https://liftmanual.com/warrior-iii-pose/",
    "wheel.jpg": "https://liftmanual.com/wheel-pose-urdhva-dhanurasana/",
    "wide-leg-fold.jpg": "https://liftmanual.com/wide-legged-forward-bend-prasarita-padottanasana/",
    "worlds-greatest.jpg": "https://liftmanual.com/worlds-greatest-stretch/",
    "wrist-extensor.jpg": "https://liftmanual.com/wrist-extensor-stretch/",
    "wrist-flexor.jpg": "https://liftmanual.com/wrist-flexor-stretch/",
}

# Stretches with no equivalent page on liftmanual.com (verified against the
# full /stretching/ index). The script will report these as 'no source' rather
# than guess a wrong match. Source photos for these yourself.
NO_SOURCE = {
    "cow-face.jpg",
    "elephant-walks.jpg",
    "floss-femoral.jpg",
    "floss-median.jpg",
    "floss-radial.jpg",
    "floss-sciatic.jpg",
    "floss-ulnar.jpg",
    "gate-pose.jpg",
    "hawaiian-squat.jpg",
    "reverse-prayer.jpg",
    "scapular-pushups.jpg",
    "standing-hip-openers.jpg",
    "windmills.jpg",
    "windshield-wipers.jpg",
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
    """Returns list of (filename, display_name). Lines look like:
         pigeon.jpg                          Pigeon Hip Stretch  [static, both sides]
    """
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"\s+(\S+\.(?:jpg|jpeg|png|webp))\s+(.+?)(?:\s{2,}\[.*\])?\s*$", line)
            if m:
                fname = m.group(1).strip()
                name = m.group(2).strip()
                out.append((fname, name))
    return out


def parse_index(htmltext):
    """Returns list of (title, url) for every exercise/stretch link on the index."""
    pairs = []
    for m in re.finditer(r'<a[^>]+href="(https://liftmanual\.com/[^"]+/)"[^>]*>([^<]+)</a>', htmltext):
        url, title = m.group(1), html.unescape(m.group(2)).strip()
        if title and "/exercises" not in url:
            pairs.append((title, url))
    # dedupe, keep first
    seen, uniq = set(), []
    for t, u in pairs:
        if u in seen:
            continue
        seen.add(u)
        uniq.append((t, u))
    return uniq


def slug_variants(filename):
    base = re.sub(r"\.(jpg|jpeg|png|webp)$", "", filename)
    base = base.lower()
    variants = {base}
    variants.add(base + "-stretch")
    variants.add(base + "-pose")
    variants.add(base + "-yoga-pose")
    variants.add(base.replace("-", " "))
    return variants


def url_slug(url):
    return url.rstrip("/").rsplit("/", 1)[-1].lower()


def find_match(filename, name, index, index_norm, min_conf):
    # explicitly confirmed: no equivalent page exists on liftmanual.com
    if filename in NO_SOURCE:
        return None, 0.0, "no-source"
    # a) override
    if filename in OVERRIDES:
        return OVERRIDES[filename], 1.0, "override"
    nname = normalize(name)
    # b) exact title match
    for (title, url), tnorm in zip(index, index_norm):
        if tnorm == nname:
            return url, 1.0, "exact"
    # c) filename-as-slug match
    variants = slug_variants(filename)
    for (title, url) in index:
        if url_slug(url) in variants:
            return url, 0.97, "slug"
    # d) fuzzy
    best, best_conf = None, 0.0
    for (title, url), tnorm in zip(index, index_norm):
        c = difflib.SequenceMatcher(None, nname, tnorm).ratio()
        if c > best_conf:
            best_conf, best = c, url
    if best and best_conf >= min_conf:
        return best, round(best_conf, 3), "fuzzy"
    return None, round(best_conf, 3), "UNMATCHED"


def extract_og_image(htmltext):
    m = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', htmltext)
    if m:
        return html.unescape(m.group(1))
    m = re.search(r'<meta[^>]+content="([^"]+)"[^>]+property="og:image"', htmltext)
    if m:
        return html.unescape(m.group(1))
    return None


def already_has_photo(base):
    for ext in IMG_EXTS:
        if os.path.exists(os.path.join(PHOTOS_DIR, base + ext)):
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--min-confidence", type=float, default=0.86)
    args = ap.parse_args()

    if not os.path.exists(CHEATSHEET):
        sys.exit("ERROR: photo-filenames.txt not found in repo root.")
    os.makedirs(PHOTOS_DIR, exist_ok=True)

    stretches = parse_cheatsheet(CHEATSHEET)
    if args.limit:
        stretches = stretches[: args.limit]
    print(f"Loaded {len(stretches)} stretches from cheat-sheet.")

    print("Fetching liftmanual index…")
    index = parse_index(get(INDEX_URL).decode("utf-8", "replace"))
    index_norm = [normalize(t) for t, _ in index]
    print(f"Index has {len(index)} entries.")

    rows = []
    downloaded = skipped = failed = 0
    for i, (fname, name) in enumerate(stretches, 1):
        base = re.sub(r"\.(jpg|jpeg|png|webp)$", "", fname)
        if already_has_photo(base) and not args.force:
            rows.append([fname, name, "skipped-exists", "", "", ""])
            skipped += 1
            continue
        url, conf, how = find_match(fname, name, index, index_norm, args.min_confidence)
        if not url:
            rows.append([fname, name, "UNMATCHED", conf, "", ""])
            failed += 1
            print(f"[{i}/{len(stretches)}] {name}: UNMATCHED (best {conf})")
            continue
        if args.dry_run:
            rows.append([fname, name, f"would-{how}", conf, url, ""])
            print(f"[{i}/{len(stretches)}] {name}: {how} {conf} -> {url}")
            time.sleep(DELAY)
            continue
        try:
            page = get(url).decode("utf-8", "replace")
            time.sleep(DELAY)
            img = extract_og_image(page)
            if not img:
                rows.append([fname, name, "no-og-image", conf, url, ""])
                failed += 1
                continue
            ext = os.path.splitext(img.split("?")[0])[1].lower()
            if ext not in IMG_EXTS:
                ext = ".jpg"
            data = get(img)
            time.sleep(DELAY)
            with open(os.path.join(PHOTOS_DIR, base + ext), "wb") as fh:
                fh.write(data)
            rows.append([fname, name, f"ok-{how}", conf, url, img])
            downloaded += 1
            print(f"[{i}/{len(stretches)}] {name}: saved {base}{ext} ({how} {conf})")
        except Exception as e:
            rows.append([fname, name, f"error:{e}", conf, url, ""])
            failed += 1
            print(f"[{i}/{len(stretches)}] {name}: ERROR {e}")

    with open(REPORT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["filename", "name", "status", "confidence", "page_url", "image_url"])
        w.writerows(rows)

    print(f"\nDone. downloaded={downloaded} skipped={skipped} failed={failed}")
    print(f"Report: {REPORT}")
    if args.dry_run:
        print("Dry run — nothing downloaded. Review fetch-report.csv, then run for real.")


if __name__ == "__main__":
    main()
