#!/usr/bin/env python3
"""
TPMS Test Runner - Background task management for interactive web execution.

Manages a task queue that executes TPMS standalone tests in background threads.
Only one task runs at a time; others are queued.

Key features:
- TestRegistry: pluggable test types (extensible for future test flows)
- TaskManager: single-concurrency queue with log capture and DB auto-import
- Log persistence to files named with the task's build_number timestamp
"""

import configparser
import json
import logging
import os
import re
import subprocess
import threading
import time
import traceback
from datetime import datetime

logger = logging.getLogger('tpms.runner')

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# db/ directory (this file's directory)
DB_DIR = os.path.dirname(os.path.abspath(__file__))
# standalone/ directory (sibling of db/)
STANDALONE_DIR = os.path.join(os.path.dirname(DB_DIR), 'standalone')
# testprofiles.cfg
TESTPROFILES_CFG = os.path.join(STANDALONE_DIR, 'testprofiles.cfg')
# Log directory for task logs
TASK_LOG_DIR = os.path.join(DB_DIR, 'task_logs')


# ---------------------------------------------------------------------------
# Test Registry (extensible for future test types)
# ---------------------------------------------------------------------------

class TestRegistry:
    """
    Registry for test types. New test flows can be registered here.

    Each entry:
        key: unique identifier (used in API and frontend)
        name: display name
        description: human-readable description
        runner: function name in TaskManager that executes this test type
        config_source: config file path (relative to standalone dir)
    """

    _registry = {
        'standalone': {
            'name': 'Standalone Performance Test',
            'description': 'Standard TPMS performance test: flash image → run tests → collect results',
            'runner': '_run_standalone_test',
            'config_source': 'testprofiles.cfg',
        },
        # Future test types can be added here:
        # 'custom_benchmark': {
        #     'name': 'Custom Benchmark',
        #     'description': 'Custom benchmark flow',
        #     'runner': '_run_custom_benchmark',
        #     'config_source': 'custom.cfg',
        # },
    }

    @classmethod
    def get_all_types(cls):
        """Return list of registered test types for API consumption."""
        result = []
        for key, info in cls._registry.items():
            result.append({
                'type': key,
                'name': info['name'],
                'description': info['description'],
            })
        return result

    @classmethod
    def get_info(cls, test_type):
        """Return info for a specific test type, or None if not found."""
        return cls._registry.get(test_type)

    @classmethod
    def get_runner_method(cls, test_type):
        """Return the runner method name for a test type."""
        info = cls._registry.get(test_type)
        if info:
            return info['runner']
        return None


# ---------------------------------------------------------------------------
# Config parsing helpers
# ---------------------------------------------------------------------------

def parse_testprofiles(cfg_path=TESTPROFILES_CFG):
    """
    Parse testprofiles.cfg and return list of profile sections.

    Returns:
        list of dicts: [{name, version, profile, arch, ...}, ...]
    """
    if not os.path.exists(cfg_path):
        logger.error("testprofiles.cfg not found: %s", cfg_path)
        return []

    config = configparser.ConfigParser(interpolation=None)
    config.read(cfg_path)

    profiles = []
    for section in config.sections():
        if section == 'common':
            continue
        entry = {'name': section}
        for key in config[section]:
            entry[key] = config[section][key]
        profiles.append(entry)

    return profiles


def get_rpi_profiles(cfg_path=TESTPROFILES_CFG):
    """Return only rpi-related profiles (filtering for unified-rpi)."""
    profiles = parse_testprofiles(cfg_path)
    return [p for p in profiles if 'unified-rpi' in p['name']]


def get_profile_config(profile_name, cfg_path=TESTPROFILES_CFG):
    """Return config dict for a specific profile."""
    config = configparser.ConfigParser(interpolation=None)
    config.read(cfg_path)
    if profile_name not in config.sections():
        return None
    entry = {'name': profile_name}
    for key in config[profile_name]:
        entry[key] = config[profile_name][key]
    return entry


def parse_tizen_version(profile_name):
    """
    Extract tizen version from profile name.
    e.g. '11.0-unified-rpi-64bit' -> '11.0'
         '10.1-unified-rpi-toolchain-32bit' -> '10.1'
    """
    match = re.match(r'^(\d+\.\d+)', profile_name)
    if match:
        return match.group(1)
    return None


def get_tizen_profile(profile_name):
    """
    Extract the TIZEN_PROFILE (without version prefix) from profile name.
    e.g. '11.0-unified-rpi-64bit' -> 'unified-rpi-64bit'
    """
    match = re.match(r'^\d+\.\d+-(.+)$', profile_name)
    if match:
        return match.group(1)
    return profile_name


def get_test_items_for_profile(profile_name):
    """
    Parse the tpms_cfg_*.json for a profile and return test items with enable status.

    Returns:
        list of {name, enabled} dicts
    """
    profile_config = get_profile_config(profile_name)
    if not profile_config:
        return []

    cfg_file = profile_config.get('tpms_cfg', '')
    if not cfg_file:
        return []

    cfg_path = os.path.join(STANDALONE_DIR, cfg_file)
    if not os.path.exists(cfg_path):
        logger.error("tpms_cfg not found: %s", cfg_path)
        return []

    with open(cfg_path, 'r') as f:
        cfg_data = json.load(f)

    enabled = cfg_data.get('enabled', {})
    # Filter out non-test entries like 'save_target_images'
    skip_keys = {'save_target_images'}
    test_items = []
    for key, val in enabled.items():
        if key in skip_keys:
            continue
        test_items.append({
            'name': key,
            'enabled': val == 'enable',
        })

    return test_items


def create_temp_config(profile_name, selected_tests):
    """
    Create a temporary tpms_cfg JSON with only selected tests enabled.

    Args:
        profile_name: profile name (e.g. '11.0-unified-rpi-64bit')
        selected_tests: list of test names to enable

    Returns:
        path to temp config file, or None on failure
    """
    profile_config = get_profile_config(profile_name)
    if not profile_config:
        return None

    cfg_file = profile_config.get('tpms_cfg', '')
    if not cfg_file:
        return None

    cfg_path = os.path.join(STANDALONE_DIR, cfg_file)
    if not os.path.exists(cfg_path):
        return None

    with open(cfg_path, 'r') as f:
        cfg_data = json.load(f)

    # Update enabled dict
    enabled = cfg_data.get('enabled', {})
    for key in enabled:
        if key == 'save_target_images':
            continue
        enabled[key] = 'enable' if key in selected_tests else 'disable'

    cfg_data['enabled'] = enabled

    # Write temp config
    temp_cfg_name = cfg_file.replace('.json', '_temp.json')
    temp_cfg_path = os.path.join(STANDALONE_DIR, temp_cfg_name)
    with open(temp_cfg_path, 'w') as f:
        json.dump(cfg_data, f, indent=4)

    return temp_cfg_path


# ---------------------------------------------------------------------------
# Device checking
# ---------------------------------------------------------------------------

def check_connected_devices():
    """
    Run 'sdb devices' and return list of connected devices.

    Returns:
        list of {serial, type} dicts
    """
    try:
        result = subprocess.run(
            ['sdb', 'devices'],
            capture_output=True, text=True, timeout=15
        )
        devices = []
        for line in result.stdout.strip().split('\n'):
            line = line.strip()
            if not line or line.startswith('List') or line.startswith('*'):
                continue
            parts = line.split()
            if len(parts) >= 3:
                devices.append({
                    'serial': parts[0],
                    'state': parts[1],
                    'type': parts[2],
                })
        return devices
    except Exception as e:
        logger.error("Failed to check devices: %s", e)
        return []


def has_rpi_device():
    """Check if at least one rpi device is connected."""
    devices = check_connected_devices()
    for d in devices:
        if 'rpi' in d.get('type', '').lower():
            return True
    return False


# ---------------------------------------------------------------------------
# Snapshot ID fetching
# ---------------------------------------------------------------------------

def get_available_snapshots(profile_name):
    """
    Fetch available snapshot IDs for a profile by parsing the snapshot directory.

    Returns:
        list of snapshot ID strings (e.g. ['20260907.1', '20260906.2', ...])
        Returns ['latest'] if fetching fails.
    """
    profile_config = get_profile_config(profile_name)
    if not profile_config:
        return ['latest']

    platform_url = profile_config.get('platform_url', '')
    if not platform_url:
        return ['latest']

    # platform_url ends with /latest/images/standard/...
    # We need to go up to the parent of 'latest' to list available snapshots
    # e.g. .../Tizen-Unified/latest/images/... -> .../Tizen-Unified/
    # The snapshot dirs are like tizen-unified_YYYYMMDD.N/

    # Find 'latest' in the URL and get the parent directory
    url_parts = platform_url.rstrip('/').split('/')
    try:
        latest_idx = url_parts.index('latest')
        parent_url = '/'.join(url_parts[:latest_idx]) + '/'
    except ValueError:
        return ['latest']

    try:
        result = subprocess.run(
            ['wget', '-q', '-O', '-', parent_url],
            capture_output=True, text=True, timeout=30
        )
        html = result.stdout
        if not html:
            return ['latest']

        # Parse directory listing for snapshot IDs
        # Look for patterns like tizen-unified_YYYYMMDD.N or tizen-VERSION-unified_YYYYMMDD.N
        pattern = re.compile(r'(tizen[\w-]*_\d{8}\.\d+)')

        # Also handle toolchain URLs
        pattern_toolchain = re.compile(r'(tizen[\w-]*-toolchain_\d{8}\.\d+)')

        snapshots = set()
        for match in pattern.finditer(html):
            snapshots.add(match.group(1))
        for match in pattern_toolchain.finditer(html):
            snapshots.add(match.group(1))

        # Extract just the version part (YYYYMMDD.N)
        version_pattern = re.compile(r'(\d{8}\.\d+)')
        versions = set()
        for s in snapshots:
            vmatch = version_pattern.search(s)
            if vmatch:
                versions.add(vmatch.group(1))

        # Sort descending (newest first)
        sorted_versions = sorted(versions, reverse=True)
        if sorted_versions:
            return ['latest'] + sorted_versions[:50]  # Limit to 50
        return ['latest']

    except Exception as e:
        logger.warning("Failed to fetch snapshots for %s: %s", profile_name, e)
        return ['latest']


# ---------------------------------------------------------------------------
# Task representation
# ---------------------------------------------------------------------------

class Task:
    """Represents a single test execution task."""

    def __init__(self, task_id, test_type, profile, selected_tests,
                 snapshot_id, test_only, build_number, created_by):
        self.task_id = task_id
        self.test_type = test_type
        self.profile = profile
        self.selected_tests = selected_tests  # list of test names
        self.snapshot_id = snapshot_id
        self.test_only = test_only
        self.build_number = build_number  # timestamp string like '20260907_193456'
        self.created_by = created_by

        self.status = 'pending'  # pending, running, completed, failed
        self.created_at = datetime.now().isoformat()
        self.started_at = None
        self.finished_at = None
        self.error_message = None
        self.result_job = None  # job name for DB import
        self.result_build_number = None  # build number for DB

        # Log buffer (in-memory, for real-time polling)
        self._log_lines = []
        self._log_lock = threading.Lock()

        # Log file path
        self.log_file = os.path.join(TASK_LOG_DIR, '{}_{}.log'.format(
            build_number, task_id))

    def append_log(self, line):
        """Append a log line (thread-safe)."""
        with self._log_lock:
            self._log_lines.append(line)

    def get_logs(self, offset=0):
        """Get log lines from offset. Returns (lines, total_count)."""
        with self._log_lock:
            lines = self._log_lines[offset:]
            return lines, len(self._log_lines)

    def to_dict(self):
        """Serialize task to dict for API response."""
        return {
            'task_id': self.task_id,
            'test_type': self.test_type,
            'profile': self.profile,
            'selected_tests': self.selected_tests,
            'snapshot_id': self.snapshot_id,
            'test_only': self.test_only,
            'build_number': self.build_number,
            'created_by': self.created_by,
            'status': self.status,
            'created_at': self.created_at,
            'started_at': self.started_at,
            'finished_at': self.finished_at,
            'error_message': self.error_message,
            'result_job': self.result_job,
            'result_build_number': self.result_build_number,
        }


# ---------------------------------------------------------------------------
# Task Manager
# ---------------------------------------------------------------------------

class TaskManager:
    """
    Manages test task queue with single concurrency.

    Only one task runs at a time. Others wait in queue.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self._tasks = {}  # task_id -> Task
        self._task_order = []  # list of task_ids in creation order
        self._queue_lock = threading.Lock()
        self._current_task = None
        self._next_task_id = 1
        self._worker_thread = None
        self._db_path = None

        # Ensure log directory exists
        os.makedirs(TASK_LOG_DIR, exist_ok=True)

    def set_db_path(self, db_path):
        """Set the SQLite DB path for auto-importing results."""
        self._db_path = db_path

    def create_task(self, test_type, profile, selected_tests, snapshot_id,
                    test_only, created_by='web'):
        """
        Create a new task and add to queue.

        Returns:
            Task object, or None if a task is already running/queued for the same profile.
        """
        with self._queue_lock:
            # Check if there's already a running or queued task
            for task in self._tasks.values():
                if task.status in ('pending', 'running'):
                    # Allow queuing, but warn
                    pass

            # Generate task ID and build_number
            task_id = 'task_{}'.format(self._next_task_id)
            self._next_task_id += 1

            build_number = datetime.now().strftime('%Y%m%d_%H%M%S')

            task = Task(
                task_id=task_id,
                test_type=test_type,
                profile=profile,
                selected_tests=selected_tests,
                snapshot_id=snapshot_id,
                test_only=test_only,
                build_number=build_number,
                created_by=created_by,
            )

            self._tasks[task_id] = task
            self._task_order.append(task_id)

        # Start worker thread if not running
        self._ensure_worker()

        return task

    def get_task(self, task_id):
        """Get a task by ID."""
        return self._tasks.get(task_id)

    def get_all_tasks(self):
        """Get all tasks (newest first)."""
        return [self._tasks[tid] for tid in reversed(self._task_order)]

    def get_current_task(self):
        """Get the currently running task, or None."""
        return self._current_task

    def get_queue_status(self):
        """Get queue status summary."""
        running = 0
        pending = 0
        completed = 0
        failed = 0
        for task in self._tasks.values():
            if task.status == 'running':
                running += 1
            elif task.status == 'pending':
                pending += 1
            elif task.status == 'completed':
                completed += 1
            elif task.status == 'failed':
                failed += 1
        return {
            'running': running,
            'pending': pending,
            'completed': completed,
            'failed': failed,
            'total': len(self._tasks),
        }

    def _ensure_worker(self):
        """Ensure the worker thread is running."""
        if self._worker_thread is None or not self._worker_thread.is_alive():
            self._worker_thread = threading.Thread(
                target=self._worker_loop, daemon=True
            )
            self._worker_thread.start()

    def _worker_loop(self):
        """Main worker loop: pick next pending task and execute."""
        while True:
            # Find next pending task
            next_task = None
            with self._queue_lock:
                for task_id in self._task_order:
                    task = self._tasks[task_id]
                    if task.status == 'pending':
                        next_task = task
                        break

            if next_task is None:
                # No more tasks, exit worker
                break

            self._execute_task(next_task)

    def _execute_task(self, task):
        """Execute a single task."""
        task.status = 'running'
        task.started_at = datetime.now().isoformat()
        self._current_task = task

        self._log(task, '=' * 60)
        self._log(task, 'Task started: {}'.format(task.task_id))
        self._log(task, '  Test type: {}'.format(task.test_type))
        self._log(task, '  Profile: {}'.format(task.profile))
        self._log(task, '  Selected tests: {}'.format(', '.join(task.selected_tests)))
        self._log(task, '  Snapshot ID: {}'.format(task.snapshot_id))
        self._log(task, '  Test only: {}'.format(task.test_only))
        self._log(task, '  Build number: {}'.format(task.build_number))
        self._log(task, '=' * 60)

        try:
            # Get runner method for this test type
            runner_name = TestRegistry.get_runner_method(task.test_type)
            if runner_name:
                runner_func = getattr(self, runner_name, None)
                if runner_func:
                    success = runner_func(task)
                else:
                    raise Exception("Runner method {} not found".format(runner_name))
            else:
                raise Exception("Unknown test type: {}".format(task.test_type))

            if success:
                task.status = 'completed'
                self._log(task, '\n✓ Task completed successfully!')
            else:
                task.status = 'failed'
                task.error_message = 'Test execution returned failure'
                self._log(task, '\n✗ Task failed: test execution returned failure')

        except Exception as e:
            task.status = 'failed'
            task.error_message = str(e)
            self._log(task, '\n✗ Task failed with exception:')
            self._log(task, traceback.format_exc())

        finally:
            task.finished_at = datetime.now().isoformat()
            self._current_task = None
            self._log(task, '\nTask finished at: {}'.format(task.finished_at))
            self._log(task, 'Final status: {}'.format(task.status))

    def _log(self, task, message):
        """Write log line to task buffer and file."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        line = '[{}] {}'.format(timestamp, message)
        task.append_log(line)

        # Also write to file
        try:
            with open(task.log_file, 'a') as f:
                f.write(line + '\n')
        except Exception as e:
            logger.warning("Failed to write log file: %s", e)

    # -----------------------------------------------------------------------
    # Test runner: standalone
    # -----------------------------------------------------------------------

    def _run_standalone_test(self, task):
        """
        Execute the standalone TPMS test flow.

        This calls TPMS.sh which handles:
        1. Download image (if not test_only)
        2. Flash to device
        3. Install plugins
        4. Run standalone.py tests
        5. Generate report

        Then imports results to DB.
        """
        profile_name = task.profile
        tizen_version = parse_tizen_version(profile_name)
        tizen_profile = get_tizen_profile(profile_name)

        if not tizen_version:
            raise Exception("Could not parse tizen version from profile: {}".format(profile_name))

        self._log(task, 'Parsed: version={}, profile={}'.format(tizen_version, tizen_profile))

        # Check device connection
        self._log(task, '\n--- Checking device connection ---')
        devices = check_connected_devices()
        if devices:
            for d in devices:
                self._log(task, '  Found device: {} ({})'.format(d['serial'], d['type']))
        else:
            raise Exception('No devices connected. Please connect an rpi device before running tests.')

        # Create temp config with selected tests
        self._log(task, '\n--- Creating temporary config ---')
        temp_cfg_path = create_temp_config(profile_name, task.selected_tests)
        if not temp_cfg_path:
            raise Exception('Failed to create temporary config for profile: {}'.format(profile_name))
        self._log(task, '  Temp config: {}'.format(temp_cfg_path))

        # Prepare workspace
        workspace_dir = os.path.join(STANDALONE_DIR, 'workspace')
        os.makedirs(workspace_dir, exist_ok=True)

        # Build TPMS.sh command
        # TPMS.sh expects: profile tizen_version test_only snapshot_id
        # But we need to use our temp config, so we'll call standalone.py directly
        # with a modified testprofiles.cfg that points to our temp config

        # Actually, the cleanest approach: call TPMS.sh which does everything
        # But TPMS.sh uses the original testprofiles.cfg. We need to modify
        # the tpms_cfg path temporarily.

        # Strategy: Create a temp testprofiles.cfg that points to our temp tpms_cfg
        temp_cfg_name = os.path.basename(temp_cfg_path)

        # Read original testprofiles.cfg, modify the tpms_cfg for our profile
        config = configparser.ConfigParser(interpolation=None)
        config.read(TESTPROFILES_CFG)

        if profile_name in config.sections():
            original_cfg = config[profile_name].get('tpms_cfg', '')
            config[profile_name]['tpms_cfg'] = temp_cfg_name

            temp_testprofiles_path = os.path.join(STANDALONE_DIR, 'testprofiles_temp.cfg')
            with open(temp_testprofiles_path, 'w') as f:
                config.write(f)

            self._log(task, '  Temp testprofiles.cfg: {}'.format(temp_testprofiles_path))
        else:
            raise Exception('Profile {} not found in testprofiles.cfg'.format(profile_name))

        # Build the TPMS.sh command
        test_only_str = 'true' if task.test_only else 'false'

        # TPMS.sh uses environment variables CURRENT_DIR, WORKSPACE_DIR, etc.
        # It expects to be run from the standalone/ directory
        cmd = [
            'bash', 'TPMS.sh',
            tizen_profile,
            tizen_version,
            test_only_str,
            task.snapshot_id,
        ]

        self._log(task, '\n--- Executing TPMS.sh ---')
        self._log(task, '  Command: {}'.format(' '.join(cmd)))
        self._log(task, '  Working dir: {}'.format(STANDALONE_DIR))
        self._log(task, '  Workspace: {}'.format(workspace_dir))

        # Run TPMS.sh as subprocess, capturing output in real-time
        env = os.environ.copy()
        env['CURRENT_DIR'] = STANDALONE_DIR
        env['WORKSPACE_DIR'] = workspace_dir
        env['COMMON_DIR'] = os.path.join(STANDALONE_DIR, 'common')

        process = subprocess.Popen(
            cmd,
            cwd=STANDALONE_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            text=True,
            bufsize=1,
        )

        # Read output line by line
        for line in process.stdout:
            line = line.rstrip('\n')
            self._log(task, line)

        process.wait()
        return_code = process.returncode

        self._log(task, '\nTPMS.sh exited with code: {}'.format(return_code))

        # Check for termination file
        terminate_file = os.path.join(workspace_dir, 'Terminate_Test.txt')
        if os.path.exists(terminate_file):
            with open(terminate_file, 'r') as f:
                terminate_reason = f.read().strip()
            self._log(task, 'Test terminated: {}'.format(terminate_reason))
            # Don't fail completely - we might still have partial results

        # Clean up temp files
        try:
            os.remove(temp_testprofiles_path)
            os.remove(temp_cfg_path)
        except Exception:
            pass

        # Import results to DB
        self._log(task, '\n--- Importing results to database ---')
        self._import_results_to_db(task, profile_name, workspace_dir)

        if return_code != 0:
            self._log(task, 'TPMS.sh returned non-zero exit code')
            # Still consider it a partial success if we imported results
            # The task status will be set by _execute_task based on return value

        return return_code == 0

    def _import_results_to_db(self, task, profile_name, workspace_dir):
        """
        Find test results in workspace and import to SQLite DB.

        Looks for report.txt or perfpublisher.xml in the workspace directory.
        """
        if not self._db_path:
            self._log(task, '  DB path not set, skipping import')
            return

        # Find result files
        # Results are in workspace_dir/<profile_name>/<snapshot_id>/
        # The snapshot_id in standalone.py is set from the device's BUILD_ID
        # or stays as "now_testing"

        result_dirs = []
        profile_result_dir = os.path.join(workspace_dir, profile_name)
        if os.path.isdir(profile_result_dir):
            for subdir in os.listdir(profile_result_dir):
                subdir_path = os.path.join(profile_result_dir, subdir)
                if os.path.isdir(subdir_path):
                    result_dirs.append(subdir_path)

        if not result_dirs:
            self._log(task, '  No result directories found in {}'.format(profile_result_dir))
            return

        # Use the most recent result dir
        result_dir = max(result_dirs, key=os.path.getmtime)
        self._log(task, '  Result directory: {}'.format(result_dir))

        # Find report.txt or perfpublisher.xml
        report_file = None
        for candidate in ['report.txt', 'perfpublisher.xml']:
            path = os.path.join(result_dir, candidate)
            if os.path.exists(path):
                report_file = path
                break

        if not report_file:
            self._log(task, '  No report.txt or perfpublisher.xml found in result directory')
            return

        self._log(task, '  Found result file: {}'.format(report_file))

        # Import to DB using tpms_db module
        try:
            # Add db dir to path
            import sys
            if DB_DIR not in sys.path:
                sys.path.insert(0, DB_DIR)

            from tpms_db import get_db_conn, save_file_to_db

            # Use build_number as build_number in DB
            # Convert timestamp to integer for DB (use epoch seconds)
            build_num_int = int(datetime.strptime(
                task.build_number, '%Y%m%d_%H%M%S'
            ).timestamp())

            conn = get_db_conn(self._db_path)
            count = save_file_to_db(
                conn, report_file,
                job_name=profile_name,
                build_number=build_num_int,
                replace=True
            )
            conn.close()

            self._log(task, '  Imported {} records to DB (job={}, build={})'.format(
                count, profile_name, build_num_int))

            task.result_job = profile_name
            task.result_build_number = build_num_int

        except Exception as e:
            self._log(task, '  ERROR importing to DB: {}'.format(e))
            self._log(task, traceback.format_exc())


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

def get_task_manager():
    """Get the singleton TaskManager instance."""
    return TaskManager()
