#!/usr/bin/env python3
"""
Publish flexible video ads to Meta.

TEMPLATE. The /meta-ad-publish skill fills in placeholders + the CLUSTERS dict.

Each cluster becomes ONE flexible ad. Each cluster contains up to 10 videos
(video_id + thumbnail_hash pairs from upload-video.sh) plus up to 5 primary
texts and up to 5 headlines.
"""

import json
import os
import sys
import time
import requests

TOKEN = os.environ.get("META_ACCESS_TOKEN")
AD_ACCOUNT = os.environ.get("META_AD_ACCOUNT_ID")
PAGE_ID = os.environ.get("META_PAGE_ID")
INSTAGRAM_USER_ID = os.environ.get("META_INSTAGRAM_USER_ID")

ADSET_ID = "<<ADSET_ID>>"
LP_URL = "<<LP_URL>>"
CTA = "<<CTA>>"

# Each cluster is ONE flexible ad. Videos must have been uploaded via
# upload-video.sh first; the resulting video_info files give VIDEO_ID +
# THUMBNAIL_HASH pairs.
CLUSTERS = {
    # "cluster-key": {
    #     "name": "Ad name",
    #     "videos": [
    #         {"video_id": "1234567890", "thumbnail_hash": "abc123..."},
    #         # ... up to 10
    #     ],
    #     "primary_texts": [...],   # up to 5
    #     "headlines": [...],       # up to 5
    #     "link_description": "",   # optional, shows under headline
    # },
}

UTM_TAGS = (
    "utm_source=facebook"
    "&utm_medium=paid"
    "&utm_campaign={{campaign.name}}"
    "&utm_term={{adset.name}}"
    "&utm_content={{ad.name}}"
    "&fbadid={{ad.id}}"
)

API = "https://graph.facebook.com/v25.0"


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
    for placeholder, val in [("ADSET_ID", ADSET_ID), ("LP_URL", LP_URL), ("CTA", CTA)]:
        if val.startswith("<<"):
            fail(f"Template not filled in: {placeholder}")
    if not CLUSTERS:
        fail("CLUSTERS is empty.")


def build_object_story_spec(first_video, primary_text, headline, description):
    video_data = {
        "video_id": first_video["video_id"],
        "image_hash": first_video["thumbnail_hash"],
        "message": primary_text,
        "title": headline,
        "call_to_action": {"type": CTA, "value": {"link": LP_URL}},
    }
    if description:
        video_data["link_description"] = description
    spec = {"page_id": PAGE_ID, "video_data": video_data}
    if INSTAGRAM_USER_ID:
        spec["instagram_user_id"] = INSTAGRAM_USER_ID
    return spec


def create_creative(name, first_video, primary_text, headline, description):
    data = {
        "access_token": TOKEN,
        "name": name,
        "object_story_spec": json.dumps(build_object_story_spec(first_video, primary_text, headline, description)),
        "url_tags": UTM_TAGS,
        "contextual_multi_ads": json.dumps({"enroll_status": "OPT_OUT"}),
    }
    r = requests.post(f"{API}/{AD_ACCOUNT}/adcreatives", data=data, timeout=60)
    if r.status_code != 200:
        fail(f"Creative create failed:\n{r.text}")
    return r.json()["id"]


def create_ad(name, creative_id, videos, primary_texts, headlines):
    asset_groups_spec = {
        "groups": [{
            "videos": [{"video_id": v["video_id"], "image_hash": v["thumbnail_hash"]} for v in videos],
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


def main():
    assert_config()
    results = []
    for key, cluster in CLUSTERS.items():
        name = cluster["name"]
        videos = cluster["videos"]
        primary_texts = cluster["primary_texts"][:5]
        headlines = cluster["headlines"][:5]
        description = cluster.get("link_description", "")

        if len(videos) > 10:
            fail(f"{name}: {len(videos)} videos exceeds Meta's 10/ad limit")
        if len(primary_texts) < 1 or len(headlines) < 1:
            fail(f"{name}: needs at least 1 primary text and 1 headline")
        for v in videos:
            if not v.get("video_id") or not v.get("thumbnail_hash"):
                fail(f"{name}: video missing video_id or thumbnail_hash: {v}")

        print(f"--- {name} ({len(videos)} vids, {len(primary_texts)} primary, {len(headlines)} headlines) ---")
        creative_id = create_creative(name, videos[0], primary_texts[0], headlines[0], description)
        print(f"  creative {creative_id}")
        ad_id = create_ad(name, creative_id, videos, primary_texts, headlines)
        print(f"  ad      {ad_id} (PAUSED)\n")
        results.append({
            "cluster": key,
            "name": name,
            "creative_id": creative_id,
            "ad_id": ad_id,
        })

    out_path = os.path.splitext(__file__)[0] + ".results.json"
    with open(out_path, "w") as f:
        json.dump({"adset_id": ADSET_ID, "ads": results}, f, indent=2)
    print(f"Saved results to {out_path}")
    print("\nAll ads created PAUSED. Run verify-and-activate.py to activate after review.")


if __name__ == "__main__":
    main()
