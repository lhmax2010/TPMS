#!/usr/bin/env python3
"""
TPMS database query functions.

All DB read operations used by the web server and report generators.
"""

import json
import math
import sqlite3

from tpms_constants import (
    KEY_METRICS, LOWER_IS_BETTER, HIGHER_IS_BETTER,
    LOWER_IS_BETTER_PREFIXES, HIGHER_IS_BETTER_PREFIXES, REGRESSION_THRESHOLD,
    is_lower_is_better, is_higher_is_better, is_regression, fmt_val,
    get_sort_key, is_memory_detail, is_sub_test,
    filter_and_sort_metrics, evaluate_regression, REGRESSION_HISTORY_SIZE,
)



def get_db_conn(db_path, read_only=True):
    if read_only:
        conn = sqlite3.connect('file:{}?mode=ro'.format(db_path), uri=True)
    else:
        conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Basic query functions
# ---------------------------------------------------------------------------

def get_build_metrics(conn, job, build):
    cur = conn.execute(
        """SELECT metric_name, metric_value, metric_unit, test_name,
                  is_relevant, executed, passed, has_timed_out
           FROM performance_data
           WHERE job_name=? AND build_number=?
           ORDER BY metric_name, test_name""",
        (job, build)
    )
    return [dict(row) for row in cur.fetchall()]


def get_build_info(conn, job, build):
    cur = conn.execute(
        """SELECT DISTINCT build_id, test_time
           FROM performance_data
           WHERE job_name=? AND build_number=? LIMIT 1""",
        (job, build)
    )
    row = cur.fetchone()
    if row:
        return dict(row)
    return {'build_id': None, 'test_time': None}


def get_previous_build(conn, job, build):
    cur = conn.execute(
        """SELECT DISTINCT build_number FROM performance_data
           WHERE job_name=? AND build_number<?
           ORDER BY build_number DESC LIMIT 1""",
        (job, build)
    )
    row = cur.fetchone()
    return row[0] if row else None


def get_trend_data(conn, job, metric, count=30):
    cur = conn.execute(
        """SELECT build_number, build_id, metric_value, metric_unit, executed, passed, has_timed_out
           FROM performance_data
           WHERE job_name=? AND metric_name=? AND is_relevant=1
           ORDER BY build_number DESC LIMIT ?""",
        (job, metric, count)
    )
    rows = [dict(row) for row in cur.fetchall()]
    rows.reverse()
    return rows


def get_all_jobs(conn):
    cur = conn.execute(
        "SELECT DISTINCT job_name FROM performance_data ORDER BY job_name"
    )
    return [row[0] for row in cur.fetchall()]


def get_latest_build(conn, job):
    cur = conn.execute(
        "SELECT MAX(build_number) FROM performance_data WHERE job_name=?",
        (job,)
    )
    row = cur.fetchone()
    return row[0] if row and row[0] else None


def get_meminfo_data(conn, job, build):
    cur = conn.execute(
        """SELECT test_name, metric_name, metric_value, metric_unit
           FROM performance_data
           WHERE job_name=? AND build_number=?
           AND metric_name LIKE 'MEMINFO_%'
           ORDER BY metric_value DESC""",
        (job, build)
    )
    return [dict(row) for row in cur.fetchall()]


def get_memps_data(conn, job, build):
    cur = conn.execute(
        """SELECT test_name, metric_name, metric_value, metric_unit
           FROM performance_data
           WHERE job_name=? AND build_number=?
           AND metric_name LIKE 'MEMPS_%'
           ORDER BY metric_value DESC""",
        (job, build)
    )
    return [dict(row) for row in cur.fetchall()]


def get_compare_data(conn, jobs, metric):
    results = []
    for job in jobs:
        cur = conn.execute(
            """SELECT build_number, build_id, metric_value, metric_unit, passed
               FROM performance_data
               WHERE job_name=? AND metric_name=? AND is_relevant=1
               ORDER BY build_number DESC LIMIT 1""",
            (job, metric)
        )
        row = cur.fetchone()
        if row:
            results.append(dict(row))
            results[-1]['job_name'] = job
        else:
            results.append({'job_name': job, 'metric_value': None})
    return results


# ---------------------------------------------------------------------------
# Aggregated data for serve mode (JSON producers)
# ---------------------------------------------------------------------------

def get_key_metric_value(conn, job, build, metric):
    """Get a single key metric value for a job/build."""
    cur = conn.execute(
        """SELECT metric_value, metric_unit, test_name, executed, passed, has_timed_out
           FROM performance_data
           WHERE job_name=? AND build_number=? AND metric_name=? AND is_relevant=1
           LIMIT 1""",
        (job, build, metric)
    )
    row = cur.fetchone()
    return dict(row) if row else None


def get_key_data(conn, job, build):
    """Get key metric data (current + previous + trend) for a build."""
    prev_build = get_previous_build(conn, job, build)
    key_data = []

    for metric in KEY_METRICS:
        curr_val = get_key_metric_value(conn, job, build, metric)

        prev_val = None
        if prev_build:
            prev_val = get_key_metric_value(conn, job, prev_build, metric)

        trend = get_trend_data(conn, job, metric, 30)
        history = [point['metric_value'] for point in trend
                   if point['build_number'] != build and point['executed']
                   and point['passed'] and not point['has_timed_out']]
        decision = evaluate_regression(metric,
                                       curr_val['metric_value'] if curr_val and curr_val['executed']
                                       and curr_val['passed'] and not curr_val['has_timed_out'] else None,
                                       history[-REGRESSION_HISTORY_SIZE:])

        key_data.append({
            'metric': metric,
            'current': curr_val,
            'previous': prev_val,
            'trend': trend,
            'regression': decision['regression'],
            'improved': decision['improved'],
            'regression_info': decision,
        })

    return key_data, prev_build


def get_dynamic_data_json(conn):
    """Query DB for all dynamic comparison data and return as JSON string."""
    all_jobs = get_all_jobs(conn)

    cur = conn.execute(
        "SELECT DISTINCT metric_name FROM performance_data "
        "WHERE is_relevant=1 ORDER BY metric_name"
    )
    all_metrics = [row[0] for row in cur.fetchall()]

    builds_per_job = {}
    for job in all_jobs:
        cur = conn.execute(
            "SELECT DISTINCT build_number FROM performance_data "
            "WHERE job_name=? ORDER BY build_number DESC",
            (job,)
        )
        builds_per_job[job] = [row[0] for row in cur.fetchall()]

    cur = conn.execute(
        """SELECT job_name, build_number, metric_name, metric_value, metric_unit, test_name
           FROM performance_data
           WHERE is_relevant=1 AND metric_value IS NOT NULL
           ORDER BY job_name, build_number, metric_name"""
    )

    metric_data = {}
    metric_units = {}
    for row in cur.fetchall():
        job = row[0]
        build = row[1]
        metric = row[2]
        value = row[3]
        unit = row[4]
        test_name = row[5]

        if job not in metric_data:
            metric_data[job] = {}
        if build not in metric_data[job]:
            metric_data[job][build] = {}
        metric_data[job][build][metric] = {
            'value': value,
            'test_name': test_name,
        }
        if metric not in metric_units:
            metric_units[metric] = unit

    build_ids = {}
    cur = conn.execute(
        "SELECT DISTINCT job_name, build_number, build_id "
        "FROM performance_data WHERE build_id IS NOT NULL"
    )
    for row in cur.fetchall():
        job = row[0]
        build = row[1]
        bid = row[2]
        if job not in build_ids:
            build_ids[job] = {}
        build_ids[job][build] = bid

    return json.dumps({
        'jobs': all_jobs,
        'metrics': all_metrics,
        'builds_per_job': builds_per_job,
        'metric_data': metric_data,
        'metric_units': metric_units,
        'build_ids': build_ids,
        'key_metrics': KEY_METRICS,
        'lower_is_better': list(LOWER_IS_BETTER),
        'higher_is_better': list(HIGHER_IS_BETTER),
        'lower_is_better_prefixes': list(LOWER_IS_BETTER_PREFIXES),
        'higher_is_better_prefixes': list(HIGHER_IS_BETTER_PREFIXES),
    })



def get_compare_catalog_json(conn, page=1, per_page=100):
    """Return only the compare selector catalog, never the metric history.

    Build values are intentionally kept here because they populate the build
    selector.  Metric values are fetched only after the user selects a build.
    """
    all_jobs = get_all_jobs(conn)
    page = max(1, page)
    per_page = max(1, min(per_page, 200))
    start = (page - 1) * per_page
    jobs = all_jobs[start:start + per_page]
    builds_per_job = {}
    build_ids = {}
    for job in jobs:
        cur = conn.execute(
            """SELECT build_number, MAX(build_id) AS build_id
               FROM performance_data WHERE job_name=?
               GROUP BY build_number ORDER BY build_number DESC""",
            (job,)
        )
        rows = cur.fetchall()
        builds_per_job[job] = [row['build_number'] for row in rows]
        build_ids[job] = {row['build_number']: row['build_id'] for row in rows}

    return json.dumps({
        'jobs': jobs,
        'builds_per_job': builds_per_job,
        'build_ids': build_ids,
        'key_metrics': KEY_METRICS,
        'lower_is_better': list(LOWER_IS_BETTER),
        'higher_is_better': list(HIGHER_IS_BETTER),
        'lower_is_better_prefixes': list(LOWER_IS_BETTER_PREFIXES),
        'higher_is_better_prefixes': list(HIGHER_IS_BETTER_PREFIXES),
        'page': page,

        'per_page': per_page,
        'total': len(all_jobs),
        'total_pages': max(1, (len(all_jobs) + per_page - 1) // per_page),
    })


def get_selected_compare_data_json(conn, selections):
    """Return key metrics for explicitly selected (job, build) pairs only.

    A display metric is selected deterministically when a build contains the
    same key metric from multiple tests: relevant rows, then passing rows,
    then lexical test name, then insertion id.  All candidates are reported
    in ``duplicates`` so callers can surface the ambiguity instead of silently
    overwriting a value.
    """
    result = {'selections': [], 'duplicate_policy': {
        'identity': ['metric_name', 'test_name'],
        'key_metric_winner': 'is_relevant DESC, passed DESC, test_name ASC, id ASC',
    }}
    for job, build in selections:
        cur = conn.execute(
            """SELECT id, metric_name, metric_value, metric_unit, test_name,
                      is_relevant, passed
               FROM performance_data
               WHERE job_name=? AND build_number=? AND is_relevant=1
                 AND metric_name IN ({})
               ORDER BY metric_name, is_relevant DESC, passed DESC, test_name ASC, id ASC""".format(
                   ','.join('?' for _ in KEY_METRICS)),
            (job, build, *KEY_METRICS)
        )
        grouped = {}
        for row in cur.fetchall():
            grouped.setdefault(row['metric_name'], []).append(dict(row))
        metrics = {}
        duplicates = {}
        for metric, candidates in grouped.items():
            winner = candidates[0]
            metrics[metric] = {
                'value': winner['metric_value'],
                'unit': winner['metric_unit'],
                'test_name': winner['test_name'],
            }
            if len(candidates) > 1:
                duplicates[metric] = [c['test_name'] for c in candidates]
        result['selections'].append({
            'job': job, 'build': build, 'metrics': metrics,
            'duplicates': duplicates,
        })
    return json.dumps(result)


def get_summary_data_json(conn):
    """Return latest summary in set-based queries (no per-job N+1 reads)."""
    latest_rows = conn.execute("""
        WITH latest AS (
            SELECT job_name, MAX(build_number) AS build_number
            FROM performance_data GROUP BY job_name
        )
        SELECT l.job_name, l.build_number,
               MAX(p.build_id) AS build_id, MAX(p.test_time) AS test_time,
               SUM(CASE WHEN p.executed=0 THEN 1 ELSE 0 END) AS not_executed,
               SUM(CASE WHEN p.passed=0 THEN 1 ELSE 0 END) AS failed,
               SUM(CASE WHEN p.has_timed_out=1 THEN 1 ELSE 0 END) AS timed_out
        FROM latest l
        JOIN performance_data p ON p.job_name=l.job_name AND p.build_number=l.build_number
        GROUP BY l.job_name, l.build_number ORDER BY l.job_name
    """).fetchall()
    metric_rows = conn.execute("""
        WITH latest AS (
            SELECT job_name, MAX(build_number) AS build_number
            FROM performance_data GROUP BY job_name
        ), ranked_metrics AS (
            SELECT p.job_name, p.build_number, p.metric_name, p.metric_value, p.metric_unit,
                   ROW_NUMBER() OVER (
                       PARTITION BY p.job_name, p.build_number, p.metric_name
                       ORDER BY p.passed DESC, p.test_name, p.id) AS rn
            FROM performance_data p JOIN latest l
              ON l.job_name=p.job_name AND l.build_number=p.build_number
            WHERE p.is_relevant=1 AND p.metric_name IN ({})
        )
        SELECT job_name, build_number, metric_name, metric_value, metric_unit
        FROM ranked_metrics WHERE rn=1
    """.format(','.join('?' for _ in KEY_METRICS)), KEY_METRICS).fetchall()
    metric_map = {}
    for metric in metric_rows:
        metric_map.setdefault((metric['job_name'], metric['build_number']), {})[metric['metric_name']] = {
            'value': metric['metric_value'], 'unit': metric['metric_unit']}
    inconsistent_units = {(row['job_name'], row['build_number'], row['metric_name'])
                          for row in conn.execute("""
        WITH latest AS (
            SELECT job_name, MAX(build_number) AS build_number
            FROM performance_data GROUP BY job_name
        )
        SELECT p.job_name, p.build_number, p.metric_name
        FROM performance_data p JOIN latest l
          ON l.job_name=p.job_name AND l.build_number=p.build_number
        WHERE p.is_relevant=1 AND p.metric_name IN ({})
        GROUP BY p.job_name, p.build_number, p.metric_name
        HAVING COUNT(DISTINCT COALESCE(p.metric_unit, '')) > 1
    """.format(','.join('?' for _ in KEY_METRICS)), KEY_METRICS).fetchall()}
    summary = []
    for source in latest_rows:
        row = dict(source)
        metrics = metric_map.get((row['job_name'], row['build_number']), {})
        missing = [metric for metric in KEY_METRICS if metric not in metrics]
        warnings = []
        if row['failed']: warnings.append('FAIL {}'.format(row['failed']))
        if row['timed_out']: warnings.append('TIMEOUT {}'.format(row['timed_out']))
        if row['not_executed']: warnings.append('NOT EXECUTED {}'.format(row['not_executed']))
        if missing: warnings.append('MISSING ' + ', '.join(missing))
        unit_mismatch = [name for name in metrics
                         if (row['job_name'], row['build_number'], name) in inconsistent_units]
        if unit_mismatch: warnings.append('UNIT MISMATCH ' + ', '.join(unit_mismatch))
        abnormal = [name for name, metric in metrics.items()
                    if metric['value'] is None or not math.isfinite(metric['value'])]
        if abnormal: warnings.append('INVALID VALUE ' + ', '.join(abnormal))
        label = get_label(conn, row['job_name'], row['build_number'])
        summary.append({'job': row['job_name'], 'build': row['build_number'],
                        'build_id': row['build_id'], 'test_time': row['test_time'],
                        'label': label,
                        'metrics': metrics, 'warnings': warnings})

    return json.dumps({
        'summary': summary,
        'key_metrics': KEY_METRICS,
        'metric_units': {m: '' for m in KEY_METRICS},
    })


def get_profile_detail_json(conn, job, page=1, per_page=20):
    """Query DB for a profile's build list with key metrics, paginated."""
    total = conn.execute("SELECT COUNT(DISTINCT build_number) FROM performance_data WHERE job_name=?", (job,)).fetchone()[0]
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))

    offset = (page - 1) * per_page
    rows = conn.execute("""
        WITH page_builds AS (
            SELECT build_number FROM performance_data WHERE job_name=?
            GROUP BY build_number ORDER BY build_number DESC LIMIT ? OFFSET ?
        ), ranked_metrics AS (
            SELECT p.*, ROW_NUMBER() OVER (
                PARTITION BY p.build_number, p.metric_name
                ORDER BY p.passed DESC, p.test_name, p.id) AS rn
            FROM performance_data p JOIN page_builds b ON b.build_number=p.build_number
            WHERE p.job_name=? AND p.is_relevant=1
        )
        SELECT b.build_number, MAX(p.build_id) build_id, MAX(p.test_time) test_time,
               rm.metric_name, rm.metric_value, rm.metric_unit
        FROM page_builds b JOIN performance_data p ON p.job_name=? AND p.build_number=b.build_number
        LEFT JOIN ranked_metrics rm ON rm.build_number=b.build_number AND rm.rn=1
        GROUP BY b.build_number, rm.metric_name ORDER BY b.build_number DESC
    """, (job, per_page, offset, job, job)).fetchall()
    build_map = {}
    for source in rows:
        row = dict(source)
        target = build_map.setdefault(row['build_number'], {'build': row['build_number'], 'build_id': row['build_id'], 'test_time': row['test_time'], 'metrics': {}})
        if row['metric_name'] in KEY_METRICS and row['metric_value'] is not None:
            target['metrics'][row['metric_name']] = {'value': row['metric_value'], 'unit': row['metric_unit']}
    builds = list(build_map.values())
    for build in builds:
        build['label'] = get_label(conn, job, build['build'])

    return json.dumps({
        'job': job,
        'builds': builds,
        'page': page,
        'per_page': per_page,
        'total': total,
        'total_pages': total_pages,
        'key_metrics': KEY_METRICS,
    })


def get_trend_data_json(conn, job, count=30):
    """Get trend data for key metrics as JSON for serve mode."""
    trends = {}
    for metric in KEY_METRICS:
        trend = get_trend_data(conn, job, metric, count)
        trends[metric] = {
            'labels': [str(t['build_number']) for t in trend],
            'values': [t['metric_value'] for t in trend],
            'unit': trend[-1]['metric_unit'] if trend else '',
            'build_ids': [t.get('build_id') or '' for t in trend],
        }

    return json.dumps({
        'job': job,
        'trends': trends,
        'key_metrics': KEY_METRICS,
    })


def _union_metrics(*metric_sets):
    """Return a deterministic union keyed by (metric_name, test_name).

    Comparisons must not hide a metric simply because it exists only on the
    second or third target. The schema's unique index makes this identity
    unambiguous within one build.
    """
    merged = {}
    for metrics in metric_sets:
        for metric in metrics:
            merged.setdefault((metric['metric_name'], metric['test_name']), metric)
    return list(merged.values())


def get_compare_detail_json(conn, jobA, buildA, jobB, buildB):
    """Get detailed comparison data between two targets as JSON."""
    metricsA = get_build_metrics(conn, jobA, buildA)
    metricsB = get_build_metrics(conn, jobB, buildB)

    lookupA = {(m['metric_name'], m['test_name']): m for m in metricsA}
    lookupB = {(m['metric_name'], m['test_name']): m for m in metricsB}

    perf, mem = filter_and_sort_metrics(_union_metrics(metricsA, metricsB))

    rows = []

    def process_metric(m):
        mn = m['metric_name']
        tn = m['test_name']
        key = (mn, tn)
        mA = lookupA.get(key)
        mB = lookupB.get(key)
        val_a = mA['metric_value'] if mA else None
        val_b = mB['metric_value'] if mB else None
        unit = (mA or mB)['metric_unit'] or ''
        passed = 'PASS' if (mA or mB)['passed'] else 'FAIL'

        change_str = '-'
        reg = False
        improved = False

        if val_a is not None and val_b is not None and val_b != 0:
            pct = (val_a - val_b) / abs(val_b) * 100
            change_str = '{:+.1f}%'.format(pct)
            reg = is_regression(mn, val_a, val_b)
            if is_lower_is_better(mn):
                improved = pct < -REGRESSION_THRESHOLD * 100
            elif is_higher_is_better(mn):
                improved = pct > REGRESSION_THRESHOLD * 100

        rows.append({
            'test_name': tn,
            'metric_name': mn,
            'unit': unit,
            'val_a': str(val_a) if val_a is not None else 'N/A',
            'val_b': str(val_b) if val_b is not None else 'N/A',
            'change': change_str,
            'regression': reg,
            'improved': improved,

            'is_sub_test': is_sub_test(tn),
            'passed': passed,
        })

    for m in perf:
        process_metric(m)

    if mem:
        rows.append({
            'test_name': 'Memory Detail Information',
            'val_a': '', 'val_b': '', 'change': '',
            'regression': False, 'improved': False, 'is_sub_test': False,
            'is_separator': True,
        })
        for m in mem:
            process_metric(m)

    labelA = '{} #{}'.format(jobA, buildA)
    labelB = '{} #{}'.format(jobB, buildB)
    labelAText = get_label(conn, jobA, buildA)
    labelBText = get_label(conn, jobB, buildB)

    payload = {
        'labelA': labelA,
        'labelB': labelB,
        'label_a': labelAText,
        'label_b': labelBText,
        'rows': rows,
    }
    rigor = get_memory_rigor_comparison(conn, jobA, buildA, jobB, buildB)
    if rigor is not None:
        payload['memory_rigor'] = rigor
        methods = rigor.get('methods') or [rigor.get('quality_a', {}).get('method'), rigor.get('quality_b', {}).get('method')]
        if methods[0] != methods[1]:
            for row in rows:
                name = row.get('metric_name', '')
                if name == 'IdleMemoryUsage' or name.startswith(('MEMINFO_', 'MEMPS - ')):
                    row['method_warning'] = '测量方法不同，数值不可直接比较'
    return json.dumps(payload)


def get_compare_detail_3way_json(conn, jobA, buildA, jobB, buildB, jobC, buildC):
    """Get detailed comparison data between three targets as JSON."""
    metricsA = get_build_metrics(conn, jobA, buildA)
    metricsB = get_build_metrics(conn, jobB, buildB)
    metricsC = get_build_metrics(conn, jobC, buildC)

    lookupA = {(m['metric_name'], m['test_name']): m for m in metricsA}
    lookupB = {(m['metric_name'], m['test_name']): m for m in metricsB}
    lookupC = {(m['metric_name'], m['test_name']): m for m in metricsC}

    # Separate into performance and memory metrics (same as 2-way comparison)
    perf, mem = filter_and_sort_metrics(_union_metrics(metricsA, metricsB, metricsC))

    rows = []

    def process_metric(m):
        mn = m['metric_name']
        tn = m['test_name']
        key = (mn, tn)
        mA = lookupA.get(key)
        mB = lookupB.get(key)
        val_b = mB['metric_value'] if mB else None

        mC = lookupC.get(key)
        val_c = mC['metric_value'] if mC else None
        val_a = mA['metric_value'] if mA else None
        unit = (mA or mB or mC)['metric_unit'] or ''

        rows.append({
            'test_name': tn,
            'metric_name': mn,
            'unit': unit,
            'val_a': val_a,
            'val_b': val_b,
            'val_c': val_c,
            'is_sub_test': is_sub_test(tn),
        })

    # Process performance metrics
    for m in perf:
        process_metric(m)

    # Add separator for memory metrics if they exist
    if mem:
        rows.append({
            'test_name': 'Memory Detail Information',
            'val_a': None, 'val_b': None, 'val_c': None,
            'is_sub_test': False,
            'is_separator': True,
        })
        # Process memory metrics
        for m in mem:
            process_metric(m)

    labelA = '{} #{}'.format(jobA, buildA)
    labelB = '{} #{}'.format(jobB, buildB)
    labelC = '{} #{}'.format(jobC, buildC)
    labelAText = get_label(conn, jobA, buildA)
    labelBText = get_label(conn, jobB, buildB)
    labelCText = get_label(conn, jobC, buildC)

    return json.dumps({
        'labelA': labelA,
        'labelB': labelB,
        'labelC': labelC,
        'label_a': labelAText,
        'label_b': labelBText,
        'label_c': labelCText,
        'rows': rows,
    })


def get_test_trend_json(conn, job, test_name, metric_name, build_number, window=10):
    """Get trend data for a specific test/metric around a build number.

    Returns JSON with trend data for ±window builds (default 10 each side).
    """
    # Get the target build info first
    cur = conn.execute(
        """SELECT build_id, test_time FROM performance_data
           WHERE job_name=? AND build_number=? AND test_name=? AND metric_name=?
           LIMIT 1""",
        (job, build_number, test_name, metric_name)
    )
    target = cur.fetchone()
    if not target:
        return json.dumps({'error': 'Build not found'})

    target_build_id = target['build_id']
    target_test_time = target['test_time']

    # Get trend data: ±window around the build
    cur = conn.execute(
        """SELECT build_number, build_id, metric_value, metric_unit, test_time
           FROM performance_data
           WHERE job_name=? AND test_name=? AND metric_name=?
             AND build_number BETWEEN ? AND ?
           ORDER BY build_number""",
        (job, test_name, metric_name, build_number - window, build_number + window)
    )

    trend = []
    for row in cur.fetchall():
        trend.append({
            'build_number': row['build_number'],
            'build_id': row['build_id'],
            'metric_value': row['metric_value'],
            'metric_unit': row['metric_unit'],
            'test_time': row['test_time'],
            'is_target': row['build_number'] == build_number,
        })

    return json.dumps({
        'test_name': test_name,
        'metric_name': metric_name,
        'target_build': build_number,
        'target_build_id': target_build_id,
        'target_test_time': target_test_time,
        'trend': trend,
    })


def get_all_metrics_for_comparison(conn, jobA, buildA, jobB, buildB):
    """Get all metrics (not just key metrics) for comparison between two builds.

    Used for detailed Excel export in Compare page.
    Filters out separator rows and sorts by SORT_ORDER + test_name.
    """
    metricsA = get_build_metrics(conn, jobA, buildA)
    metricsB = get_build_metrics(conn, jobB, buildB)

    lookupA = {(m['metric_name'], m['test_name']): m for m in metricsA}
    lookupB = {(m['metric_name'], m['test_name']): m for m in metricsB}

    # Union keeps metrics that exist only in Target B visible in Excel too.
    perfA, memA = filter_and_sort_metrics(_union_metrics(metricsA, metricsB))
    all_filtered = perfA + memA

    # Process all metrics
    rows = []
    for m in all_filtered:
        mn = m['metric_name']
        tn = m['test_name']
        key = (mn, tn)
        mA = lookupA.get(key)
        mB = lookupB.get(key)
        val_a = mA['metric_value'] if mA else None
        val_b = mB['metric_value'] if mB else None
        unit = (mA or mB)['metric_unit']
        passed = 'PASS' if (mA or mB)['passed'] else 'FAIL'

        change_str = '-'
        reg = False
        improved = False

        if val_a is not None and val_b is not None and val_b != 0:
            pct = (val_a - val_b) / abs(val_b) * 100
            change_str = '{:+.1f}%'.format(pct)
            reg = is_regression(mn, val_a, val_b)
            if is_lower_is_better(mn):
                improved = pct < -REGRESSION_THRESHOLD * 100
            elif is_higher_is_better(mn):
                improved = pct > REGRESSION_THRESHOLD * 100

        rows.append({
            'test_name': tn,
            'metric_name': mn,
            'unit': unit or '',

            'val_a': str(val_a) if val_a is not None else 'N/A',
            'val_b': str(val_b) if val_b is not None else 'N/A',
            'change': change_str,
            'passed': passed,
            'is_sub_test': is_sub_test(tn),
        })

    return rows



# ============================================================================
# Build Labels Management
# ============================================================================

def get_label(conn, job_name, build_number):
    """Get label for a specific job/build. Returns label string or None."""
    # build_labels is an optional feature table: databases created before
    # label management existed (or never initialized with
    # create_build_labels_table.py) do not have it. A missing table must
    # not break summary/detail/compare views — degrade to "no label".
    try:
        cur = conn.execute(
            "SELECT label FROM build_labels WHERE job_name=? AND build_number=?",
            (job_name, build_number)
        )
        row = cur.fetchone()
    except sqlite3.OperationalError:
        return None
    return row[0] if row else None


def add_or_update_label(conn, job_name, build_number, label):
    """Add or update label for a job/build. Returns True if successful."""
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT OR REPLACE INTO build_labels (job_name, build_number, label, updated_date)
               VALUES (?, ?, ?, CURRENT_TIMESTAMP)""",
            (job_name, build_number, label)
        )
        conn.commit()
        return True
    except sqlite3.Error:
        return False


def delete_label(conn, job_name, build_number):
    """Delete label for a job/build. Returns True if successful."""
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM build_labels WHERE job_name=? AND build_number=?",
            (job_name, build_number)
        )
        conn.commit()
        return True
    except sqlite3.Error:
        return False


def get_all_labels(conn, job_name):
    """Get all labels for a job. Returns dict {build_number: label}."""
    cur = conn.execute(
        "SELECT build_number, label FROM build_labels WHERE job_name=? ORDER BY build_number DESC",
        (job_name,)
    )
    return {row[0]: row[1] for row in cur.fetchall()}


def get_builds_with_labels_json(conn, job_name):
    """Get all builds for a job with their labels. Returns JSON."""
    # Get all builds for the job with build_id
    cur = conn.execute(
        "SELECT build_number, MAX(build_id) AS build_id FROM performance_data WHERE job_name=? GROUP BY build_number ORDER BY build_number DESC",
        (job_name,)
    )
    builds = [(row[0], row[1]) for row in cur.fetchall()]

    # Get all labels for this job
    labels = get_all_labels(conn, job_name)

    # Combine into list of dicts
    result = []
    for build_num, build_id in builds:
        result.append({
            "build_number": build_num,
            "build_id": build_id or "",
            "label": labels.get(build_num, "")
        })


    return json.dumps({
        "job_name": job_name,
        "builds": result
    })



def get_memory_rigor_comparison(conn, jobA, buildA, jobB, buildB):
    """Separate additive payload; never apply old 10% thresholds to rigor."""
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'standalone'))
    from memory_rigor import load_run, compare_runs, run_quality, method_info, comparison_warnings
    a, b = load_run(conn, jobA, buildA), load_run(conn, jobB, buildB)
    if a is None and b is None:
        return None
    if a is None or b is None:
        return {'conclusion': '一侧没有严谨模式样本，不作结论',
                'methods': [method_info(a),method_info(b)], 'warnings': comparison_warnings(a,b),
                'quality_a': run_quality(a) if a else None,
                'quality_b': run_quality(b) if b else None}
    return compare_runs(a, b)
