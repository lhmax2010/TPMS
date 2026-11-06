/* TPMS Run Test Page - JavaScript */

var runPollInterval = null;
var runLogOffset = 0;
var runCurrentTaskId = null;
var runLogAutoScroll = true;

// --- Initialize run page ---
function initRunPage() {
    loadTestTypes();
    loadProfiles();
    loadDeviceStatus();
    loadQueueStatus();
    loadTaskList();

    // Start polling for queue status
    if (runPollInterval) clearInterval(runPollInterval);
    runPollInterval = setInterval(function() {
        loadQueueStatus();
        loadTaskList();
        if (runCurrentTaskId) {
            pollTaskLogs(runCurrentTaskId);
        }
    }, 3000); // Poll every 3 seconds
}

// --- Load test types ---
function loadTestTypes() {
    fetch('/api/tests/types')
    .then(function(r) { return r.json(); })
    .then(function(data) {
        var select = document.getElementById('runTestType');
        if (!select) return;
        select.innerHTML = '';
        data.types.forEach(function(t) {
            var opt = document.createElement('option');
            opt.value = t.type;
            opt.textContent = t.name;
            select.appendChild(opt);
        });
    })
    .catch(function(err) {
        console.error('Failed to load test types:', err);
    });
}

// --- Load profiles ---
function loadProfiles() {
    fetch('/api/tests/profiles')
    .then(function(r) { return r.json(); })
    .then(function(data) {
        var select = document.getElementById('runProfile');
        if (!select) return;
        select.innerHTML = '<option value="">-- Select Profile --</option>';
        data.profiles.forEach(function(p) {
            var opt = document.createElement('option');
            opt.value = p.name;
            opt.textContent = p.name + ' (' + p.arch + ')';
            select.appendChild(opt);
        });
    })
    .catch(function(err) {
        console.error('Failed to load profiles:', err);
    });
}

// --- Load test items for selected profile ---
function onProfileChange() {
    var profile = document.getElementById('runProfile').value;
    var container = document.getElementById('runTestItems');
    var snapshotSelect = document.getElementById('runSnapshotId');

    if (!profile) {
        container.innerHTML = '<div class="empty-msg">Select a profile first</div>';
        snapshotSelect.innerHTML = '<option value="latest">latest</option>';
        return;
    }

    // Load test items
    container.innerHTML = '<div class="loading-msg">Loading test items...</div>';
    fetch('/api/tests/profiles/' + encodeURIComponent(profile) + '/items')
    .then(function(r) { return r.json(); })
    .then(function(data) {
        container.innerHTML = '';
        if (data.items.length === 0) {
            container.innerHTML = '<div class="empty-msg">No test items found</div>';
            return;
        }
        data.items.forEach(function(item) {
            var div = document.createElement('div');
            div.className = 'run-test-item';

            var checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.id = 'test_' + item.name;
            checkbox.value = item.name;
            checkbox.checked = item.enabled;

            var label = document.createElement('label');
            label.htmlFor = 'test_' + item.name;
            label.textContent = item.name;

            var status = document.createElement('span');
            status.className = 'test-status ' + (item.enabled ? 'enabled' : 'disabled');
            status.textContent = item.enabled ? 'ON' : 'OFF';

            div.appendChild(checkbox);
            div.appendChild(label);
            div.appendChild(status);
            container.appendChild(div);
        });
    })
    .catch(function(err) {
        container.innerHTML = '<div class="run-error-msg">Failed to load test items: ' + err.message + '</div>';
    });

    // Load snapshots
    snapshotSelect.innerHTML = '<option value="latest">latest</option>';
    var snapshotLoading = document.getElementById('runSnapshotLoading');
    if (snapshotLoading) snapshotLoading.style.display = 'inline';

    fetch('/api/tests/profiles/' + encodeURIComponent(profile) + '/snapshots')
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (snapshotLoading) snapshotLoading.style.display = 'none';
        data.snapshots.forEach(function(s) {
            var opt = document.createElement('option');
            opt.value = s;
            opt.textContent = s;
            snapshotSelect.appendChild(opt);
        });
    })
    .catch(function(err) {
        if (snapshotLoading) snapshotLoading.style.display = 'none';
        console.error('Failed to load snapshots:', err);
    });
}

// --- Load device status ---
function loadDeviceStatus() {
    var container = document.getElementById('runDeviceStatus');
    if (!container) return;

    fetch('/api/devices')
    .then(function(r) { return r.json(); })
    .then(function(data) {
        var hasRpi = false;
        var deviceList = [];
        data.devices.forEach(function(d) {
            deviceList.push(d.serial + ' (' + d.type + ')');
            if (d.type.toLowerCase().indexOf('rpi') >= 0) hasRpi = true;
        });

        if (hasRpi) {
            container.className = 'run-device-status connected';
            container.innerHTML = '<span class="device-dot"></span> Device connected: ' + deviceList.join(', ');
        } else if (data.devices.length > 0) {
            container.className = 'run-device-status disconnected';
            container.innerHTML = '<span class="device-dot"></span> Device connected but not rpi: ' + deviceList.join(', ');
        } else {
            container.className = 'run-device-status disconnected';
            container.innerHTML = '<span class="device-dot"></span> No device connected';
        }
    })
    .catch(function(err) {
        container.className = 'run-device-status disconnected';
        container.innerHTML = '<span class="device-dot"></span> Failed to check device: ' + err.message;
    });
}

// --- Run test ---
function runTest() {
    var testType = document.getElementById('runTestType').value;
    var profile = document.getElementById('runProfile').value;
    var snapshotId = document.getElementById('runSnapshotId').value;
    var testOnly = document.getElementById('runTestOnly').checked;

    // Get selected tests
    var selectedTests = [];
    var checkboxes = document.querySelectorAll('#runTestItems input[type="checkbox"]:checked');
    checkboxes.forEach(function(cb) { selectedTests.push(cb.value); });

    if (!profile) {
        alert('Please select a profile.');
        return;
    }
    if (selectedTests.length === 0) {
        alert('Please select at least one test.');
        return;
    }

    var btn = document.getElementById('runTestBtn');

    btn.disabled = true;
    btn.textContent = 'Starting...';

    fetch('/api/run/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            test_type: testType,
            profile: profile,
            selected_tests: selectedTests,
            snapshot_id: snapshotId,
            test_only: testOnly,
        })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        btn.disabled = false;
        btn.textContent = '▶ Run Test';

        if (data.error) {
            alert('Error: ' + data.error);
            return;
        }

        // Task created, start monitoring
        runCurrentTaskId = data.task_id;
        runLogOffset = 0;
        showTaskMonitor(data.task_id);
        loadQueueStatus();
        loadTaskList();
    })
    .catch(function(err) {
        btn.disabled = false;
        btn.textContent = '▶ Run Test';
        alert('Failed to start test: ' + err.message);
    });
}

// --- Show task monitor ---
function showTaskMonitor(taskId) {
    var monitor = document.getElementById('runTaskMonitor');
    monitor.style.display = 'block';

    var viewer = document.getElementById('runLogViewer');
    viewer.innerHTML = '';

    // Poll immediately
    pollTaskLogs(taskId);
}

// --- Poll task logs ---
function pollTaskLogs(taskId) {
    fetch('/api/run/logs/' + taskId + '?offset=' + runLogOffset)
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.error) return;

        var viewer = document.getElementById('runLogViewer');

        data.lines.forEach(function(line) {
            var div = document.createElement('div');
            div.className = 'log-line';

            // Highlight certain lines
            if (line.indexOf('✓') >= 0 || line.indexOf('success') >= 0) {
                div.className += ' success';
            } else if (line.indexOf('✗') >= 0 || line.indexOf('ERROR') >= 0 || line.indexOf('error') >= 0) {
                div.className += ' error';
            } else if (line.indexOf('---') >= 0 || line.indexOf('===') >= 0) {
                div.className += ' section';
            }

            div.textContent = line;
            viewer.appendChild(div);
        });

        runLogOffset = data.total;

        // Auto scroll
        if (runLogAutoScroll) {
            viewer.scrollTop = viewer.scrollHeight;
        }

        // Update task status display
        var statusBadge = document.getElementById('runMonitorStatus');
        if (statusBadge) {
            statusBadge.className = 'run-task-status-badge ' + data.task_status;
            statusBadge.textContent = data.task_status;
        }

        // If task finished, show result link
        if (data.task_status === 'completed' || data.task_status === 'failed') {
            loadTaskStatus(taskId);
        }
    })
    .catch(function(err) {
        console.error('Failed to poll logs:', err);
    });
}

// --- Load task status (for result link) ---
function loadTaskStatus(taskId) {
    fetch('/api/run/status/' + taskId)
    .then(function(r) { return r.json(); })
    .then(function(data) {
        var resultArea = document.getElementById('runTaskResult');
        if (data.status === 'completed' && data.result_job && data.result_build_number) {
            resultArea.innerHTML = '<a class="run-result-link" href="#" onclick="showBuildReport(\'' +
                data.result_job + '\', ' + data.result_build_number + '); return false;">📊 View Report</a>';
        } else if (data.status === 'failed') {
            resultArea.innerHTML = '<div class="run-error-msg">Task failed: ' + (data.error_message || 'Unknown error') + '</div>';
        }
    })
    .catch(function(err) {
        console.error('Failed to load task status:', err);
    });
}

// --- Show build report (reuse dashboard function) ---
function showBuildReport(job, build) {
    showBuildPage(job, build);
}

// --- Load queue status ---
function loadQueueStatus() {
    fetch('/api/run/status')
    .then(function(r) { return r.json(); })
    .then(function(data) {
        var container = document.getElementById('runQueueStatus');
        if (!container) return;

        var q = data.queue;
        container.innerHTML =
            '<span class="run-queue-badge running">Running: ' + q.running + '</span>' +
            '<span class="run-queue-badge pending">Pending: ' + q.pending + '</span>' +
            '<span class="run-queue-badge completed">Completed: ' + q.completed + '</span>' +
            '<span class="run-queue-badge failed">Failed: ' + q.failed + '</span>';

        // Update current task display
        var currentTask = document.getElementById('runCurrentTask');
        if (data.current_task) {
            currentTask.innerHTML = '<strong>Current:</strong> ' + data.current_task.profile +
                ' (' + data.current_task.status + ')';
        } else {
            currentTask.innerHTML = '<strong>Current:</strong> Idle';
        }
    })
    .catch(function(err) {
        console.error('Failed to load queue status:', err);
    });
}

// --- Load task list ---
function loadTaskList() {
    fetch('/api/run/tasks')
    .then(function(r) { return r.json(); })
    .then(function(data) {
        var container = document.getElementById('runTaskList');
        if (!container) return;

        if (data.tasks.length === 0) {
            container.innerHTML = '<div class="empty-msg">No tasks yet</div>';
            return;
        }

        container.innerHTML = '';
        data.tasks.forEach(function(task) {
            var card = document.createElement('div');
            card.className = 'run-task-card status-' + task.status;

            var info = document.createElement('div');
            info.className = 'run-task-info';

            var title = document.createElement('div');
            title.className = 'run-task-title';
            title.textContent = task.profile + ' - ' + task.test_type;

            var meta = document.createElement('div');
            meta.className = 'run-task-meta';
            var metaText = task.created_at + ' | Tests: ' + task.selected_tests.length;
            if (task.error_message) {
                metaText += ' | Error: ' + task.error_message;
            }
            meta.textContent = metaText;

            info.appendChild(title);
            info.appendChild(meta);

            var actions = document.createElement('div');
            actions.className = 'run-task-actions';

            var badge = document.createElement('span');
            badge.className = 'run-task-status-badge ' + task.status;
            badge.textContent = task.status;
            actions.appendChild(badge);

            // Add view button for completed tasks with results
            if (task.status === 'completed' && task.result_job && task.result_build_number) {
                var link = document.createElement('a');
                link.className = 'run-result-link';
                link.href = '#';
                link.onclick = function(e) {
                    e.preventDefault();
                    showBuildReport(task.result_job, task.result_build_number);
                };
                link.textContent = '📊 Report';
                actions.appendChild(link);
            }

            // Add monitor button for running/pending tasks
            if (task.status === 'running' || task.status === 'pending') {
                var monitorBtn = document.createElement('button');
                monitorBtn.className = 'btn';
                monitorBtn.style.cssText = 'padding:4px 12px;font-size:12px;background:#1a237e;color:white;';
                monitorBtn.textContent = '📋 Monitor';
                monitorBtn.onclick = function() {
                    runCurrentTaskId = task.task_id;
                    runLogOffset = 0;
                    showTaskMonitor(task.task_id);
                };
                actions.appendChild(monitorBtn);
            }

            card.appendChild(info);
            card.appendChild(actions);
            container.appendChild(card);
        });
    })
    .catch(function(err) {
        console.error('Failed to load task list:', err);
    });
}

// --- Toggle auto scroll ---
function toggleLogAutoScroll() {
    runLogAutoScroll = document.getElementById('runLogAutoScroll').checked;
}
