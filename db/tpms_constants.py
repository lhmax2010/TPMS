#!/usr/bin/env python3
"""
TPMS constants and helper functions.

Shared across all TPMS web/db modules.
"""

# Key metrics to show in summary
KEY_METRICS = [
    'BootingTime', 'IdleMemoryUsage', 'NANDUsage',
    'AppLaunchingTime', 'WebAppLaunchingTime', 'Dali3DUI',
    'RootFS Size',
]

# Metrics where lower is better (for regression detection)
LOWER_IS_BETTER = {
    'BootingTime', 'IdleMemoryUsage', 'AppLaunchingTime',
    'WebAppLaunchingTime', 'NANDUsage',
    'executiontime', 'RootFS Size', 'DotNet',
}

# Metrics where higher is better (exact metric-name match)
HIGHER_IS_BETTER = {
    'Dali3DUI', 'GLBench', 'FFmpeg', 'GStreamer', 'TFLite', 'Kernel',
}

# Sub-metric prefixes matched with str.startswith().
#
# Many benchmarks report one entry per sub-test, so the stored metric names
# look like "<Category> - <sub-test>", e.g.
#   "FFmpeg - h264_1000frames_1080p.mp4 (1threads)"   (decode fps)
#   "GStreamer - h264_1000frames_4k.mp4"              (decode fps)
#   "GLBench - <scene>"                               (fps)
#   "Kernel - hackbench_hackbench_thread_4"           (Time, seconds)
#   "Kernel - coremark_single_iterations_per_sec"     (Iterations/Sec)
# The bare names in HIGHER_IS_BETTER never equal these full names, so
# direction is resolved by prefix matching:
#   - higher is better: FFmpeg / GStreamer / GLBench (decode/render fps —
#     higher frame rate is better), Kernel tinymembench (MB/s), schbench
#     (rps), ipc-benchmark (msg/s), whetstone (MIPS), dhrystone, coremark
#   - lower  is better: TFLite (inference latency, us), DotNet (benchmark
#     timing, us/ns), Kernel hackbench (Time, seconds — execution time)
LOWER_IS_BETTER_PREFIXES = (
    'TFLite - ',
    'DotNet - ',
    'Kernel - hackbench',
)


HIGHER_IS_BETTER_PREFIXES = (
    'FFmpeg - ',
    'GStreamer - ',
    'GLBench - ',
    'Kernel - tinymembench',
    'Kernel - schbench',
    'Kernel - ipc-benchmark',
    'Kernel - whetstone',
    'Kernel - dhrystone',
    'Kernel - coremark',
)



REGRESSION_THRESHOLD = 0.10  # 10%
REGRESSION_HISTORY_SIZE = 10
REGRESSION_MIN_ABSOLUTE_CHANGE = 0.01
REGRESSION_MAD_MULTIPLIER = 3.0

# Sort order for test names in detailed tables
SORT_ORDER = [
    'Booting Time',
    'Idle Memory Usage',
    'NAND Usage',
    'RootFS Size',
    'App Launching Time',
    'AppLaunching_main',
    'AppLaunching_create',
    'AppLaunching_reset',
    'AppLaunching_launching',
    'Web App Launching Time',
    'WebAppLaunching_main',
    'WebAppLaunching_create',
    'WebAppLaunching_reset',
    'WebAppLaunching_rendering',
    'WebAppLaunching_launching',
    '3D UI Dali',
    'GLBench',
    'FFmpeg',
    'GStreamer',
    'TFLite',
    'Kernel',
    'DotNet',
]



def get_sort_key(test_name):
    """Get sort priority for a test name. Lower = earlier in table."""
    for i, pattern in enumerate(SORT_ORDER):
        if test_name.startswith(pattern):
            return i
    return len(SORT_ORDER)


def is_memory_detail(test_name):
    """Check if test name is memory detail (MEMPS, MEMINFO, MEM_USED)."""
    return (test_name.startswith('MEMPS') or
            test_name.startswith('MEMINFO') or
            test_name.startswith('MEM_USED'))


def is_sub_test(test_name):
    """Check if test name is a sub-test (should be indented)."""
    return (test_name.startswith('AppLaunching_') or
            test_name.startswith('WebAppLaunching_'))


def is_lower_is_better(metric_name):
    """Check if lower values are better for this metric.

    Memory metrics (MEMPS, MEMINFO, MEM_USED) are also lower-is-better.
    Sub-metric prefixes in LOWER_IS_BETTER_PREFIXES (e.g. Kernel hackbench
    time) override the broad higher-is-better category direction.
    """
    for prefix in LOWER_IS_BETTER_PREFIXES:
        if metric_name.startswith(prefix):
            return True
    if metric_name in LOWER_IS_BETTER:
        return True
    if (metric_name.startswith('MEMPS') or
            metric_name.startswith('MEMINFO') or
            metric_name.startswith('MEM_USED')):
        return True
    return False


def is_higher_is_better(metric_name):
    """Check if higher values are better for this metric.

    Matches the broad HIGHER_IS_BETTER set (exact) or the
    HIGHER_IS_BETTER_PREFIXES (prefix, for Kernel sub-benchmarks).
    """
    if metric_name in HIGHER_IS_BETTER:
        return True
    for prefix in HIGHER_IS_BETTER_PREFIXES:
        if metric_name.startswith(prefix):
            return True
    return False


def is_regression(metric_name, curr, prev):
    if curr is None or prev is None or prev == 0:
        return False
    pct = (curr - prev) / abs(prev)
    if is_lower_is_better(metric_name):
        return pct > REGRESSION_THRESHOLD
    elif is_higher_is_better(metric_name):
        return pct < -REGRESSION_THRESHOLD
    return abs(pct) >= REGRESSION_THRESHOLD


def evaluate_regression(metric_name, current, history):
    """Classify a value against recent valid history.

    The old fixed 10% rule is retained as a minimum signal, but the reference
    is now the median of recent successful samples.  MAD makes the decision
    resistant to a single noisy build.  Callers must pass only rows from
    executed, passing, non-timeout tests; missing/failed data is a warning,
    not a performance regression.
    """
    valid = [float(value) for value in history if value is not None]
    if current is None or len(valid) < 3:
        return {'regression': False, 'improved': False, 'reason': 'insufficient_history'}

    ordered = sorted(valid)
    middle = len(ordered) // 2
    baseline = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
    if baseline == 0:
        return {'regression': False, 'improved': False, 'reason': 'zero_baseline'}

    deviations = sorted(abs(value - baseline) for value in valid)
    middle = len(deviations) // 2
    mad = deviations[middle] if len(deviations) % 2 else (deviations[middle - 1] + deviations[middle]) / 2
    delta = float(current) - baseline
    relative_change = abs(delta) / abs(baseline)
    absolute_floor = max(REGRESSION_MIN_ABSOLUTE_CHANGE, mad * REGRESSION_MAD_MULTIPLIER)
    meaningful = relative_change >= REGRESSION_THRESHOLD and abs(delta) >= absolute_floor
    lower_is_better = is_lower_is_better(metric_name)
    direction = -1 if lower_is_better else 1
    return {
        'regression': bool(meaningful and delta * direction < 0),
        'improved': bool(meaningful and delta * direction > 0),
        'reason': 'median_mad',
        'baseline': baseline,
        'mad': mad,
        'sample_count': len(valid),
    }


def fmt_val(val, unit=''):
    if val is None:
        return 'N/A'
    if unit == 's' and val < 10:
        return '{:.3f} {}'.format(val, unit)
    elif unit in ('MB', 'KB', 'GB'):
        return '{:.2f} {}'.format(val, unit)
    elif unit == 'fps':
        return '{:.1f} {}'.format(val, unit)
    return '{:.2f} {}'.format(val, unit) if unit else '{:.2f}'.format(val)


def filter_and_sort_metrics(all_metrics):
    """Filter separator rows and sort into performance + memory sections.

    Returns (perf_metrics, mem_metrics) lists.
    """
    filtered = []
    for m in all_metrics:
        tn = m['test_name']
        val = m['metric_value']
        if '====' in tn and val is not None and val <= -9999:
            continue
        filtered.append(m)

    perf = [m for m in filtered if not is_memory_detail(m['test_name'])]
    mem = [m for m in filtered if is_memory_detail(m['test_name'])]

    perf.sort(key=lambda m: (get_sort_key(m['test_name']), m['test_name']))
    mem.sort(key=lambda m: m['test_name'])

    return perf, mem
