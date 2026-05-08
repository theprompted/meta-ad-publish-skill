#!/usr/bin/env python3
"""
Activate ads created by publish-image.py / publish-video.py and verify
all 3 levels (campaign, ad set, ad) reach effective_status == ACTIVE.

Activation does NOT cascade. Campaign ACTIVE != ad set ACTIVE != ad ACTIVE.

Usage: python3 verify-and-activate.py path/to/publish-script.results.json
"""

import json
import os
import sys
import time
import requests

TOKEN = os.environ.get("META_ACCESS_TOKEN")
API = "https://graph.facebook.com/v25.0"


def fail(msg):
    print(f"\n❌ {msg}\n")
    sys.exit(1)


def post_status(obj_id, status):
    r = requests.post(f"{API}/{obj_id}", data={"status": status, "access_token": TOKEN}, timeout=30)
    if r.status_code != 200:
        fail(f"Failed to set {obj_id} -> {status}: {r.text}")
    return r.json()


def get_status(obj_id):
    r = requests.get(
        f"{API}/{obj_id}",
        params={"access_token": TOKEN, "fields": "id,name,status,effective_status,campaign_id,adset_id"},
        timeout=30,
    )
    if r.status_code != 200:
        fail(f"Failed to read {obj_id}: {r.text}")
    return r.json()


def main():
    if len(sys.argv) < 2:
        fail("Usage: verify-and-activate.py path/to/results.json")
    if not TOKEN:
        fail("META_ACCESS_TOKEN not set")

    with open(sys.argv[1]) as f:
        results = json.load(f)

    adset_id = results["adset_id"]
    ad_ids = [a["ad_id"] for a in results["ads"]]

    # Look up campaign for the ad set
    adset = get_status(adset_id)
    campaign_id = adset["campaign_id"]

    print(f"Activating campaign {campaign_id}...")
    post_status(campaign_id, "ACTIVE")

    print(f"Activating ad set {adset_id}...")
    post_status(adset_id, "ACTIVE")

    for ad_id in ad_ids:
        print(f"Activating ad {ad_id}...")
        post_status(ad_id, "ACTIVE")

    # Settle, then verify effective_status
    print("\nWaiting 4s for state to settle, then verifying effective_status...\n")
    time.sleep(4)

    problems = []
    for label, obj_id in [
        ("campaign", campaign_id),
        ("ad set", adset_id),
        *[("ad", a) for a in ad_ids],
    ]:
        s = get_status(obj_id)
        es = s.get("effective_status")
        marker = "✓" if es in ("ACTIVE", "IN_PROCESS") else "⚠"
        print(f"  {marker} {label:8} {obj_id:20} status={s.get('status')}  effective_status={es}  {s.get('name','')}")
        if es not in ("ACTIVE", "IN_PROCESS"):
            problems.append((label, obj_id, es))

    if problems:
        print("\n⚠ Some objects did not reach ACTIVE/IN_PROCESS effective_status:")
        for label, obj_id, es in problems:
            print(f"   {label} {obj_id}: effective_status={es}")
        print("\nCommon causes: parent paused, billing issue, ad pending review (IN_PROCESS is normal),")
        print("or Meta is still processing. Re-run this script in a minute.")
        sys.exit(2)

    print("\n✓ All levels active.")


if __name__ == "__main__":
    main()
