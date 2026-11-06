#!/bin/bash

# tflitebench.sh — TensorFlow Lite model inference benchmark (device-side)
#
# Usage: tflitebench.sh MODEL_DIR RESULT_FILE
#   MODEL_DIR    - directory on device containing .tflite model files
#   RESULT_FILE  - absolute path to the output result file
#
# This script is part of the TPMS tflite_benchmark_test.
# It scans MODEL_DIR for .tflite files, runs tflite_benchmark_model
# for each model, and writes a summary table (including per-model
# average inference time in microseconds) to RESULT_FILE.

echo -e '\033[34m' ' '

function test_exit {
	echo -e '\033[0m' ' '
	exit $1
}

file_name=${0##*/}
test_name=${file_name%%\.*}

function usage {
	echo "usage: $file_name MODEL_DIR RESULT_FILE"
}

echo "start $test_name"

if [ $# -lt 2 ]; then
	usage
	echo "not enough argument" 1>&2
	test_exit -1
fi

MODEL_DIR="$1"
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

if [ ! -d "$MODEL_DIR" ]; then
	echo "Error: MODEL_DIR does not exist: $MODEL_DIR" | tee -a "$RESULT_FILE"
	test_exit -1
fi

# Find tflite_benchmark_model binary
TFLITE_BIN=$(which tflite_benchmark_model 2>/dev/null || find / -name tflite_benchmark_model -type f 2>/dev/null | head -1)
if [ -z "$TFLITE_BIN" ]; then
	echo "Error: tflite_benchmark_model not found on device" | tee -a "$RESULT_FILE"
	test_exit -1
fi

echo "Using tflite_benchmark_model: $TFLITE_BIN" | tee -a "$RESULT_FILE"

# Detect available model files
echo "Scanning for .tflite files under: $MODEL_DIR" | tee -a "$RESULT_FILE"
FILES=()
while IFS= read -r filename; do
	[ -n "$filename" ] && FILES+=("$filename")
done < <(ls -1 "$MODEL_DIR"/*.tflite 2>/dev/null)

if [ ${#FILES[@]} -eq 0 ]; then
	echo "Error: No .tflite files found under $MODEL_DIR" | tee -a "$RESULT_FILE"
	test_exit -1
fi

echo "Detected ${#FILES[@]} models:" | tee -a "$RESULT_FILE"
for f in "${FILES[@]}"; do
	echo "  - $(basename "$f")" | tee -a "$RESULT_FILE"
done

# Benchmark parameters
WARMUP_RUNS=5
NUM_RUNS=50
MIN_SECS=50
NUM_THREADS=1

echo "========================================" | tee -a "$RESULT_FILE"
echo "TensorFlow Lite Inference Benchmark" | tee -a "$RESULT_FILE"
echo "Start time: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$RESULT_FILE"
echo "Parameters: warmup_runs=$WARMUP_RUNS, num_runs=$NUM_RUNS, min_secs=$MIN_SECS, num_threads=$NUM_THREADS" | tee -a "$RESULT_FILE"
echo "========================================" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

# Set CPU governor to performance mode for consistent results
echo performance | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor 2>/dev/null || true

# Temporary directory for per-model results
RESULT_DIR=$(mktemp -d)
trap "rm -rf $RESULT_DIR" EXIT

# Main benchmark loop
for model in "${FILES[@]}"; do
	model_name=$(basename "$model")

	echo "========================================" | tee -a "$RESULT_FILE"
	echo "Model: $model_name" | tee -a "$RESULT_FILE"
	echo "========================================" | tee -a "$RESULT_FILE"

	# Run benchmark
	output=$($TFLITE_BIN --warmup_runs=$WARMUP_RUNS --num_runs=$NUM_RUNS --min_secs=$MIN_SECS --num_threads=$NUM_THREADS --graph="$model" 2>&1)

	# Display last few lines
	echo "$output" | tail -5 >> "$RESULT_FILE"

	# Extract Inference (avg) value
	# Line looks like: Inference timings in us: Init: ..., First inference: ..., Warmup (avg): ..., Inference (avg): 2.59591e+06
	inference_line=$(echo "$output" | grep "Inference timings in us" || true)

	if [ -n "$inference_line" ]; then
		inference_avg=$(echo "$inference_line" | sed 's/.*Inference (avg): //' | sed 's/[^0-9.eE+-].*//')

		# Convert scientific notation to plain number
		inference_plain=$(awk -v val="$inference_avg" 'BEGIN {
			if (val ~ /[eE]/) {
				printf "%.0f\n", val
			} else {
				printf "%.0f\n", val
			}
		}')

		echo "$inference_plain" > "$RESULT_DIR/$model_name"
		echo ">>> Inference (avg): $inference_plain us" | tee -a "$RESULT_FILE"
	else
		echo "0" > "$RESULT_DIR/$model_name"
		echo ">>> Failed to extract inference time" | tee -a "$RESULT_FILE"
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

printf "%-40s | %-20s\n" "Model" "Inference Avg (us)" | tee -a "$RESULT_FILE"
echo "------------------------------------------------------------" | tee -a "$RESULT_FILE"

for model in "${FILES[@]}"; do
	model_name=$(basename "$model")
	result_file="$RESULT_DIR/$model_name"
	inference="N/A"
	[ -f "$result_file" ] && val=$(cat "$result_file") && [ "$val" != "0" ] && inference="$val"
	printf "%-40s | %-20s\n" "$model_name" "$inference" | tee -a "$RESULT_FILE"
done

echo "" | tee -a "$RESULT_FILE"
echo "Results saved to: $RESULT_FILE"

echo "end $test_name"
test_exit 0
