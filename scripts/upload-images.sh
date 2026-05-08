#!/bin/bash
# Upload images to a Meta ad account and save hashes.
# Usage: ./upload-images.sh "/path/to/image/folder" "/path/to/output-hashes.txt"
#
# Reads META_AD_ACCOUNT_ID and META_ACCESS_TOKEN from environment or a local .env.
# Handles filenames with spaces, commas, and special characters.
# Outputs: hash|filename per line to the output file.

set -e

# Load .env from current dir if not already in environment
if [ -f ".env" ] && [ -z "$META_ACCESS_TOKEN" ]; then
  set -a
  . ./.env
  set +a
fi

DIR="$1"
OUTPUT="$2"

if [ -z "$DIR" ] || [ -z "$OUTPUT" ]; then
  echo "Usage: $0 <image-directory> <output-hashes-file>"
  exit 1
fi

if [ -z "$META_ACCESS_TOKEN" ]; then
  echo "Error: META_ACCESS_TOKEN not set. Add it to .env or export it."
  exit 1
fi

if [ -z "$META_AD_ACCOUNT_ID" ]; then
  echo "Error: META_AD_ACCOUNT_ID not set (e.g. act_1234567890)."
  exit 1
fi

if [ ! -d "$DIR" ]; then
  echo "Error: Directory not found: $DIR"
  exit 1
fi

> "$OUTPUT"
COUNT=0
TOTAL=$(find "$DIR" -maxdepth 1 \( -name "*.png" -o -name "*.jpg" -o -name "*.jpeg" \) | wc -l | tr -d ' ')

echo "Uploading $TOTAL images from $DIR to $META_AD_ACCOUNT_ID..."

find "$DIR" -maxdepth 1 \( -name "*.png" -o -name "*.jpg" -o -name "*.jpeg" \) -print0 | sort -z | while IFS= read -r -d '' FILE; do
  COUNT=$((COUNT + 1))
  BASENAME=$(basename "$FILE")
  RESULT=$(curl -s -X POST "https://graph.facebook.com/v25.0/$META_AD_ACCOUNT_ID/adimages" \
    -F "access_token=$META_ACCESS_TOKEN" \
    -F "filename=@\"$FILE\"")
  HASH=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(list(d['images'].values())[0]['hash'])" 2>/dev/null)
  if [ -n "$HASH" ]; then
    echo "$HASH|$BASENAME" >> "$OUTPUT"
    echo "[$COUNT/$TOTAL] ✓ $HASH | $BASENAME"
  else
    echo "[$COUNT/$TOTAL] ✗ FAILED: $BASENAME"
    echo "  Response: $RESULT"
    echo "FAILED|$BASENAME" >> "$OUTPUT"
  fi
  sleep 1
done

SUCCEEDED=$(grep -cv FAILED "$OUTPUT" 2>/dev/null || echo 0)
FAILED_COUNT=$(grep -c FAILED "$OUTPUT" 2>/dev/null || echo 0)
echo ""
echo "Done. $SUCCEEDED succeeded, $FAILED_COUNT failed."
echo "Hashes saved to: $OUTPUT"
