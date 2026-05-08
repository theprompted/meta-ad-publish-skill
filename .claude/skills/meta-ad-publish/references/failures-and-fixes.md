# Meta Ad Publish — Failures and Fixes

Every failure mode encountered in production. Read before the first API call.

---

## Failure #1 — Image upload returns empty / hash file is empty

**Symptom:** `upload-images.sh` runs but produces 0 lines in the hash file. Curl returns empty or exit 26.

**Cause:** Filenames with spaces, commas, or special characters (`Image Mar 17, 2026, 07_06_12.png`) break naive iteration.

**Fix:** Always run via `scripts/upload-images.sh` (uses `find -print0` + `read -d ''` + escaped curl `-F "filename=@\"$FILE\""`). Don't write inline curl loops.

---

## Failure #2 — "Cannot Create Dynamic Creative ad In Non-Dynamic Creative Ad Set"

**Cause:** `asset_feed_spec` was used on the creative. That makes it a Dynamic Creative, which only works in Dynamic Creative ad sets — and those allow only **one ad** ever.

**Fix:** Use `creative_asset_groups_spec` on the **ad** call (NOT the creative call). This is Flexible Ad Format. No special ad-set flag needed; multiple ads per ad set work.

---

## Failure #3 — `asset_feed_spec` errors

Don't use it. See Failure #2.

---

## Failure #4 — `instagram_actor_id is not supported in object_story_spec`

**Cause:** Used the page-backed Instagram actor ID (the one shown in the Ads Manager UI under the IG handle).

**Fix:** Use `instagram_user_id` with the **Instagram Business Account ID**, which is different. Look it up via:

```bash
curl -s -G "https://graph.facebook.com/v25.0/<PAGE_ID>" \
  --data-urlencode "access_token=$META_ACCESS_TOKEN" \
  --data-urlencode "fields=instagram_business_account"
```

Returns `{"instagram_business_account": {"id": "<USE_THIS>"}}`.

---

## Failure #5 — "Flexible Format Image/Video Mismatch"

```
"The first image/video of the first Flexible Format asset group must
match the image/video in the creative spec."
```

**Cause:** `object_story_spec.link_data.image_hash` (or `video_data.video_id`) doesn't match `groups[0].images[0].hash` (or videos[0]).

**Fix:** Set the first asset in `object_story_spec` and `groups[0]` to the same value. The object_story_spec is the "default fallback" version of the ad — it must be consistent with the first asset in the flexible group.

---

## Failure #6 — "The link field is required"

**Cause:** Missing `link` inside `object_story_spec.link_data`.

**Fix:** Always include `link`, `image_hash`, `message`, `name`, and `call_to_action` in `link_data`.

---

## Failure #7 — Transient API error during ad creation

```json
{"error": {"message": "An unexpected error has occurred...", "is_transient": true, "code": 2}}
```

**Fix:** Sleep 5s, retry once. The publish-image.py and publish-video.py templates do this automatically.

---

## Failure #8 — Background shell tasks produce no output

**Cause:** Quoting context differs in background shell tasks. Escaped `\"$FILE\"` may be re-escaped or stripped.

**Fix:** Always use the standalone shell scripts in `scripts/`, never inline curl in a background task.

---

## Failure #9 — Wrong optimization_goal

**Cause:** Cost Cap ad sets need `OFFSITE_CONVERSIONS`, ROAS ad sets need `VALUE`. Mixing them up creates ad sets that never optimise.

**Fix:**
- Cost Cap: `optimization_goal=OFFSITE_CONVERSIONS`, `bid_amount=<cents>`
- ROAS:     `optimization_goal=VALUE`, `bid_constraints={"roas_average_floor": <floor*10000>}`

---

## Failure #10 — Searching Meta docs for the wrong feature name

The Ads Manager UI calls it "Add text option". The API calls it **Flexible Ad Format**. Search docs for "Meta flexible ad format" or go straight to `developers.facebook.com/docs/marketing-api/flexible-ad-format/`.

---

## Failure #11 — Long ad copy breaks shell escaping

**Symptom:** curl with quoted ad copy containing single quotes, em dashes, emoji, newlines fails or sends garbled text.

**Fix:** Always use Python `requests` + `json.dumps()` for ad creation. Reserve curl for simple parameter calls (status updates, queries).

---

## Failure #12 — `creative_asset_groups_spec` on creative call (the most expensive trap)

**Symptom:** First ad succeeds. Second ad to the same ad set fails with "Cannot have more than one ad in given Dynamic Creative Ad Set" — even though `is_dynamic_creative=false` on the ad set.

**Cause:** Putting `creative_asset_groups_spec` on the `/adcreatives` call silently makes the ad set behave like a Dynamic Creative one.

**Fix:** ONLY put `creative_asset_groups_spec` on the `/ads` call.

- Creative call: `object_story_spec` + `url_tags` + `contextual_multi_ads`
- Ad call: `creative` (id ref) + `creative_asset_groups_spec` + `status`

---

## Failure #13 — Token not loaded → "object doesn't exist"

**Symptom:** Curl returns:
```
"Unsupported post request. Object with ID 'X' does not exist, cannot
be loaded due to missing permissions, or does not support this operation."
```

**Cause:** `$META_ACCESS_TOKEN` is empty because the .env wasn't sourced. Meta sees no auth → returns a generic "doesn't exist" error.

**Fix:** Always source the .env first:

```bash
source .env && curl ... "access_token=$META_ACCESS_TOKEN"
```

Python scripts using `python-dotenv`'s `load_dotenv()` handle this automatically.

---

## Quick Reference — Correct Values

| What | Correct | Wrong |
|---|---|---|
| Instagram field in object_story_spec | `instagram_user_id` | `instagram_actor_id` |
| Multi-asset format | `creative_asset_groups_spec` (on /ads) | `asset_feed_spec` |
| Multi-advertiser opt-out | `contextual_multi_ads: {enroll_status: "OPT_OUT"}` | (omit it) |
| Cost Cap optimization | `OFFSITE_CONVERSIONS` | `VALUE` |
| ROAS optimization | `VALUE` + `bid_constraints` | `OFFSITE_CONVERSIONS` |
| Status to verify | `effective_status` | `status` |
| API version | `v25.0` | older versions |
