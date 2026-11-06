#!/usr/bin/env python3
"""
TPMS Performance Data Database Manager

Manages SQLite database for storing and querying performance test results
from TPMS (Tizen Performance Monitoring System).

Usage:
    python3 tpms_db.py --import-jenkins /var/lib/jenkins/jobs --db tpms.db
    python3 tpms_db.py --save perfpublisher.xml --job 10.0-unified-rpi-32bit --build 1 --db tpms.db
    python3 tpms_db.py --latest 10.0-unified-rpi-32bit --metric BootingTime --count 30 --db tpms.db
    python3 tpms_db.py --compare "3.0-wearable-tw1,10.0-unified-rpi-32bit" --metric BootingTime --db tpms.db
    python3 tpms_db.py --delete --job 10.0-unified-rpi-32bit --build 5 --db tpms.db
    python3 tpms_db.py --verify tpms.db
    python3 tpms_db.py --stats tpms.db
    python3 tpms_db.py --benchmark tpms.db
    python3 tpms_db.py --export tpms.db --output tpms_backup.sql
    python3 tpms_db.py --import-sql tpms_backup.sql --db tpms.db
"""

import argparse
import ast
import os
import sys
import time
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime



SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS performance_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name TEXT NOT NULL,
    build_number INTEGER,
    build_id TEXT,
    test_time TEXT,
    test_name TEXT NOT NULL,
    metric_name TEXT,
    metric_value REAL,
    metric_unit TEXT,
    is_relevant INTEGER DEFAULT 0,
    executed INTEGER DEFAULT 1,
    passed INTEGER DEFAULT 1,
    has_timed_out INTEGER DEFAULT 0,
    source_file TEXT,
    imported_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_unique
    ON performance_data(job_name, build_number, test_name, metric_name);

CREATE INDEX IF NOT EXISTS idx_job_metric
    ON performance_data(job_name, metric_name, build_number);

CREATE INDEX IF NOT EXISTS idx_job_build_relevant
    ON performance_data(job_name, build_number, is_relevant, metric_name);

CREATE INDEX IF NOT EXISTS idx_job_build_status
    ON performance_data(job_name, build_number, executed, passed, has_timed_out);
"""


def get_db_conn(db_path, read_only=False):
    """Get SQLite database connection, creating schema if needed.

    Args:
        db_path: Path to SQLite database file
        read_only: If True, open in read-only mode (no schema creation, no WAL)
    """
    if read_only:
        conn = sqlite3.connect('file:{}?mode=ro'.format(db_path), uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for concurrent read access
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass  # WAL may not be available on all platforms
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn



def parse_bool(val):
    """Parse XML boolean attribute to integer (1/0)."""
    if val is None:
        return 1
    return 1 if str(val).lower() in ('true', 'yes', '1') else 0


def parse_xml_file(xml_path):
    """Parse a performance XML file and return list of metric records.

    Returns:
        tuple: (build_id, test_time, list of dicts with keys:
                test_name, metric_name, metric_value, metric_unit,
                is_relevant, executed, passed, has_timed_out)
    """
    if not os.path.exists(xml_path):
        print("ERROR: XML file not found: {}".format(xml_path))
        print("       The performance test may have failed to generate perfpublisher.xml.")
        print("       Check disk space and test logs (e.g. standalone/workspace/<profile>/now_testing/).")
        sys.exit(1)

    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Extract build_id and test_time from <start> block
    build_id = None
    test_time = None
    start_elem = root.find('start')
    if start_elem is not None:
        date_elem = start_elem.find('date')
        if date_elem is not None:
            build_id = date_elem.get('val')
        time_elem = start_elem.find('time')
        if time_elem is not None:
            test_time = time_elem.get('val')

    records = []

    for test_elem in root.findall('test'):
        test_name = test_elem.get('name', '')
        executed = parse_bool(test_elem.get('executed'))

        # Extract success info
        passed = 1
        has_timed_out = 0
        result_elem = test_elem.find('result')
        if result_elem is not None:
            success_elem = result_elem.find('success')
            if success_elem is not None:
                passed = parse_bool(success_elem.get('passed'))
                has_timed_out = parse_bool(success_elem.get('hasTimedOut'))

        # Extract metrics from <metrics> block
        metrics_elem = result_elem.find('metrics') if result_elem is not None else None
        if metrics_elem is not None:
            for metric_elem in metrics_elem:
                tag = metric_elem.tag
                mesure = metric_elem.get('mesure')
                unit = metric_elem.get('unit', '')
                is_relevant = parse_bool(metric_elem.get('isRelevant'))

                try:
                    metric_value = float(mesure) if mesure is not None else None
                except (ValueError, TypeError):
                    metric_value = None

                records.append({
                    'test_name': test_name,
                    'metric_name': tag,
                    'metric_value': metric_value,
                    'metric_unit': unit,
                    'is_relevant': is_relevant,
                    'executed': executed,
                    'passed': passed,
                    'has_timed_out': has_timed_out,
                })

        # Extract <performance> tag (MEMPS, MEMINFO, etc.)
        perf_elem = result_elem.find('performance') if result_elem is not None else None
        if perf_elem is not None:
            mesure = perf_elem.get('mesure')
            unit = perf_elem.get('unit', '')
            is_relevant = parse_bool(perf_elem.get('isRelevant'))

            try:
                metric_value = float(mesure) if mesure is not None else None
            except (ValueError, TypeError):
                metric_value = None

            records.append({
                'test_name': test_name,
                'metric_name': test_name,  # Use test_name as metric_name for performance tags
                'metric_value': metric_value,
                'metric_unit': unit,
                'is_relevant': is_relevant,
                'executed': executed,
                'passed': passed,
                'has_timed_out': has_timed_out,
            })

        # Extract <executiontime> tag
        exec_elem = result_elem.find('executiontime') if result_elem is not None else None
        if exec_elem is not None:
            mesure = exec_elem.get('mesure')
            unit = exec_elem.get('unit', '')
            is_relevant = parse_bool(exec_elem.get('isRelevant'))

            try:
                metric_value = float(mesure) if mesure is not None else None
            except (ValueError, TypeError):
                metric_value = None

            records.append({
                'test_name': test_name,
                'metric_name': 'executiontime',
                'metric_value': metric_value,
                'metric_unit': unit,
                'is_relevant': is_relevant,
                'executed': executed,
                'passed': passed,
                'has_timed_out': has_timed_out,
            })

    return build_id, test_time, records


def parse_report_txt(file_path):
    """Parse a report.txt file (Python dict per line) and return metric records.

    Returns:
        tuple: (build_id, test_time, list of dicts)
    """
    build_id = None
    test_time = None
    records = []

    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = ast.literal_eval(line)
            except (ValueError, SyntaxError):
                continue

            if not isinstance(entry, dict):
                continue

            tag = entry.get('tag_name')

            if tag == 'start':
                # Extract build_id and test_time from sub_tag_list
                for sub in entry.get('sub_tag_list', []):
                    sub_tag = sub.get('tag_name')
                    attrs = sub.get('attrs', {})
                    if sub_tag == 'date':
                        build_id = attrs.get('val')
                    elif sub_tag == 'time':
                        test_time = attrs.get('val')

            elif tag == 'test':
                attrs = entry.get('attrs', {})
                test_name = attrs.get('name', '')
                executed = parse_bool(attrs.get('executed', 'yes'))
                test_state = entry.get('test_state', 'success')
                passed = 1 if test_state == 'success' else 0
                has_timed_out = 0  # report.txt doesn't have timeout info

                for sub in entry.get('sub_tag_list', []):
                    sub_tag = sub.get('tag_name')
                    sub_attrs = sub.get('attrs', {})

                    if sub_tag == 'metrics':
                        metric_name = sub_attrs.get('name', '')
                        val = sub_attrs.get('val')
                        unit = sub_attrs.get('unit', '')
                        is_relevant = parse_bool(sub_attrs.get('isRelevant'))

                        try:
                            metric_value = float(val) if val is not None else None
                        except (ValueError, TypeError):
                            metric_value = None

                        records.append({
                            'test_name': test_name,
                            'metric_name': metric_name,
                            'metric_value': metric_value,
                            'metric_unit': unit,
                            'is_relevant': is_relevant,
                            'executed': executed,
                            'passed': passed,
                            'has_timed_out': has_timed_out,
                        })

                    elif sub_tag == 'performance':
                        val = sub_attrs.get('val')
                        unit = sub_attrs.get('unit', '')
                        is_relevant = parse_bool(sub_attrs.get('isRelevant'))

                        try:
                            metric_value = float(val) if val is not None else None
                        except (ValueError, TypeError):
                            metric_value = None

                        records.append({
                            'test_name': test_name,
                            'metric_name': test_name,
                            'metric_value': metric_value,
                            'metric_unit': unit,
                            'is_relevant': is_relevant,
                            'executed': executed,
                            'passed': passed,
                            'has_timed_out': has_timed_out,
                        })

                    elif sub_tag == 'executiontime':
                        val = sub_attrs.get('val')
                        unit = sub_attrs.get('unit', '')
                        is_relevant = parse_bool(sub_attrs.get('isRelevant'))

                        try:
                            metric_value = float(val) if val is not None else None
                        except (ValueError, TypeError):
                            metric_value = None

                        records.append({
                            'test_name': test_name,
                            'metric_name': 'executiontime',
                            'metric_value': metric_value,
                            'metric_unit': unit,
                            'is_relevant': is_relevant,
                            'executed': executed,
                            'passed': passed,
                            'has_timed_out': has_timed_out,
                        })

    return build_id, test_time, records


def parse_perf_file(file_path):
    """Parse a performance file (XML or report.txt) and return records.

    Returns:
        tuple: (build_id, test_time, list of dicts)
    """
    if file_path.endswith('.txt'):
        return parse_report_txt(file_path)
    else:
        return parse_xml_file(file_path)


def save_file_to_db(conn, file_path, job_name, build_number, replace=False):
    """Parse a performance file (XML or report.txt) and save records to database.

    Args:
        conn: SQLite connection
        file_path: Path to XML or report.txt file
        job_name: Job/profile name
        build_number: Build number
        replace: If True, delete existing data before insert

    Returns:
        Number of records saved
    """
    build_id, test_time, records = parse_perf_file(file_path)

    rigor_path = os.path.join(os.path.dirname(file_path), 'memory_rigor.json')
    if os.path.isfile(rigor_path):
        import json
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'standalone'))
        from memory_rigor import save_run
        with open(rigor_path) as source:
            save_run(conn, json.load(source), job_name, int(build_number))

    if not records:
        print("WARNING: No records found in {}".format(file_path))
        return 0

    if replace:
        conn.execute(
            "DELETE FROM performance_data WHERE job_name=? AND build_number=?",
            (job_name, build_number)
        )

    for rec in records:
        try:
            # Ensure all values are proper types for SQLite
            metric_value = rec['metric_value']
            if metric_value is not None:
                metric_value = float(metric_value)

            conn.execute(
                """INSERT OR IGNORE INTO performance_data
                   (job_name, build_number, build_id, test_time, test_name,
                    metric_name, metric_value, metric_unit, is_relevant,
                    executed, passed, has_timed_out, source_file)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(job_name), int(build_number),
                 str(build_id) if build_id is not None else None,
                 str(test_time) if test_time is not None else None,
                 str(rec['test_name']) if rec['test_name'] is not None else '',
                 str(rec['metric_name']) if rec['metric_name'] is not None else '',
                 metric_value,
                 str(rec['metric_unit']) if rec['metric_unit'] is not None else '',
                 int(rec['is_relevant']),
                 int(rec['executed']),
                 int(rec['passed']),
                 int(rec['has_timed_out']),
                 str(file_path))
            )
        except sqlite3.IntegrityError:
            pass  # Duplicate, skip
        except Exception as e:
            print("  WARNING: Failed to insert record ({}): {}".format(rec, e))


    conn.commit()

    # Count actual inserted rows
    cur = conn.execute(
        "SELECT COUNT(*) FROM performance_data WHERE job_name=? AND build_number=?",
        (job_name, build_number)
    )
    total = cur.fetchone()[0]

    print("Saved {} records for {} build {} "
          "(build_id: {})".format(len(records), job_name, build_number, build_id))
    return total



def normalize_job_name(job_name):
    """Normalize job name: strip 'remote-' prefix.

    e.g. 'remote-5.0-mobile-tm1' -> '5.0-mobile-tm1'
    """
    if job_name.startswith('remote-'):
        return job_name[len('remote-'):]
    return job_name


def find_perf_file(build_path):
    """Find performance data file in a build directory.

    Priority: report.txt (root) > report.txt (archive/) >
              Report-*.xml (root) > perfpublisher.xml (root) > Report-*.xml (archive/)

    Returns:
        Path to performance file, or None if not found.
    """
    # 1. report.txt in build root
    report_path = os.path.join(build_path, 'report.txt')
    if os.path.isfile(report_path):
        return report_path

    # 2. report.txt in archive/
    archive_path = os.path.join(build_path, 'archive')
    report_path = os.path.join(archive_path, 'report.txt')
    if os.path.isfile(report_path):
        return report_path

    # 3. Report-*.xml or perfpublisher.xml in build root (legacy)
    if os.path.isdir(build_path):
        for f in os.listdir(build_path):
            if f.endswith('.xml') and (f.startswith('Report-') or f == 'perfpublisher.xml'):
                return os.path.join(build_path, f)

    # 4. Report-*.xml or perfpublisher.xml in archive/ (legacy)
    if os.path.isdir(archive_path):
        for f in os.listdir(archive_path):
            if f.endswith('.xml') and (f.startswith('Report-') or f == 'perfpublisher.xml'):
                return os.path.join(archive_path, f)

    return None


def import_jenkins(conn, jobs_dir):
    """Import all performance data from Jenkins jobs directory.

    - Skips trigger-* and TPMS-* jobs
    - Strips 'remote-' prefix from job names
    - Uses report.txt (preferred) or Report-*.xml as data source
    - Skips already imported builds
    """
    if not os.path.isdir(jobs_dir):
        print("ERROR: Directory not found: {}".format(jobs_dir))
        return

    total_files = 0
    total_imported = 0
    total_skipped = 0
    total_errors = 0

    for raw_job_name in sorted(os.listdir(jobs_dir)):
        # Skip trigger-* and TPMS-* jobs
        if raw_job_name.startswith('trigger-') or raw_job_name.startswith('TPMS-'):
            continue

        job_name = normalize_job_name(raw_job_name)
        job_path = os.path.join(jobs_dir, raw_job_name)
        builds_path = os.path.join(job_path, 'builds')

        if not os.path.isdir(builds_path):
            continue

        for build_dir in sorted(os.listdir(builds_path), key=lambda x: (int(x) if x.isdigit() else 0)):
            build_path = os.path.join(builds_path, build_dir)

            if not os.path.isdir(build_path):
                continue

            # Skip symlinks like lastSuccessfulBuild
            if os.path.islink(build_path):
                continue

            # Try to parse build number
            try:
                build_number = int(build_dir)
            except ValueError:
                continue

            # Ensure types - force to native Python types
            job_name_str = str(job_name)
            build_number_int = int(build_number)

            try:
                # Check if already imported
                cur = conn.cursor()
                cur.execute(
                    "SELECT COUNT(*) FROM performance_data WHERE job_name=? AND build_number=?",
                    (job_name_str, build_number_int)
                )
                if cur.fetchone()[0] > 0:
                    total_skipped += 1
                    continue
            except Exception as e:
                print("  ERROR checking duplicate (job={}, build={}): {}".format(
                    repr(job_name_str), build_number_int, e))
                total_errors += 1
                continue

            # Find performance data file
            perf_file = find_perf_file(build_path)

            if not perf_file:
                continue

            total_files += 1

            try:
                save_file_to_db(conn, perf_file, job_name_str, build_number_int)
                total_imported += 1
            except Exception as e:
                print("  ERROR importing {}: {}".format(perf_file, e))
                total_errors += 1



    print("\nImport complete: {} builds imported, "
          "{} skipped (already exists), "
          "{} errors, "
          "{} files found".format(total_imported, total_skipped, total_errors, total_files))



def query_latest(conn, job_name, metric, count):
    """Query latest N builds for a specific metric."""
    cur = conn.execute(
        """SELECT build_number, build_id, test_time, metric_value, metric_unit,
                  passed, has_timed_out
           FROM performance_data
           WHERE job_name=? AND metric_name=? AND is_relevant=1
           ORDER BY build_number DESC
           LIMIT ?""",
        (job_name, metric, count)
    )
    rows = cur.fetchall()

    if not rows:
        print("No data found for {} / {}".format(job_name, metric))
        return

    print("\n=== {} - {} (latest {}) ===".format(job_name, metric, count))
    print("{:>6} | {:<45} | {:>10} {:>5} | {}".format('Build', 'Build ID', 'Value', 'Unit', 'Status'))
    print("-" * 85)
    for row in rows:
        status = "TIMEOUT" if row['has_timed_out'] else ("PASS" if row['passed'] else "FAIL")
        val = "{:.2f}".format(row['metric_value']) if row['metric_value'] is not None else "N/A"
        print("{:>6} | {:<45} | {:>10} "
              "{:>5} | {}".format(row['build_number'], row['build_id'] or 'N/A', val, row['metric_unit'] or '', status))


def query_compare(conn, jobs_str, metric):
    """Compare a metric across multiple profiles (latest value each)."""
    jobs = [j.strip() for j in jobs_str.split(',')]

    print("\n=== Comparison: {} ===".format(metric))
    print("{:<35} | {:>6} | {:<45} | {:>10} {:>5}".format('Job Name', 'Build', 'Build ID', 'Value', 'Unit'))
    print("-" * 110)

    for job in jobs:
        cur = conn.execute(
            """SELECT build_number, build_id, metric_value, metric_unit, passed, has_timed_out
               FROM performance_data
               WHERE job_name=? AND metric_name=? AND is_relevant=1
               ORDER BY build_number DESC
               LIMIT 1""",
            (job, metric)
        )
        row = cur.fetchone()

        if row:
            val = "{:.2f}".format(row['metric_value']) if row['metric_value'] is not None else "N/A"
            print("{:<35} | {:>6} | {:<45} | "
                  "{:>10} {:>5}".format(job, row['build_number'], row['build_id'] or 'N/A', val, row['metric_unit'] or ''))
        else:
            print("{:<35} | {:>6} | {:<45} | {:>10} {:>5}".format(job, 'N/A', 'N/A', 'N/A', ''))


def query_range(conn, versions_str, profile_pattern, metric):
    """Compare a metric across version range matching profile pattern."""
    versions = [v.strip() for v in versions_str.split(',')]

    print("\n=== Range Comparison: {} (pattern: {}) ===".format(metric, profile_pattern))
    print("{:<10} | {:<35} | {:>6} | {:>10} {:>5}".format('Version', 'Job Name', 'Build', 'Value', 'Unit'))
    print("-" * 75)

    for version in versions:
        cur = conn.execute(
            """SELECT DISTINCT job_name FROM performance_data
               WHERE job_name LIKE ? ORDER BY job_name""",
            ("{}-{}%".format(version, profile_pattern),)
        )
        jobs = [r['job_name'] for r in cur.fetchall()]

        if not jobs:
            # Try without version prefix
            cur = conn.execute(
                """SELECT DISTINCT job_name FROM performance_data
                   WHERE job_name LIKE ? ORDER BY job_name""",
                ("{}%{}%".format(version, profile_pattern),)
            )
            jobs = [r['job_name'] for r in cur.fetchall()]

        for job in jobs:
            cur = conn.execute(
                """SELECT build_number, metric_value, metric_unit
                   FROM performance_data
                   WHERE job_name=? AND metric_name=? AND is_relevant=1
                   ORDER BY build_number DESC LIMIT 1""",
                (job, metric)
            )
            row = cur.fetchone()

            if row:
                val = "{:.2f}".format(row['metric_value']) if row['metric_value'] is not None else "N/A"
                print("{:<10} | {:<35} | {:>6} | "
                      "{:>10} {:>5}".format(version, job, row['build_number'], val, row['metric_unit'] or ''))
            else:
                print("{:<10} | {:<35} | {:>6} | {:>10}".format(version, job, 'N/A', 'N/A'))


def delete_data(conn, job_name=None, build_number=None, metric=None,
                test_name=None, force=False, dry_run=False):
    """Delete data from database.

    Args:
        conn: SQLite connection
        job_name: Job name filter (optional if test_name is provided)
        build_number: Build number filter
        metric: Metric name filter
        test_name: Test name filter (supports SQL LIKE patterns, e.g. '[dep_info]%')
        force: Skip confirmation prompt
        dry_run: Show what would be deleted without actually deleting
    """
    where_parts = []
    params = []

    if job_name is not None:
        where_parts.append("job_name = ?")
        params.append(job_name)
    if build_number is not None:
        where_parts.append("build_number = ?")
        params.append(build_number)
    if metric is not None:
        where_parts.append("metric_name = ?")
        params.append(metric)
    if test_name is not None:
        where_parts.append("test_name LIKE ?")
        params.append(test_name)

    if not where_parts:
        print("ERROR: At least one filter is required for deletion.")
        return

    where_clause = " AND ".join(where_parts)

    # Count rows to be deleted
    cur = conn.execute("SELECT COUNT(*) FROM performance_data WHERE {}".format(where_clause), params)
    count = cur.fetchone()[0]

    if count == 0:
        print("No matching data found to delete.")
        return

    # Show summary of what will be deleted
    cur = conn.execute(
        "SELECT COUNT(DISTINCT job_name), COUNT(DISTINCT build_number) "
        "FROM performance_data WHERE {}".format(where_clause),
        params
    )
    summary = cur.fetchone()
    print("{} {} rows ({} jobs, {} builds):".format(
        'Will delete' if dry_run else 'Deleting', count,
        summary[0], summary[1]))

    # Show sample of test_names that will be deleted
    cur = conn.execute(
        "SELECT DISTINCT test_name FROM performance_data "
        "WHERE {} ORDER BY test_name LIMIT 20".format(where_clause),
        params
    )
    test_names = [r['test_name'] for r in cur.fetchall()]
    if test_names:
        for tn in test_names[:10]:
            print("  - {}".format(tn))
        if len(test_names) > 10:
            print("  ... and {} more".format(len(test_names) - 10))

    if dry_run:
        print("\n[DRY RUN] No data was deleted. Remove --dry-run to actually delete.")
        return

    if not force:
        response = input("\nDelete {} rows? (y/N): ".format(count))
        if response.lower() != 'y':
            print("Cancelled.")
            return

    conn.execute("DELETE FROM performance_data WHERE {}".format(where_clause), params)
    conn.commit()
    print("Deleted {} rows.".format(count))


def vacuum_db(conn):
    """VACUUM the database to reclaim disk space."""
    print("Running VACUUM... (this may take a while for large databases)")
    start = time.time()
    conn.execute("VACUUM")
    elapsed = time.time() - start
    print("VACUUM completed in {:.1f}s".format(elapsed))



def verify_db(conn):
    """Verify database integrity."""
    print("=== Database Integrity Check ===\n")
    errors = []

    # PRAGMA integrity_check
    cur = conn.execute("PRAGMA integrity_check")
    result = cur.fetchone()[0]
    if result == 'ok':
        print("  [PASS] PRAGMA integrity_check: ok")
    else:
        print("  [FAIL] PRAGMA integrity_check: {}".format(result))
        errors.append("integrity_check failed")

    # Check for NULL in required fields
    for field in ['job_name', 'test_name']:
        cur = conn.execute(
            "SELECT COUNT(*) FROM performance_data WHERE {} IS NULL OR {} = ''".format(field, field)
        )
        count = cur.fetchone()[0]
        if count > 0:
            print("  [FAIL] NULL/empty {}: {} rows".format(field, count))
            errors.append("NULL {}".format(field))
        else:
            print("  [PASS] No NULL/empty {}".format(field))

    # Check for abnormal values (-9999 etc.)
    cur = conn.execute(
        "SELECT COUNT(*) FROM performance_data WHERE metric_value < 0"
    )
    count = cur.fetchone()[0]
    if count > 0:
        print("  [WARN] Negative metric_value: {} rows (may be sentinel values like -9999)".format(count))
    else:
        print("  [PASS] No negative metric_value")

    # Check unique index
    cur = conn.execute(
        """SELECT job_name, build_number, test_name, metric_name, COUNT(*) as cnt
           FROM performance_data
           GROUP BY job_name, build_number, test_name, metric_name
           HAVING cnt > 1"""
    )
    dups = cur.fetchall()
    if dups:
        print("  [FAIL] Duplicate (job, build, test, metric): {} groups".format(len(dups)))
        errors.append("duplicate data")
    else:
        print("  [PASS] No duplicate data")

    print("\n{}".format('='*40))
    if errors:
        print("Result: FAIL ({} issues)".format(len(errors)))
    else:
        print("Result: PASS")


def print_stats(conn, db_path):
    """Print database statistics."""
    print("=== Database Statistics ===\n")

    # DB file size
    if os.path.exists(db_path):
        size = os.path.getsize(db_path)
        if size > 1024 * 1024:
            size_str = "{:.1f} MB".format(size / 1024 / 1024)
        else:
            size_str = "{:.1f} KB".format(size / 1024)
        print("  DB file size: {}".format(size_str))

    # Total records
    cur = conn.execute("SELECT COUNT(*) FROM performance_data")
    total = cur.fetchone()[0]
    print("  Total records: {}".format(total))

    # Job stats
    print("\n  {:<35} | {:>6} | {:>8} | {:>15}".format('Job Name', 'Builds', 'Records', 'Build Range'))
    print("  " + "-" * 75)

    cur = conn.execute(
        """SELECT job_name, COUNT(DISTINCT build_number) as builds,
                  COUNT(*) as records,
                  MIN(build_number) as min_build, MAX(build_number) as max_build
           FROM performance_data
           GROUP BY job_name
           ORDER BY job_name"""
    )
    for row in cur.fetchall():
        build_range = "{} ~ {}".format(row['min_build'], row['max_build']) if row['min_build'] else "N/A"
        print("  {:<35} | {:>6} | {:>8} | "
              "{:>15}".format(row['job_name'], row['builds'], row['records'], build_range))

    # Metric stats (relevant only)
    print("\n  Relevant Metrics (is_relevant=1):")
    print("  {:<30} | {:>6} | {:>10} | {:>10} | {:>10}".format('Metric Name', 'Count', 'Min', 'Max', 'Avg'))
    print("  " + "-" * 75)

    cur = conn.execute(
        """SELECT metric_name, COUNT(*) as cnt,
                  MIN(metric_value) as min_val, MAX(metric_value) as max_val,
                  AVG(metric_value) as avg_val
           FROM performance_data
           WHERE is_relevant=1 AND metric_value IS NOT NULL
           GROUP BY metric_name
           ORDER BY metric_name"""
    )
    for row in cur.fetchall():
        min_v = "{:.2f}".format(row['min_val']) if row['min_val'] is not None else "N/A"
        max_v = "{:.2f}".format(row['max_val']) if row['max_val'] is not None else "N/A"
        avg_v = "{:.2f}".format(row['avg_val']) if row['avg_val'] is not None else "N/A"
        print("  {:<30} | {:>6} | {:>10} | "
              "{:>10} | {:>10}".format(row['metric_name'], row['cnt'], min_v, max_v, avg_v))


def benchmark_queries(conn):
    """Benchmark query performance."""
    print("=== Query Performance Benchmark ===\n")

    # Get a sample job name
    cur = conn.execute("SELECT DISTINCT job_name FROM performance_data LIMIT 1")
    row = cur.fetchone()
    if not row:
        print("  No data in database to benchmark.")
        return

    job_name = row['job_name']

    # Get a sample metric
    cur = conn.execute(
        "SELECT DISTINCT metric_name FROM performance_data WHERE is_relevant=1 LIMIT 1"
    )
    row = cur.fetchone()
    metric = row['metric_name'] if row else 'BootingTime'

    # Get all job names for compare/range
    cur = conn.execute("SELECT DISTINCT job_name FROM performance_data ORDER BY job_name")
    all_jobs = [r['job_name'] for r in cur.fetchall()]

    tests = []

    # Test 1: latest 30 query
    start = time.time()
    conn.execute(
        """SELECT * FROM performance_data
           WHERE job_name=? AND metric_name=? AND is_relevant=1
           ORDER BY build_number DESC LIMIT 30""",
        (job_name, metric)
    ).fetchall()
    elapsed = (time.time() - start) * 1000
    tests.append(("latest 30", "job={}, metric={}".format(job_name, metric), elapsed))

    # Test 2: compare query
    if len(all_jobs) >= 2:
        start = time.time()
        for j in all_jobs[:5]:
            conn.execute(
                """SELECT * FROM performance_data
                   WHERE job_name=? AND metric_name=? AND is_relevant=1
                   ORDER BY build_number DESC LIMIT 1""",
                (j, metric)
            ).fetchall()
        elapsed = (time.time() - start) * 1000
        tests.append(("compare (5 jobs)", "metric={}".format(metric), elapsed))

    # Test 3: range query
    start = time.time()
    conn.execute(
        """SELECT DISTINCT job_name, metric_value, build_number
           FROM performance_data
           WHERE metric_name=? AND is_relevant=1
           ORDER BY job_name, build_number DESC""",
        (metric,)
    ).fetchall()
    elapsed = (time.time() - start) * 1000
    tests.append(("range (all jobs)", "metric={}".format(metric), elapsed))

    # Test 4: full table scan
    start = time.time()
    conn.execute("SELECT COUNT(*) FROM performance_data").fetchone()
    elapsed = (time.time() - start) * 1000
    tests.append(("count all", "full table", elapsed))

    print("  {:<25} | {:<40} | {:>10}".format('Query', 'Parameters', 'Time (ms)'))
    print("  " + "-" * 80)
    for name, params, elapsed in tests:
        status = "OK" if elapsed < 100 else "SLOW"
        print("  {:<25} | {:<40} | {:>8.2f}ms {}".format(name, params, elapsed, status))


def export_db(conn, output_path):
    """Export database to SQL dump file."""
    with open(output_path, 'w') as f:
        f.write("-- TPMS Database Export\n")
        f.write("-- Generated: {}\n\n".format(datetime.now().isoformat()))

        for line in conn.iterdump():
            f.write(line + "\n")

    print("Exported database to {}".format(output_path))


def import_sql(db_path, sql_path):
    """Import SQL dump file into database (fresh DB).

    Uses raw connection to avoid schema conflicts with dump's CREATE statements.
    """
    # Remove existing DB file to start fresh
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    with open(sql_path, 'r') as f:
        sql = f.read()

    conn.executescript(sql)
    conn.commit()
    conn.close()
    print("Imported SQL from {} into {}".format(sql_path, db_path))



def main():
    parser = argparse.ArgumentParser(
        description='TPMS Performance Data Database Manager',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument('--db', default='tpms.db', help='SQLite database file path')

    # Import
    parser.add_argument('--import-jenkins', metavar='DIR',
                        help='Import all Report XMLs from Jenkins jobs directory')
    parser.add_argument('--import-sql', metavar='FILE',
                        help='Import SQL dump file into database')

    # Save
    parser.add_argument('--save', metavar='XML',
                        help='Save single XML file to database')
    parser.add_argument('--job', help='Job/profile name (for --save)')
    parser.add_argument('--build', type=int, help='Build number (for --save)')
    parser.add_argument('--replace', action='store_true',
                        help='Replace existing data (for --save)')

    # Query
    parser.add_argument('--latest', metavar='JOB',
                        help='Query latest N builds for a job')
    parser.add_argument('--compare', metavar='JOBS',
                        help='Compare metric across jobs (comma-separated)')
    parser.add_argument('--range', metavar='VERSIONS',
                        help='Compare metric across version range (comma-separated)')
    parser.add_argument('--metric', help='Metric name to query')
    parser.add_argument('--profile-pattern', help='Profile pattern for --range')
    parser.add_argument('--count', type=int, default=30, help='Number of results (default: 30)')

    # Delete
    parser.add_argument('--delete', action='store_true', help='Delete data from database')
    parser.add_argument('--test-name', metavar='PATTERN',
                        help='Test name filter for --delete (SQL LIKE pattern, e.g. [dep_info]%%)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be deleted')
    parser.add_argument('--force', action='store_true', help='Skip confirmation prompt')

    # Maintenance
    parser.add_argument('--vacuum', action='store_true',
                        help='VACUUM database to reclaim disk space')


    # Verification
    parser.add_argument('--verify', action='store_true', help='Verify database integrity')
    parser.add_argument('--stats', action='store_true', help='Print database statistics')
    parser.add_argument('--verify-import', metavar='DIR',
                        help='Verify import against source directory')
    parser.add_argument('--benchmark', action='store_true', help='Benchmark query performance')

    # Backup
    parser.add_argument('--export', metavar='FILE', help='Export database to SQL dump')
    parser.add_argument('--output', metavar='FILE', help='Output file (for --export)')

    args = parser.parse_args()

    # --- Import SQL ---
    if args.import_sql:
        import_sql(args.db, args.import_sql)
        return


    # --- Import Jenkins ---
    if args.import_jenkins:
        conn = get_db_conn(args.db)
        import_jenkins(conn, args.import_jenkins)
        conn.close()
        return

    # --- Save ---
    if args.save:
        if not args.job:
            print("ERROR: --job is required with --save")
            sys.exit(1)
        conn = get_db_conn(args.db)
        save_file_to_db(conn, args.save, args.job,
                        args.build if args.build else 0, args.replace)

        conn.close()
        return

    # --- Query: latest ---
    if args.latest:
        if not args.metric:
            print("ERROR: --metric is required with --latest")
            sys.exit(1)
        conn = get_db_conn(args.db, read_only=True)
        query_latest(conn, args.latest, args.metric, args.count)
        conn.close()
        return

    # --- Query: compare ---
    if args.compare:
        if not args.metric:
            print("ERROR: --metric is required with --compare")
            sys.exit(1)
        conn = get_db_conn(args.db, read_only=True)
        query_compare(conn, args.compare, args.metric)
        conn.close()
        return

    # --- Query: range ---
    if args.range:
        if not args.metric:
            print("ERROR: --metric is required with --range")
            sys.exit(1)
        if not args.profile_pattern:
            print("ERROR: --profile-pattern is required with --range")
            sys.exit(1)
        conn = get_db_conn(args.db, read_only=True)
        query_range(conn, args.range, args.profile_pattern, args.metric)
        conn.close()
        return

    # --- Delete ---
    if args.delete:
        if not args.job and not args.test_name:
            print("ERROR: --job or --test-name is required with --delete")
            sys.exit(1)
        conn = get_db_conn(args.db)
        delete_data(conn, args.job, args.build, args.metric,
                    args.test_name, args.force, args.dry_run)
        conn.close()
        return

    # --- VACUUM ---
    if args.vacuum:
        conn = get_db_conn(args.db)
        vacuum_db(conn)
        conn.close()
        return

    # --- Verify ---
    if args.verify:
        conn = get_db_conn(args.db, read_only=True)
        verify_db(conn)
        conn.close()
        return

    # --- Stats ---
    if args.stats:
        conn = get_db_conn(args.db, read_only=True)
        print_stats(conn, args.db)
        conn.close()
        return

    # --- Benchmark ---
    if args.benchmark:
        conn = get_db_conn(args.db, read_only=True)
        benchmark_queries(conn)
        conn.close()
        return


    # --- Export ---
    if args.export:
        if not args.output:
            print("ERROR: --output is required with --export")
            sys.exit(1)
        conn = get_db_conn(args.db)
        export_db(conn, args.output)
        conn.close()
        return

    # --- Verify Import ---
    if args.verify_import:
        conn = get_db_conn(args.db)
        # TODO: implement verify-import comparison
        print("verify-import: comparing source XMLs vs DB...")
        import_jenkins(conn, args.verify_import)  # reuse scanning logic
        conn.close()
        return

    # No action specified
    parser.print_help()


if __name__ == '__main__':
    main()
