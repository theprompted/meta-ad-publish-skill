# meta-ad-publish

A Claude Code skill that walks you through publishing flexible image or video ads to Meta (Facebook + Instagram) via the Marketing API.

You answer questions, the skill generates a customised Python script, runs it, and verifies activation. No need to learn the API.

---

## What it does

- **Image OR video ads** in Meta's Flexible Ad Format (multiple images/videos × multiple texts × multiple headlines per ad — Meta picks the best combos).
- **Existing or new ad sets.** If you don't have one yet, the skill creates a Cost Cap or ROAS ad set + campaign with sensible defaults.
- **Drafts copy from your landing page**, or accepts copy you've already written.
- **Proposes image clusters** when you have more than 10 images (Meta's per-ad limit).
- **Generates a Python script** for the batch — the script is auditable, re-runnable, and on disk.
- **Activates and verifies** all 3 levels (campaign + ad set + ad), since Meta's activation does NOT cascade.

Built around the patterns that have shipped across thousands of ads in production. See `.claude/skills/meta-ad-publish/references/failures-and-fixes.md` for the 13 known failure modes and their fixes — every one of them has burned someone before.

---

## Install

1. Copy `.claude/skills/meta-ad-publish/` into your project's `.claude/skills/` folder. (Or clone this repo into a project.)
2. Make the helpers executable:
   ```
   chmod +x scripts/upload-images.sh scripts/upload-video.sh
   ```
3. Get a Meta Marketing API access token. Generate one by creating a System User in Meta Business Suite + an App in developers.facebook.com, then pressing Generate Token on the System User. ([Visual walkthrough](https://theprompted.github.io/matandvics-funnel/meta-api-setup/) covers the click-by-click.)
4. Save the token in a `.env` file at your project root:
   ```
   META_ACCESS_TOKEN=EAC...your-token...
   ```
   Make sure `.env` is in your `.gitignore`. The skill will warn you if it isn't.

That's it for install. The skill asks for your account IDs (ad account, page, Instagram, pixel) on first run and saves them to `.claude/state/meta-publish-config.json`.

---

## Usage

In Claude Code:

```
/meta-ad-publish
```

The skill takes it from there. It walks you through:

1. **First run only:** confirm your ad account ID, page ID, Instagram user ID (optional), pixel ID.
2. Image ad or video ad?
3. Where are the assets?
4. Existing ad set, or create a new one?
5. (If new) Cost Cap, ROAS, or both? What's the cap / floor?
6. Landing page URL + CTA button?
7. (If you have >10 images) Approve image clusters or split differently?
8. Have copy ready, or want me to draft from your LP?
9. Review the generated script.
10. Run it.
11. Verify and activate.

Every step has a "back out" option. Nothing is published until you confirm at the run step. All ads start PAUSED.

---

## Files

```
.claude/skills/meta-ad-publish/
  SKILL.md                          # the skill itself
  references/
    failures-and-fixes.md           # 13 documented failures + fixes
    api-quick-reference.md          # Meta API endpoints in one page

templates/
  publish-image.py                  # image-ad template (skill customises this)
  publish-video.py                  # video-ad template
  verify-and-activate.py            # post-publish verification

scripts/
  upload-images.sh                  # image upload helper
  upload-video.sh                   # video upload + thumbnail extraction
```

The skill copies templates into `./publish-runs/publish-<date>-<batch>.py` for each run. Those are your auditable artifacts — they don't need to be re-generated; you can re-run them later or adapt them for the next batch.

---

## Why script-generation, not direct API calls

The skill could call Meta's API directly each time. It doesn't, because:

1. **Re-runnable.** If the script fails halfway, fix it and re-run — without re-answering all the questions.
2. **Auditable.** The exact payload sent to Meta is on disk. If Meta rejects something, the script is the artifact.
3. **Survives interrupts.** A crashed Claude Code session doesn't lose your batch.
4. **Matches what's known to work.** Every successful publish across thousands of ads followed this pattern.

---

## Locked rules (the skill follows these without asking)

- All ads created PAUSED. Activation is a separate, verified step.
- API version: v25.0.
- Use Flexible Ad Format (`creative_asset_groups_spec` on the AD call), never Dynamic Creative.
- First image hash on the creative must equal the first image in the ad's asset groups.
- `creative_asset_groups_spec` lives on the `/ads` call, NEVER on `/adcreatives`.
- ROAS ad sets reuse the Cost Cap creative_id (preserves Meta's learning).
- `instagram_user_id`, never `instagram_actor_id`. Look up the IG Business Account ID, not the page-backed actor ID.
- Set `contextual_multi_ads: {enroll_status: "OPT_OUT"}` on every creative.

If you're curious why each rule exists, every one is in `references/failures-and-fixes.md`.

---

## Troubleshooting

| Error | What it means | Where to look |
|---|---|---|
| "object doesn't exist" | Token not loaded (despite the misleading message) | Failure #13 |
| "Image/Video Mismatch" | First asset in creative ≠ first in groups[0] | Failure #5 |
| "Cannot have more than one ad in DCT Ad Set" | `creative_asset_groups_spec` was put on /adcreatives by mistake | Failure #12 |
| "instagram_actor_id is not supported" | Wrong IG ID — use the Business Account ID | Failure #4 |
| Empty hash file | Filenames have spaces/commas — use the upload-images.sh helper | Failure #1 |

For everything else, paste the full error to the skill and it'll either find a documented fix or stop and surface it cleanly.

---

## License

MIT.
