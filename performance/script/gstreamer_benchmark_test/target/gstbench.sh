#!/bin/bash

# gstbench.sh — GStreamer video decoding performance benchmark (device-side)
#
# Usage: gstbench.sh TEST_DIR RESULT_FILE
#   TEST_DIR     - directory on device containing test video files (with h264/, hevc/ subdirs)
#   RESULT_FILE  - absolute path to the output result file
#
# This script is part of the TPMS gstreamer_benchmark_test.
# It scans subdirectories under TEST_DIR for video files, runs GStreamer
# decoding benchmarks with multiple iterations, and writes a summary
# (including per-file average FPS, min, max, std dev) to RESULT_FILE.

echo -e '\033[34m' ' '

function test_exit {
	echo -e '\033[0m' ' '
	exit $1
}

file_name=${0##*/}
# UEP-safe invocation pipes this script via stdin, making $0="bash";
# allow the caller to pass the real test name explicitly.
test_name=${TPMS_TEST_NAME:-${file_name%%\.*}}

function usage {
	echo "usage: $file_name TEST_DIR RESULT_FILE"
}

echo "start $test_name"

if [ $# -lt 2 ]; then
	usage
	echo "not enough argument" 1>&2
	test_exit -1
fi

TEST_DIR="$1"
RESULT_FILE="$2"

if [[ $RESULT_FILE != /* ]]; then
	echo "result file must be absolute path" 1>&2
	test_exit -1
fi

result_path=${RESULT_FILE%/*}/

if [ ! -d "${result_path}" ]; then
	mkdir -p "$result_path"
fi

# Remove previous result
if [ -e "${RESULT_FILE}" ]; then
	rm "$RESULT_FILE"
	sync
fi

if [ ! -d "$TEST_DIR" ]; then
	echo "Error: TEST_DIR does not exist: $TEST_DIR" | tee -a "$RESULT_FILE"
	test_exit -1
fi

# Script directory (where test_h264.sh, test_h265.sh are located)
# Under UEP-safe pipe invocation $0 is "bash", so fall back to the
# caller-provided TPMS_SCRIPT_DIR (the directory this script lives in).
SCRIPT_DIR="${TPMS_SCRIPT_DIR:-$(cd "$(dirname "$0")" && pwd)}"

# Subdirectories to scan for test video files
VIDEO_SUBDIRS=(h264 hevc)

# Detect available test files from subdirectories
echo "Scanning for video files under: $TEST_DIR" | tee -a "$RESULT_FILE"
FILES=()
SCRIPTS=()
for subdir in "${VIDEO_SUBDIRS[@]}"; do
	dir_path="${TEST_DIR}/${subdir}"
	if [ -d "$dir_path" ]; then
		while IFS= read -r filename; do
			[ -n "$filename" ] && FILES+=("${subdir}/${filename}")
			# Determine test script based on subdirectory
			if [ "$subdir" == "h264" ]; then
				SCRIPTS+=("${SCRIPT_DIR}/test_h264.sh")
			elif [ "$subdir" == "hevc" ]; then
				SCRIPTS+=("${SCRIPT_DIR}/test_h265.sh")
			else
				SCRIPTS+=("")
			fi
		done < <(ls -1 "$dir_path" 2>/dev/null)
	fi
done

if [ ${#FILES[@]} -eq 0 ]; then
	echo "Error: No video files found under $TEST_DIR" | tee -a "$RESULT_FILE"
	test_exit -1
fi

echo "Detected ${#FILES[@]} files:" | tee -a "$RESULT_FILE"
for f in "${FILES[@]}"; do
	echo "  - $f" | tee -a "$RESULT_FILE"
done

ITERATIONS=5

echo "========================================" | tee -a "$RESULT_FILE"
echo "GStreamer Decoding Performance Test" | tee -a "$RESULT_FILE"
echo "Start time: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$RESULT_FILE"
echo "Running ${ITERATIONS} iterations per file and averaging" | tee -a "$RESULT_FILE"
echo "========================================" | tee -a "$RESULT_FILE"

# Check files
for file in "${FILES[@]}"; do
	[ ! -f "$TEST_DIR/$file" ] && echo "Warning: File does not exist: $TEST_DIR/$file" | tee -a "$RESULT_FILE"
done
echo "" | tee -a "$RESULT_FILE"

# Set CPU governor to performance mode for consistent results
echo performance | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor 2>/dev/null || true

# Temporary directory for per-file results
RESULT_DIR=$(mktemp -d)
trap "rm -rf $RESULT_DIR" EXIT

# Run a single benchmark iteration
# Outputs FPS value on stdout (for capture by caller)
run_benchmark() {
	local file="$1"
	local script="$2"
	local iteration="$3"
	local filename=$(basename "$file")

	echo "[$(date '+%H:%M:%S')] Iteration $iteration/${ITERATIONS}: $filename" >> "$RESULT_FILE"

	# Clear system caches
	echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true
	sync

	# Execute benchmark (UEP-safe pipe invocation: $0 becomes "bash")
	output=$(cat "$script" | bash -s -- "$file" 2>&1)

	# Display last few lines
	echo "$output" | tail -4 >> "$RESULT_FILE"

	# Extract FPS value - use sed/awk instead of grep -oP (not available in busybox)
	# Look for "Average decode FPS:" followed by a number
	fps=$(echo "$output" | grep "Average decode FPS:" | sed 's/.*Average decode FPS:[[:space:]]*//' | awk '{print $1}')

	if [ -n "$fps" ]; then
		echo "$fps"
	else
		echo "  -> FPS extraction failed" >> "$RESULT_FILE"
		echo ""
	fi
}

is_number() {
	case "$1" in
		''|*[!0-9.]*) return 1 ;;
		*) return 0 ;;
	esac
}

echo "Starting test..." | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

# Main benchmark loop
for i in "${!FILES[@]}"; do
	file_path="$TEST_DIR/${FILES[$i]}"
	script="${SCRIPTS[$i]}"
	[ ! -f "$file_path" ] && continue
	[ -z "$script" ] && continue
	[ ! -f "$script" ] && echo "Warning: test script not found: $script" | tee -a "$RESULT_FILE" && continue

	filename=$(basename "$file_path")
	key="${filename}"

	fps_sum=0
	valid_count=0
	fps_values=""
	min_fps=999999
	max_fps=0

	echo "========================================" | tee -a "$RESULT_FILE"
	echo "File: $filename | Script: $(basename $script)" | tee -a "$RESULT_FILE"
	echo "========================================" | tee -a "$RESULT_FILE"

	for iter in $(seq 1 $ITERATIONS); do
		fps=$(run_benchmark "$file_path" "$script" "$iter")

		if is_number "$fps" && [ "$(awk -v f="$fps" 'BEGIN { print (f > 0) ? 1 : 0 }')" -eq 1 ] 2>/dev/null; then
			# Use awk for floating point arithmetic (bc may not be available)
			fps_sum=$(awk -v s="$fps_sum" -v f="$fps" 'BEGIN { printf "%.2f", s + f }')
			valid_count=$((valid_count + 1))
			[ -z "$fps_values" ] && fps_values="$fps" || fps_values="$fps_values, $fps"

			# Track min/max using awk
			if [ "$(awk -v a="$fps" -v b="$min_fps" 'BEGIN { print (a < b) ? 1 : 0 }')" -eq 1 ] 2>/dev/null; then
				min_fps=$fps
			fi
			if [ "$(awk -v a="$fps" -v b="$max_fps" 'BEGIN { print (a > b) ? 1 : 0 }')" -eq 1 ] 2>/dev/null; then
				max_fps=$fps
			fi
		fi
		echo "" | tee -a "$RESULT_FILE"
	done

	# Save results
	if [ "$valid_count" -gt 0 ]; then
		avg=$(awk -v s="$fps_sum" -v c="$valid_count" 'BEGIN { printf "%.2f", s / c }')

		# Calculate standard deviation using awk
		if [ "$valid_count" -gt 1 ]; then
			std_dev=$(echo "$fps_values" | awk -v avg="$avg" '{
				n = split($0, vals, ", ")
				sum_sq = 0
				for(i=1; i<=n; i++) {
					diff = vals[i] - avg
					sum_sq += diff * diff
				}
				printf "%.2f", sqrt(sum_sq / n)
			}')
		else
			std_dev="0.00"
		fi

		echo "$avg $min_fps $max_fps $std_dev" > "$RESULT_DIR/$key"
		echo ">>> Avg FPS: $avg | Min: $min_fps | Max: $max_fps | Std Dev: $std_dev" | tee -a "$RESULT_FILE"
	else
		echo "0 0 0 0" > "$RESULT_DIR/$key"
		echo ">>> All failed" | tee -a "$RESULT_FILE"
	fi
	echo "" | tee -a "$RESULT_FILE"
done

# Summary report
echo "" | tee -a "$RESULT_FILE"
echo "========================================" | tee -a "$RESULT_FILE"
echo "Performance Test Summary" | tee -a "$RESULT_FILE"
echo "End time: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$RESULT_FILE"
echo "========================================" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

printf "%-35s | %-10s | %-10s | %-10s | %-10s\n" "File" "Avg FPS" "Min FPS" "Max FPS" "Std Dev" | tee -a "$RESULT_FILE"
echo "-----------------------------------------------------------------------" | tee -a "$RESULT_FILE"

for i in "${!FILES[@]}"; do
	filename=$(basename "${FILES[$i]}")
	key="${filename}"
	result_file="$RESULT_DIR/$key"
	avg="N/A"
	min="N/A"
	max="N/A"
	std="N/A"
	if [ -f "$result_file" ]; then
		read avg min max std < "$result_file"
	fi
	printf "%-35s | %-10s | %-10s | %-10s | %-10s\n" "$filename" "$avg" "$min" "$max" "$std" | tee -a "$RESULT_FILE"
done

echo "" | tee -a "$RESULT_FILE"
echo "Results saved to: $RESULT_FILE"

echo "end $test_name"
test_exit 0
