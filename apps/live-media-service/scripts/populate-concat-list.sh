#!/bin/bash

# Populate concat list from existing batch files
# Usage: ./populate-concat-list.sh <stream-id> [storage-path]

set -e

STREAM_ID="${1:-test-stream}"
STORAGE_PATH="${2:-./storage}"
OUTPUT_DIR="${STORAGE_PATH}/processed_fragments/output/${STREAM_ID}"
CONCAT_LIST="${OUTPUT_DIR}/concat-list.txt"

echo "🔧 Populating concat list for stream: ${STREAM_ID}"
echo "   Output directory: ${OUTPUT_DIR}"
echo "   Concat list: ${CONCAT_LIST}"

# Check if output directory exists
if [ ! -d "${OUTPUT_DIR}" ]; then
  echo "❌ Error: Output directory does not exist: ${OUTPUT_DIR}"
  exit 1
fi

# Check if there are any batch files
BATCH_COUNT=$(find "${OUTPUT_DIR}" -name "batch-*.mp4" | wc -l | tr -d ' ')
if [ "${BATCH_COUNT}" -eq 0 ]; then
  echo "❌ Error: No batch files found in ${OUTPUT_DIR}"
  exit 1
fi

echo "   Found ${BATCH_COUNT} batch files"

# Create concat list
echo "📝 Creating concat list..."
> "${CONCAT_LIST}"  # Clear existing file

# Add batch files in order
find "${OUTPUT_DIR}" -name "batch-*.mp4" | sort -V | while read -r file; do
  # Get absolute path
  ABS_PATH=$(cd "$(dirname "$file")" && pwd)/$(basename "$file")
  echo "file '${ABS_PATH}'" >> "${CONCAT_LIST}"
  echo "   Added: $(basename "$file")"
done

echo "✅ Concat list created successfully!"
echo "   Total entries: $(wc -l < "${CONCAT_LIST}" | tr -d ' ')"
echo ""
echo "📄 Concat list contents:"
cat "${CONCAT_LIST}"

