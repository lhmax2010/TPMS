#!/bin/bash
# ipc-benchmark runner
# IPC performance benchmark suite
# Higher throughput = better performance

ITERATIONS=1
MESSAGE_COUNT=9000000

# Message sizes matching PTS (Phoronix Test Suite)
MESSAGE_SIZES=(512 2048)

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -i N    Number of iterations (default: 3)"
    echo "  -c N    Message count (default: 9000000)"
    echo "  -h      Show this help"
    echo ""
    echo "Runs each IPC method with 512 and 2048 byte messages (matching PTS)"
}

while getopts "i:c:h" opt; do
    case $opt in
        i) ITERATIONS=$OPTARG ;;
        c) MESSAGE_COUNT=$OPTARG ;;
        h) usage; exit 0 ;;
        *) usage; exit 1 ;;
    esac
done

# IPC methods and their PTS display names
ipc_name() {
    case "$1" in
        ipc-pipe)       echo "Unnamed Pipe" ;;
        ipc-fifo)       echo "FIFO Named Pipe" ;;
        ipc-socketpair) echo "Unnamed Unix Domain Socket" ;;
        ipc-tcp)        echo "TCP Socket" ;;
        *)              echo "$1" ;;
    esac
}

IPC_METHODS=("ipc-pipe" "ipc-fifo" "ipc-socketpair" "ipc-tcp")

echo "=========================================="
echo "ipc-benchmark - IPC Performance Benchmark"
echo "Message count: $MESSAGE_COUNT"
echo "Message sizes: ${MESSAGE_SIZES[*]} bytes"
echo "Iterations: $ITERATIONS"
echo "=========================================="

for i in $(seq 1 $ITERATIONS); do
    echo ""
    echo "==================== Run $i/$ITERATIONS ===================="

    for method in "${IPC_METHODS[@]}"; do
        if ! command -v "$method" &>/dev/null; then
            echo "Warning: $method not found"
            continue
        fi

        for size in "${MESSAGE_SIZES[@]}"; do
            echo 3 > /proc/sys/vm/drop_caches
            sleep 1
            name=$(ipc_name "$method")
            echo "--- $name $size ---"
            "$method" "$size" "$MESSAGE_COUNT" 2>&1
        done
    done
done

echo ""
echo "=========================================="
echo "Benchmark completed"
echo "=========================================="
