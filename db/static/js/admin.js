/* TPMS Admin - Build Labels Management */

var adminUser = 'web';  // Auth disabled - always logged in
var adminSessionCheckInterval = null;
var adminWarningShown = false;


// Show admin login modal
function showAdminLoginModal() {
    document.getElementById('adminLoginModal').classList.add('active');
    document.getElementById('adminUsername_input').focus();
}

// Close admin login modal
function closeAdminLoginModal() {
    document.getElementById('adminLoginModal').classList.remove('active');
    document.getElementById('adminLoginError').style.display = 'none';
    document.getElementById('adminUsername_input').value = '';
    document.getElementById('adminPassword_input').value = '';
}

// Admin login
function adminLogin() {
    var username = document.getElementById('adminUsername_input').value.trim();
    var password = document.getElementById('adminPassword_input').value;

    if (!username || !password) {
        showAdminLoginError('Please enter username and password');
        return;
    }

    fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username, password: password })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.success) {
            adminUser = username;
            closeAdminLoginModal();
            updateAdminUI();
            startSessionCheck();
            showMenuPage('admin', null);
            loadAdminJobs();
        } else {
            showAdminLoginError(data.error || 'Login failed');
        }
    })
    .catch(function(err) {
        showAdminLoginError('Error: ' + err.message);
    });
}

// Admin logout
function adminLogout() {
    fetch('/api/auth/logout', { method: 'POST' })
    .then(function() {
        adminUser = null;
        adminWarningShown = false;
        stopSessionCheck();
        closeSessionWarningModal();
        resetLabelManager();
        updateAdminUI();
        showMenuPage('summary', document.querySelector('.menu li'));
    });
}

// Reset Label Manager state
function resetLabelManager() {
    var select = document.getElementById('adminJobSelect');
    if (select) {
        select.innerHTML = '<option value="">-- Select a profile --</option>';
    }
    var tbody = document.getElementById('adminBuildsList');
    if (tbody) {
        tbody.innerHTML = '';
    }
    var container = document.getElementById('adminBuildsContainer');
    if (container) {
        container.style.display = 'none';
    }
}

// Show login error
function showAdminLoginError(message) {
    var errorDiv = document.getElementById('adminLoginError');
    errorDiv.textContent = message;
    errorDiv.style.display = 'block';
}

// Update admin UI based on login state
function updateAdminUI() {
    var sidebarAdmin = document.getElementById('sidebarAdmin');
    var sidebarAdminUser = document.getElementById('sidebarAdminUser');
    var labelManagerMenu = document.getElementById('labelManagerMenu');

    if (adminUser) {
        sidebarAdmin.style.display = 'none';
        sidebarAdminUser.style.display = 'flex';
        labelManagerMenu.style.display = 'block';
        document.getElementById('adminUsername').textContent = '👤 ' + adminUser;
    } else {
        sidebarAdmin.style.display = 'block';
        sidebarAdminUser.style.display = 'none';
        labelManagerMenu.style.display = 'none';
    }
}

// Check session status periodically
function startSessionCheck() {
    adminSessionCheckInterval = setInterval(checkAdminSession, 30000); // Check every 30 seconds
}

function stopSessionCheck() {
    if (adminSessionCheckInterval) {
        clearInterval(adminSessionCheckInterval);
        adminSessionCheckInterval = null;
    }
}

function checkAdminSession() {
    fetch('/api/auth/check')
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (!data.authenticated) {
            // Session expired
            adminUser = null;
            adminWarningShown = false;
            stopSessionCheck();
            closeSessionWarningModal();  // Close warning modal if open
            updateAdminUI();
            alert('Your session has expired. Please login again.');
            showMenuPage('summary', document.querySelector('.menu li'));
        } else if (data.timeout_warning && !adminWarningShown) {
            // Show warning
            adminWarningShown = true;
            showSessionWarningModal(data.time_remaining);
        }
    });
}

// Session warning modal
function showSessionWarningModal(secondsRemaining) {
    document.getElementById('sessionWarningModal').classList.add('active');
    updateWarningCountdown(secondsRemaining);

    // Update countdown every second
    var countdownInterval = setInterval(function() {
        secondsRemaining--;
        updateWarningCountdown(secondsRemaining);
        if (secondsRemaining <= 0) {
            clearInterval(countdownInterval);
            closeSessionWarningModal();
            adminLogout();
        }
    }, 1000);

    // Store interval ID for cleanup
    document.getElementById('sessionWarningModal').countdownInterval = countdownInterval;
}

function closeSessionWarningModal() {
    var modal = document.getElementById('sessionWarningModal');
    if (modal.countdownInterval) {
        clearInterval(modal.countdownInterval);
    }
    modal.classList.remove('active');
}

function updateWarningCountdown(seconds) {
    var minutes = Math.floor(seconds / 60);
    var secs = seconds % 60;
    document.getElementById('warningTimeLeft').textContent =
        minutes + ':' + (secs < 10 ? '0' : '') + secs;
}

function extendSession() {
    // Check session to reset timeout
    fetch('/api/auth/check')
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.authenticated) {
            adminWarningShown = false;
            closeSessionWarningModal();
        }
    });
}

// Load admin jobs
function loadAdminJobs() {
    if (!adminUser) {
        console.log('[ADMIN] Not logged in, skipping loadAdminJobs');
        return;
    }

    console.log('[ADMIN] Loading jobs from catalog...');

    // Use the compare catalog API which lists all jobs
    fetch('/api/compare/catalog')
    .then(function(r) {
        console.log('[ADMIN] /api/compare/catalog response:', r.status);
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
    })
    .then(function(data) {
        console.log('[ADMIN] Catalog received:', data.jobs ? data.jobs.length + ' jobs' : 'no jobs field');
        var select = document.getElementById('adminJobSelect');
        select.innerHTML = '<option value="">-- Select a profile --</option>';

        if (!data.jobs || data.jobs.length === 0) {
            console.warn('[ADMIN] No jobs found in response');
            select.innerHTML += '<option disabled>No profiles available</option>';
            return;
        }

        data.jobs.forEach(function(job) {
            var option = document.createElement('option');
            option.value = job;
            option.textContent = job;
            select.appendChild(option);
        });
        console.log('[ADMIN] Jobs loaded successfully');
    })
    .catch(function(err) {
        console.error('[ADMIN] Error loading jobs:', err);
        var select = document.getElementById('adminJobSelect');
        select.innerHTML += '<option disabled style="color:red;">Error loading profiles</option>';
    });
}

// Load builds for selected job
function adminLoadBuilds() {
    if (!adminUser) return;

    var job = document.getElementById('adminJobSelect').value;
    if (!job) {
        document.getElementById('adminBuildsContainer').style.display = 'none';
        return;
    }

    fetch('/api/admin/builds/' + encodeURIComponent(job))
    .then(function(r) { return r.json(); })
    .then(function(data) {
        document.getElementById('adminJobName').textContent = job;
        var tbody = document.getElementById('adminBuildsList');
        tbody.innerHTML = '';

        data.builds.forEach(function(build) {
            var tr = document.createElement('tr');
            tr.innerHTML =
                '<td style="padding:10px;border-bottom:1px solid #eee;"><strong>#' + build.build_number + '</strong></td>' +
                '<td style="padding:10px;border-bottom:1px solid #eee;font-size:11px;color:#f57c00;font-weight:500;">' + (build.build_id || '<em style="color:#ccc;">N/A</em>') + '</td>' +
                '<td style="padding:10px;border-bottom:1px solid #eee;">' + (build.label || '<em style="color:#999;">No label</em>') + '</td>' +
                '<td style="padding:10px;border-bottom:1px solid #eee;">' +
                '<button class="btn" style="padding:4px 8px;font-size:12px;background:#1a237e;color:white;" ' +
                'onclick="editBuildLabel(\'' + job + '\', ' + build.build_number + ', \'' + (build.label || '').replace(/'/g, "\\'") + '\')">Edit</button>' +
                '</td>';
            tbody.appendChild(tr);
        });


        document.getElementById('adminBuildsContainer').style.display = 'block';
    });
}

// Edit build label
function editBuildLabel(job, build, currentLabel) {
    var newLabel = prompt('Enter label for ' + job + ' #' + build + ':', currentLabel);

    if (newLabel === null) {
        // User cancelled
        return;
    }

    newLabel = newLabel.trim();

    if (newLabel === currentLabel) {
        // No change
        return;
    }

    if (newLabel === '' && currentLabel === '') {
        // No label before, no label after
        return;
    }

    if (newLabel === '') {
        // Delete label
        fetch('/api/labels/' + encodeURIComponent(job) + '/' + build, { method: 'DELETE' })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.success) {
                adminLoadBuilds();
            } else {
                alert('Error: ' + (data.error || 'Failed to delete label'));
            }
        });
    } else {
        // Create or update label
        fetch('/api/labels/' + encodeURIComponent(job) + '/' + build, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ label: newLabel })
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.success) {
                adminLoadBuilds();
            } else {
                alert('Error: ' + (data.error || 'Failed to save label'));
            }
        });
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    // Check if user is already logged in
    fetch('/api/auth/check')
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.authenticated) {
            adminUser = data.username;
            updateAdminUI();
            startSessionCheck();
        } else {
            updateAdminUI();
        }
    });

    // Add Enter key support for login modal
    var usernameInput = document.getElementById('adminUsername_input');
    var passwordInput = document.getElementById('adminPassword_input');
    if (usernameInput) {
        usernameInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') adminLogin();
        });
    }
    if (passwordInput) {
        passwordInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') adminLogin();
        });
    }
});

// Call this when admin page is shown
function initLabelManager() {
    if (!adminUser) {
        showAdminLoginModal();
        return;
    }
    resetLabelManager();
    loadAdminJobs();
}
