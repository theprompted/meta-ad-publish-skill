#!/usr/bin/env python3
"""
Publish flexible image ads to Meta.

This is a TEMPLATE. The /meta-ad-publish skill copies it and replaces the
PLACEHOLDER values + the CLUSTERS dict before running.

Once filled in, run: python3 publish-<date>-<batch>.py

All ads are created PAUSED. Activation is a separate step (see verify-and-activate.py).
"""

import json
import os
import sys
import time
import requests

# ============================================================
# CONFIG (filled in by skill)
# ============================================================

# Required env vars
TOKEN = os.environ.get("META_ACCESS_TOKEN")
AD_ACCOUNT = os.environ.get("META_AD_ACCOUNT_ID")  # e.g. act_1234567890
PAGE_ID = os.environ.get("META_PAGE_ID")
INSTAGRAM_USER_ID = os.environ.get("META_INSTAGRAM_USER_ID")  # may be empty/None

# Filled in by skill
ADSET_ID = "<<ADSET_ID>>"        # target ad set (existing or freshly created)
LP_URL = "<<LP_URL>>"            # destination URL on click
HASHES_FILE = "<<HASHES_FILE>>"  # path to upload-images.sh output
CTA = "<<CTA>>"                  # LEARN_MORE | SHOP_NOW | SIGN_UP | etc

# Clusters: each cluster becomes ONE flexible ad in the ad set.
# Each cluster has a name, the image filenames it contains, and its 5 primary
# texts + 5 headlines (Meta's hard limits).
CLUSTERS = {
    # "cluster-key": {
    #     "name": "Ad name as shown in Ads Manager",
    #     "images": [
    #         "image-01.png",
    #         "image-02.png",
    #         # ... up to 10
    #     ],
    #     "primary_texts": [
    #         "Primary text 1",
    #         # ... up to 5
    #     ],
    #     "headlines": [
    #         "Headline 1",
    #         # ... up to 5
    #     ],
    # },
}

# UTM tags applied via url_tags on the creative (Meta expands {{...}} at serve time)
UTM_TAGS = (
    "utm_source=facebook"
    "&utm_medium=paid"
    "&utm_campaign={{campaign.name}}"
    "&utm_term={{adset.name}}"
    "&utm_content={{ad.name}}"
    "&fbadid={{ad.id}}"
)

API = "https://graph.facebook.com/v25.0"

# ============================================================
# Helpers
# ============================================================

def fail(msg):
    print(f"\n❌ {msg}\n")
    sys.exit(1)


def assert_config():
    missing = [k for k, v in [
        ("META_ACCESS_TOKEN", TOKEN),
        ("META_AD_ACCOUNT_ID", AD_ACCOUNT),
        ("META_PAGE_ID", PAGE_ID),
    ] if not v]
    if missing:
        fail("Missing env vars: " + ", ".join(missing))
    for placeholder in ["<<ADSET_ID>>", "<<LP_URL>>", "<<HASHES_FILE>>", "<<CTA>>"]:
        if placeholder in (ADSET_ID, LP_URL, HASHES_FILE, CTA):
            fail(f"Template not filled in: {placeholder} still has placeholder value")
    if not CLUSTERS:
        fail("CLUSTERS is empty. Add at least one cluster before running.")


def load_hashes(path):
    """Read hash|filename file produced by upload-images.sh."""
    if not os.path.exists(path):
        fail(f"Hashes file not found: {path}")
    out = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("FAILED"):
                continue
            h, name = line.split("|", 1)
            out[name] = h
    return out


def lookup_hashes(image_filenames, hashes):
    out = []
    for name in image_filenames:
        if name not in hashes:
            fail(f"No upload hash for image: {name}\nKnown: {sorted(hashes)}")
        out.append(hashes[name])
    return out


def build_object_story_spec(first_image_hash, primary_text, headline):
    link_data = {
        "link": LP_URL,
        "image_hash": first_image_hash,  # MUST equal groups[0].images[0].hash
        "message": primary_text,
        "name": headline,
        "call_to_action": {"type": CTA, "value": {"link": LP_URL}},
    }
    spec = {"page_id": PAGE_ID, "link_data": link_data}
    if INSTAGRAM_USER_ID:
        spec["instagram_user_id"] = INSTAGRAM_USER_ID
    return spec


def create_creative(name, first_image_hash, primary_text, headline):
    data = {
        "access_token": TOKEN,
        "name": name,
        "object_story_spec": json.dumps(build_object_story_spec(first_image_hash, primary_text, headline)),
        "url_tags": UTM_TAGS,
        "contextual_multi_ads": json.dumps({"enroll_status": "OPT_OUT"}),
    }
    r = requests.post(f"{API}/{AD_ACCOUNT}/adcreatives", data=data, timeout=60)
    if r.status_code != 200:
        fail(f"Creative create failed:\n{r.text}")
    return r.json()["id"]


def create_ad(name, creative_id, image_hashes, primary_texts, headlines):
    asset_groups_spec = {
        "groups": [{
            "images": [{"hash": h} for h in image_hashes],
            "texts": (
                [{"text": t, "text_type": "primary_text"} for t in primary_texts]
                + [{"text": h, "text_type": "headline"} for h in headlines]
            ),
            "call_to_action": {"type": CTA, "value": {"link": LP_URL}},
        }]
    }
    data = {
        "access_token": TOKEN,
        "name": name,
        "adset_id": ADSET_ID,
        "creative": json.dumps({"creative_id": creative_id}),
        "creative_asset_groups_spec": json.dumps(asset_groups_spec),
        "status": "PAUSED",
    }
    r = requests.post(f"{API}/{AD_ACCOUNT}/ads", data=data, timeout=60)
    if r.status_code != 200:
        # Retry once on transient errors (Failure #7 in references)
        try:
            err = r.json().get("error", {})
            if err.get("is_transient"):
                print(f"  transient error, retrying after 5s...")
                time.sleep(5)
                r = requests.post(f"{API}/{AD_ACCOUNT}/ads", data=data, timeout=60)
        except Exception:
            pass
    if r.status_code != 200:
        fail(f"Ad create failed:\n{r.text}")
    return r.json()["id"]


# ============================================================
# Main
# ============================================================

def main():
    assert_config()
    hashes = load_hashes(HASHES_FILE)
    print(f"Loaded {len(hashes)} image hashes from {HASHES_FILE}\n")

    results = []
    for key, cluster in CLUSTERS.items():
        name = cluster["name"]
        images = cluster["images"]
        primary_texts = cluster["primary_texts"][:5]
        headlines = cluster["headlines"][:5]

        if len(images) > 10:
            fail(f"{name}: {len(images)} images exceeds Meta's 10/ad limit")
        if len(primary_texts) < 1 or len(headlines) < 1:
            fail(f"{name}: needs at least 1 primary text and 1 headline")

        image_hashes = lookup_hashes(images, hashes)

        print(f"--- {name} ({len(images)} imgs, {len(primary_texts)} primary, {len(headlines)} headlines) ---")
        creative_id = create_creative(name, image_hashes[0], primary_texts[0], headlines[0])
        print(f"  creative {creative_id}")
        ad_id = create_ad(name, creative_id, image_hashes, primary_texts, headlines)
        print(f"  ad      {ad_id} (PAUSED)\n")
        results.append({
            "cluster": key,
            "name": name,
            "creative_id": creative_id,
            "ad_id": ad_id,
        })

    # Save results next to this script for the verify-and-activate step
    out_path = os.path.splitext(__file__)[0] + ".results.json"
    with open(out_path, "w") as f:
        json.dump({
            "adset_id": ADSET_ID,
            "ads": results,
        }, f, indent=2)
    print(f"Saved results to {out_path}")
    print("\nAll ads created PAUSED. Run verify-and-activate.py to activate after review.")


if __name__ == "__main__":
    main()
