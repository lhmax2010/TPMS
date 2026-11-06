#!/bin/bash

# test_h265.sh — H.265/HEVC decoding performance test using GStreamer
#
# Usage: test_h265.sh TEST_FILE
#   TEST_FILE - path to the H.265/HEVC video file to decode

# === User Configuration ===
TEST_FILE="$1"
TOTAL_FRAMES=1000
# === End Configuration ===

echo "Starting H.265 decoding performance test..."
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

# Run decoding pipeline: file source -> H.265 parse -> H.265 decode -> fake sink
# For raw H.265 streams (.h265), use h265parse directly (no demuxer needed)
gst-launch-1.0 -q filesrc location="$TEST_FILE" ! \
    h265parse ! \
    avdec_h265 ! \
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
