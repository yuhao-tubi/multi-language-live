#!/bin/bash

# Test script to compare stdin vs concat approaches for FFmpeg streaming
# This demonstrates both methods with actual fragments

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FRAGMENTS_DIR="$PROJECT_ROOT/storage/processed_fragments/output/test-stream"
RTMP_URL="rtmp://localhost/live/test-stream"
TEST_DURATION=30

echo "========================================"
echo "FFmpeg Streaming Approach Comparison"
echo "========================================"
echo ""
echo "Fragments directory: $FRAGMENTS_DIR"
echo "RTMP URL: $RTMP_URL"
echo ""

# Check if SRS is running
if ! curl -s http://localhost:1985/api/v1/versions/ > /dev/null 2>&1; then
    echo "❌ SRS is not running. Start it with: npm run start:srs"
    exit 1
fi

# Check if fragments exist
if [ ! -d "$FRAGMENTS_DIR" ] || [ -z "$(ls -A "$FRAGMENTS_DIR" 2>/dev/null)" ]; then
    echo "❌ No fragments found in $FRAGMENTS_DIR"
    echo "Run the pipeline first to generate fragments"
    exit 1
fi

FRAGMENT_COUNT=$(ls -1 "$FRAGMENTS_DIR"/*.mp4 2>/dev/null | wc -l)
echo "Found $FRAGMENT_COUNT fragments"
echo ""

# ======================
# Test 1: Concat Demuxer
# ======================
test_concat() {
    echo "========================================"
    echo "Test 1: Concat Demuxer Approach"
    echo "========================================"
    echo ""
    
    CONCAT_FILE="/tmp/test-concat-list.txt"
    
    # Create concat list
    echo "Creating concat list..."
    > "$CONCAT_FILE"
    for fragment in "$FRAGMENTS_DIR"/*.mp4; do
        echo "file '$fragment'" >> "$CONCAT_FILE"
    done
    
    echo "Concat list contents:"
    cat "$CONCAT_FILE"
    echo ""
    
    echo "Starting FFmpeg with concat demuxer..."
    echo "Command:"
    echo "  ffmpeg -re -f concat -safe 0 -i $CONCAT_FILE \\"
    echo "    -c:v copy -c:a copy -f flv $RTMP_URL-concat"
    echo ""
    
    timeout $TEST_DURATION ffmpeg -hide_banner -loglevel info \
        -re \
        -f concat \
        -safe 0 \
        -i "$CONCAT_FILE" \
        -c:v copy \
        -c:a copy \
        -f flv \
        "$RTMP_URL-concat" 2>&1 | tee /tmp/ffmpeg-concat.log &
    
    CONCAT_PID=$!
    echo "FFmpeg PID: $CONCAT_PID"
    echo ""
    
    # Monitor for a few seconds
    sleep 5
    
    if ps -p $CONCAT_PID > /dev/null; then
        echo "✅ Concat approach: FFmpeg running successfully"
        echo "   View stream at: http://localhost:8080/players/srs_player.html?stream=test-stream-concat"
        echo ""
        
        # Test dynamic append (simulating new fragment arrival)
        echo "Testing dynamic append..."
        sleep 2
        echo "file '$FRAGMENTS_DIR/batch-0.mp4'" >> "$CONCAT_FILE"
        kill -SIGHUP $CONCAT_PID 2>/dev/null || true
        echo "   Sent SIGHUP to reload concat list"
        echo ""
        
        sleep 3
        kill $CONCAT_PID 2>/dev/null || true
        wait $CONCAT_PID 2>/dev/null || true
    else
        echo "❌ Concat approach: FFmpeg exited prematurely"
        echo "   Check /tmp/ffmpeg-concat.log for errors"
        echo ""
    fi
    
    rm -f "$CONCAT_FILE"
}

# ===================
# Test 2: stdin Pipe
# ===================
test_stdin() {
    echo "========================================"
    echo "Test 2: stdin Piping Approach"
    echo "========================================"
    echo ""
    
    echo "Starting FFmpeg with stdin input..."
    echo "Command:"
    echo "  cat fragments/*.mp4 | ffmpeg -re -f mp4 -i pipe:0 \\"
    echo "    -c:v copy -c:a copy -f flv $RTMP_URL-stdin"
    echo ""
    
    (
        for fragment in "$FRAGMENTS_DIR"/*.mp4; do
            echo "Piping: $(basename "$fragment")"
            cat "$fragment"
        done
    ) | timeout $TEST_DURATION ffmpeg -hide_banner -loglevel info \
        -re \
        -f mp4 \
        -i pipe:0 \
        -c:v copy \
        -c:a copy \
        -f flv \
        "$RTMP_URL-stdin" 2>&1 | tee /tmp/ffmpeg-stdin.log &
    
    STDIN_PID=$!
    echo "FFmpeg PID: $STDIN_PID"
    echo ""
    
    # Monitor
    sleep 5
    
    if ps -p $STDIN_PID > /dev/null; then
        echo "✅ stdin approach: FFmpeg running successfully"
        echo "   View stream at: http://localhost:8080/players/srs_player.html?stream=test-stream-stdin"
        echo ""
        
        sleep 5
        kill $STDIN_PID 2>/dev/null || true
        wait $STDIN_PID 2>/dev/null || true
    else
        echo "❌ stdin approach: FFmpeg exited prematurely"
        echo "   Check /tmp/ffmpeg-stdin.log for errors"
        echo ""
    fi
}

# =====================
# Test 3: Continuous stdin (realistic)
# =====================
test_continuous_stdin() {
    echo "========================================"
    echo "Test 3: Continuous stdin (Realistic)"
    echo "========================================"
    echo "This simulates fragments arriving over time"
    echo ""
    
    echo "Starting FFmpeg with stdin (persistent)..."
    
    # Start FFmpeg with stdin open
    mkfifo /tmp/stream-pipe 2>/dev/null || true
    
    (
        timeout $TEST_DURATION ffmpeg -hide_banner -loglevel info \
            -re \
            -f mp4 \
            -i pipe:0 \
            -c:v copy \
            -c:a copy \
            -f flv \
            "$RTMP_URL-continuous" < /tmp/stream-pipe
    ) 2>&1 | tee /tmp/ffmpeg-continuous.log &
    
    FFMPEG_PID=$!
    
    # Give FFmpeg time to start
    sleep 1
    
    # Simulate fragments arriving every 2 seconds
    (
        for fragment in "$FRAGMENTS_DIR"/*.mp4; do
            echo "$(date '+%H:%M:%S') - Sending: $(basename "$fragment")"
            cat "$fragment" > /tmp/stream-pipe
            sleep 2
        done
        
        # Close pipe
        exec 3>&- 2>/dev/null || true
    ) &
    
    FEEDER_PID=$!
    
    echo "FFmpeg PID: $FFMPEG_PID"
    echo "Feeder PID: $FEEDER_PID"
    echo ""
    echo "✅ Continuous stdin: Streaming fragments..."
    echo "   View stream at: http://localhost:8080/players/srs_player.html?stream=test-stream-continuous"
    echo ""
    
    # Wait for feeder to complete
    wait $FEEDER_PID 2>/dev/null || true
    
    # Clean up
    kill $FFMPEG_PID 2>/dev/null || true
    wait $FFMPEG_PID 2>/dev/null || true
    rm -f /tmp/stream-pipe
}

# ====================
# Main Test Execution
# ====================
main() {
    echo "Select test to run:"
    echo "  1) Concat Demuxer"
    echo "  2) stdin Piping (simple)"
    echo "  3) stdin Piping (continuous/realistic)"
    echo "  4) All tests"
    echo ""
    read -p "Enter choice [1-4]: " choice
    echo ""
    
    case $choice in
        1)
            test_concat
            ;;
        2)
            test_stdin
            ;;
        3)
            test_continuous_stdin
            ;;
        4)
            test_concat
            echo ""
            sleep 2
            test_stdin
            echo ""
            sleep 2
            test_continuous_stdin
            ;;
        *)
            echo "Invalid choice"
            exit 1
            ;;
    esac
    
    echo ""
    echo "========================================"
    echo "Tests Complete"
    echo "========================================"
    echo ""
    echo "Log files:"
    echo "  - /tmp/ffmpeg-concat.log"
    echo "  - /tmp/ffmpeg-stdin.log"
    echo "  - /tmp/ffmpeg-continuous.log"
    echo ""
}

# Run if executed directly
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    main
fi

