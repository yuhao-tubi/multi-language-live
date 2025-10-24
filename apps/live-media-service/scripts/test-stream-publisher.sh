#!/bin/bash

# Test StreamPublisher with pre-recorded batch files
# This script runs a manual test that publishes batch files to SRS at real-time pace

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🎬 StreamPublisher Playback Test"
echo "================================="
echo ""

# Check if SRS is running
if ! curl -s "http://localhost:1985/api/v1/versions" > /dev/null 2>&1; then
    echo "⚠️  Warning: SRS doesn't appear to be running"
    echo "   Start it with: ./scripts/start-srs.sh"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check if batch files exist
BATCH_DIR="$PROJECT_DIR/storage/processed_fragments/output/test-stream"
if [ ! -d "$BATCH_DIR" ]; then
    echo "❌ Batch directory not found: $BATCH_DIR"
    echo "   Please ensure batch files exist before running this test."
    exit 1
fi

BATCH_COUNT=$(find "$BATCH_DIR" -name "batch-*.mp4" -type f | wc -l | tr -d ' ')
if [ "$BATCH_COUNT" -eq 0 ]; then
    echo "❌ No batch files found in $BATCH_DIR"
    exit 1
fi

echo "✅ Found $BATCH_COUNT batch files"
echo ""

# Run the test
cd "$PROJECT_DIR"
npx tsx tests/manual/stream-publisher-playback.test.ts

echo ""
echo "✅ Test completed!"

