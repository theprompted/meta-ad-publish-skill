# Meta Ad Publish

Guided publishing of flexible image and video ads to Meta via the Marketing API. Walks the user through every decision, generates a customised Python publish script for the batch, runs it, then verifies activation across all 3 levels (campaign + ad set + ad).

This skill is **invoked by name** — when the user types `/meta-ad-publish` or asks to "publish ads to Meta", "create Facebook ads", "ship a flexible ad", etc.

---

## When to use this skill

The user has:
- Image files OR video files they want to publish as a Facebook/Instagram ad
- A Meta access token (from the Meta API setup guide) saved as `META_ACCESS_TOKEN`
- Either an existing ad set to publish into, OR wants to create one as part of this run

The user does NOT need to:
- Have written ad copy yet (skill can draft from a landing page or product description)
- Know the Meta API
- Have decided on Cost Cap vs ROAS bid strategy

---

## How the skill works

The skill is **fully guided** — it asks questions via AskUserQuestion, fills in a generic Python template from `templates/`, runs the script, then activates and verifies.

**The execution model is script-generation, not direct API calls.** Reasons:
1. The script is on disk if anything fails — replay/debug without re-answering questions
2. The script is auditable — exact payloads sent to Meta are visible
3. The pattern matches what is known to work in production over many publish runs

---

## Files used by this skill

- `references/failures-and-fixes.md` — read this BEFORE the first API call. 13 documented failures and their fixes.
- `references/api-quick-reference.md` — Meta API endpoints, payloads, limits in one page.
- `templates/publish-image.py` — image-ad template, copied + customised per batch.
- `templates/publish-video.py` — video-ad template, same idea.
- `templates/verify-and-activate.py` — runs after publish; activates 3 levels and verifies effective_status.
- `scripts/upload-images.sh` — image upload helper (handles filenames with spaces/commas).
- `scripts/upload-video.sh` — video upload + thumbnail extraction + thumbnail upload.

All paths in this doc are relative to wherever the skill files were installed (typically the project's `.claude/skills/meta-ad-publish/`).

---

## The full guided flow

### Phase 0 — First-run config

Goal: capture the user's account identifiers once, save them, and never ask again.

**Check for existing config first** at `.claude/state/meta-publish-config.json`. If present and not stale, skip to Phase 1 and confirm only.

If absent, ask via AskUserQuestion:

1. **What's your Meta ad account ID?** (format `act_1234567890`) — find it in Ads Manager URL or Business Settings → Ad Accounts.
2. **What's your Facebook Page ID?** — Business Settings → Pages.
3. **Do you advertise on Instagram too? If yes, paste your Instagram User ID.** (Optional — leave blank for Facebook-only.) Note: this is the **Instagram User ID** not the page-backed actor ID — see failures-and-fixes #4.
4. **What's your Pixel ID?** — Events Manager.
5. **Do you have a `.env` file in this project?** — branch:
   - **Yes** → ask for the variable name (default `META_ACCESS_TOKEN`). Verify by sourcing.
   - **No** → ask user to paste the token. Save to `./.env` as `META_ACCESS_TOKEN=...` and ensure `.env` is in `.gitignore`.

Save the rest to `.claude/state/meta-publish-config.json`:

```json
{
  "ad_account_id": "act_...",
  "page_id": "...",
  "instagram_user_id": "..." | null,
  "pixel_id": "...",
  "token_env_var": "META_ACCESS_TOKEN",
  "saved_at": "YYYY-MM-DD"
}
```

**Do NOT save the token itself in the JSON.** Only the env var name.

---

### Phase 1 — Asset type

```
AskUserQuestion: "What kind of ad are you publishing?"
  - Image ad (one or more images, no video)
  - Video ad (one or more videos)
```

Mixed (image + video in the same flexible ad) is intentionally not supported — match the patterns we know work in production.

---

### Phase 2 — Asset intake

**Image branch:**
1. Ask: "Where are your image files?" (folder path).
2. List files (PNG/JPG/JPEG). Show count.
3. **Approval gate:** if there are >10 images, the user may want to split into 2 ads (Phase 5). Tell them now so they think about it.
4. Run `scripts/upload-images.sh "<folder>" "/tmp/meta-ad-publish-<timestamp>-hashes.txt"`.
5. Verify: count of `hash|filename` lines matches expected. Show any FAILED entries.

**Video branch:**
1. Ask: "Where are your video file(s)?" (folder path or single file path).
2. For each video, ask: "Pick thumbnail second" — default 0, can offer 1, 2, or "first frame after fade-in" (manual pick).
3. Run `scripts/upload-video.sh "<video>" "/tmp/meta-publish-<videoname>-info.txt" <thumb-second>`.
4. Repeat for every video. Collect `(video_id, thumbnail_hash)` pairs.
5. Verify: every video reached `video_status == ready`.

---

### Phase 3 — Ad set selection

```
AskUserQuestion: "Where should this ad land?"
  - Existing ad set (most common)
  - Create a new ad set + campaign for this product/funnel
```

**Existing branch:**
1. Query `GET /{AD_ACCOUNT}/campaigns?fields=id,name,status,bid_strategy` to find non-archived campaigns.
2. For each, fetch ad sets: `GET /{CAMPAIGN_ID}/adsets?fields=id,name,status,optimization_goal`.
3. Present a flat list grouped by campaign. User picks one.

**Create-new branch (opt-in):** see Phase 3b.

---

### Phase 3b — Create a new campaign + ad set (opt-in)

Only entered if user picked "Create a new ad set" in Phase 3.

**Step 1 — Cost Cap, ROAS, or both?**

```
AskUserQuestion: "What bid strategy?"
  - Cost Cap (recommended for first launch — Meta optimises for purchases under your cap)
  - ROAS (only if you have proven creative + want to enforce a return floor)
  - Both — create a Cost Cap pair and a ROAS pair (mirrors how mature accounts run)
```

Explain inline:
- Cost Cap = "spend up to $X per purchase, Meta tries to get them under that"
- ROAS = "spend whatever it takes as long as return-on-ad-spend stays above N×"

**Step 2 — Cost Cap amount**

Ask for the cap. Help with the formula:

> "A common starting cap is **AOV ÷ 2.2** (your average order value divided by 2.2). If your AOV is €70, that's a €32 cap. This roughly aligns with a 20% contribution-margin target after Meta's typical CPC + COGS. Want to use that, or set a custom cap?"

Result: a number in the user's currency. Convert to cents/lowest unit before sending (Meta wants integer cents).

**Step 3 — ROAS floor (if applicable)**

Ask: "What ROAS floor? Common starting points: 1.3, 1.5, 2.0. Higher = stricter (less spend but better ROI)."

Convert: `roas_average_floor = floor * 10000` (so 1.5 → 15000).

**Step 4 — Targeting + objective**

Use safe defaults and surface them to the user before creating:
- Geo: ask the user (e.g. "US", "UK", "Canada", custom country list)
- Age: 18–65 default
- Objective: `OUTCOME_SALES` (the standard for ecommerce purchase campaigns)
- Optimization goal: `OFFSITE_CONVERSIONS` (Cost Cap) or `VALUE` (ROAS) — failure #9 in references
- Billing event: `IMPRESSIONS`
- Attribution: 7-day click-through

**Step 5 — Create**

Issue the API calls (campaign first, then ad sets). Both created PAUSED. Log the IDs.

---

### Phase 4 — Landing page URL + CTA

Ask:
1. "What's the landing page URL?" — full URL incl. `https://`. This will receive the click.
2. "Pick a call-to-action button:" — `LEARN_MORE` (default), `SHOP_NOW`, `SIGN_UP`, `GET_OFFER`. Show 4 options.

---

### Phase 5 — Cluster proposal (image branch only)

The skill proposes 1–2 thematic clusters. Each cluster is one flexible ad.

**Logic:**
- ≤10 assets → propose **1 cluster** with all assets.
- >10 assets → propose **2 clusters** of roughly equal size, ideally split by visual theme. If the skill cannot infer themes from filenames or the LP, default to a 50/50 numerical split and label them "Cluster A" / "Cluster B".

**To infer themes (good-faith attempt):**
1. Look at filenames for repeated tokens (e.g. `bedside-01`, `bedside-02`, `evidence-03`).
2. Or read the LP at the URL provided in Phase 4 and group images by which section they'd fit (problem/agitation/proof/solution).
3. Or skip inference and present it as a numerical split.

Show the proposal:

> Proposed 2 flexible ads (you have 18 images, Meta caps at 10/ad):
>
> **Ad A — "Bedside" (10 images)**
> - bedside-01.png, bedside-02.png, ... ceiling-03.png
>
> **Ad B — "Aftermath" (8 images)**
> - drawer-01.png, mirror-02.png, ... empty-bottle-04.png
>
> Approve, swap an image between clusters, merge to 1 ad, or pick differently?

Use AskUserQuestion. Always offer:
- Approve as proposed
- Merge into 1 ad (cap at 10 images — drop the rest, ask which)
- Re-split manually (drop into a follow-up where the user lists filenames per cluster)

---

### Phase 6 — Copy

```
AskUserQuestion: "Do you have ad copy ready, or want me to draft?"
  - I have copy ready
  - Draft it for me (uses the LP and product context)
  - Mix — I'll write headlines, you draft primary texts
```

**"Have copy ready" branch:**
1. Per cluster, ask: "Paste your primary texts (one per line, max 5)."
2. Per cluster, ask: "Paste your headlines (one per line, max 5)."
3. Validate: ≤5 of each, headline length ≤ 40 chars (Meta's recommendation), primary text ≤ ~125 chars before "See more" truncation.

**"Draft" branch:**
1. Read the LP URL (`WebFetch` or curl-and-strip).
2. For each cluster, write **5 distinct primary text angles** and **5 distinct headlines**. The ANGLES must be different — not 5 rephrasings of the same idea. Reference common angles: problem (status quo failing), proof (specific evidence), reframe (new way to see it), urgency (now or never), social (others made the switch).
3. Show drafts. Offer: accept, regenerate, or edit specific lines.

**"Mix" branch:** combine the two — ask the user which half they want to write, draft the other half.

In all branches, end at the validation gate: ≤5 primary, ≤5 headline, character limits checked.

---

### Phase 7 — Bid strategy assignment

If the ad set the user picked (or just created) is Cost Cap **and** there's a paired ROAS ad set in the same campaign (or a sibling ROAS campaign), ask:

```
"I see a matching ROAS ad set. Want me to also publish these ads into ROAS using the same creative IDs (saves Meta's learning, recommended)?"
  - Yes — duplicate to ROAS too
  - Cost Cap only for now
```

If yes → after publishing to Cost Cap, run a duplicate-to-ROAS step that creates new ad objects in the ROAS ad set referencing the same `creative_id`. **Never recreate the creative** — see locked-rules below.

---

### Phase 8 — Generate the publish script

1. Pick template: `publish-image.py` or `publish-video.py`.
2. Copy to `./publish-runs/publish-<YYYY-MM-DD>-<batch-name>.py`.
3. Replace `<<ADSET_ID>>`, `<<LP_URL>>`, `<<HASHES_FILE>>` (image only), `<<CTA>>`.
4. Fill in the `CLUSTERS` dict from Phases 5 + 6.
5. Show the user the file path. Offer:
   - "Open the script for review before running"
   - "Run it now"

---

### Phase 9 — Run the script

```bash
cd <project root>  # so .env is sourced
source .env  # for shell-based scripts
python3 ./publish-runs/publish-<date>-<batch>.py
```

Stream output. Each cluster prints `creative {id}` then `ad {id} (PAUSED)`. On any error, **stop** — show the error inline, offer:
- "Retry the script as-is" (transient errors)
- "Show me the error in failures-and-fixes.md" (known errors)
- "Edit the script and re-run"

---

### Phase 10 — Verify and activate

Always-paused-by-default is the rule. Activation is a deliberate step.

```
AskUserQuestion: "Ads created PAUSED. Ready to activate?"
  - Yes — activate all 3 levels (campaign + ad set + ads)
  - Not yet — review in Ads Manager first
```

If yes, run `templates/verify-and-activate.py <results.json>`. The script:
1. Activates campaign → ad set → each ad
2. Waits 4 seconds
3. Re-reads `effective_status` for all of them
4. Reports any that aren't `ACTIVE` or `IN_PROCESS` (which is normal during Meta review)

If anything stays PAUSED after activation, surface why (parent paused, billing issue, etc.) — see references.

---

## Locked rules (never break)

1. **Always source the .env or load_dotenv() before any API call.** Empty `$META_ACCESS_TOKEN` → Meta returns "object doesn't exist" — misleading; really means "no auth". (Failure #13.)
2. **Use Flexible Ad Format (`creative_asset_groups_spec` on the AD call), never Dynamic Creative (`asset_feed_spec` on the creative call).** Dynamic Creative limits to 1 ad per ad set. (Failure #2.)
3. **First image hash must match between `object_story_spec.link_data.image_hash` and `creative_asset_groups_spec.groups[0].images[0].hash`.** (Failure #5.)
4. **Use `instagram_user_id` not `instagram_actor_id`. The "ID" shown in the Ads Manager UI under the IG account is usually the page-backed actor ID — wrong.** (Failure #4.)
5. **Set `contextual_multi_ads: {enroll_status: "OPT_OUT"}` on every creative.** Otherwise Meta may merge into multi-advertiser ad sets.
6. **All ads created PAUSED. Always.** Activation is a separate, verified step.
7. **Activation does NOT cascade.** Campaign ACTIVE ≠ ad set ACTIVE ≠ ads ACTIVE. Verify each level's `effective_status`.
8. **For ROAS ad sets, reuse the Cost Cap `creative_id`. Never recreate the creative.** Preserves Meta's learning across bid strategies.
9. **Hard limits per ad: 10 images OR 10 videos, 5 primary texts, 5 headlines.** Only `primary_text` and `headline` text types — `description` is rejected.
10. **`creative_asset_groups_spec` goes on the `/ads` call, NEVER on `/adcreatives`.** Putting it on the creative call silently turns the ad set into a Dynamic Creative ad set and blocks the next ad. (Failure #12.)
11. **For video ads: upload thumbnail as an ad image, get its hash, pass that as `image_hash` in `video_data`.** Don't use Meta's CDN thumbnail URLs — they expire.

---

## API quick reference

| Endpoint | Purpose | Notes |
|---|---|---|
| `POST /{AD_ACCOUNT}/adimages` | Upload image, get hash | Use upload-images.sh |
| `POST /{AD_ACCOUNT}/advideos` | Upload video, get id | Poll `/{video_id}?fields=status` until `video_status==ready` |
| `POST /{AD_ACCOUNT}/adcreatives` | Create creative | `object_story_spec` only — NO `creative_asset_groups_spec` |
| `POST /{AD_ACCOUNT}/ads` | Create ad | `creative_asset_groups_spec` HERE, status=PAUSED |
| `POST /{AD_ACCOUNT}/campaigns` | Create campaign | `objective=OUTCOME_SALES`, `bid_strategy=COST_CAP` or `LOWEST_COST_WITH_MIN_ROAS` |
| `POST /{AD_ACCOUNT}/adsets` | Create ad set | `optimization_goal=OFFSITE_CONVERSIONS` (Cost Cap) or `VALUE` (ROAS) |
| `POST /{ID}` | Update status | `status=ACTIVE` or `PAUSED` |
| `GET /{ID}?fields=effective_status` | Verify after activation | `effective_status` not `status` |

API version: **v25.0** throughout.

---

## What to do if a step fails

1. Read the error message. Most are documented in `references/failures-and-fixes.md`.
2. If `is_transient: true` in the error → retry once after 5 seconds. The template scripts already do this.
3. The publish script is on disk. Don't re-run the whole skill — fix the script, re-run it.
4. If the error is unfamiliar, paste the FULL error JSON to the user and stop. Don't guess.
