#!/bin/bash

# test_h264.sh — H.264 decoding performance test using GStreamer
#
# Usage: test_h264.sh TEST_FILE
#   TEST_FILE - path to the H.264 video file to decode

# === User Configuration ===
TEST_FILE="$1"
TOTAL_FRAMES=1000
# === End Configuration ===

echo "Starting H.264 decoding performance test..."
echo "Test file: $TEST_FILE"
echo "Total frames: $TOTAL_FRAMES"
echo "----------------------------------------"

# Check gst-launch-1.0 is available
if ! command -v gst-launch-1.0 >/dev/null 2>&1; then
    echo "ERROR: gst-launch-1.0 not found"
    echo "Decode time: 0 seconds"
    echo "Average decode FPS: 0"
    echo "----------------------------------------"
    exit 1
fi

# Record start time (second precision; use awk for sub-second if available)
START_TIME=$(date +%s)

# Run decoding pipeline: file source -> H.264 parse -> H.264 decode -> fake sink
# Capture stderr for debugging but don't suppress completely
gst-launch-1.0 -q filesrc location="$TEST_FILE" ! \
    qtdemux ! h264parse ! \
    avdec_h264 ! \
    fakesink sync=false 2>&1

# Record end time
END_TIME=$(date +%s)

# Calculate elapsed time (seconds) and average FPS using awk (bc may not be available)
read ELAPSED_TIME AVG_FPS <<EOF
$(awk -v s="$START_TIME" -v e="$END_TIME" -v f="$TOTAL_FRAMES" 'BEGIN { elapsed = e - s; if (elapsed <= 0) elapsed = 1; fps = f / elapsed; printf "%.2f %.2f", elapsed, fps }')
EOF

echo "Test complete!"
echo "----------------------------------------"
echo "Decode time:    ${ELAPSED_TIME} seconds"
echo "Average decode FPS: ${AVG_FPS}"
echo "----------------------------------------"
