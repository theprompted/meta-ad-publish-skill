#!/bin/bash
# Upload a video to a Meta ad account, extract a thumbnail, upload the thumbnail as an ad image.
# Outputs: VIDEO_ID and THUMBNAIL_HASH on stdout (also written to OUTPUT file).
# Usage: ./upload-video.sh "/path/to/video.mp4" "/path/to/output-video-info.txt" [thumbnail-second]
#
# Polls Meta until video_status == "ready" before exiting.

set -e

if [ -f ".env" ] && [ -z "$META_ACCESS_TOKEN" ]; then
  set -a
  . ./.env
  set +a
fi

VIDEO="$1"
OUTPUT="$2"
THUMB_SECOND="${3:-0}"

if [ -z "$VIDEO" ] || [ -z "$OUTPUT" ]; then
  echo "Usage: $0 <video-file> <output-info-file> [thumbnail-second-default-0]"
  exit 1
fi

if [ -z "$META_ACCESS_TOKEN" ] || [ -z "$META_AD_ACCOUNT_ID" ]; then
  echo "Error: META_ACCESS_TOKEN or META_AD_ACCOUNT_ID not set."
  exit 1
fi

if [ ! -f "$VIDEO" ]; then
  echo "Error: Video not found: $VIDEO"
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "Error: ffmpeg not installed (brew install ffmpeg)."
  exit 1
fi

VIDEO_TITLE=$(basename "$VIDEO" | sed 's/\.[^.]*$//')

echo "Uploading video: $VIDEO_TITLE"
RESULT=$(curl -s -X POST "https://graph.facebook.com/v25.0/$META_AD_ACCOUNT_ID/advideos" \
  -F "access_token=$META_ACCESS_TOKEN" \
  -F "title=$VIDEO_TITLE" \
  -F "source=@\"$VIDEO\"")

VIDEO_ID=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null)

if [ -z "$VIDEO_ID" ]; then
  echo "FAILED to upload video. Response:"
  echo "$RESULT"
  exit 1
fi

echo "  Video uploaded, id=$VIDEO_ID"
echo "  Polling for video_status=ready..."

for i in $(seq 1 60); do
  STATUS=$(curl -s -G "https://graph.facebook.com/v25.0/$VIDEO_ID" \
    --data-urlencode "access_token=$META_ACCESS_TOKEN" \
    --data-urlencode "fields=status")
  VS=$(echo "$STATUS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',{}).get('video_status',''))" 2>/dev/null)
  echo "    [$i] video_status=$VS"
  if [ "$VS" = "ready" ]; then
    break
  fi
  sleep 5
done

if [ "$VS" != "ready" ]; then
  echo "Video did not reach ready status after 5 minutes. Aborting."
  exit 1
fi

# Extract thumbnail
THUMB="/tmp/meta-thumb-$$.jpg"
ffmpeg -y -ss "$THUMB_SECOND" -i "$VIDEO" -vframes 1 -q:v 2 "$THUMB" >/dev/null 2>&1

if [ ! -f "$THUMB" ]; then
  echo "Failed to extract thumbnail."
  exit 1
fi

echo "  Thumbnail extracted at second $THUMB_SECOND -> $THUMB"

# Upload thumbnail as ad image
THUMB_RESULT=$(curl -s -X POST "https://graph.facebook.com/v25.0/$META_AD_ACCOUNT_ID/adimages" \
  -F "access_token=$META_ACCESS_TOKEN" \
  -F "filename=@\"$THUMB\"")
THUMB_HASH=$(echo "$THUMB_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(list(d['images'].values())[0]['hash'])" 2>/dev/null)

if [ -z "$THUMB_HASH" ]; then
  echo "Failed to upload thumbnail. Response:"
  echo "$THUMB_RESULT"
  exit 1
fi

echo "  Thumbnail uploaded, hash=$THUMB_HASH"

# Save to output file
echo "VIDEO_ID=$VIDEO_ID" > "$OUTPUT"
echo "THUMBNAIL_HASH=$THUMB_HASH" >> "$OUTPUT"
echo "VIDEO_FILE=$VIDEO" >> "$OUTPUT"
echo "THUMB_SECOND=$THUMB_SECOND" >> "$OUTPUT"

echo ""
echo "Done. Info saved to: $OUTPUT"
echo "  VIDEO_ID=$VIDEO_ID"
echo "  THUMBNAIL_HASH=$THUMB_HASH"

rm -f "$THUMB"
