#!/bin/bash
# Tinymembench runner script
# Memory bandwidth benchmark
# Higher MB/s = better performance

ITERATIONS=${1:-1}

echo "=========================================="
echo "Tinymembench - Memory Benchmark"
echo "Iterations: $ITERATIONS"
echo "=========================================="

echo 3 > /proc/sys/vm/drop_caches

for i in $(seq 1 $ITERATIONS); do
    echo ""
    echo "--- Run $i/$ITERATIONS ---"
    tinymembench
done

echo ""
echo "=========================================="
echo "All runs completed"
echo "=========================================="
