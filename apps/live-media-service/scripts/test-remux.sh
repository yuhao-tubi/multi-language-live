#!/bin/bash

# Test remux script - mimics the Remuxer.ts FFmpeg command with longest duration flags
# Usage: ./test-remux.sh [batch-number] [output-name]
# Example: ./test-remux.sh 0 test-output

set -e

# Get batch number (default: 0)
BATCH_NUM=${1:-0}
OUTPUT_NAME=${2:-"remux-test"}

# Set base directory (relative to script location)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$SCRIPT_DIR/.."

# Input paths
VIDEO_PATH="$BASE_DIR/storage/processed_fragments/video/test-stream/batch-${BATCH_NUM}.mp4"
AUDIO_PATH="$BASE_DIR/storage/processed_fragments/processed_audio/test-stream/batch-${BATCH_NUM}.mp4"

# Output path
OUTPUT_PATH="$BASE_DIR/storage/processed_fragments/output/test-stream/${OUTPUT_NAME}-batch-${BATCH_NUM}.mp4"

echo "=========================================="
echo "Testing Remux with Longest Duration"
echo "=========================================="
echo "Batch Number: ${BATCH_NUM}"
echo "Video Input:  ${VIDEO_PATH}"
echo "Audio Input:  ${AUDIO_PATH}"
echo "Output:       ${OUTPUT_PATH}"
echo ""

# Check if input files exist
if [ ! -f "$VIDEO_PATH" ]; then
    echo "❌ Error: Video file not found: $VIDEO_PATH"
    exit 1
fi

if [ ! -f "$AUDIO_PATH" ]; then
    echo "❌ Error: Audio file not found: $AUDIO_PATH"
    exit 1
fi

# Get durations before remux
echo "📊 Input file durations:"
echo ""
echo "Video duration:"
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$VIDEO_PATH" | xargs printf "  %.3f seconds\n"
echo ""
echo "Audio duration:"
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$AUDIO_PATH" | xargs printf "  %.3f seconds\n"
echo ""

# Ensure output directory exists
mkdir -p "$(dirname "$OUTPUT_PATH")"

echo "🎬 Running FFmpeg remux (with longest duration flags)..."
echo ""

# FFmpeg command - matches Remuxer.ts exactly
ffmpeg -y \
  -i "$VIDEO_PATH" \
  -i "$AUDIO_PATH" \
  -map 0:v \
  -c:v copy \
  -map 1:a \
  -c:a aac \
  -b:a 128k \
  -af apad \
  -f mp4 \
  -movflags frag_keyframe+empty_moov \
  "$OUTPUT_PATH"

echo ""
echo "✅ Remux complete!"
echo ""

# Get output duration
echo "📊 Output file duration:"
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$OUTPUT_PATH" | xargs printf "  %.3f seconds\n"
echo ""

# Get file sizes
echo "📦 File sizes:"
ls -lh "$VIDEO_PATH" | awk '{print "  Video: " $5}'
ls -lh "$AUDIO_PATH" | awk '{print "  Audio: " $5}'
ls -lh "$OUTPUT_PATH" | awk '{print "  Output: " $5}'
echo ""

echo "=========================================="
echo "✅ Test complete! Output saved to:"
echo "   $OUTPUT_PATH"
echo "=========================================="

