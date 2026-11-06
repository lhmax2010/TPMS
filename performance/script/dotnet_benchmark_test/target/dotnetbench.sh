#!/bin/bash

# dotnetbench.sh — .NET MicroBenchmarks performance benchmark (device-side)
#
# Usage: dotnetbench.sh BENCH_DIR RESULT_FILE
#   BENCH_DIR    - directory on device where MicroBenchmarks.dll is located
#   RESULT_FILE  - absolute path to the output result file
#
# This script is part of the TPMS dotnet_benchmark_test.
# It runs `dotnet MicroBenchmarks.dll` for a set of predefined benchmark cases
# (each with a --filter expression), captures the BenchmarkDotNet output, and
# writes a summary table (Case | Method | Mean) to RESULT_FILE.
#
# Note: Lower Mean values indicate faster performance.

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
	echo "usage: $file_name BENCH_DIR RESULT_FILE"
}

echo "start $test_name"

if [ $# -lt 2 ]; then
	usage
	echo "not enough argument" 1>&2
	test_exit -1
fi

BENCH_DIR="$1"
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

if [ ! -d "$BENCH_DIR" ]; then
	echo "Error: BENCH_DIR does not exist: $BENCH_DIR" | tee -a "$RESULT_FILE"
	test_exit -1
fi

if [ ! -f "${BENCH_DIR}/MicroBenchmarks.dll" ]; then
	echo "Error: MicroBenchmarks.dll not found at ${BENCH_DIR}" | tee -a "$RESULT_FILE"
	test_exit -1
fi

# Benchmark case definitions: "CaseName|filter_expression"
BENCH_CASES=(
	"Sin|System.MathBenchmarks.Single.Sin"
	"SinCos|System.MathBenchmarks.Single.SinCos"
	"Exp|System.MathBenchmarks.Single.Exp"
	"Pow|System.MathBenchmarks.Single.Pow"
	"DivRemInt32|System.MathBenchmarks.MathTests.DivRemInt32"
	"Span_Fill|System.Memory.Span<Byte>.Fill"
	"Span_CopyTo|System.Memory.Span<Byte>.CopyTo"
	"Span_IndexOfValue|System.Memory.Span<Byte>.IndexOfValue"
	"TryParseDouble|System.Buffers.Text.Tests.Utf8ParserTests.TryParseDouble"
	"Int32_Parse|System.Tests.Perf_Int32.Parse"
	"PopCount|System.Numerics.Tests.Perf_BitOperations.PopCount_uint"
	"LeadingZeroCount|System.Numerics.Tests.Perf_BitOperations.LeadingZeroCount_uint"
	"Vector128_Add|System.Runtime.Intrinsics.Tests.Perf_Vector128Float.AddBenchmark"
	"Vector128_Sqrt|System.Runtime.Intrinsics.Tests.Perf_Vector128Float.SquareRootBenchmark"
	"String_Concat|System.Tests.Perf_String.Concat_str_str"
	"Array_Reverse|System.Tests.Perf_Array.Reverse"
	"Interlocked_Increment|System.Threading.Tests.Perf_Interlocked.Increment_int"
)

echo "========================================" | tee -a "$RESULT_FILE"
echo ".NET MicroBenchmarks Performance Test" | tee -a "$RESULT_FILE"
echo "Start time: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$RESULT_FILE"
echo "Bench dir: $BENCH_DIR" | tee -a "$RESULT_FILE"
echo "========================================" | tee -a "$RESULT_FILE"

# Set CPU governor to performance mode for consistent results
echo "Setting CPU governor to performance mode..." | tee -a "$RESULT_FILE"
echo performance | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor 2>/dev/null || true

TMP_RAW=$(mktemp)
trap "rm -f $TMP_RAW" EXIT

cd "$BENCH_DIR" || test_exit -1

total_cases=${#BENCH_CASES[@]}
current=0

for entry in "${BENCH_CASES[@]}"; do
	current=$((current + 1))
	case_name="${entry%%|*}"
	filter_expr="${entry#*|}"

	echo "" | tee -a "$RESULT_FILE"
	echo "========================================" | tee -a "$RESULT_FILE"
	echo "[$current/$total_cases] Running: $case_name" | tee -a "$RESULT_FILE"
	echo "  filter: $filter_expr" | tee -a "$RESULT_FILE"
	echo "========================================" | tee -a "$RESULT_FILE"

	# Run the benchmark, capture output
	DOTNET_PerfMapEnabled=1 dotnet MicroBenchmarks.dll --filter "${filter_expr}" -i > "$TMP_RAW" 2>&1 || {
		echo "  WARNING: Benchmark '$case_name' returned non-zero status" | tee -a "$RESULT_FILE"
	}

	# Dump raw output for reference
	cat "$TMP_RAW" >> "$RESULT_FILE"

	# Parse the BenchmarkDotNet output table.
	# Strip ANSI color codes first, then awk finds the "Method", "value"
	# (the benchmark parameter, if present) and "Mean" columns in the
	# pipe-delimited table and emits "Case|Method|value|Mean" lines.
	# The "value" column keeps multi-parameter cases (e.g. Int32.Parse with
	# value=-2147483648 / 12345 / 2147483647 / 4) as distinct rows.
	sed 's/\x1b\[[0-9;]*m//g' "$TMP_RAW" | awk -v casename="$case_name" '
	BEGIN { in_table = 0; mean_col = 0; method_col = 0; value_col = 0 }
	/\| *Method/ {
		in_table = 1
		n = split($0, cols, "|")
		for (i = 1; i <= n; i++) {
			gsub(/^ +| +$/, "", cols[i])
			if (cols[i] == "Method") method_col = i
			if (cols[i] == "value")  value_col = i
			if (cols[i] == "Mean")   mean_col = i
		}
		next
	}
	in_table && /^\|[- ]+\|/ { next }
	in_table && /^\|/ {
		n = split($0, fields, "|")
		if (method_col > 0 && mean_col > 0 && method_col <= n && mean_col <= n) {
			method_val = fields[method_col]
			mean_val = fields[mean_col]
			gsub(/^ +| +$/, "", method_val)
			gsub(/^ +| +$/, "", mean_val)
			value_val = ""
			if (value_col > 0 && value_col <= n) {
				value_val = fields[value_col]
				gsub(/^ +| +$/, "", value_val)
			}
			if (method_val != "" && mean_val != "") {
				printf "%s|%s|%s|%s\n", casename, method_val, value_val, mean_val
			}
		}
		next
	}
	in_table && !/^\|/ { in_table = 0 }
	' >> "${RESULT_FILE}.parsed"

	echo "  Done: $case_name" | tee -a "$RESULT_FILE"
done

# Summary report
echo "" | tee -a "$RESULT_FILE"
echo "========================================" | tee -a "$RESULT_FILE"
echo "Performance Test Summary" | tee -a "$RESULT_FILE"
echo "End time: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$RESULT_FILE"
echo "========================================" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

printf "%-25s | %-25s | %-15s | %-15s\n" "Case" "Method" "value" "Mean" | tee -a "$RESULT_FILE"
echo "--------------------------------------------------------------------------------" | tee -a "$RESULT_FILE"

if [ -f "${RESULT_FILE}.parsed" ]; then
	while IFS='|' read -r cname mname vname mval; do
		printf "%-25s | %-25s | %-15s | %-15s\n" "$cname" "$mname" "$vname" "$mval" | tee -a "$RESULT_FILE"
	done < "${RESULT_FILE}.parsed"
	rm -f "${RESULT_FILE}.parsed"
fi

echo "" | tee -a "$RESULT_FILE"
echo "Results saved to: $RESULT_FILE"

echo "end $test_name"
test_exit 0
