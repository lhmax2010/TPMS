/* TPMS Dashboard - Main JavaScript */

var D = null;
var chartInstance = null;
var lastCompareResult = null;
var currentProfileJob = null;
var currentProfilePage = 1;
var compareMode = 2;  // 2 or 3 targets
var compareCatalogPage = 0;
var compareCatalogLoading = false;
var pendingCompareState = null;

function escapeHtml(value) {
    return String(value == null ? '' : value)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function element(tag, text, className) {
    var node = document.createElement(tag);
    if (text !== undefined && text !== null) node.textContent = text;
    if (className) node.className = className;
    return node;
}

function showMessage(container, message, className) {
    container.replaceChildren(element('div', message, className || 'empty-msg'));
}

// Helper to check prefix-list membership (D.*_prefixes come from the server;
// fall back to built-in defaults when the payload does not provide them).
function matchesAnyPrefix(metricName, prefixes) {
    if (!prefixes) return false;
    for (var i = 0; i < prefixes.length; i++) {
        if (metricName.startsWith(prefixes[i])) return true;
    }
    return false;
}

var DEFAULT_LOWER_PREFIXES = ['TFLite - ', 'DotNet - ', 'Kernel - hackbench'];
var DEFAULT_HIGHER_PREFIXES = ['FFmpeg - ', 'GStreamer - ', 'GLBench - ',
    'Kernel - tinymembench', 'Kernel - schbench', 'Kernel - ipc-benchmark',
    'Kernel - whetstone', 'Kernel - dhrystone', 'Kernel - coremark'];

// Helper to check if a metric is lower-is-better
function isLowerIsBetter(metricName) {
    if (D.lower_is_better && D.lower_is_better.includes(metricName)) {
        return true;
    }
    // Sub-metric prefixes (e.g. "TFLite - xxx" latency, "DotNet - xxx" timing,
    // "Kernel - hackbench" execution time)
    if (matchesAnyPrefix(metricName, D.lower_is_better_prefixes || DEFAULT_LOWER_PREFIXES)) {
        return true;
    }
    // Auto-detect memory metrics
    if (metricName.startsWith('MEMPS') ||
        metricName.startsWith('MEMINFO') ||
        metricName.startsWith('MEM_USED')) {
        return true;
    }
    return false;
}

// Helper to check if a metric is higher-is-better
function isHigherIsBetter(metricName) {
    if (D.higher_is_better && D.higher_is_better.includes(metricName)) {
        return true;
    }
    // Sub-metric prefixes (e.g. "FFmpeg - xxx" / "GStreamer - xxx" decode fps,
    // "GLBench - xxx" render fps — higher frame rate is better)
    if (matchesAnyPrefix(metricName, D.higher_is_better_prefixes || DEFAULT_HIGHER_PREFIXES)) {
        return true;
    }
    return false;
}


// --- Go to home (Summary page) ---
function goHome() {
    if (window.location.hash) {
        history.pushState(null, '', window.location.pathname);
    }
    showMenuPage('summary', document.querySelector('.menu li'));
}

// --- Info tooltip ---
function toggleInfoTooltip(event) {
    event.stopPropagation();
    var tooltip = document.getElementById('infoTooltip');
    tooltip.classList.toggle('active');
}

document.addEventListener('click', function(event) {
    var tooltip = document.getElementById('infoTooltip');
    var icon = event.target.closest('.info-icon');
    if (tooltip && tooltip.classList.contains('active') && !icon) {
        tooltip.classList.remove('active');
    }
});

// --- Hash / deep-link support ---
var _suppressHashUpdate = false;

function updateHash(hash) {
    if (_suppressHashUpdate) return;
    var current = window.location.hash.replace(/^#/, '');
    if (current !== hash) {
        history.pushState(null, '', hash ? '#' + hash : window.location.pathname);
    }
}

function parseHash() {
    var hash = window.location.hash.replace(/^#/, '');
    if (!hash) return { page: 'summary' };

    var params = {};
    hash.split('&').forEach(function(pair) {
        var kv = pair.split('=', 2);
        params[decodeURIComponent(kv[0])] = kv[1] ? decodeURIComponent(kv[1]) : '';
    });

    if (params.profile) {
        return { page: 'profile', job: params.profile, pageNum: parseInt(params.page) || 1 };
    }
    if (params.build_job) {
        return { page: 'build', job: params.build_job, build: parseInt(params.build) || null };
    }
    if (params.run !== undefined) {
        return { page: 'run' };
    }
    if (params.about !== undefined) {
        return { page: 'about' };
    }
    if (params.compare !== undefined) {


        var state = { page: 'compare' };
        if (params.mode) state.mode = parseInt(params.mode) || 2;
        if (params.jobA) state.jobA = params.jobA;
        if (params.buildA) state.buildA = parseInt(params.buildA) || null;
        if (params.jobB) state.jobB = params.jobB;
        if (params.buildB) state.buildB = parseInt(params.buildB) || null;
        if (params.jobC) state.jobC = params.jobC;
        if (params.buildC) state.buildC = parseInt(params.buildC) || null;
        return state;
    }
    return { page: 'summary' };
}


function applyHash() {
    var state = parseHash();
    _suppressHashUpdate = true;
    try {
        if (state.page === 'profile') {
            showProfilePage(state.job, state.pageNum);
        } else if (state.page === 'build' && state.build) {
            showBuildPage(state.job, state.build);
        } else if (state.page === 'compare') {
            showMenuPage('compare', document.querySelectorAll('.menu li')[1]);
            if (state.jobA || state.jobB || state.jobC) {
                pendingCompareState = state;
                tryApplyPendingCompare();
            }
        } else if (state.page === 'run') {
            var runMenuItem = document.querySelector('.menu li:nth-child(3)');
            showMenuPage('run', runMenuItem);
        } else if (state.page === 'about') {
            showMenuPage('about', document.getElementById('sidebarAbout'));
        } else {




            showMenuPage('summary', document.querySelector('.menu li'));
        }
    } finally {
        _suppressHashUpdate = false;
    }
}

window.addEventListener('popstate', function() { applyHash(); });

// --- Menu navigation ---
function showMenuPage(name, el) {
    document.querySelectorAll('.page').forEach(function(p) { p.classList.remove('active'); });
    document.getElementById('page-' + name).classList.add('active');
    if (el) {
        document.querySelectorAll('.menu li').forEach(function(li) { li.classList.remove('active'); });
        el.classList.add('active');
    }

    if (name === 'compare') {
        updateHash('compare');
    } else if (name === 'summary') {
        updateHash('');
    } else if (name === 'about') {
        updateHash('about');
    } else if (name === 'run' && typeof initRunPage === 'function') {
        initRunPage();
        updateHash('run');
    } else if (name === 'admin' && typeof initLabelManager === 'function') {
        initLabelManager();
    }
}



// --- View 1: Summary ---
function loadSummary() {
    document.getElementById('summarySearchInput').value = '';
    fetch('/api/summary').then(function(r) { return r.json(); }).then(function(data) {
        renderSummary(data);
    }).catch(function(err) {
        showMessage(document.getElementById('summaryContent'), 'Error loading summary: ' + err);
    });
}

var summaryData = null;

function renderSummary(data) {
    summaryData = data;
    var metrics = data.key_metrics;
    var rows = data.summary;

    var noResults = element('div', 'No results found');
    noResults.id = 'summaryNoResults';
    noResults.style.cssText = 'text-align:center;color:#999;padding:20px;display:none;';
    var table = element('table'); table.id = 'summaryTable';
    var headRow = element('tr');
    ['Profile', 'Build', 'Build ID'].concat(metrics).concat(['Quality']).forEach(function(name) { headRow.appendChild(element('th', name)); });
    var thead = element('thead'); thead.appendChild(headRow); table.appendChild(thead);
    var body = element('tbody'); body.id = 'summaryTableBody';
    rows.forEach(function(row) {
        var tr = element('tr', null, 'summary-row');
        tr.dataset.profile = row.job.toLowerCase(); tr.dataset.buildId = (row.build_id || '').toLowerCase();
        var profileCell = element('td'); var link = element('span', row.job, 'profile-link');
        link.addEventListener('click', function() { showProfilePage(row.job, 1); }); profileCell.appendChild(link); tr.appendChild(profileCell);
        tr.appendChild(element('td', '#' + row.build));
        var buildIdCell = element('td', row.build_id || 'N/A'); buildIdCell.style.cssText = 'font-size:11px;color:#f57c00;font-weight:500;'; tr.appendChild(buildIdCell);
        metrics.forEach(function(m) {
            var mv = row.metrics[m];
            if (mv) {
                tr.appendChild(element('td', mv.value.toFixed(2) + ' ' + (mv.unit || '')));
            } else {
                var missing = element('td', 'N/A'); missing.style.cssText = 'color:#f57c00;font-weight:500;'; tr.appendChild(missing);
            }
        });
        var quality = element('td', row.warnings && row.warnings.length ? row.warnings.join(', ') : 'OK');
        if (row.warnings && row.warnings.length) { quality.style.cssText = 'color:#f57c00;font-size:11px;font-weight:500;'; tr.title = row.warnings.join('; '); }
        else quality.style.cssText = 'color:#2e7d32;font-size:11px;font-weight:500;';
        tr.appendChild(quality);
        body.appendChild(tr);
    });
    table.appendChild(body);
    document.getElementById('summaryContent').replaceChildren(noResults, table);
}

function filterSummaryTable() {
    var searchInput = document.getElementById('summarySearchInput').value.toLowerCase();
    var rows = document.querySelectorAll('#summaryTableBody .summary-row');
    var visibleCount = 0;

    rows.forEach(function(row) {
        var profile = row.getAttribute('data-profile');
        var buildId = row.getAttribute('data-build-id');
        var matches = profile.includes(searchInput) || buildId.includes(searchInput);
        row.style.display = matches ? '' : 'none';
        if (matches) visibleCount++;
    });

    var noResultsDiv = document.getElementById('summaryNoResults');
    var summaryTable = document.getElementById('summaryTable');

    if (visibleCount === 0) {
        noResultsDiv.style.display = 'block';
        summaryTable.style.display = 'none';
    } else {
        noResultsDiv.style.display = 'none';
        summaryTable.style.display = 'table';
    }
}

// --- View 2: Profile Detail ---
function showProfilePage(job, page) {
    currentProfileJob = job;
    currentProfilePage = page;

    document.querySelectorAll('.page').forEach(function(p) { p.classList.remove('active'); });
    document.getElementById('page-profile').classList.add('active');

    document.getElementById('profileTitle').textContent = job + ' Performance Report';
    showMessage(document.getElementById('profileContent'), 'Loading...', 'loading-msg');
    document.getElementById('profilePagination').replaceChildren();
    showMessage(document.getElementById('profileTrendGrid'), 'Loading trends...', 'loading-msg');

    fetch('/api/trend/' + encodeURIComponent(job))
        .then(function(r) { return r.json(); })
        .then(function(data) { renderProfileTrends(data); })
        .catch(function(err) {
            showMessage(document.getElementById('profileTrendGrid'), 'Error loading trends: ' + err);
        });

    fetch('/api/profile/' + encodeURIComponent(job) + '?page=' + page)
        .then(function(r) { return r.json(); })
        .then(function(data) { renderProfileDetail(data); })
        .catch(function(err) {
            showMessage(document.getElementById('profileContent'), 'Error: ' + err);
        });

    updateHash('profile=' + encodeURIComponent(job) + '&page=' + page);
}

function renderProfileTrends(data) {
    var grid = document.getElementById('profileTrendGrid');
    grid.innerHTML = '';
    data.key_metrics.forEach(function(metric) {
        var t = data.trends[metric];
        if (!t || !t.values || t.values.length === 0) return;
        var card = document.createElement('div');
        card.style.cssText = 'background:white;padding:10px;border-radius:6px;box-shadow:0 1px 2px rgba(0,0,0,0.1);border-left:3px solid #1a237e;';
        card.innerHTML = '<div style="font-size:12px;font-weight:600;color:#666;margin-bottom:5px;">' + escapeHtml(metric) + ' (' + escapeHtml(t.unit || '') + ')</div>' +
            '<canvas id="trendChart_' + metric + '" height="100"></canvas>';
        grid.appendChild(card);

        var ctx = document.getElementById('trendChart_' + metric);
        if (ctx) {
            new Chart(ctx, {
                type: 'line',
                data: {
                    labels: t.labels,
                    datasets: [{ label: metric, data: t.values, borderColor: '#1a237e', backgroundColor: 'rgba(26,35,126,0.1)', fill: true, tension: 0.3, pointRadius: 2 }]
                },
                options: {
                    responsive: true,
                    plugins: { legend: { display: false } },
                    scales: { x: { ticks: { font: { size: 9 }, maxRotation: 45 } }, y: { ticks: { font: { size: 9 } } } }
                }
            });
        }
    });
}

function renderProfileDetail(data) {
    var metrics = data.key_metrics;
    var builds = data.builds;
    var table = element('table');
    var header = element('tr');
    ['Build', 'Label', 'Build ID', 'Test Time'].concat(metrics).forEach(function(name) { header.appendChild(element('th', name)); });
    var thead = element('thead'); thead.appendChild(header); table.appendChild(thead);
    var tbody = element('tbody');
    builds.forEach(function(row) {
        var tr = element('tr', null, 'build-row');
        tr.addEventListener('click', function() { showBuildPage(data.job, row.build); });
        var buildCell = element('td'); buildCell.appendChild(element('strong', '#' + row.build)); tr.appendChild(buildCell);
        var labelCell = element('td');
        if (row.label) {
            var badge = element('span', row.label);
            badge.style.cssText = 'display:inline-block;background:#1a237e;color:white;padding:3px 8px;border-radius:3px;font-size:11px;font-weight:600;';
            labelCell.appendChild(badge);
        } else {
            labelCell.textContent = '—';
            labelCell.style.cssText = 'color:#ccc;';
        }
        tr.appendChild(labelCell);
        var buildIdCell = element('td', row.build_id || 'N/A'); buildIdCell.style.cssText = 'font-size:11px;color:#999;'; tr.appendChild(buildIdCell);
        var timeCell = element('td', row.test_time || 'N/A'); timeCell.style.cssText = 'font-size:11px;color:#999;'; tr.appendChild(timeCell);
        metrics.forEach(function(m) {
            var mv = row.metrics[m];
            if (mv) {
                tr.appendChild(element('td', mv.value.toFixed(2) + ' ' + (mv.unit || '')));
            } else {
                var missing = element('td', 'N/A'); missing.style.color = '#ccc'; tr.appendChild(missing);
            }
        });
        tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    document.getElementById('profileContent').replaceChildren(table);

    var pg = document.getElementById('profilePagination');
    pg.replaceChildren();
    if (data.total_pages > 1) {
        var prevBtn = element('button', 'Prev', 'btn btn-primary'); prevBtn.disabled = data.page <= 1;
        prevBtn.addEventListener('click', function() { showProfilePage(currentProfileJob, data.page - 1); });
        var info = element('span', 'Page ' + data.page + ' of ' + data.total_pages + ' (' + data.total + ' builds)', 'page-info');
        var nextBtn = element('button', 'Next', 'btn btn-primary'); nextBtn.disabled = data.page >= data.total_pages;
        nextBtn.addEventListener('click', function() { showProfilePage(currentProfileJob, data.page + 1); });
        pg.append(prevBtn, info, nextBtn);
    }
}

// --- View 3: Build Detail ---
function showBuildPage(job, build) {
    document.querySelectorAll('.page').forEach(function(p) { p.classList.remove('active'); });
    document.getElementById('page-build').classList.add('active');

    document.getElementById('buildTitle').textContent = job + ' - Build #' + build;

    var frame = document.getElementById('reportFrame');
    frame.src = '/api/report/' + encodeURIComponent(job) + '/' + build;

    updateHash('build_job=' + encodeURIComponent(job) + '&build=' + build);
}

// --- Compare page ---
function loadCompareData() {
    loadCompareCatalogPage(1, true);
}

function loadCompareCatalogPage(page, reset) {
    if (compareCatalogLoading) return;
    compareCatalogLoading = true;
    fetch('/api/compare/catalog?page=' + page + '&per_page=100').then(function(r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
    }).then(function(data) {
        if (reset || !D) {
            D = data;
            initCompare();
        } else {
            data.jobs.forEach(function(job) {
                if (D.jobs.indexOf(job) !== -1) return;
                D.jobs.push(job);
                D.builds_per_job[job] = data.builds_per_job[job];
                D.build_ids[job] = data.build_ids[job];
                appendCompareProfile(job);
            });
            D.page = data.page;
        }
        compareCatalogPage = data.page;
        document.getElementById('loadMoreProfilesBtn').style.display = data.page < data.total_pages ? '' : 'none';
        document.getElementById('compareCatalogInfo').textContent = D.jobs.length + ' / ' + data.total + ' profiles loaded';
    }).catch(function(err) {
        document.getElementById('emptyArea').textContent = 'Error loading data: ' + err;
    }).finally(function() {
        compareCatalogLoading = false;
    });
}

function loadMoreCompareProfiles() {
    if (D && compareCatalogPage < D.total_pages) loadCompareCatalogPage(compareCatalogPage + 1, false);
}

function appendCompareProfile(job) {
    ['A', 'B', 'C'].forEach(function(side) {
        document.getElementById('job' + side).appendChild(new Option(job, job));
    });
}

// --- Compare deep-link (URL hash) support ---

/**
 * Look up a build_number by its build_id string within a job.
 * Returns the build_number (int) or null if not found.
 */
function findBuildByBid(job, bid) {
    if (!D || !D.build_ids || !D.build_ids[job]) return null;
    var ids = D.build_ids[job];
    var bestMatch = null;
    for (var bn in ids) {
        if (ids.hasOwnProperty(bn) && ids[bn] === bid) {
            var num = parseInt(bn);
            if (bestMatch === null || num > bestMatch) {
                bestMatch = num;
            }
        }
    }
    return bestMatch;
}


/**
 * Try to apply the pending compare state (from URL hash).
 * Waits until the compare catalog data (D) is loaded.
 * If the requested job is not in the first catalog page, loads more pages.
 */
function tryApplyPendingCompare() {
    if (!pendingCompareState) return;
    if (!D || !D.jobs) {
        // Catalog not loaded yet; retry shortly
        setTimeout(tryApplyPendingCompare, 200);
        return;
    }

    var s = pendingCompareState;

    // Check if all requested jobs are available; if not, load more catalog pages
    var allJobsPresent = true;
    ['jobA', 'jobB', 'jobC'].forEach(function(key) {
        if (s[key] && D.jobs.indexOf(s[key]) === -1) {
            allJobsPresent = false;
        }
    });

    if (!allJobsPresent) {
        if (D.page < D.total_pages) {
            loadCompareCatalogPage(D.page + 1, false);
            // Re-check after loading more
            setTimeout(tryApplyPendingCompare, 300);
        } else {
            // All pages loaded but job still not found
            console.warn('[COMPARE-LINK] Requested job not found in catalog after loading all pages');
            pendingCompareState = null;
        }
        return;
    }

    // All jobs are available; apply the state
    _suppressHashUpdate = true;
    try {
        // Set mode first
        if (s.mode === 3) {
            setCompareMode(3);
        } else {
            setCompareMode(2);
        }

        // Apply each target
        ['A', 'B', 'C'].forEach(function(side) {
            var jobKey = 'job' + side;
            var buildKey = 'build' + side;
            if (s[jobKey]) {
                var jobSel = document.getElementById('job' + side);
                jobSel.value = s[jobKey];
                updateBuildIds(side);

                if (s[buildKey]) {
                    document.getElementById('buildId' + side).value = s[buildKey];
                }
            }
        });
    } finally {
        _suppressHashUpdate = false;
    }

    // Clear pending state and trigger compare
    pendingCompareState = null;
    compare();
}

/**
 * Copy the current compare URL to clipboard.
 */
function copyCompareLink() {
    var url = window.location.origin + window.location.pathname + window.location.hash;
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(function() {
            var btn = document.getElementById('copyLinkBtn');
            var origText = btn.textContent;
            btn.textContent = 'Copied!';
            setTimeout(function() { btn.textContent = origText; }, 2000);
        }).catch(function() {
            // Fallback for older browsers
            var tmp = document.createElement('input');
            tmp.value = url;
            document.body.appendChild(tmp);
            tmp.select();
            document.execCommand('copy');
            document.body.removeChild(tmp);
            var btn = document.getElementById('copyLinkBtn');
            var origText = btn.textContent;
            btn.textContent = 'Copied!';
            setTimeout(function() { btn.textContent = origText; }, 2000);
        });
    } else {
        var tmp = document.createElement('input');
        tmp.value = url;
        document.body.appendChild(tmp);
        tmp.select();
        document.execCommand('copy');
        document.body.removeChild(tmp);
        var btn = document.getElementById('copyLinkBtn');
        var origText = btn.textContent;
        btn.textContent = 'Copied!';
        setTimeout(function() { btn.textContent = origText; }, 2000);
    }
}

/**
 * Update the URL hash with the current compare selection.
 */
function updateCompareHash() {

    var jobA = document.getElementById('jobA').value;
    var buildA = document.getElementById('buildIdA').value;
    var jobB = document.getElementById('jobB').value;
    var buildB = document.getElementById('buildIdB').value;

    var parts = ['compare', 'mode=' + compareMode];
    parts.push('jobA=' + encodeURIComponent(jobA));
    if (buildA) parts.push('buildA=' + buildA);
    parts.push('jobB=' + encodeURIComponent(jobB));
    if (buildB) parts.push('buildB=' + buildB);

    if (compareMode === 3) {
        var jobC = document.getElementById('jobC').value;
        var buildC = document.getElementById('buildIdC').value;
        parts.push('jobC=' + encodeURIComponent(jobC));
        if (buildC) parts.push('buildC=' + buildC);
    }

    updateHash(parts.join('&'));
}

function initCompare() {
    var jobA = document.getElementById('jobA');
    var jobB = document.getElementById('jobB');
    var jobC = document.getElementById('jobC');
    D.jobs.forEach(function(j) {
        appendCompareProfile(j);
    });
    if (D.jobs.length > 0) {
        jobA.value = D.jobs[0];
        updateBuildIds('A');
    }
    if (D.jobs.length > 1) {
        jobB.value = D.jobs[D.jobs.length - 1];
    } else if (D.jobs.length > 0) {
        jobB.value = D.jobs[0];
    }
    updateBuildIds('B');

    if (D.jobs.length > 2) {
        jobC.value = D.jobs[Math.floor(D.jobs.length / 2)];
        updateBuildIds('C');
    }

    jobA.disabled = false;
    jobB.disabled = false;
    jobC.disabled = false;
    document.getElementById('buildIdA').disabled = false;
    document.getElementById('buildIdB').disabled = false;
    document.getElementById('buildIdC').disabled = false;
    document.getElementById('compareBtn').disabled = false;

    setCompareMode(2);

    // Apply pending compare state from URL hash if present
    if (pendingCompareState) {
        tryApplyPendingCompare();
    }
}


function setCompareMode(mode) {
    compareMode = mode;
    var mode2Btn = document.getElementById('mode2Btn');
    var mode3Btn = document.getElementById('mode3Btn');
    var target3Box = document.getElementById('target3Box');
    var compareGrid = document.getElementById('compareGrid');

    if (mode === 2) {
        mode2Btn.style.background = '#1a237e';
        mode3Btn.style.background = '#999';
        target3Box.style.display = 'none';
        compareGrid.style.gridTemplateColumns = '1fr 1fr';
    } else {
        mode2Btn.style.background = '#999';
        mode3Btn.style.background = '#1a237e';
        target3Box.style.display = 'block';
        compareGrid.style.gridTemplateColumns = '1fr 1fr 1fr';
    }

    document.getElementById('resultArea').style.display = 'none';
    document.getElementById('compareDetailArea').style.display = 'none';
    document.getElementById('emptyArea').style.display = 'block';
}

function compare3() {
    var jobA = document.getElementById('jobA').value;
    var buildA = parseInt(document.getElementById('buildIdA').value);
    var jobB = document.getElementById('jobB').value;
    var buildB = parseInt(document.getElementById('buildIdB').value);
    var jobC = document.getElementById('jobC').value;
    var buildC = parseInt(document.getElementById('buildIdC').value);

    if (!jobA || !jobB || !jobC || isNaN(buildA) || isNaN(buildB) || isNaN(buildC)) {
        alert('Please select profiles and build IDs for all three targets.');
        return;
    }

    updateCompareHash();

    document.getElementById('resultArea').style.display = 'none';
    document.getElementById('compareDetailArea').style.display = 'none';
    document.getElementById('emptyArea').style.display = 'block';
    document.getElementById('emptyArea').innerHTML = '<div class="loading-msg">Loading 3-way comparison...</div>';


    var bidA = (D.build_ids[jobA] && D.build_ids[jobA][buildA]) || 'N/A';
    var bidB = (D.build_ids[jobB] && D.build_ids[jobB][buildB]) || 'N/A';
    var bidC = (D.build_ids[jobC] && D.build_ids[jobC][buildC]) || 'N/A';

    var url = '/api/compare_detail_3way/' + encodeURIComponent(jobA) + '/' + buildA + '/' +
              encodeURIComponent(jobB) + '/' + buildB + '/' +
              encodeURIComponent(jobC) + '/' + buildC;

    console.log('[3WAY] Fetching:', url);

    fetch(url)
        .then(function(r) {
            console.log('[3WAY] Response status:', r.status);
            return r.json();
        })
        .then(function(data) {
            console.log('[3WAY] Data received:', data);
            renderCompare3Way(data);
            lastCompareResult = {
                jobA: jobA, buildA: buildA, bidA: bidA,
                jobB: jobB, buildB: buildB, bidB: bidB,
                jobC: jobC, buildC: buildC, bidC: bidC
            };
            document.getElementById('downloadBtn').disabled = false;
            document.getElementById('copyLinkBtn').disabled = false;
        })

        .catch(function(err) {
            console.error('[3WAY] Error:', err);
            document.getElementById('emptyArea').innerHTML = '<div class="empty-msg">Error loading 3-way comparison: ' + escapeHtml(err) + '</div>';
        });
}

function renderCompare3Way(data) {
    console.log('[3WAY] renderCompare3Way called with data:', data);

    var labelA = data.labelA;
    var labelB = data.labelB;
    var labelC = data.labelC;
    var labelAText = data.label_a || '';
    var labelBText = data.label_b || '';
    var labelCText = data.label_c || '';
    var rows = data.rows;

    console.log('[3WAY] Labels:', labelA, labelB, labelC);
    console.log('[3WAY] Rows count:', rows.length);

    document.getElementById('resultArea').style.display = 'block';
    document.getElementById('emptyArea').style.display = 'none';

    // Hide all tables in resultArea (2-way comparison tables) for 3-way mode
    var tablesInResultArea = document.querySelectorAll('#resultArea > table');
    tablesInResultArea.forEach(function(table) {
        table.style.display = 'none';
    });

    document.getElementById('resultTitle').textContent = '3개 비교: ' + labelA + ' vs ' + labelB + ' vs ' + labelC;

    var cardsHtml = '';
    var buildA = labelA.split(' #')[1];
    var buildB = labelB.split(' #')[1];
    var buildC = labelC.split(' #')[1];
    var jobA = labelA.split(' #')[0];
    var jobB = labelB.split(' #')[0];
    var jobC = labelC.split(' #')[0];

    var badgeA = labelAText ? '<span style="display:inline-block;background:#fff;color:#1a237e;padding:2px 6px;border-radius:3px;font-size:10px;font-weight:600;margin-top:4px;">' + escapeHtml(labelAText) + '</span>' : '';
    var badgeB = labelBText ? '<span style="display:inline-block;background:#fff;color:#e91e63;padding:2px 6px;border-radius:3px;font-size:10px;font-weight:600;margin-top:4px;">' + escapeHtml(labelBText) + '</span>' : '';
    var badgeC = labelCText ? '<span style="display:inline-block;background:#fff;color:#4caf50;padding:2px 6px;border-radius:3px;font-size:10px;font-weight:600;margin-top:4px;">' + escapeHtml(labelCText) + '</span>' : '';

    cardsHtml += '<div class="compare-card" style="border-left-color: #1a237e; background-color: #f3f5fa;"><h3>' + escapeHtml(jobA) + '</h3><div class="value">#' + escapeHtml(buildA) + '</div>' + badgeA + '</div>';
    cardsHtml += '<div class="compare-card" style="border-left-color: #e91e63; background-color: #fce4ec;"><h3>' + escapeHtml(jobB) + '</h3><div class="value">#' + escapeHtml(buildB) + '</div>' + badgeB + '</div>';
    cardsHtml += '<div class="compare-card" style="border-left-color: #4caf50; background-color: #f1f8e9;"><h3>' + escapeHtml(jobC) + '</h3><div class="value">#' + escapeHtml(buildC) + '</div>' + badgeC + '</div>';
    var summaryCards = document.getElementById('summaryCards');
    summaryCards.innerHTML = cardsHtml;
    // Make cards display in single row for 3-way (3 columns)
    summaryCards.style.gridTemplateColumns = 'repeat(3, 1fr)';
    summaryCards.style.gap = '20px';

    // Render Metric comparison table (KEY METRICS ONLY) and Test Name table first (don't wait for charts)
    var metricsSet = {};
    var metricRows = [];

    // Only include KEY_METRICS in the metric table
    D.key_metrics.forEach(function(keyMetric) {
        rows.forEach(function(r) {
            if (!r.is_separator && r.metric_name === keyMetric && !metricsSet[keyMetric]) {
                metricsSet[keyMetric] = true;
                metricRows.push(r);
            }
        });
    });

    var html = '<h2>Metric Comparison</h2>';
    html += '<table style="margin-top:15px;"><thead><tr><th>Metric</th><th>' + escapeHtml(labelA) + '</th><th>' + escapeHtml(labelB) + '</th><th>' + escapeHtml(labelC) + '</th></tr></thead><tbody>';

    metricRows.forEach(function(r) {
        var va = r.val_a !== null ? r.val_a.toFixed(2) : 'N/A';
        var vb = r.val_b !== null ? r.val_b.toFixed(2) : 'N/A';
        var vc = r.val_c !== null ? r.val_c.toFixed(2) : 'N/A';
        var unit = r.unit || '';

        var vaStr = va !== 'N/A' ? va + (unit ? ' ' + unit : '') : 'N/A';
        var vbStr = vb !== 'N/A' ? vb + (unit ? ' ' + unit : '') : 'N/A';
        var vcStr = vc !== 'N/A' ? vc + (unit ? ' ' + unit : '') : 'N/A';

        // 3-way comparison coloring: best vs 2nd, worst vs 2nd with 10% threshold
        var vaClass = '', vbClass = '', vcClass = '';
        if (va !== 'N/A' && vb !== 'N/A' && vc !== 'N/A') {
            var numA = parseFloat(va), numB = parseFloat(vb), numC = parseFloat(vc);
            var lowerIsBetter = isLowerIsBetter(r.metric_name);

            // Create array with values and their original indices
            var vals = [{val: numA, idx: 0}, {val: numB, idx: 1}, {val: numC, idx: 2}];
            vals.sort(function(a, b) {
                return lowerIsBetter ? (a.val - b.val) : (b.val - a.val);
            });

            var best = vals[0].val;
            var middle = vals[1].val;
            var worst = vals[2].val;

            // Calculate 10% threshold against middle value
            var bestDiff = Math.abs((best - middle) / middle);
            var worstDiff = Math.abs((worst - middle) / middle);

            // Assign colors based on 10% difference from middle
            var classes = ['', '', ''];
            if (bestDiff >= 0.1) { classes[vals[0].idx] = ' class="val-3way-best"'; }
            if (worstDiff >= 0.1) { classes[vals[2].idx] = ' class="val-3way-worst"'; }

            vaClass = classes[0];
            vbClass = classes[1];
            vcClass = classes[2];
        }

        html += '<tr><td>' + escapeHtml(r.metric_name) + '</td>' +
            '<td' + vaClass + '>' + vaStr + '</td>' +
            '<td' + vbClass + '>' + vbStr + '</td>' +
            '<td' + vcClass + '>' + vcStr + '</td></tr>';
    });

    html += '</tbody></table>';

    html += '<h2 style="margin-top:30px;">Test Name Comparison</h2>';
    html += '<table style="margin-top:15px;"><thead><tr><th>Test Name</th><th>' + escapeHtml(labelA) + '</th><th>' + escapeHtml(labelB) + '</th><th>' + escapeHtml(labelC) + '</th></tr></thead><tbody>';

    rows.forEach(function(r) {
        if (r.is_separator) {
            html += '<tr class="section-divider"><td colspan="4">' + escapeHtml(r.test_name) + '</td></tr>';
        } else {
            var indent = r.is_sub_test ? '&nbsp;&nbsp;&nbsp;&nbsp;' : '';
            var va = r.val_a !== null ? r.val_a.toFixed(2) : 'N/A';
            var vb = r.val_b !== null ? r.val_b.toFixed(2) : 'N/A';
            var vc = r.val_c !== null ? r.val_c.toFixed(2) : 'N/A';
            var unit = r.unit || '';

            var vaStr = va !== 'N/A' ? va + (unit ? ' ' + unit : '') : 'N/A';
            var vbStr = vb !== 'N/A' ? vb + (unit ? ' ' + unit : '') : 'N/A';
            var vcStr = vc !== 'N/A' ? vc + (unit ? ' ' + unit : '') : 'N/A';

            // 3-way comparison coloring: best vs 2nd, worst vs 2nd with 10% threshold
            var vaClass = '', vbClass = '', vcClass = '';
            if (va !== 'N/A' && vb !== 'N/A' && vc !== 'N/A') {
                var numA = parseFloat(va), numB = parseFloat(vb), numC = parseFloat(vc);
                var lowerIsBetter = isLowerIsBetter(r.metric_name);

                // Create array with values and their original indices
                var vals = [{val: numA, idx: 0}, {val: numB, idx: 1}, {val: numC, idx: 2}];
                vals.sort(function(a, b) {
                    return lowerIsBetter ? (a.val - b.val) : (b.val - a.val);
                });

                var best = vals[0].val;
                var middle = vals[1].val;
                var worst = vals[2].val;

                // Calculate 10% threshold against middle value
                var bestDiff = Math.abs((best - middle) / middle);
                var worstDiff = Math.abs((worst - middle) / middle);

                // Assign colors based on 10% difference from middle
                var classes = ['', '', ''];
                if (bestDiff >= 0.1) { classes[vals[0].idx] = ' class="val-3way-best"'; }
                if (worstDiff >= 0.1) { classes[vals[2].idx] = ' class="val-3way-worst"'; }

                vaClass = classes[0];
                vbClass = classes[1];
                vcClass = classes[2];
            }

            html += '<tr><td>' + indent + escapeHtml(r.test_name) + '</td>' +
                '<td' + vaClass + '>' + vaStr + '</td>' +
                '<td' + vbClass + '>' + vbStr + '</td>' +
                '<td' + vcClass + '>' + vcStr + '</td></tr>';
        }
    });

    html += '</tbody></table>';

    console.log('[3WAY] HTML length:', html.length);
    console.log('[3WAY] Setting compareDetailArea innerHTML');

    var detailArea = document.getElementById('compareDetailArea');
    console.log('[3WAY] compareDetailArea element:', detailArea);
    console.log('[3WAY] compareDetailArea display before:', detailArea.style.display);

    detailArea.style.display = 'block';
    detailArea.innerHTML = html;

    console.log('[3WAY] compareDetailArea display after:', detailArea.style.display);
    console.log('[3WAY] compareDetailArea innerHTML length:', detailArea.innerHTML.length);

    // Render charts AFTER tables are rendered
    console.log('[3WAY] About to render charts');
    renderCompare3WayCharts(rows, labelA, labelB, labelC);
}

function renderCompare3WayCharts(rows, labelA, labelB, labelC) {
    console.log('[3WAY] renderCompare3WayCharts starting');

    // Destroy all existing chart instances
    if (window.compareChartInstances) {
        window.compareChartInstances.forEach(function(c) {
            try {
                if (c && typeof c.destroy === 'function') {
                    c.destroy();
                }
            } catch (e) {
                console.warn('[3WAY] Error destroying chart:', e);
            }
        });
    }
    window.compareChartInstances = [];

    var container = document.getElementById('compareChartContainer');
    if (!container) {
        console.error('[3WAY] compareChartContainer not found');
        return;
    }

    // Completely clear container
    container.innerHTML = '';

    var metricsSet = {};
    var chartCount = 0;

    // Only create charts for KEY_METRICS
    D.key_metrics.forEach(function(keyMetric) {
        if (metricsSet[keyMetric]) return;

        // Find first occurrence of this key metric
        var foundRow = null;
        for (var i = 0; i < rows.length; i++) {
            if (!rows[i].is_separator && rows[i].metric_name === keyMetric) {
                foundRow = rows[i];
                break;
            }
        }

        if (!foundRow) return;

        metricsSet[keyMetric] = true;

        var m = foundRow.metric_name;
        var va = foundRow.val_a;
        var vb = foundRow.val_b;
        var vc = foundRow.val_c;
        var unit = foundRow.unit || '';

        if (va === null && vb === null && vc === null) return;

        var canvasId = 'compareChart3_' + m.replace(/[^a-zA-Z0-9]/g, '_') + '_' + chartCount;
        chartCount++;

        var card = document.createElement('div');
        card.style.cssText = 'background:#f8f9fa;padding:10px;border-radius:6px;border-left:3px solid #1a237e;';
        card.innerHTML = '<div style="font-size:12px;font-weight:600;color:#666;margin-bottom:5px;">' + escapeHtml(m) + ' (' + escapeHtml(unit) + ')</div>' +
            '<canvas id="' + canvasId + '" height="80"></canvas>';
        container.appendChild(card);

        // Use setTimeout to ensure DOM is ready
        (function(metricName, valA, valB, valC, metricUnit, canvasID) {
            setTimeout(function() {
                var ctx = document.getElementById(canvasID);
                if (!ctx) {
                    console.warn('[3WAY] Canvas element not found:', canvasID);
                    return;
                }

                try {
                    // Determine best value (for coloring)
                    var values = [valA, valB, valC].filter(function(v) { return v !== null; });
                    var bestIdx = -1;
                    if (values.length > 0) {
                        if (isLowerIsBetter(metricName)) {
                            var minVal = Math.min.apply(null, values);
                            bestIdx = [valA, valB, valC].indexOf(minVal);
                        } else if (isHigherIsBetter(metricName)) {
                            var maxVal = Math.max.apply(null, values);
                            bestIdx = [valA, valB, valC].indexOf(maxVal);
                        }
                    }


                    var colors = ['rgba(26,35,126,0.7)', 'rgba(233,30,99,0.7)', 'rgba(76,175,80,0.7)'];
                    var pointColors = ['#1a237e', '#e91e63', '#4caf50'];
                    if (bestIdx >= 0) {
                        pointColors[bestIdx] = '#FFD700';  // Gold for best
                    }

                    var chart = new Chart(ctx, {
                        type: 'bar',
                        data: {
                            labels: [labelA.split(' #')[0], labelB.split(' #')[0], labelC.split(' #')[0]],
                            datasets: [{
                                label: metricName,
                                data: [valA, valB, valC],
                                backgroundColor: colors,
                                borderColor: pointColors,
                                borderWidth: 2
                            }]
                        },
                        options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: false } } }
                    });
                    window.compareChartInstances.push(chart);
                    console.log('[3WAY] Chart created for:', metricName);
                } catch (e) {
                    console.error('[3WAY] Error creating chart for', metricName, ':', e);
                }
            }, 0);
        })(m, va, vb, vc, unit, canvasId);
    });

    console.log('[3WAY] renderCompare3WayCharts completed');
}

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
    if (builds.length > 0) {
        buildIdSel.value = builds[0];
    }
}

function compare() {
    if (compareMode === 3) {
        compare3();
        return;
    }

    var jobA = document.getElementById('jobA').value;
    var buildA = parseInt(document.getElementById('buildIdA').value);
    var jobB = document.getElementById('jobB').value;
    var buildB = parseInt(document.getElementById('buildIdB').value);

    if (!jobA || !jobB || isNaN(buildA) || isNaN(buildB)) {
        alert('Please select profiles and build IDs for both targets.');
        return;
    }

    updateCompareHash();

    document.getElementById('emptyArea').style.display = 'block';
    document.getElementById('emptyArea').innerHTML = '<div class="loading-msg">Loading comparison...</div>';
    var url = '/api/compare/selection?selection=' + encodeURIComponent(jobA + ':' + buildA) +

              '&selection=' + encodeURIComponent(jobB + ':' + buildB);
    fetch(url).then(function(r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
    }).then(function(data) {
        var selectedA = data.selections[0] || { metrics: {}, duplicates: {} };
        var selectedB = data.selections[1] || { metrics: {}, duplicates: {} };
        renderSelectedComparison(jobA, buildA, jobB, buildB, selectedA, selectedB);
    }).catch(function(err) {
        document.getElementById('emptyArea').innerHTML =
            '<div class="empty-msg">Error loading comparison: ' + escapeHtml(err) + '</div>';
    });
}

function renderSelectedComparison(jobA, buildA, jobB, buildB, selectedA, selectedB) {
    var dataA = selectedA.metrics || {};
    var dataB = selectedB.metrics || {};

    var metrics = D.key_metrics.filter(function(m) {
        return dataA[m] || dataB[m];
    });

    if (metrics.length === 0) {
        document.getElementById('resultArea').style.display = 'none';
        document.getElementById('emptyArea').style.display = 'block';
        document.getElementById('emptyArea').innerHTML =
            '<div class="empty-msg">No metrics found for the selected builds</div>';
        document.getElementById('downloadBtn').disabled = true;
        return;
    }

    document.getElementById('resultArea').style.display = 'block';
    document.getElementById('emptyArea').style.display = 'none';
    document.getElementById('downloadBtn').disabled = false;
    document.getElementById('copyLinkBtn').disabled = false;

    var bidA = (D.build_ids[jobA] && D.build_ids[jobA][buildA]) || 'N/A';
    var bidB = (D.build_ids[jobB] && D.build_ids[jobB][buildB]) || 'N/A';
    var labelA = jobA + ' #' + buildA;
    var labelB = jobB + ' #' + buildB;

    // Fetch labels for summary cards
    Promise.all([
        fetch('/api/labels/' + encodeURIComponent(jobA) + '/' + buildA).then(function(r) { return r.json(); }).catch(function() { return {}; }),
        fetch('/api/labels/' + encodeURIComponent(jobB) + '/' + buildB).then(function(r) { return r.json(); }).catch(function() { return {}; })
    ]).then(function(results) {
        var labelAText = results[0].label || '';
        var labelBText = results[1].label || '';

        var badgeA = labelAText ? '<span style="display:inline-block;background:#f3f5fa;color:#1a237e;padding:2px 6px;border-radius:3px;font-size:10px;font-weight:600;margin-top:4px;">' + escapeHtml(labelAText) + '</span>' : '';
        var badgeB = labelBText ? '<span style="display:inline-block;background:#fce4ec;color:#e91e63;padding:2px 6px;border-radius:3px;font-size:10px;font-weight:600;margin-top:4px;">' + escapeHtml(labelBText) + '</span>' : '';

        var cardsHtml = '';
        cardsHtml += '<div class="compare-card"><h3>' + escapeHtml(jobA) + '</h3><div class="value">#' + buildA + '</div><div class="build-id">' + escapeHtml(bidA) + '</div>' + badgeA + '</div>';
        cardsHtml += '<div class="compare-card"><h3>' + escapeHtml(jobB) + '</h3><div class="value">#' + buildB + '</div><div class="build-id">' + escapeHtml(bidB) + '</div>' + badgeB + '</div>';
        var summaryCards = document.getElementById('summaryCards');
        summaryCards.innerHTML = cardsHtml;
        // Reset grid to 2-column for 2-way comparison
        summaryCards.style.gridTemplateColumns = '';
        summaryCards.style.gap = '';
    });

    document.getElementById('thA').textContent = labelA;
    document.getElementById('thB').textContent = labelB;
    document.getElementById('resultTitle').textContent = labelA + '  vs  ' + labelB;

    var tbody = '';
    var excelRows = [];

    metrics.forEach(function(m) {
        var va = dataA[m] ? dataA[m].value : null;
        var vb = dataB[m] ? dataB[m].value : null;
        var unit = (dataA[m] || dataB[m] || {}).unit || '';

        var diffStr = '', pctStr = '', verdict = '', verdictClass = 'diff-neutral';
        var diffNum = null, pctNum = null;

        if (va !== null && vb !== null) {
            var diff = va - vb;
            diffNum = diff;
            diffStr = (diff >= 0 ? '+' : '') + diff.toFixed(2) + ' ' + unit;
            if (vb !== 0) {
                var pct = ((va - vb) / Math.abs(vb) * 100);
                pctNum = pct;
                pctStr = (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%';
                var lowerBetter = isLowerIsBetter(m);
                var higherBetter = isHigherIsBetter(m);
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

        var vaStr = va !== null ? va.toFixed(2) + (unit ? ' ' + escapeHtml(unit) : '') : 'N/A';
        var vbStr = vb !== null ? vb.toFixed(2) + (unit ? ' ' + escapeHtml(unit) : '') : 'N/A';

        var rowClass = '', valClass = '';
        if (verdictClass === 'diff-worse') { rowClass = 'row-regression'; valClass = 'val-bad'; }
        else if (verdictClass === 'diff-better') { rowClass = 'row-improved'; valClass = 'val-good'; }

        tbody += '<tr class="' + rowClass + '"><td>' + escapeHtml(m) + '</td>' +
            '<td class="' + valClass + '">' + vaStr + '</td>' +
            '<td class="' + valClass + '">' + vbStr + '</td>' +
            '<td>' + diffStr + '</td><td>' + pctStr + '</td></tr>';

        excelRows.push({ metric: m, target1: va, target2: vb, unit: unit, diff: diffNum, changePct: pctNum, verdict: verdict });
    });

    document.getElementById('compareBody').innerHTML = tbody;

    // Show 2-way tables in resultArea
    var tablesInResultArea = document.querySelectorAll('#resultArea > table');
    tablesInResultArea.forEach(function(table) {
        table.style.display = '';
    });

    lastCompareResult = { jobA: jobA, buildA: buildA, bidA: bidA, jobB: jobB, buildB: buildB, bidB: bidB, rows: excelRows };

    var metricUnits = {};
    metrics.forEach(function(metric) { metricUnits[metric] = (dataA[metric] || dataB[metric] || {}).unit || ''; });
    renderCompareCharts(metrics, dataA, dataB, labelA, labelB, metricUnits);
    loadCompareDetail(jobA, buildA, jobB, buildB);
}

function renderCompareCharts(metrics, dataA, dataB, labelA, labelB, metricUnits) {
    if (window.compareChartInstances) {
        window.compareChartInstances.forEach(function(c) { c.destroy(); });
    }
    window.compareChartInstances = [];

    var container = document.getElementById('compareChartContainer');
    container.innerHTML = '';

    metrics.forEach(function(m) {
        var va = dataA[m] ? dataA[m].value : null;
        var vb = dataB[m] ? dataB[m].value : null;
        var unit = metricUnits[m] || '';

        var card = document.createElement('div');
        card.style.cssText = 'background:#f8f9fa;padding:10px;border-radius:6px;border-left:3px solid #1a237e;';
        card.innerHTML = '<div style="font-size:12px;font-weight:600;color:#666;margin-bottom:5px;">' + escapeHtml(m) + ' (' + escapeHtml(unit) + ')</div>' +
            '<canvas id="compareChart_' + m + '" height="80"></canvas>';
        container.appendChild(card);

        var ctx = document.getElementById('compareChart_' + m);
        if (ctx && va !== null && vb !== null) {
            var chart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: [labelA, labelB],
                    datasets: [{ label: m, data: [va, vb], backgroundColor: ['rgba(26,35,126,0.7)', 'rgba(233,30,99,0.7)'], borderColor: ['#1a237e', '#e91e63'], borderWidth: 1 }]
                },
                options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: false } } }
            });
            window.compareChartInstances.push(chart);
        }
    });
}

function loadCompareDetail(jobA, buildA, jobB, buildB) {
    var detailArea = document.getElementById('compareDetailArea');
    detailArea.style.display = 'block';
    detailArea.innerHTML = '<div class="loading-msg">Loading detailed comparison...</div>';

    fetch('/api/compare_detail/' + encodeURIComponent(jobA) + '/' + buildA + '/' + encodeURIComponent(jobB) + '/' + buildB)
        .then(function(r) { return r.json(); })
        .then(function(data) { renderCompareDetail(data); })
        .catch(function(err) {
            detailArea.innerHTML = '<div class="empty-msg">Error loading detail: ' + escapeHtml(err) + '</div>';
        });
}

function renderCompareDetail(data) {
    var labelA = data.labelA;
    var labelB = data.labelB;
    var rows = data.rows;

    var html = '<table><thead><tr><th>Test Name</th><th>' + escapeHtml(labelA) + '</th><th>' + escapeHtml(labelB) + '</th><th>Change</th></tr></thead><tbody>';

    rows.forEach(function(r) {
        var rowClass = '', valClass = '', changeClass = '';
        if (r.regression) { rowClass = 'row-regression'; valClass = 'val-bad'; changeClass = 'val-bad'; }
        else if (r.improved) { rowClass = 'row-improved'; valClass = 'val-good'; changeClass = 'val-good'; }
        var indent = r.is_sub_test ? '&nbsp;&nbsp;&nbsp;&nbsp;' : '';

        if (r.is_separator) {
            html += '<tr class="section-divider"><td colspan="4">' + escapeHtml(r.test_name) + '</td></tr>';
        } else {
            html += '<tr class="' + rowClass + '"><td>' + indent + escapeHtml(r.test_name) + '</td>' +
                '<td class="' + valClass + '">' + escapeHtml(r.val_a) + '</td>' +
                '<td class="' + valClass + '">' + escapeHtml(r.val_b) + '</td>' +
                '<td class="' + changeClass + '">' + escapeHtml(r.change) + (r.method_warning ? '<br><strong role="alert" style="color:#b00020">' + escapeHtml(r.method_warning) + '</strong>' : '') + '</td></tr>';
        }
    });

    html += '</tbody></table>';
    if (data.memory_rigor) { html += renderMemoryRigor(data.memory_rigor); }
    document.getElementById('compareDetailArea').innerHTML = html;
}

function downloadExcel() {
    if (!lastCompareResult) { alert('Please run Compare first.'); return; }
    var r = lastCompareResult;

    if (r.jobC) {
        // 3-way comparison - all metrics via API
        var url = '/api/compare_detail_3way/' + encodeURIComponent(r.jobA) + '/' + r.buildA + '/' +
                  encodeURIComponent(r.jobB) + '/' + r.buildB + '/' +
                  encodeURIComponent(r.jobC) + '/' + r.buildC;

        fetch(url).then(function(res) { return res.json(); }).then(function(data) {
            var wsData = [];
            wsData.push(['TPMS 3-Way Comparison - All Metrics']);
            wsData.push([]);
            wsData.push(['Target 1', r.jobA + ' #' + r.buildA, r.bidA]);
            wsData.push(['Target 2', r.jobB + ' #' + r.buildB, r.bidB]);
            wsData.push(['Target 3', r.jobC + ' #' + r.buildC, r.bidC]);
            wsData.push([]);
            wsData.push(['Test Name', 'Target 1 (' + r.jobA + ')', 'Target 2 (' + r.jobB + ')', 'Target 3 (' + r.jobC + ')', 'Unit']);

            data.rows.forEach(function(row) {
                if (!row.is_separator) {
                    wsData.push([
                        row.test_name,
                        row.val_a !== null ? row.val_a.toFixed(2) : 'N/A',
                        row.val_b !== null ? row.val_b.toFixed(2) : 'N/A',
                        row.val_c !== null ? row.val_c.toFixed(2) : 'N/A',
                        row.unit || ''
                    ]);
                }
            });

            var ws = XLSX.utils.aoa_to_sheet(wsData);
            ws['!cols'] = [{wch: 50}, {wch: 20}, {wch: 20}, {wch: 20}, {wch: 10}];
            var wb = XLSX.utils.book_new();
            XLSX.utils.book_append_sheet(wb, ws, '3-Way Comparison');
            XLSX.writeFile(wb, 'comparison_3way_' + r.buildA + '_' + r.buildB + '_' + r.buildC + '.xlsx');
        }).catch(function(err) {
            alert('Failed to download Excel: ' + err);
        });
    } else {
        // 2-way comparison - detailed with all metrics
        var url = '/api/all_metrics_compare/' + encodeURIComponent(r.jobA) + '/' + r.buildA + '/' +
                  encodeURIComponent(r.jobB) + '/' + r.buildB;

        fetch(url).then(function(res) { return res.json(); }).then(function(allRows) {
            var wsData = [];
            wsData.push(['TPMS Performance Comparison - All Metrics']);
            wsData.push([]);
            wsData.push(['Target 1', r.jobA + ' #' + r.buildA, r.bidA]);
            wsData.push(['Target 2', r.jobB + ' #' + r.buildB, r.bidB]);
            wsData.push([]);
            wsData.push(['Test Name', 'Target 1 (' + r.jobA + ' #' + r.buildA + ')', 'Target 2 (' + r.jobB + ' #' + r.buildB + ')', 'Change %', 'Status', 'Unit']);

            allRows.forEach(function(row) {
                wsData.push([
                    row.test_name,
                    row.val_a,
                    row.val_b,
                    row.change,
                    row.passed,
                    row.unit || ''
                ]);
            });

            var ws = XLSX.utils.aoa_to_sheet(wsData);
            ws['!cols'] = [{wch: 50}, {wch: 20}, {wch: 20}, {wch: 15}, {wch: 10}, {wch: 10}];
            var wb = XLSX.utils.book_new();
            XLSX.utils.book_append_sheet(wb, ws, 'Comparison');
            XLSX.writeFile(wb, 'comparison_' + r.jobA + '_' + r.buildA + '_vs_' + r.jobB + '_' + r.buildB + '.xlsx');
        }).catch(function(err) {
            alert('Failed to download Excel: ' + err);
        });
    }
}

// --- Set Jenkins link dynamically ---
(function() {
    var jenkinsLink = document.getElementById('jenkinsLink');
    if (jenkinsLink) {
        var host = window.location.hostname;
        jenkinsLink.href = 'http://' + host + ':8080/';
    }
})();

// --- Initialize on load ---
loadSummary();
loadCompareData();


if (window.location.hash) {
    applyHash();
}


function memoryGateLabel(reason) {
    return ({steady_criteria_met: '满足判据', fixed_uptime_reached: '达到固定开机采集时刻',
        waiting_fixed_uptime: '等待固定开机时刻', criteria_not_met: '尚未满足判据',
        insufficient_samples: '采样序列不足', steady: '满足判据', fixed: '到点采集',
        limit: '按上限采集', unstable: '采集时内存未平稳', error: '采集失败', waiting: '等待中'})[reason] || reason;
}

function renderMemoryRigor(report) {
    var html = '<h3>内存严谨模式（A − B，kB）</h3>';
    (report.warnings || []).forEach(function(w) { html += '<p role="alert" style="color:#b00020;font-weight:bold">警告：' + escapeHtml(w) + '</p>'; });
    if (report.conclusion) { html += '<p>' + escapeHtml(report.conclusion) + '</p>'; }
    ['quality_a', 'quality_b'].forEach(function(key) {
        var q = report[key];
        html += '<h4>' + (key === 'quality_a' ? 'A' : 'B') + '</h4>';
        if (!q) { html += '<p>N/A</p>'; return; }
        html += '<p>样本 ' + escapeHtml(q.samples) + ' / ' + escapeHtml(q.expected_samples) +
            '；无效 ' + escapeHtml(q.invalid_samples) + '</p>';
        (q.gates || []).forEach(function(g) {
            html += '<p>开机 ' + escapeHtml(g.boot_index) + '：' + escapeHtml(memoryGateLabel(g.reason || g.status)) +
                '；门控结束 uptime ' + escapeHtml(g.uptime) + ' s</p>';
        });
        html += '<p>方法：' + escapeHtml(JSON.stringify(q.method)) + '</p>';
        (q.per_boot || []).forEach(function(b) { html += '<p>开机 ' + b.boot_index + ' 有效/无效/缺失：' + b.valid + '/' + b.invalid + '/' + b.missing + '；' + escapeHtml(JSON.stringify(b.invalid_reasons)) + '</p>'; });
        (q.capture_uptimes || []).forEach(function(x) { html += '<p>开机 ' + x.boot_index + ' 样本 ' + x.sample_index + ' 内核线程：' + escapeHtml(x.kernel_threads) + '；采集期间退出：' + escapeHtml(JSON.stringify(x.exited_processes)) + '</p>'; });
        html += '<details><summary>传输耗时、文件数与清理记录</summary><pre>' + escapeHtml(JSON.stringify({transfers:q.transfers,cleanup:q.cleanup},null,2)) + '</pre></details>';
        html += '<p>采集 uptime：' + escapeHtml((q.capture_uptimes || []).map(function(x) { return x.uptime + ' s / coverage=' + (x.coverage === null ? 'N/A' : x.coverage); }).join(', ')) + '</p>';
        (q.warnings || []).forEach(function(w) { html += '<p>' + escapeHtml(w) + '</p>'; });
    });
    if (report.metrics && report.metrics.length) {
        html += '<table><thead><tr><th>指标</th><th>A 均值 / 极差</th><th>B 均值 / 极差</th><th>差值 kB</th><th>判定</th></tr></thead><tbody>';
        report.metrics.forEach(function(m) {
            html += '<tr><td>' + escapeHtml(m.metric) + '</td><td>' + escapeHtml(m.a ? m.a.mean + ' / ' + m.a.range : 'N/A') +
                '</td><td>' + escapeHtml(m.b ? m.b.mean + ' / ' + m.b.range : 'N/A') + '</td><td>' +
                escapeHtml(m.delta_kB === null ? 'N/A' : m.delta_kB) + '</td><td>' + escapeHtml(m.conclusion) + '</td></tr>';
        });
        html += '</tbody></table>';
    }
    if (report.process_groups) {
        ['common','only_a','only_b'].forEach(function(key) {
            var g = report.process_groups[key];
            html += '<details><summary>' + escapeHtml({common:'共同进程',only_a:'只在 A',only_b:'只在 B'}[key]) +
                ' Pss+SwapPss：A=' + escapeHtml(g.sum_a_kB === null ? 'N/A' : g.sum_a_kB) +
                '，B=' + escapeHtml(g.sum_b_kB === null ? 'N/A' : g.sum_b_kB) + '</summary><pre>' +
                escapeHtml(JSON.stringify(g.rows, null, 2)) + '</pre></details>';
        });
        html += '<p>' + escapeHtml(report.decomposition.definition) + '</p><pre>' +
            escapeHtml(JSON.stringify(report.decomposition,null,2)) + '</pre>';
    } else if (report.process_groups_reason) { html += '<p>' + escapeHtml(report.process_groups_reason) + '</p>'; }
    return html;
}
