"""Focused API and query regression tests for the TPMS web dashboard."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'db'))

import tpms_web
from tpms_constants import evaluate_regression
from tpms_db import get_db_conn
from tpms_db_queries import get_summary_data_json


class TpmsWebTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        conn = get_db_conn(self.path)
        rows = []
        for build, value in enumerate((100, 101, 99, 100, 130), 1):
            rows.append(('job-a', build, 'id-{}'.format(build), '2026-01-{:02d}'.format(build),
                         'Booting Time', 'BootingTime', value, 'ms', 1, 1, 1, 0))
        rows.append(('job-a', 5, 'id-5', '2026-01-05', 'Timeout test', 'Other', None, 'ms', 0, 1, 0, 1))
        conn.executemany("""INSERT INTO performance_data
            (job_name, build_number, build_id, test_time, test_name, metric_name,
             metric_value, metric_unit, is_relevant, executed, passed, has_timed_out)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", rows)
        conn.commit()
        conn.close()
        tpms_web.DB_PATH = self.path
        self.client = tpms_web.app.test_client()

    def tearDown(self):
        os.unlink(self.path)

    def test_summary_contains_data_quality_warnings(self):
        conn = get_db_conn(self.path, read_only=True)
        payload = json.loads(get_summary_data_json(conn))
        conn.close()
        self.assertEqual(payload['summary'][0]['metrics']['BootingTime']['value'], 130)
        self.assertTrue(any('TIMEOUT' in warning for warning in payload['summary'][0]['warnings']))
        self.assertTrue(any('MISSING' in warning for warning in payload['summary'][0]['warnings']))

    def test_health_and_conditional_catalog(self):
        health = self.client.get('/healthz')
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json['status'], 'ok')
        catalog = self.client.get('/api/compare/catalog')
        self.assertEqual(catalog.status_code, 200)
        self.assertEqual(self.client.get('/api/compare/catalog', headers={
            'If-None-Match': catalog.headers['ETag']}).status_code, 304)

    def test_median_mad_regression_ignores_single_outlier(self):
        decision = evaluate_regression('BootingTime', 130, [100, 101, 99, 100])
        self.assertTrue(decision['regression'])
        self.assertFalse(evaluate_regression('BootingTime', 105, [100, 1000, 100, 101])['regression'])


if __name__ == '__main__':
    unittest.main()
