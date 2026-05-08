# Meta Marketing API — Quick Reference

API version used throughout: **v25.0**

---

## Endpoints used

```
# Image upload
POST https://graph.facebook.com/v25.0/{AD_ACCOUNT}/adimages
  -F access_token=$TOKEN
  -F filename=@file.png
  → returns {"images": {"file.png": {"hash": "..."}}}

# Video upload
POST https://graph.facebook.com/v25.0/{AD_ACCOUNT}/advideos
  -F access_token=$TOKEN
  -F title="Video Title"
  -F source=@file.mp4
  → returns {"id": "<video_id>"}

# Poll video readiness
GET  https://graph.facebook.com/v25.0/{VIDEO_ID}?fields=status
  → status.video_status == "ready" when ready

# Create creative
POST https://graph.facebook.com/v25.0/{AD_ACCOUNT}/adcreatives
  body:
    access_token, name,
    object_story_spec (JSON string),
    url_tags (UTM string),
    contextual_multi_ads={"enroll_status":"OPT_OUT"}

# Create ad
POST https://graph.facebook.com/v25.0/{AD_ACCOUNT}/ads
  body:
    access_token, name, adset_id,
    creative={"creative_id": "..."},
    creative_asset_groups_spec (JSON string),
    status="PAUSED"

# Update status (activate)
POST https://graph.facebook.com/v25.0/{ID}
  -d status=ACTIVE
  -d access_token=$TOKEN

# Verify effective_status
GET  https://graph.facebook.com/v25.0/{ID}?fields=id,name,status,effective_status
```

---

## Hard limits per ad

| Limit | Value |
|---|---|
| Images | 10 |
| Videos | 10 |
| Primary texts | 5 |
| Headlines | 5 |
| Other text types | not allowed (`description` rejected) |

---

## Cost Cap ad set body

```
optimization_goal=OFFSITE_CONVERSIONS
billing_event=IMPRESSIONS
bid_amount=<integer cents>
promoted_object={"pixel_id":"<PIXEL_ID>","custom_event_type":"PURCHASE"}
targeting={"geo_locations":{"countries":["US"],"location_types":["home"]},"age_min":18,"age_max":65}
attribution_spec=[{"event_type":"CLICK_THROUGH","window_days":7}]
status=PAUSED
```

## ROAS ad set body

```
optimization_goal=VALUE
billing_event=IMPRESSIONS
bid_constraints={"roas_average_floor": <floor * 10000>}
promoted_object={"pixel_id":"<PIXEL_ID>","custom_event_type":"PURCHASE"}
targeting=...
attribution_spec=...
status=PAUSED
```

## Campaign body

```
name="..."
objective=OUTCOME_SALES
bid_strategy=COST_CAP            # or LOWEST_COST_WITH_MIN_ROAS
daily_budget=<cents>
special_ad_categories=[]
status=PAUSED
```

---

## Image ad — full creative + ad payload

```python
# CREATIVE
object_story_spec = {
  "page_id": PAGE_ID,
  "instagram_user_id": INSTAGRAM_USER_ID,   # OMIT if facebook-only
  "link_data": {
    "link": LP_URL,
    "image_hash": image_hashes[0],          # MUST match groups[0].images[0].hash
    "message": primary_texts[0],
    "name": headlines[0],
    "call_to_action": {"type": CTA, "value": {"link": LP_URL}}
  }
}
# POST to /adcreatives with object_story_spec, url_tags, contextual_multi_ads

# AD
creative_asset_groups_spec = {
  "groups": [{
    "images": [{"hash": h} for h in image_hashes],     # up to 10
    "texts": (
      [{"text": t, "text_type": "primary_text"} for t in primary_texts] +
      [{"text": h, "text_type": "headline"}     for h in headlines]
    ),
    "call_to_action": {"type": CTA, "value": {"link": LP_URL}}
  }]
}
# POST to /ads with creative={creative_id}, creative_asset_groups_spec, status=PAUSED
```

---

## Video ad — full creative + ad payload

```python
# CREATIVE
object_story_spec = {
  "page_id": PAGE_ID,
  "instagram_user_id": INSTAGRAM_USER_ID,
  "video_data": {
    "video_id": videos[0]["video_id"],
    "image_hash": videos[0]["thumbnail_hash"],     # required
    "message": primary_texts[0],
    "title": headlines[0],
    "link_description": "<optional>",
    "call_to_action": {"type": CTA, "value": {"link": LP_URL}}
  }
}

# AD
creative_asset_groups_spec = {
  "groups": [{
    "videos": [
      {"video_id": v["video_id"], "image_hash": v["thumbnail_hash"]}
      for v in videos                                # up to 10
    ],
    "texts": (
      [{"text": t, "text_type": "primary_text"} for t in primary_texts] +
      [{"text": h, "text_type": "headline"}     for h in headlines]
    ),
    "call_to_action": {"type": CTA, "value": {"link": LP_URL}}
  }]
}
```

---

## UTM tags pattern

Set `url_tags` on the creative (not on the ad). Meta expands `{{...}}` at serve time:

```
utm_source=facebook&utm_medium=paid&utm_campaign={{campaign.name}}&utm_term={{adset.name}}&utm_content={{ad.name}}&fbadid={{ad.id}}
```
