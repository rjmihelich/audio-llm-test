#!/usr/bin/env bash
#
# Bulk voice generation script for Audio LLM Test
# Seeds multilingual corpus, syncs voices, and generates WAVs
# across all free TTS providers (edge, gtts, piper, espeak)
#
# Usage: ssh ryan@10.10.70.10 'bash -s' < scripts/bulk_generate_voices.sh
#   or:  scp to server and run locally
#
set -euo pipefail

API="http://localhost:8000/api/speech"
LANGUAGES='["en","es","fr","de","it","pt-BR","ja","ko","zh"]'
FREE_PROVIDERS='["edge","gtts","piper","espeak"]'
PER_CATEGORY=50  # 50 utterances per command category per language

echo "========================================"
echo "  Bulk Voice Generation"
echo "========================================"
echo ""

# -------------------------------------------------------------------
# Step 1: Seed multilingual corpus
# -------------------------------------------------------------------
echo "[1/4] Seeding multilingual corpus (${LANGUAGES})..."
echo "       ${PER_CATEGORY} utterances per category per language"

SEED_RESULT=$(curl -s -X POST "${API}/corpus/seed" \
  -H "Content-Type: application/json" \
  -d "{
    \"languages\": ${LANGUAGES},
    \"per_category\": ${PER_CATEGORY}
  }")

echo "       Result: ${SEED_RESULT}"
echo ""

# Check corpus count
CORPUS_COUNT=$(curl -s "${API}/corpus" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))")
echo "       Total corpus entries: ${CORPUS_COUNT}"
echo ""

# -------------------------------------------------------------------
# Step 2: Sync all voices
# -------------------------------------------------------------------
echo "[2/4] Syncing voices from all providers..."

SYNC_RESULT=$(curl -s -X POST "${API}/voices/sync")
echo "       Result: ${SYNC_RESULT}"
echo ""

# Count voices
VOICE_COUNT=$(curl -s "${API}/voices" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))")
echo "       Total voices available: ${VOICE_COUNT}"
echo ""

# -------------------------------------------------------------------
# Step 3: Show generation plan
# -------------------------------------------------------------------
echo "[3/4] Generation plan:"
echo ""

# Count voice breakdown by provider
curl -s "${API}/voices" | python3 -c "
import json, sys
voices = json.load(sys.stdin)
providers = {}
for v in voices:
    p = v['provider']
    providers[p] = providers.get(p, 0) + 1
free = ['edge', 'gtts', 'piper', 'espeak']
total_free = 0
for p in sorted(providers):
    marker = ' (FREE)' if p in free else ' (PAID - skipping)'
    print(f'         {p}: {providers[p]} voices{marker}')
    if p in free:
        total_free += providers[p]
print(f'')
print(f'       Free voices: {total_free}')
print(f'       Corpus entries: $CORPUS_COUNT')
print(f'       Total WAVs to generate: {total_free * int(\"$CORPUS_COUNT\")}')
"
echo ""

# -------------------------------------------------------------------
# Step 4: Generate WAVs per provider using streaming endpoint
# -------------------------------------------------------------------
echo "[4/4] Generating WAVs..."
echo ""

for PROVIDER in edge gtts piper espeak; do
  echo "  --- ${PROVIDER} ---"

  # Count how many voices this provider has
  PCOUNT=$(curl -s "${API}/voices" | python3 -c "
import json, sys
voices = json.load(sys.stdin)
count = sum(1 for v in voices if v['provider'] == '${PROVIDER}')
print(count)
")

  if [ "$PCOUNT" = "0" ]; then
    echo "  No voices for ${PROVIDER}, skipping"
    echo ""
    continue
  fi

  echo "  ${PCOUNT} voices x ${CORPUS_COUNT} utterances"
  echo "  Starting generation (this may take a while)..."

  # Use the non-streaming endpoint with a high max_total
  # Process in batches of 500 to avoid timeouts
  BATCH=0
  while true; do
    BATCH=$((BATCH + 1))

    RESULT=$(curl -s --max-time 600 -X POST "${API}/generate-wavs" \
      -H "Content-Type: application/json" \
      -d "{
        \"providers\": [\"${PROVIDER}\"],
        \"max_total\": 500
      }" 2>&1)

    # Check if we got an error (no more pending samples)
    if echo "$RESULT" | grep -q '"generated":0'; then
      echo "  Batch ${BATCH}: No more pending samples"
      break
    fi

    if echo "$RESULT" | grep -q '"detail"'; then
      # Could be "No pending samples" or similar
      echo "  Batch ${BATCH}: ${RESULT}"
      break
    fi

    GENERATED=$(echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('generated',0))" 2>/dev/null || echo "?")
    FAILED=$(echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('failed',0))" 2>/dev/null || echo "?")
    echo "  Batch ${BATCH}: generated=${GENERATED}, failed=${FAILED}"

    # If nothing was generated, we're done
    if [ "$GENERATED" = "0" ]; then
      break
    fi
  done

  echo ""
done

# -------------------------------------------------------------------
# Final summary
# -------------------------------------------------------------------
echo "========================================"
echo "  Generation Complete!"
echo "========================================"
echo ""

# Count WAVs on disk
WAV_COUNT=$(find /home/ryan/server/apps/audio-llm-test/storage/audio/ -name '*.wav' 2>/dev/null | wc -l)
echo "  Total WAV files on disk: ${WAV_COUNT}"
echo ""

# Show breakdown
echo "  By voice directory:"
for dir in /home/ryan/server/apps/audio-llm-test/storage/audio/*/; do
  if [ -d "$dir" ]; then
    COUNT=$(find "$dir" -name '*.wav' | wc -l)
    SIZE=$(du -sh "$dir" | cut -f1)
    echo "    $(basename $dir): ${COUNT} files (${SIZE})"
  fi
done

echo ""
TOTAL_SIZE=$(du -sh /home/ryan/server/apps/audio-llm-test/storage/audio/ | cut -f1)
echo "  Total storage: ${TOTAL_SIZE}"

# Show stats from API
echo ""
echo "  API stats:"
curl -s "${API}/stats" | python3 -c "
import json, sys
stats = json.load(sys.stdin)
if isinstance(stats, list):
    for s in stats:
        print(f'    {s}')
elif isinstance(stats, dict):
    for k, v in stats.items():
        print(f'    {k}: {v}')
" 2>/dev/null || echo "    (stats endpoint not available)"

echo ""
echo "Done!"
