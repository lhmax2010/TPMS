#!/bin/bash

# ffbench.sh — FFmpeg video decoding performance benchmark (device-side)
#
# Usage: ffbench.sh TEST_DIR RESULT_FILE
#   TEST_DIR     - directory on device containing test video files (with h264/, hevc/ subdirs)
#   RESULT_FILE  - absolute path to the output result file
#
# This script is part of the TPMS ffmpeg_benchmark_test.
# It scans subdirectories under TEST_DIR for video files, runs FFmpeg
# decoding benchmarks with multiple iterations, and writes a summary
# table (including per-file average FPS) to RESULT_FILE.

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

# Subdirectories to scan for test video files
VIDEO_SUBDIRS=(h264 hevc)

# Detect available test files from subdirectories
echo "Scanning for video files under: $TEST_DIR" | tee -a "$RESULT_FILE"
FILES=()
for subdir in "${VIDEO_SUBDIRS[@]}"; do
	dir_path="${TEST_DIR}/${subdir}"
	if [ -d "$dir_path" ]; then
		while IFS= read -r filename; do
			[ -n "$filename" ] && FILES+=("${subdir}/${filename}")
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

# Identify decoder type from filename
get_decoder() {
	local fname
	fname=$(basename "$1" | tr '[:upper:]' '[:lower:]')
	case "$fname" in
		*avc*|*h264*) echo "h264" ;;
		*hevc*|*h265*|*x265*) echo "hevc" ;;
		*vp9*) echo "vp9" ;;
		*vp8*) echo "vp8" ;;
		*mpeg2*|*mpegps*|*vob*) echo "mpeg2video" ;;
		*mpeg4*|*divx*|*xvid*) echo "mpeg4" ;;
		*av1*) echo "av1" ;;
		*) echo "" ;;
	esac
}

THREADS=(1)
ITERATIONS=5

echo "========================================" | tee -a "$RESULT_FILE"
echo "FFmpeg Decoding Performance Test" | tee -a "$RESULT_FILE"
echo "Start time: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$RESULT_FILE"
echo "Running ${ITERATIONS} iterations per configuration and averaging" | tee -a "$RESULT_FILE"
echo "========================================" | tee -a "$RESULT_FILE"

# Check files
for file in "${FILES[@]}"; do
	[ ! -f "$TEST_DIR/$file" ] && echo "Warning: File does not exist: $TEST_DIR/$file" | tee -a "$RESULT_FILE"
done
echo "" | tee -a "$RESULT_FILE"

# Temporary directory for per-file results
RESULT_DIR=$(mktemp -d)
trap "rm -rf $RESULT_DIR" EXIT

# Extract fps from ffmpeg benchmark output
extract_fps() {
	echo "$1" | sed 's/.*fps=[ ]*//;s/ .*//'
}

is_number() {
	case "$1" in
		''|*[!0-9.]*) return 1 ;;
		*) return 0 ;;
	esac
}

# Run a single benchmark iteration
run_benchmark() {
	local file="$1"
	local threads=$2
	local decoder=$3
	local iteration=$4
	local filename=$(basename "$file")

	echo "[$(date '+%H:%M:%S')] Iteration $iteration/${ITERATIONS}: $filename (threads: $threads)" >> "$RESULT_FILE"

	# Execute benchmark
	# -nostdin is mandatory when this script is piped to bash via stdin
	# (UEP-safe invocation): otherwise ffmpeg eats the remaining script text.
	output=$(ffmpeg -nostdin -nostats -threads $threads -benchmark -c:v $decoder -i "$file" -f null - 2>&1)

	# Display last few lines
	echo "$output" | tail -4 >> "$RESULT_FILE"

	# Extract fps
	fps_line=$(echo "$output" | grep "fps=" | tail -1)
	fps=$(extract_fps "$fps_line")

	if is_number "$fps" && [ -n "$fps" ]; then
		echo "$fps"
	else
		echo "  -> Extraction failed, fps_line=[$fps_line], fps=[$fps]" >> "$RESULT_FILE"
		echo ""
	fi
}

echo "Starting test..." | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

# Set CPU governor to performance mode for consistent results
echo performance | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor 2>/dev/null || true

# Main benchmark loop
for file in "${FILES[@]}"; do
	file_path="$TEST_DIR/$file"
	[ ! -f "$file_path" ] && continue

	decoder=$(get_decoder "$file_path")
	[ -z "$decoder" ] && continue

	filename=$(basename "$file_path")

	for thread_count in "${THREADS[@]}"; do
		key="${filename}_${thread_count}threads"
		fps_sum=0
		valid_count=0
		fps_values=""

		echo "========================================" | tee -a "$RESULT_FILE"
		echo "File: $filename | Decoder: $decoder | Threads: $thread_count" | tee -a "$RESULT_FILE"
		echo "========================================" | tee -a "$RESULT_FILE"

		for i in $(seq 1 $ITERATIONS); do
			fps=$(run_benchmark "$file_path" "$thread_count" "$decoder" "$i")

			# Drop the "-gt 0" integer check: fps can be decimal (e.g. 9.1
			# for hevc), which makes bash "[ -gt ]" fail with "integer
			# expression expected". is_number already validates the value.
			if is_number "$fps"; then
				# awk float math: bash $(( )) is integer-only and aborts the
				# assignment on decimal fps (e.g. 9.1), which silently kept
				# fps_sum at 0 while valid_count still grew -> avg came out 0.
				fps_sum=$(awk "BEGIN{print $fps_sum + $fps}")
				valid_count=$((valid_count + 1))
				[ -z "$fps_values" ] && fps_values="$fps" || fps_values="$fps_values, $fps"
			fi
			echo "" | tee -a "$RESULT_FILE"
		done

		# Save results
		if [ "$valid_count" -gt 0 ]; then
			# Float average with 2 decimals (was integer division $((sum/count)),
			# which breaks on decimal fps sums). The host parser passes the
			# value through as a string, so decimals are safe end-to-end.
			avg=$(awk "BEGIN{printf \"%.2f\", $fps_sum/$valid_count}")
			echo "$avg" > "$RESULT_DIR/$key"
			echo ">>> Average FPS: $avg (valid count: $valid_count, raw: $fps_values)" | tee -a "$RESULT_FILE"
		else
			echo "FAIL" > "$RESULT_DIR/$key"
			echo ">>> All failed" | tee -a "$RESULT_FILE"
		fi
		echo "" | tee -a "$RESULT_FILE"
	done
done

# Summary report
echo "" | tee -a "$RESULT_FILE"
echo "========================================" | tee -a "$RESULT_FILE"
echo "Performance Test Summary" | tee -a "$RESULT_FILE"
echo "End time: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$RESULT_FILE"
echo "========================================" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

printf "%-35s | %-6s | %-10s\n" "File" "Threads" "Avg FPS" | tee -a "$RESULT_FILE"
echo "-----------------------------------------------" | tee -a "$RESULT_FILE"

for file in "${FILES[@]}"; do
	filename=$(basename "$file")
	for thread_count in "${THREADS[@]}"; do
		key="${filename}_${thread_count}threads"
		result_file="$RESULT_DIR/$key"
		fps="N/A"
		[ -f "$result_file" ] && val=$(cat "$result_file") && [ "$val" != "FAIL" ] && fps="$val"
		printf "%-35s | %-6s | %-10s\n" "$filename" "$thread_count" "$fps" | tee -a "$RESULT_FILE"
	done
done

echo "" | tee -a "$RESULT_FILE"
echo "Results saved to: $RESULT_FILE"

echo "end $test_name"
test_exit 0
