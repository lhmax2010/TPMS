#!/bin/bash
# Hackbench runner script
# Linux kernel scheduler benchmark (PTS compatible)
# Lower time = better performance

ITERATIONS=1
LOOPS=50000

# Group counts and types matching PTS
MYGROUPS=(4 8 16)
TYPES=(thread process)

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -i N       Number of iterations (default: 3)"
    echo "  -l N       Loops per group (default: 50000)"
    echo "  -g N       Run single group count only"
    echo "  -t TYPE    Run single type only (thread or process)"
    echo "  -h         Show this help"
    echo ""
    echo "Default: runs all PTS combinations (Thread/Process × 4/8/16 groups)"
    echo ""
    echo "Examples:"
    echo "  $0                        # Full PTS matrix"
    echo "  $0 -g 4 -t thread         # Single test: Thread 4"
    echo "  $0 -i 5 -l 100000         # Full matrix, 5 iterations, 100000 loops"
}

SINGLE_GROUP=""
SINGLE_TYPE=""

while getopts "i:g:t:l:h" opt; do
    case $opt in
        i) ITERATIONS=$OPTARG ;;
        g) SINGLE_GROUP=$OPTARG ;;
        t) SINGLE_TYPE=$OPTARG ;;
        l) LOOPS=$OPTARG ;;
        h) usage; exit 0 ;;
        *) usage; exit 1 ;;
    esac
done

# If single group/type specified, override arrays
if [ -n "$SINGLE_GROUP" ]; then
    GROUPS=("$SINGLE_GROUP")
fi
if [ -n "$SINGLE_TYPE" ]; then
    TYPES=("$SINGLE_TYPE")
fi

echo "=========================================="
echo "Hackbench - Scheduler Benchmark"
echo "Iterations: $ITERATIONS"
echo "Loops: $LOOPS"
echo "Groups: ${MYGROUPS[*]}"
echo "Types: ${TYPES[*]}"
echo "=========================================="

for i in $(seq 1 $ITERATIONS); do
    echo ""
    echo "==================== Run $i/$ITERATIONS ===================="
    echo 3 > /proc/sys/vm/drop_caches
    sleep 1

    for type in "${TYPES[@]}"; do
        for grp in "${MYGROUPS[@]}"; do
            echo ""
            hackbench -g "$grp" --"$type" -l "$LOOPS"
        done
    done
done

echo ""
echo "=========================================="
echo "All runs completed"
echo "=========================================="
