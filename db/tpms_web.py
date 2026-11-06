#!/usr/bin/env python3
"""
TPMS Performance Report Generator & Web Dashboard (Flask)

Generates interactive HTML reports from TPMS SQLite database.
Also serves a real-time dashboard via Flask.

Usage:
    # Web server (real-time dashboard)
    python3 tpms_web.py --db tpms.db --serve --port 9090

    # Single build report (static HTML)
    python3 tpms_web.py --db tpms.db --job 10.0-unified-rpi-32bit --build 534 --output report.html

    # Trend page (static HTML)
    python3 tpms_web.py --db tpms.db --job 10.0-unified-rpi-32bit --output trend.html

    # Profile comparison (static HTML)
    python3 tpms_web.py --db tpms.db --compare "10.0-unified-rpi-32bit,9.0-unified-rpi-32bit" --output compare.html

    # Dynamic comparison (offline HTML)
    python3 tpms_web.py --db tpms.db --dynamic --output dynamic.html
"""

import argparse
import hashlib
import json
import logging
import os
import sqlite3
import sys
import time

from flask import Flask, render_template, jsonify, request, Response, session
from markupsafe import escape

from tpms_admin import verify_credentials

from tpms_constants import (
    KEY_METRICS, LOWER_IS_BETTER, HIGHER_IS_BETTER, REGRESSION_THRESHOLD,
    is_lower_is_better, is_higher_is_better, is_regression, fmt_val,
    is_sub_test, filter_and_sort_metrics, get_sort_key,
)

from tpms_db_queries import (
    get_db_conn,
    get_build_metrics, get_build_info, get_previous_build, get_trend_data,
    get_all_jobs, get_latest_build, get_meminfo_data, get_memps_data,
    get_compare_data, get_key_data,
    get_dynamic_data_json, get_summary_data_json, get_compare_catalog_json,
    get_selected_compare_data_json,
    get_profile_detail_json, get_trend_data_json, get_compare_detail_json,
    get_test_trend_json, get_all_metrics_for_comparison, get_compare_detail_3way_json,
    get_label, add_or_update_label, delete_label, get_all_labels, get_builds_with_labels_json,
)

from tpms_runner import (
    TestRegistry, get_task_manager,
    get_rpi_profiles, get_test_items_for_profile,
    check_connected_devices, has_rpi_device,
    get_available_snapshots,
)



# ---------------------------------------------------------------------------
# Flask app setup
# ---------------------------------------------------------------------------

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = 'tpms-secret-key-change-in-production'  # For session management
app.permanent_session_lifetime = 1800  # 30 minutes idle timeout
logging.basicConfig(level=os.environ.get('TPMS_LOG_LEVEL', 'INFO'),
                    format='%(asctime)s %(levelname)s %(name)s %(message)s')
logger = logging.getLogger('tpms.web')

# Global DB path (set in run_server or main)
DB_PATH = None


def _get_conn():
    """Get a read-only DB connection using the global DB_PATH."""
    return get_db_conn(DB_PATH, read_only=True)


def _json_response(data, status=200):
    """Return JSON with a strong ETag and support conditional GET requests."""
    etag = hashlib.sha256(data.encode('utf-8')).hexdigest()
    headers = {'Cache-Control': 'private, max-age=0, must-revalidate'}
    # Compare the raw request header as well as accepting a comma-separated
    # ETag list. This avoids differences in conditional-header parsing between
    # Werkzeug versions and reverse-proxy deployments.
    raw_if_none_match = request.headers.get('If-None-Match', '')
    client_etags = {
        candidate.strip().strip('"')
        for candidate in raw_if_none_match.split(',')
    }
    if status == 200 and etag in client_etags:
        response = Response(status=304, headers=headers)
        response.set_etag(etag)
        return response
    response = Response(data, status=status,
                        content_type='application/json; charset=utf-8', headers=headers)
    response.set_etag(etag)
    return response


def _safe_json_for_script(value):
    """Serialize data safely for a ``<script>`` element."""
    return json.dumps(value).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')


@app.errorhandler(sqlite3.Error)
def _handle_database_error(error):
    logger.exception('database_error path=%s', request.path)
    return _json_response(json.dumps({'error': 'Database temporarily unavailable'}), status=503)


@app.route('/healthz')
def healthz():
    """Lightweight liveness and read-only database readiness probe."""
    try:
        conn = _get_conn()
        conn.execute('SELECT 1').fetchone()
        conn.close()
    except sqlite3.Error:
        logger.exception('healthcheck_database_error')
        return _json_response(json.dumps({'status': 'unhealthy', 'database': 'unavailable'}), status=503)
    return _json_response(json.dumps({'status': 'ok', 'database': 'ok'}))


# ---------------------------------------------------------------------------
# Static HTML generation helpers (used by both serve mode and CLI)
# ---------------------------------------------------------------------------

def _build_report_data(conn, job, build, compare_jobs=None, serve_mode=False):
    """Gather all data needed for a build report and return as dict."""

    build_info = get_build_info(conn, job, build)
    key_data, prev_build = get_key_data(conn, job, build)
    prev_build_info = get_build_info(conn, job, prev_build) if prev_build else None
    meminfo = get_meminfo_data(conn, job, build)
    memps = get_memps_data(conn, job, build)
    all_metrics = get_build_metrics(conn, job, build)

    prev_metrics = {}
    if prev_build:
        for m in get_build_metrics(conn, job, prev_build):
            key = (m['metric_name'], m['test_name'])
            prev_metrics[key] = m

    # Build cards data
    cards = []
    charts_data = {}
    for kd in key_data:
        m = kd['metric']
        curr = kd['current']
        prev = kd['previous']
        reg = kd['regression']

        curr_val = fmt_val(curr['metric_value'], curr['metric_unit']) if curr else 'N/A'
        prev_val = fmt_val(prev['metric_value'], prev['metric_unit']) if prev else 'N/A'

        change_str = ''
        change_class = ''
        if curr and prev and prev['metric_value'] and prev['metric_value'] != 0:
            pct = (curr['metric_value'] - prev['metric_value']) / abs(prev['metric_value']) * 100
            change_str = '({:+.1f}%)'.format(pct)
            if abs(pct) < 0.1:
                change_class = 'change-neutral'
            elif reg:
                change_class = 'change-bad'
            else:
                change_class = 'change-good'

        cards.append({
            'metric': m,
            'curr_val': curr_val,
            'prev_val': prev_val,
            'change_str': change_str,
            'change_class': change_class,
            'regression': reg,
        })

        trend_labels = [str(t['build_number']) for t in kd['trend']]
        trend_values = [t['metric_value'] for t in kd['trend']]
        charts_data[m] = {
            'labels': trend_labels,
            'values': trend_values,
            'unit': curr['metric_unit'] if curr else '',
        }

    # Build table rows
    perf_metrics, mem_metrics_list = filter_and_sort_metrics(all_metrics)

    table_rows = []
    for m in perf_metrics:
        table_rows.append(_build_table_row(m, prev_metrics))

    if mem_metrics_list:
        table_rows.append({
            'is_separator': True,
            'test_name': 'Memory Detail Information',
        })
        for m in mem_metrics_list:
            table_rows.append(_build_table_row(m, prev_metrics))

    # MemInfo labels for pie chart
    meminfo_labels = [{'label': m['metric_name'].replace('MEMINFO_', ''),
                       'value': m['metric_value'], 'unit': m['metric_unit']} for m in meminfo]

    # MEMPS bar data
    memps_labels = []
    memps_values = []
    for m in memps[:15]:
        label = m['metric_name'].replace('MEMPS - ', '')
        if len(label) > 35:
            label = '...' + label[-32:]
        memps_labels.append(label)
        memps_values.append(m['metric_value'])

    # Compare section
    compare_html = ''
    if compare_jobs:
        compare_data = {}
        for metric in KEY_METRICS:
            compare_data[metric] = get_compare_data(conn, compare_jobs, metric)
        compare_html = _build_compare_html(compare_data)

    js_data = _safe_json_for_script({
        'job': job,
        'build': build,
        'charts': charts_data,
        'pie_labels': [m['label'] for m in meminfo_labels],
        'pie_values': [m['value'] for m in meminfo_labels],
        'memps_labels': memps_labels,
        'memps_values': memps_values,
        'has_meminfo': bool(meminfo),
    })


    label = get_label(conn, job, build) or ''

    return {
        'job': job,
        'build': build,
        'build_id': build_info.get('build_id') or 'N/A',
        'test_time': build_info.get('test_time') or 'N/A',
        'label': label,
        'prev_build': prev_build or 'N/A',
        'prev_build_id': (prev_build_info or {}).get('build_id') or 'N/A',
        'cards': cards,
        'table_rows': table_rows,
        'meminfo': meminfo_labels,
        'meminfo_html': bool(meminfo),
        'compare_html': compare_html,
        'js_data': js_data,
        'serve_mode': serve_mode,
    }



def _build_table_row(m, prev_metrics):
    """Build a single table row dict for the detailed results table."""
    mn = m['metric_name']
    tn = m['test_name']
    val = m['metric_value']
    unit = m['metric_unit'] or ''
    passed = 'PASS' if m['passed'] else 'FAIL'

    indent = '&nbsp;&nbsp;&nbsp;&nbsp;' if is_sub_test(tn) else ''

    key = (mn, tn)
    prev_m = prev_metrics.get(key)
    prev_val_str = 'N/A'
    change_str = '-'
    reg = False
    improved = False

    if prev_m and prev_m['metric_value'] is not None and val is not None and prev_m['metric_value'] != 0:
        prev_val_str = fmt_val(prev_m['metric_value'], unit)
        pct = (val - prev_m['metric_value']) / abs(prev_m['metric_value']) * 100
        change_str = '{:+.1f}%'.format(pct)
        reg = is_regression(mn, val, prev_m['metric_value'])
        if is_lower_is_better(mn):
            improved = pct < -REGRESSION_THRESHOLD * 100
        elif is_higher_is_better(mn):
            improved = pct > REGRESSION_THRESHOLD * 100
    elif not prev_m:
        prev_val_str = 'N/A'
        change_str = '-'

    if reg:
        row_class = 'row-regression'
        val_class = 'val-bad'
        change_class = 'val-bad'
    elif improved:
        row_class = 'row-improved'
        val_class = 'val-good'
        change_class = 'val-good'
    else:
        row_class = ''
        val_class = ''
        change_class = ''

    return {
        'is_separator': False,
        'test_name': tn,
        'metric_name': mn,
        'indent': indent,
        'curr_val': fmt_val(val, unit),
        'prev_val': prev_val_str,
        'change_str': change_str,
        'passed': passed,
        'row_class': row_class,
        'val_class': val_class,
        'change_class': change_class,
    }


def _build_compare_html(compare_data):
    """Build HTML string for the compare section in report."""
    html = ''
    for metric, data in compare_data.items():
        html += '<h3>{}</h3>'.format(escape(metric))
        html += '<table class="compare-table"><tr><th>Job</th><th>Build</th><th>Value</th><th>Unit</th></tr>'
        for d in data:
            val = fmt_val(d.get('metric_value'), d.get('metric_unit', ''))
            html += '<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>'.format(
                escape(d['job_name']), d.get('build_number', 'N/A'),
                escape(val), escape(d.get('metric_unit', '')))
        html += '</table>'
    return html


# ---------------------------------------------------------------------------
# Flask routes (serve mode)
# ---------------------------------------------------------------------------

@app.route('/')
def dashboard():
    """Main dashboard HTML page."""
    return render_template('dashboard.html')


@app.route('/api/summary')
def api_summary():
    conn = _get_conn()
    try:
        data = get_summary_data_json(conn)
    finally:
        conn.close()
    return _json_response(data)


@app.route('/api/data')
def api_data():
    """Deprecated: whole-history compare payload is intentionally disabled."""
    return _json_response(json.dumps({
        'error': 'Deprecated endpoint. Use /api/compare/catalog and /api/compare/selection.'
    }), status=410)


@app.route('/api/compare/catalog')
def api_compare_catalog():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)
    conn = _get_conn()
    try:
        data = get_compare_catalog_json(conn, page=page, per_page=per_page)
    finally:
        conn.close()
    return _json_response(data)


@app.route('/api/compare/selection')
def api_compare_selection():
    """Fetch key metrics only for explicit ``job:build`` selections."""
    raw_selections = request.args.getlist('selection')
    selections = []
    for raw in raw_selections:
        job, sep, build = raw.rpartition(':')
        if not sep or not job:
            return _json_response(json.dumps({'error': 'Invalid selection'}), status=400)
        try:
            selections.append((job, int(build)))
        except ValueError:
            return _json_response(json.dumps({'error': 'Invalid build number'}), status=400)
    if not selections or len(selections) > 3:
        return _json_response(json.dumps({'error': 'Select between 1 and 3 builds'}), status=400)

    conn = _get_conn()
    try:
        data = get_selected_compare_data_json(conn, selections)
    finally:
        conn.close()
    return _json_response(data)


@app.route('/api/profile/<job>')
def api_profile(job):
    page = request.args.get('page', 1, type=int)
    conn = _get_conn()
    try:
        data = get_profile_detail_json(conn, job, page=page)
    finally:
        conn.close()
    return _json_response(data)


@app.route('/api/trend/<job>')
def api_trend(job):
    conn = _get_conn()
    try:
        data = get_trend_data_json(conn, job)
    finally:
        conn.close()
    return _json_response(data)


@app.route('/trend/<job>')
def trend_page(job):
    """Standalone trend HTML page (for iframe embed)."""
    conn = _get_conn()

    cur = conn.execute(
        """SELECT DISTINCT metric_name FROM performance_data
           WHERE job_name=? AND is_relevant=1""",
        (job,)
    )
    all_metrics = [row[0] for row in cur.fetchall()]

    # Sort metrics by KEY_METRICS order, then by sort key for others
    ordered = []
    for km in KEY_METRICS:
        if km in all_metrics:
            ordered.append(km)
    for m in all_metrics:
        if m not in ordered:
            ordered.append(m)
    metrics = ordered

    charts_data = {}
    for metric in metrics:
        trend = get_trend_data(conn, job, metric, 30)
        if trend:
            charts_data[metric] = {
                'labels': [str(t['build_number']) for t in trend],
                'values': [t['metric_value'] for t in trend],
                'unit': trend[-1]['metric_unit'] if trend else '',
            }

    latest = get_latest_build(conn, job)
    conn.close()

    js_data = _safe_json_for_script(charts_data)

    return render_template('trend.html', job=job, latest=latest or 'N/A',
                           count=30, charts_data=charts_data, js_data=js_data,
                           serve_mode=True)



@app.route('/api/report/<job>/<int:build>')
def api_report(job, build):

    """Build detail report HTML (served via Flask for iframe)."""
    conn = _get_conn()
    compare_jobs = None
    data = _build_report_data(conn, job, build, compare_jobs, serve_mode=True)
    conn.close()
    return render_template('report.html', **data)



@app.route('/api/compare_detail/<jobA>/<int:buildA>/<jobB>/<int:buildB>')
def api_compare_detail(jobA, buildA, jobB, buildB):
    conn = _get_conn()
    data = get_compare_detail_json(conn, jobA, buildA, jobB, buildB)
    conn.close()
    return Response(data, content_type='application/json; charset=utf-8',
                    headers={'Cache-Control': 'no-cache, no-store, must-revalidate'})


@app.route('/api/test_trend')
def api_test_trend():
    job = request.args.get('job', '')
    test_name = request.args.get('test_name', '')
    metric_name = request.args.get('metric_name', '')
    build = request.args.get('build', type=int)

    if not (job and test_name and metric_name and build is not None):
        return Response(json.dumps({'error': 'Missing parameters'}), status=400,
                       content_type='application/json; charset=utf-8')

    conn = _get_conn()
    data = get_test_trend_json(conn, job, test_name, metric_name, build, window=10)
    conn.close()
    return Response(data, content_type='application/json; charset=utf-8',
                    headers={'Cache-Control': 'no-cache, no-store, must-revalidate'})


@app.route('/api/all_metrics_compare/<jobA>/<int:buildA>/<jobB>/<int:buildB>')
def api_all_metrics_compare(jobA, buildA, jobB, buildB):
    conn = _get_conn()
    rows = get_all_metrics_for_comparison(conn, jobA, buildA, jobB, buildB)
    conn.close()
    return Response(json.dumps(rows), content_type='application/json; charset=utf-8',
                    headers={'Cache-Control': 'no-cache, no-store, must-revalidate'})


@app.route('/api/compare_detail_3way/<jobA>/<int:buildA>/<jobB>/<int:buildB>/<jobC>/<int:buildC>')
def api_compare_detail_3way(jobA, buildA, jobB, buildB, jobC, buildC):
    conn = _get_conn()
    data = get_compare_detail_3way_json(conn, jobA, buildA, jobB, buildB, jobC, buildC)
    conn.close()
    return Response(data, content_type='application/json; charset=utf-8',
                    headers={'Cache-Control': 'no-cache, no-store, must-revalidate'})


# ---------------------------------------------------------------------------
# Static HTML generation (CLI mode)
# ---------------------------------------------------------------------------

def generate_report(conn, job, build, output_path, compare_jobs=None):
    """Generate PerfPublisher-style HTML report for a specific build."""
    data = _build_report_data(conn, job, build, compare_jobs)
    with app.app_context():
        html = render_template('report.html', **data)

    with open(output_path, 'w') as f:
        f.write(html)

    print("Report generated: {}".format(output_path))
    print("  Job: {}, Build: {}".format(job, build))


def generate_trend_page(conn, job, output_path, count=30):
    """Generate a trend-only page for a job."""
    cur = conn.execute(
        """SELECT DISTINCT metric_name FROM performance_data
           WHERE job_name=? AND is_relevant=1""",
        (job,)
    )
    all_metrics = [row[0] for row in cur.fetchall()]

    # Sort metrics by KEY_METRICS order, then by sort key for others
    metrics = []
    for km in KEY_METRICS:
        if km in all_metrics:
            metrics.append(km)
    for m in all_metrics:
        if m not in metrics:
            metrics.append(m)


    charts_data = {}
    for metric in metrics:
        trend = get_trend_data(conn, job, metric, count)
        if trend:
            charts_data[metric] = {
                'labels': [str(t['build_number']) for t in trend],
                'values': [t['metric_value'] for t in trend],
                'unit': trend[-1]['metric_unit'] if trend else '',
            }

    latest = get_latest_build(conn, job)
    js_data = _safe_json_for_script(charts_data)

    with app.app_context():
        html = render_template('trend.html', job=job, latest=latest or 'N/A',
                               count=count, charts_data=charts_data, js_data=js_data,
                               serve_mode=False)


    with open(output_path, 'w') as f:
        f.write(html)
    print("Trend report generated: {}".format(output_path))


def generate_compare_page(conn, jobs, output_path, metrics=None):
    """Generate a comparison page across jobs."""
    if metrics is None:
        metrics = KEY_METRICS

    sections_data = {}
    js_charts = {}
    for metric in metrics:
        data = get_compare_data(conn, jobs, metric)
        sections_data[metric] = data
        js_charts[metric] = {
            'labels': [d['job_name'] for d in data],
            'values': [d.get('metric_value') or 0 for d in data],
        }

    js_data = _safe_json_for_script(js_charts)
    with app.app_context():
        html = render_template('compare.html', jobs_str=', '.join(jobs),
                               sections_data=sections_data, js_data=js_data,
                               serve_mode=False)


    with open(output_path, 'w') as f:
        f.write(html)
    print("Comparison report generated: {}".format(output_path))



def generate_dynamic_page(conn, output_path):
    """Generate a single dynamic HTML page for interactive comparison.

    The page embeds all relevant metric data as JSON and uses JavaScript
    to let users dynamically select profiles/build_ids to compare.
    """
    # Reuse the JSON data from serve mode
    data_json = get_dynamic_data_json(conn)

    # The dynamic page is self-contained; render with the embedded JSON
    html = _build_dynamic_html(data_json)

    with open(output_path, 'w') as f:
        f.write(html)
    print("Dynamic comparison page generated: {}".format(output_path))


def _build_dynamic_html(data_json):
    """Build the dynamic comparison HTML page (self-contained)."""

    # The embedded dynamic page uses a script tag, so escape tag delimiters.
    data_json = data_json.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    html = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TPMS Dynamic Comparison</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@3.9.1/dist/chart.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js"></script>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Segoe UI', Arial, sans-serif; background: #f5f5f5; color: #333; }
.container { max-width: 1200px; margin: 0 auto; padding: 20px; }
.header { background: #1a237e; color: white; padding: 20px 30px; border-radius: 8px 8px 0 0; }
.header h1 { font-size: 24px; }
.header .desc { font-size: 13px; opacity: 0.8; margin-top: 5px; }
.section { background: white; margin: 15px 0; padding: 20px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.section h2 { font-size: 18px; margin-bottom: 15px; color: #1a237e; border-bottom: 2px solid #e0e0e0; padding-bottom: 8px; }
.target-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 30px; margin-bottom: 15px; }
.target-box { border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; }
.target-box h3 { font-size: 16px; color: #1a237e; margin-bottom: 10px; }
.control-group { display: flex; flex-direction: column; gap: 5px; margin-bottom: 10px; }
.control-group label { font-size: 12px; font-weight: 600; color: #666; text-transform: uppercase; }
select { padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }
.btn-row { display: flex; gap: 10px; margin-top: 10px; }
.btn { padding: 10px 24px; border: none; border-radius: 4px; font-size: 14px; cursor: pointer; font-weight: 600; }
.btn-primary { background: #1a237e; color: white; }
.btn-primary:hover { background: #283593; }
.btn-secondary { background: #4caf50; color: white; }
.btn-secondary:hover { background: #388e3c; }
.btn:disabled { background: #ccc; cursor: not-allowed; }
.compare-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 15px; }
.compare-card { background: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 4px solid #1a237e; }
.compare-card h3 { font-size: 14px; color: #666; margin-bottom: 5px; }
.compare-card .value { font-size: 20px; font-weight: 700; color: #1a237e; }
.compare-card .build-id { font-size: 11px; color: #999; margin-top: 3px; word-break: break-all; }
table { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 15px; }
th { background: #e8eaf6; padding: 10px; text-align: left; font-weight: 600; }
td { padding: 8px 10px; border-bottom: 1px solid #eee; }
tr:hover { background: #f5f5f5; }
.diff-better { color: #4caf50; font-weight: 600; }
.diff-worse { color: #f44336; font-weight: 600; }
.diff-neutral { color: #999; }
.row-regression { background: #ffebee; }
.row-regression:hover { background: #ffcdd2; }
.row-improved { background: #e8f5e9; }
.row-improved:hover { background: #c8e6c9; }
.val-bad { color: #f44336; font-weight: 700; }
.val-good { color: #2e7d32; font-weight: 700; }
.section-divider td { background: #37474f; font-weight: 700; text-align: center; color: white; font-size: 14px; padding: 10px; }
.chart-container { margin-top: 15px; }
.empty-msg { text-align: center; padding: 40px; color: #999; font-size: 16px; }
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>TPMS Dynamic Comparison</h1>
        <div class="desc">Select two targets to compare performance metrics across profiles or within the same profile</div>
    </div>
    <div class="section">
        <h2>Target Selection</h2>
        <div class="target-grid">
            <div class="target-box">
                <h3>Target 1</h3>
                <div class="control-group"><label>Profile</label><select id="jobA" onchange="updateBuildIds('A')"></select></div>
                <div class="control-group"><label>Build ID</label><select id="buildIdA"></select></div>
            </div>
            <div class="target-box">
                <h3>Target 2</h3>
                <div class="control-group"><label>Profile</label><select id="jobB" onchange="updateBuildIds('B')"></select></div>
                <div class="control-group"><label>Build ID</label><select id="buildIdB"></select></div>
            </div>
        </div>
        <div class="btn-row">
            <button class="btn btn-primary" onclick="compare()">Compare</button>
            <button class="btn btn-secondary" id="downloadBtn" onclick="downloadExcel()" disabled>Download Excel</button>
        </div>
    </div>
    <div id="resultArea" class="section" style="display:none;">
        <h2 id="resultTitle"></h2>
        <div class="compare-grid" id="summaryCards"></div>
        <div class="chart-container"><canvas id="compareChart" height="100"></canvas></div>
        <table id="compareTable">
            <thead><tr><th>Metric</th><th id="thA">Target 1</th><th id="thB">Target 2</th><th>Diff</th><th>Change %</th><th>Verdict</th></tr></thead>
            <tbody id="compareBody"></tbody>
        </table>
    </div>
    <div id="emptyArea" class="section"><div class="empty-msg">Select profiles and build IDs, then click Compare</div></div>
</div>
<script>
var D = ''' + data_json + ''';
var chartInstance = null;
var lastCompareResult = null;

(function init() {
    var jobA = document.getElementById('jobA');
    var jobB = document.getElementById('jobB');
    D.jobs.forEach(function(j) {
        jobA.appendChild(new Option(j, j));
        jobB.appendChild(new Option(j, j));
    });
    if (D.jobs.length > 0) { jobA.value = D.jobs[0]; updateBuildIds('A'); }
    if (D.jobs.length > 1) { jobB.value = D.jobs[D.jobs.length - 1]; }
    else if (D.jobs.length > 0) { jobB.value = D.jobs[0]; }
    updateBuildIds('B');
})();

function updateBuildIds(side) {
    var jobSel = document.getElementById('job' + side);
    var buildIdSel = document.getElementById('buildId' + side);
    var job = jobSel.value;
    buildIdSel.innerHTML = '';
    var builds = D.builds_per_job[job] || [];
    builds.forEach(function(b) {
        var bid = (D.build_ids[job] && D.build_ids[job][b]) || null;
        var label = bid ? bid + ' (#' + b + ')' : '#' + b;
        buildIdSel.appendChild(new Option(label, b));
    });
    if (builds.length > 0) { buildIdSel.value = builds[0]; }
}

function compare() {
    var jobA = document.getElementById('jobA').value;
    var buildA = parseInt(document.getElementById('buildIdA').value);
    var jobB = document.getElementById('jobB').value;
    var buildB = parseInt(document.getElementById('buildIdB').value);
    if (!jobA || !jobB || isNaN(buildA) || isNaN(buildB)) { alert('Please select profiles and build IDs.'); return; }

    var dataA = (D.metric_data[jobA] && D.metric_data[jobA][buildA]) || {};
    var dataB = (D.metric_data[jobB] && D.metric_data[jobB][buildB]) || {};
    var metrics = D.key_metrics.filter(function(m) { return dataA[m] || dataB[m]; });

    if (metrics.length === 0) {
        document.getElementById('resultArea').style.display = 'none';
        document.getElementById('emptyArea').style.display = 'block';
        document.getElementById('emptyArea').innerHTML = '<div class="empty-msg">No metrics found</div>';
        document.getElementById('downloadBtn').disabled = true;
        return;
    }

    document.getElementById('resultArea').style.display = 'block';
    document.getElementById('emptyArea').style.display = 'none';
    document.getElementById('downloadBtn').disabled = false;

    var bidA = (D.build_ids[jobA] && D.build_ids[jobA][buildA]) || 'N/A';
    var bidB = (D.build_ids[jobB] && D.build_ids[jobB][buildB]) || 'N/A';
    var labelA = jobA + ' #' + buildA;
    var labelB = jobB + ' #' + buildB;
    document.getElementById('thA').textContent = labelA;
    document.getElementById('thB').textContent = labelB;
    document.getElementById('resultTitle').textContent = labelA + '  vs  ' + labelB;

    var cardsHtml = '<div class="compare-card"><h3>' + jobA + '</h3><div class="value">#' + buildA + '</div><div class="build-id">' + bidA + '</div></div>';
    cardsHtml += '<div class="compare-card"><h3>' + jobB + '</h3><div class="value">#' + buildB + '</div><div class="build-id">' + bidB + '</div></div>';
    document.getElementById('summaryCards').innerHTML = cardsHtml;

    var tbody = '';
    var chartLabels = [], chartA = [], chartB = [];
    var excelRows = [];

    metrics.forEach(function(m) {
        var va = dataA[m] ? dataA[m].value : null;
        var vb = dataB[m] ? dataB[m].value : null;
        var unit = D.metric_units[m] || '';
        var diffStr = '', pctStr = '', verdict = '', verdictClass = 'diff-neutral';
        var diffNum = null, pctNum = null;

        if (va !== null && vb !== null) {
            var diff = vb - va; diffNum = diff;
            diffStr = (diff >= 0 ? '+' : '') + diff.toFixed(2) + ' ' + unit;
            if (va !== 0) {
                var pct = ((vb - va) / Math.abs(va) * 100); pctNum = pct;
                pctStr = (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%';
                var lowerBetter = D.lower_is_better.indexOf(m) >= 0;
                var higherBetter = D.higher_is_better.indexOf(m) >= 0;
                if (lowerBetter) {
                    if (pct > 10) { verdict = 'WORSE'; verdictClass = 'diff-worse'; }
                    else if (pct < -10) { verdict = 'BETTER'; verdictClass = 'diff-better'; }
                    else { verdict = 'SIMILAR'; verdictClass = 'diff-neutral'; }
                } else if (higherBetter) {
                    if (pct > 10) { verdict = 'BETTER'; verdictClass = 'diff-better'; }
                    else if (pct < -10) { verdict = 'WORSE'; verdictClass = 'diff-worse'; }
                    else { verdict = 'SIMILAR'; verdictClass = 'diff-neutral'; }
                } else {
                    if (Math.abs(pct) > 10) { verdict = 'CHANGED'; verdictClass = 'diff-worse'; }
                    else { verdict = 'SIMILAR'; verdictClass = 'diff-neutral'; }
                }
            }
        } else {
            diffStr = 'N/A'; pctStr = 'N/A';
            verdict = (va === null && vb === null) ? 'N/A' : 'MISSING';
        }

        var vaStr = va !== null ? va.toFixed(2) + ' ' + unit : 'N/A';
        var vbStr = vb !== null ? vb.toFixed(2) + ' ' + unit : 'N/A';
        tbody += '<tr><td>' + m + '</td><td>' + vaStr + '</td><td>' + vbStr + '</td><td>' + diffStr + '</td><td>' + pctStr + '</td><td class="' + verdictClass + '">' + verdict + '</td></tr>';
        excelRows.push({ metric: m, target1: va, target2: vb, unit: unit, diff: diffNum, changePct: pctNum, verdict: verdict });
        if (va !== null && vb !== null) { chartLabels.push(m); chartA.push(va); chartB.push(vb); }
    });

    document.getElementById('compareBody').innerHTML = tbody;
    lastCompareResult = { jobA: jobA, buildA: buildA, bidA: bidA, jobB: jobB, buildB: buildB, bidB: bidB, rows: excelRows };

    if (chartInstance) { chartInstance.destroy(); }
    var ctx = document.getElementById('compareChart').getContext('2d');
    chartInstance = new Chart(ctx, {
        type: 'bar',
        data: { labels: chartLabels, datasets: [
            { label: labelA, data: chartA, backgroundColor: 'rgba(26,35,126,0.7)', borderColor: '#1a237e', borderWidth: 1 },
            { label: labelB, data: chartB, backgroundColor: 'rgba(233,30,99,0.7)', borderColor: '#e91e63', borderWidth: 1 }
        ]},
        options: { responsive: true, plugins: { legend: { position: 'top' }, title: { display: true, text: 'Metric Comparison' } }, scales: { y: { beginAtZero: false } } }
    });
}

function downloadExcel() {
    if (!lastCompareResult) { alert('Please run Compare first.'); return; }
    var r = lastCompareResult;
    var wsData = [['TPMS Performance Comparison'], [],
        ['Target 1', r.jobA + ' #' + r.buildA, r.bidA],
        ['Target 2', r.jobB + ' #' + r.buildB, r.bidB], [],
        ['Metric', 'Target 1', 'Target 2', 'Unit', 'Diff', 'Change %', 'Verdict']];
    r.rows.forEach(function(row) {
        wsData.push([row.metric, row.target1 !== null ? row.target1 : 'N/A', row.target2 !== null ? row.target2 : 'N/A', row.unit, row.diff !== null ? Math.round(row.diff * 100) / 100 : 'N/A', row.changePct !== null ? Math.round(row.changePct * 10) / 10 + '%' : 'N/A', row.verdict]);
    });
    var ws = XLSX.utils.aoa_to_sheet(wsData);
    ws['!cols'] = [{wch: 30}, {wch: 25}, {wch: 25}, {wch: 8}, {wch: 12}, {wch: 12}, {wch: 12}];
    var wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Comparison');
    XLSX.writeFile(wb, 'comparison_' + r.jobA + '_' + r.buildA + '_vs_' + r.jobB + '_' + r.buildB + '.xlsx');
}
</script>
</body>
</html>'''

    return html


# ---------------------------------------------------------------------------
# Build Labels Management API
# ---------------------------------------------------------------------------

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    """Admin login endpoint. Returns auth token on success."""
    data = request.get_json() or {}
    username = data.get('username', '')
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'error': 'Missing username or password'}), 400

    if verify_credentials(username, password):
        session.permanent = True
        session['admin_user'] = username
        session['last_activity'] = time.time()
        return jsonify({'success': True, 'username': username, 'timeout_seconds': 1800}), 200
    else:
        return jsonify({'error': 'Invalid credentials'}), 401


@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    """Admin logout endpoint."""
    session.pop('admin_user', None)
    session.pop('last_activity', None)
    return jsonify({'success': True}), 200


@app.route('/api/auth/check', methods=['GET'])
def api_check_auth():
    """Check if user is authenticated and return session status."""
    admin_user = session.get('admin_user')

    if not admin_user:
        return jsonify({
            'authenticated': False,
            'username': None,
            'timeout_warning': False,
            'time_remaining': 0
        }), 200

    # Check idle timeout (30 minutes = 1800 seconds)
    last_activity = session.get('last_activity', time.time())
    current_time = time.time()
    idle_time = current_time - last_activity
    timeout_seconds = 1800
    time_remaining = max(0, timeout_seconds - idle_time)

    # If idle timeout exceeded, logout automatically
    if idle_time > timeout_seconds:
        session.pop('admin_user', None)
        session.pop('last_activity', None)
        return jsonify({
            'authenticated': False,
            'username': None,
            'timeout_warning': False,
            'time_remaining': 0,
            'message': 'Session expired due to inactivity'
        }), 200

    # Do NOT update last_activity here - only check if timeout reached
    # Activity is updated only on actual API calls (login, label operations, etc.)

    # Show warning if less than 5 minutes remaining
    timeout_warning = time_remaining < 300

    return jsonify({
        'authenticated': True,
        'username': admin_user,
        'timeout_warning': timeout_warning,
        'time_remaining': int(time_remaining)
    }), 200


@app.route('/api/labels/<job>/<int:build>', methods=['GET'])
def api_get_label(job, build):
    """Get label for a specific job/build."""
    try:
        conn = get_db_conn(DB_PATH, read_only=True)
        label = get_label(conn, job, build)
        conn.close()
        return jsonify({'label': label or ''}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/labels/<job>/<int:build>', methods=['POST'])
def api_add_or_update_label(job, build):
    """Add or update label for a job/build. Requires admin authentication."""
    if not session.get('admin_user'):
        return jsonify({'error': 'Unauthorized'}), 401

    # Update last activity
    session['last_activity'] = time.time()

    data = request.get_json() or {}

    label = data.get('label', '').strip()

    if not label:
        return jsonify({'error': 'Label cannot be empty'}), 400

    try:
        conn = get_db_conn(DB_PATH, read_only=False)
        success = add_or_update_label(conn, job, build, label)
        conn.close()

        if success:
            return jsonify({'success': True, 'label': label}), 200
        else:
            return jsonify({'error': 'Failed to save label'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/labels/<job>/<int:build>', methods=['DELETE'])
def api_delete_label(job, build):
    """Delete label for a job/build. Requires admin authentication."""
    if not session.get('admin_user'):
        return jsonify({'error': 'Unauthorized'}), 401

    # Update last activity
    session['last_activity'] = time.time()

    try:

        conn = get_db_conn(DB_PATH, read_only=False)
        success = delete_label(conn, job, build)
        conn.close()

        if success:
            return jsonify({'success': True}), 200
        else:
            return jsonify({'error': 'Label not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/builds/<job>')
def api_admin_builds(job):
    """Get all builds for a job with their labels. For Label Manager UI."""
    if not session.get('admin_user'):
        return Response('Unauthorized', status=401)

    try:

        conn = get_db_conn(DB_PATH, read_only=True)
        json_data = get_builds_with_labels_json(conn, job)
        conn.close()
        return Response(json_data, content_type='application/json; charset=utf-8')
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# Run Test API (interactive test execution)
# ---------------------------------------------------------------------------

@app.route('/api/tests/types')
def api_test_types():
    """Return all registered test types (from TestRegistry)."""
    types = TestRegistry.get_all_types()
    return jsonify({'types': types})


@app.route('/api/tests/profiles')
def api_test_profiles():
    """Return available rpi profiles for test execution."""
    profiles = get_rpi_profiles()
    result = []
    for p in profiles:
        result.append({
            'name': p['name'],
            'description': p.get('description', ''),
            'version': p.get('version', ''),
            'arch': p.get('arch', ''),
        })
    return jsonify({'profiles': result})


@app.route('/api/tests/profiles/<path:profile_name>/items')
def api_test_items(profile_name):
    """Return available test items for a specific profile."""
    items = get_test_items_for_profile(profile_name)
    return jsonify({'items': items})


@app.route('/api/tests/profiles/<path:profile_name>/snapshots')
def api_profile_snapshots(profile_name):
    """Return available snapshot IDs for a profile."""
    snapshots = get_available_snapshots(profile_name)
    return jsonify({'snapshots': snapshots})


@app.route('/api/devices')
def api_devices():
    """Return list of connected sdb devices."""
    devices = check_connected_devices()
    return jsonify({'devices': devices})


@app.route('/api/run/test', methods=['POST'])
def api_run_test():
    """Create a new test task."""
    data = request.get_json() or {}

    test_type = data.get('test_type', 'standalone')
    profile = data.get('profile', '')
    selected_tests = data.get('selected_tests', [])
    snapshot_id = data.get('snapshot_id', 'latest')
    test_only = data.get('test_only', False)

    if not profile:
        return jsonify({'error': 'Profile is required'}), 400
    if not selected_tests:
        return jsonify({'error': 'At least one test must be selected'}), 400

    # Check device connection
    if not has_rpi_device():
        return jsonify({'error': 'No rpi device connected. Please connect a device before running tests.'}), 400

    # Create task
    tm = get_task_manager()
    tm.set_db_path(DB_PATH)

    created_by = session.get('admin_user', 'web')
    task = tm.create_task(
        test_type=test_type,
        profile=profile,
        selected_tests=selected_tests,
        snapshot_id=snapshot_id,
        test_only=test_only,
        created_by=created_by,
    )

    if task is None:
        return jsonify({'error': 'Failed to create task'}), 500

    return jsonify({'task_id': task.task_id, 'status': task.status}), 201


@app.route('/api/run/status')
def api_run_status():
    """Get queue status and current task."""
    tm = get_task_manager()
    return jsonify({
        'queue': tm.get_queue_status(),
        'current_task': tm.get_current_task().to_dict() if tm.get_current_task() else None,
    })


@app.route('/api/run/tasks')
def api_run_tasks():
    """List all tasks (newest first)."""
    tm = get_task_manager()
    tasks = [t.to_dict() for t in tm.get_all_tasks()]
    return jsonify({'tasks': tasks})


@app.route('/api/run/status/<task_id>')
def api_run_task_status(task_id):
    """Get status of a specific task."""
    tm = get_task_manager()
    task = tm.get_task(task_id)
    if task is None:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(task.to_dict())


@app.route('/api/run/logs/<task_id>')
def api_run_task_logs(task_id):
    """Get logs for a specific task. Supports offset parameter for polling."""
    tm = get_task_manager()
    task = tm.get_task(task_id)
    if task is None:
        return jsonify({'error': 'Task not found'}), 404

    offset = request.args.get('offset', 0, type=int)
    lines, total = task.get_logs(offset)

    return jsonify({
        'lines': lines,
        'total': total,
        'offset': offset,
        'has_more': False,  # logs are in-memory, no pagination needed
        'task_status': task.status,
    })


# ---------------------------------------------------------------------------
# Server runner
# ---------------------------------------------------------------------------

def run_server(db_path, port):
    """Run the Flask web server."""
    global DB_PATH
    DB_PATH = db_path

    # Verify DB is accessible
    conn = get_db_conn(db_path)
    conn.close()

    # Initialize task manager with DB path
    tm = get_task_manager()
    tm.set_db_path(db_path)

    print("TPMS web server (Flask) started on http://0.0.0.0:{}".format(port))
    print("  Database: {}".format(db_path))
    print("  Press Ctrl+C to stop")

    # Suppress werkzeug development server warning
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

    # threaded=True allows concurrent request handling while tests run in background
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)



# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='TPMS Performance Report Generator & Web Dashboard (Flask)')
    parser.add_argument('--db', default='tpms.db', help='SQLite database file')
    parser.add_argument('--job', help='Job/profile name')
    parser.add_argument('--build', type=int, help='Build number')
    parser.add_argument('--compare', metavar='JOBS',
                        help='Compare metric across jobs (comma-separated)')
    parser.add_argument('--metric', help='Metric name (for --compare)')
    parser.add_argument('--count', type=int, default=30, help='Number of builds for trend')
    parser.add_argument('--dynamic', action='store_true',
                        help='Generate dynamic comparison page (interactive)')
    parser.add_argument('--serve', action='store_true',
                        help='Run Flask HTTP server for real-time dashboard')
    parser.add_argument('--port', type=int, default=9090,
                        help='Port for serve mode (default: 9090)')
    parser.add_argument('--output', '-o', default='report.html', help='Output HTML file')
    args = parser.parse_args()

    if args.serve:
        run_server(args.db, args.port)
        return

    conn = get_db_conn(args.db)

    if args.dynamic:
        generate_dynamic_page(conn, args.output)
    elif args.compare:
        jobs = [j.strip() for j in args.compare.split(',')]
        if not args.metric:
            generate_compare_page(conn, jobs, args.output)
        else:
            generate_compare_page(conn, jobs, args.output, [args.metric])
    elif args.job:
        if args.build:
            compare_jobs = [j.strip() for j in args.compare.split(',')] if args.compare else None
            generate_report(conn, args.job, args.build, args.output, compare_jobs)
        else:
            generate_trend_page(conn, args.job, args.output, args.count)
    else:
        print("ERROR: --job, --compare, --dynamic, or --serve is required")
        parser.print_help()
        sys.exit(1)

    conn.close()


if __name__ == '__main__':
    main()
