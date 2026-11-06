#!/bin/bash
# Schbench runner script
# Linux kernel scheduler latency benchmark
# Lower latency = better performance

# Default values
ITERATIONS=3
RUNTIME=30
MSG_THREADS=
CACHE_FOOTPRINT=
EXTRA_ARGS=""

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -i N       Number of iterations (default: 3)"
    echo "  -r N       Runtime in seconds (default: 30)"
    echo "  -m N       Message threads (default: auto)"
    echo "  -F N       Cache footprint in KB (128 or 256)"
    echo "  --no-locking  Disable locking"
    echo "  -h         Show this help"
    echo ""
    echo "Examples:"
    echo "  $0                     # Default run"
    echo "  $0 -m 4 -r 60          # 4 threads, 60 seconds"
}

while [ $# -gt 0 ]; do
    case "$1" in
        -i) ITERATIONS=$2; shift 2 ;;
        -r) RUNTIME=$2; shift 2 ;;
        -m) MSG_THREADS=$2; shift 2 ;;
        -F) CACHE_FOOTPRINT=$2; shift 2 ;;
        --no-locking) EXTRA_ARGS="$EXTRA_ARGS --no-locking"; shift ;;
        -h) usage; exit 0 ;;
        *) echo "Unknown option: $1"; usage; exit 1 ;;
    esac
done

# Build command
CMD="schbench -r $RUNTIME"
[ -n "$MSG_THREADS" ] && CMD="$CMD -m $MSG_THREADS"
[ -n "$CACHE_FOOTPRINT" ] && CMD="$CMD -F $CACHE_FOOTPRINT"
[ -n "$EXTRA_ARGS" ] && CMD="$CMD $EXTRA_ARGS"

echo "=========================================="
echo "Schbench - Scheduler Latency Benchmark"
echo "Iterations: $ITERATIONS"
echo "Runtime: ${RUNTIME}s"
echo "Command: $CMD"
echo "=========================================="

for i in $(seq 1 $ITERATIONS); do
    echo ""
    echo "--- Run $i/$ITERATIONS ---"
    $CMD
done

echo ""
echo "=========================================="
echo "All runs completed"
echo "=========================================="
