#!/bin/bash

# kernelbench.sh — Linux kernel performance benchmark (device-side)
#
# Usage: kernelbench.sh TEST_DIR RESULT_FILE
#   TEST_DIR     - directory on device containing benchmark RPMs and binaries
#   RESULT_FILE  - absolute path to the output result file
#
# This script is part of the TPMS kernel_benchmark_test.
# It installs benchmark RPM packages, runs a comprehensive suite of kernel-level
# benchmarks (tinymembench, schbench, ipc-benchmark, hackbench, whetstone,
# dhrystone, coremark_multi, coremark_single), and writes a summary to RESULT_FILE.

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

# Script directory (where runner scripts are located)
# Under UEP-safe pipe invocation $0 is "bash", so fall back to the
# caller-provided TPMS_SCRIPT_DIR (the directory this script lives in).
SCRIPT_DIR="${TPMS_SCRIPT_DIR:-$(cd "$(dirname "$0")" && pwd)}"

echo "========================================" | tee -a "$RESULT_FILE"
echo "Kernel Performance Benchmark Test" | tee -a "$RESULT_FILE"
echo "Start time: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$RESULT_FILE"
echo "========================================" | tee -a "$RESULT_FILE"

# ---------------------------------------------------------------------------
# Step 1: Install benchmark RPM packages from TEST_DIR
# ---------------------------------------------------------------------------
echo "" | tee -a "$RESULT_FILE"
echo "--- Installing benchmark RPM packages ---" | tee -a "$RESULT_FILE"

RPM_PACKAGES=(
	"hackbench"
	"ipc-benchmark"
	"schbench"
	"tinymembench"
)

for pkg in "${RPM_PACKAGES[@]}"; do
	rpm_file=$(ls "${TEST_DIR}/${pkg}"-*.rpm 2>/dev/null | head -1)
	if [ -n "$rpm_file" ]; then
		echo "Installing $rpm_file ..." | tee -a "$RESULT_FILE"
		rpm -ivh --force --nodeps "$rpm_file" 2>&1 | tee -a "$RESULT_FILE"
	else
		echo "Warning: RPM for $pkg not found in $TEST_DIR" | tee -a "$RESULT_FILE"
	fi
done

# Also install debuginfo/debugsource if present (not required but harmless)
for rpm_file in "${TEST_DIR}"/*-debuginfo-*.rpm "${TEST_DIR}"/*-debugsource-*.rpm; do
	[ -f "$rpm_file" ] && rpm -ivh --force --nodeps "$rpm_file" 2>/dev/null
done

echo "RPM installation complete." | tee -a "$RESULT_FILE"

# ---------------------------------------------------------------------------
# Step 2: Copy benchmark binaries to a working directory
# ---------------------------------------------------------------------------
WORK_DIR="/opt/usr/tpms/kernel_bench"
mkdir -p "$WORK_DIR"

BENCHMARK_BINARIES=(whetstone dhrystone coremark_multi coremark_single)
for bin in "${BENCHMARK_BINARIES[@]}"; do
	if [ -f "${TEST_DIR}/${bin}" ]; then
		cp "${TEST_DIR}/${bin}" "${WORK_DIR}/"
		chmod 777 "${WORK_DIR}/${bin}"
		echo "Copied ${bin} to ${WORK_DIR}" | tee -a "$RESULT_FILE"
	else
		echo "Warning: ${bin} not found in ${TEST_DIR}" | tee -a "$RESULT_FILE"
	fi
done

# Copy runner scripts to work dir
RUNNER_SCRIPTS=(tinymembench-run.sh schbench-run.sh ipc-benchmark-run.sh hackbench-run.sh)
for script in "${RUNNER_SCRIPTS[@]}"; do
	if [ -f "${SCRIPT_DIR}/${script}" ]; then
		cp "${SCRIPT_DIR}/${script}" "${WORK_DIR}/"
		chmod 777 "${WORK_DIR}/${script}"
	fi
done

# ---------------------------------------------------------------------------
# Step 3: Set CPU governor to performance mode
# ---------------------------------------------------------------------------
echo "" | tee -a "$RESULT_FILE"
echo "Setting CPU governor to performance mode..." | tee -a "$RESULT_FILE"
echo performance | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor 2>/dev/null || true

# ---------------------------------------------------------------------------
# Step 4: Run benchmarks
# ---------------------------------------------------------------------------
echo "" | tee -a "$RESULT_FILE"
echo "========================================" | tee -a "$RESULT_FILE"
echo "Running Benchmarks" | tee -a "$RESULT_FILE"
echo "========================================" | tee -a "$RESULT_FILE"

# --- tinymembench ---
echo "" | tee -a "$RESULT_FILE"
echo "=== tinymembench ===" | tee -a "$RESULT_FILE"
echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true
sync
cd "$WORK_DIR"
cat tinymembench-run.sh | bash -s -- 1 2>&1 | tee -a "$RESULT_FILE"

# --- schbench (4 configurations) ---
echo "" | tee -a "$RESULT_FILE"
echo "=== schbench ===" | tee -a "$RESULT_FILE"
echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true
sync

echo "--- schbench -i 1 -m 4 -F 128 --no-locking ---" | tee -a "$RESULT_FILE"
cat schbench-run.sh | bash -s -- -i 1 -m 4 -F 128 --no-locking 2>&1 | tee -a "$RESULT_FILE"

echo "--- schbench -i 1 -m 4 -F 256 --no-locking ---" | tee -a "$RESULT_FILE"
cat schbench-run.sh | bash -s -- -i 1 -m 4 -F 256 --no-locking 2>&1 | tee -a "$RESULT_FILE"

echo "--- schbench -i 1 -m 4 -F 128 ---" | tee -a "$RESULT_FILE"
cat schbench-run.sh | bash -s -- -i 1 -m 4 -F 128 2>&1 | tee -a "$RESULT_FILE"

echo "--- schbench -i 1 -m 4 -F 256 ---" | tee -a "$RESULT_FILE"
cat schbench-run.sh | bash -s -- -i 1 -m 4 -F 256 2>&1 | tee -a "$RESULT_FILE"

# --- ipc-benchmark ---
echo "" | tee -a "$RESULT_FILE"
echo "=== ipc-benchmark ===" | tee -a "$RESULT_FILE"
echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true
sync
cat ipc-benchmark-run.sh | bash -s -- -i 1 -c 1000000 2>&1 | tee -a "$RESULT_FILE"

# --- hackbench ---
echo "" | tee -a "$RESULT_FILE"
echo "=== hackbench ===" | tee -a "$RESULT_FILE"
echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true
sync
cat hackbench-run.sh | bash -s -- -i 1 -l 5000 2>&1 | tee -a "$RESULT_FILE"

# --- whetstone ---
echo "" | tee -a "$RESULT_FILE"
echo "=== whetstone ===" | tee -a "$RESULT_FILE"
echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true
sync
"$WORK_DIR/whetstone" 2>&1 | tee -a "$RESULT_FILE"

# --- dhrystone ---
echo "" | tee -a "$RESULT_FILE"
echo "=== dhrystone ===" | tee -a "$RESULT_FILE"
echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true
sync
echo '' | "$WORK_DIR/dhrystone" 2>&1 | tee -a "$RESULT_FILE"

# --- coremark_multi ---
echo "" | tee -a "$RESULT_FILE"
echo "=== coremark_multi ===" | tee -a "$RESULT_FILE"
echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true
sync
"$WORK_DIR/coremark_multi" 2>&1 | tee -a "$RESULT_FILE"

# --- coremark_single ---
echo "" | tee -a "$RESULT_FILE"
echo "=== coremark_single ===" | tee -a "$RESULT_FILE"
echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true
sync
"$WORK_DIR/coremark_single" 2>&1 | tee -a "$RESULT_FILE"

# ---------------------------------------------------------------------------
# Step 5: Summary
# ---------------------------------------------------------------------------
echo "" | tee -a "$RESULT_FILE"
echo "========================================" | tee -a "$RESULT_FILE"
echo "Kernel Benchmark Test Complete" | tee -a "$RESULT_FILE"
echo "End time: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$RESULT_FILE"
echo "========================================" | tee -a "$RESULT_FILE"

# Cleanup
rm -rf "$WORK_DIR"

echo "end $test_name"
test_exit 0
