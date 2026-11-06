/* TPMS Report - Build detail JavaScript */

function escapeHtml(value) {
    return String(value == null ? '' : value)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function initReport(data) {
    reportData = data;

    // Setup clickable test names for trend popup
    var testNameElements = document.querySelectorAll('.clickable-test-name');
    if (typeof console !== 'undefined') {
        console.log('[TPMS] Found ' + testNameElements.length + ' clickable test names');
    }

    testNameElements.forEach(function(elem) {
        elem.addEventListener('click', function(e) {
            e.preventDefault();
            var row = elem.closest('tr');
            var testName = row.getAttribute('data-test-name');
            var metricName = row.getAttribute('data-metric-name');
            if (typeof console !== 'undefined') {
                console.log('[TPMS] Clicked test:', testName, 'metric:', metricName);
            }
            if (!testName || !metricName || testName === 'Memory Detail Information') return;

            var jobName = reportData.job || '';
            var buildNumber = reportData.build || '';

            if (typeof console !== 'undefined') {
                console.log('[TPMS] Opening popup for:', jobName, '#' + buildNumber, '-', testName, '/', metricName);
            }

            if (jobName && buildNumber && metricName) {
                openTrendPopup(testName, metricName, jobName, buildNumber);
            }
        });
    });

    // Render metric trend line charts

    Object.keys(reportData.charts).forEach(function(metric) {
        var ctx = document.getElementById('chart_' + metric);
        if (!ctx) return;
        var d = reportData.charts[metric];
        new Chart(ctx, {
            type: 'line',
            data: {
                labels: d.labels,
                datasets: [{
                    label: metric, data: d.values,
                    borderColor: '#1a237e', backgroundColor: 'rgba(26,35,126,0.1)',
                    fill: true, tension: 0.3, pointRadius: 2,
                }]
            },
            options: {
                responsive: true,
                plugins: { legend: { display: false } },
                scales: { x: { display: false }, y: { ticks: { font: { size: 10 } } } }
            }
        });
    });

    // Render meminfo pie chart

    if (reportData.has_meminfo) {
        var pieCtx = document.getElementById('meminfoPie');
        if (pieCtx) {
            new Chart(pieCtx, {
                type: 'pie',
                data: {
                    labels: reportData.pie_labels,
                    datasets: [{
                        data: reportData.pie_values,
                        backgroundColor: ['#1a237e','#e91e63','#4caf50','#ff9800','#9c27b0','#00bcd4','#795548','#607d8b','#cddc39','#f44336','#3f51b5','#009688']
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: { position: 'right', labels: { font: { size: 11 } } },
                        title: { display: true, text: 'Memory Info Breakdown (KB)' }
                    },
                    onClick: function(evt, item) { if (item.length > 0) { openMempsPopup(); } }
                }
            });
        }
    }
}

function openMempsPopup() {

    document.getElementById('mempsPopup').classList.add('active');
    var ctx = document.getElementById('mempsChart');
    if (ctx && !ctx._chart) {
        new Chart(ctx, {
            type: 'bar',
            data: {
                labels: reportData.memps_labels,
                datasets: [{ label: 'Memory (KB)', data: reportData.memps_values, backgroundColor: '#1a237e' }]
            },
            options: {
                indexAxis: 'y', responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false }, title: { display: true, text: 'Per-Process Memory Usage (KB)' } },
                scales: { x: { beginAtZero: true } }
            }
        });
    }
}

function closePopup(popupId) {
    document.getElementById(popupId).classList.remove('active');
}

function toggleMemoryInfo() {
    var content = document.getElementById('memInfoContent');
    var toggle = document.getElementById('memInfoToggle');
    if (content.classList.contains('expanded')) {
        content.classList.remove('expanded');
        toggle.innerHTML = '&#9654;';
    } else {
        content.classList.add('expanded');
        toggle.innerHTML = '&#9660;';
    }
}

function openTrendPopup(testName, metricName, jobName, buildNumber) {
    if (typeof console !== 'undefined') console.log('[TPMS] Opening trend popup for:', testName, '/', metricName);

    var popup = document.getElementById('trendPopup');
    if (!popup) {
        alert('Popup element not found');
        return;
    }

    // Clear previous content first
    document.getElementById('trendTitle').innerHTML = 'Loading...';
    var tbody = document.getElementById('trendTable').querySelector('tbody');
    tbody.innerHTML = '<tr><td colspan="4" style="padding:20px;text-align:center;">Loading...</td></tr>';

    popup.classList.add('active');

    var url = '/api/test_trend?' +
              'job=' + encodeURIComponent(jobName) +
              '&test_name=' + encodeURIComponent(testName) +
              '&metric_name=' + encodeURIComponent(metricName) +
              '&build=' + buildNumber;

    if (typeof console !== 'undefined') console.log('[TPMS] Fetching:', url);

    fetch(url).then(function(res) {
        if (typeof console !== 'undefined') console.log('[TPMS] Response status:', res.status);
        if (!res.ok) {
            throw new Error('HTTP ' + res.status);
        }
        return res.json();
    }).then(function(data) {
        if (typeof console !== 'undefined') console.log('[TPMS] Data received, trend items:', data && data.trend ? data.trend.length : 0);

        if (!data) {
            throw new Error('Empty response');
        }

        if (data.error) {
            throw new Error(data.error);
        }

        if (!data.trend || data.trend.length === 0) {
            throw new Error('No trend data available');
        }

        document.getElementById('trendTitle').textContent = 'Trend: ' + data.test_name;

        // For chart: sort ascending (oldest first) to show time progression
        var trendForChart = data.trend.slice().sort(function(a, b) {
            return a.build_number - b.build_number;
        });
        var labels = trendForChart.map(function(d) { return '#' + d.build_number; });
        var values = trendForChart.map(function(d) { return d.metric_value; });
        var colors = trendForChart.map(function(d) {
            return d.is_target ? 'rgba(244, 67, 54, 1)' : 'rgba(26, 35, 126, 0.6)';
        });
        var borderColors = trendForChart.map(function(d) {
            return d.is_target ? '#f44336' : '#1a237e';
        });

        // For table: sort descending (newest first)
        var trendForTable = data.trend.slice().sort(function(a, b) {
            return b.build_number - a.build_number;
        });

        if (typeof console !== 'undefined') console.log('[TPMS] Chart data ready - labels:', labels.length);

        // Safely destroy previous chart
        if (window.trendChart) {
            try {
                if (typeof window.trendChart.destroy === 'function') {
                    window.trendChart.destroy();
                }
            } catch (e) {
                if (typeof console !== 'undefined') console.warn('[TPMS] Could not destroy previous chart:', e);
            }
            window.trendChart = null;
        }

        var ctx = document.getElementById('trendChart');
        if (!ctx) {
            alert('Canvas element not found');
            return;
        }

        if (typeof console !== 'undefined') console.log('[TPMS] Creating chart...');

        try {
            window.trendChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: data.metric_name,
                        data: values,
                        borderColor: '#1a237e',
                        backgroundColor: 'rgba(26, 35, 126, 0.05)',
                        fill: true,
                        tension: 0.3,
                        pointBackgroundColor: colors,
                        pointBorderColor: borderColors,
                        pointRadius: 6,
                        pointHoverRadius: 8,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: true, labels: { font: { size: 11 } } }
                    },
                    scales: {
                        y: { beginAtZero: false, ticks: { font: { size: 10 } } }
                    }
                }
            });
            if (typeof console !== 'undefined') console.log('[TPMS] Chart created successfully');
        } catch (chartError) {
            if (typeof console !== 'undefined') console.error('[TPMS] Chart creation error:', chartError);
            alert('Chart creation failed: ' + chartError.message);
            return;
        }

        var tbody = document.getElementById('trendTable').querySelector('tbody');
        tbody.innerHTML = '';
        trendForTable.forEach(function(row) {
            var tr = document.createElement('tr');
            if (row.is_target) {
                tr.style.background = '#ffebee';
                tr.style.fontWeight = '700';
            }
            tr.innerHTML = '<td style="padding:6px;border-bottom:1px solid #eee;font-weight:' + (row.is_target ? '700' : '400') + '">#' + row.build_number + ' ' + (row.is_target ? '← 현재' : '') + '</td>' +
                          '<td style="padding:6px;border-bottom:1px solid #eee;">' + escapeHtml(row.build_id || 'N/A') + '</td>' +
                          '<td style="padding:6px;border-bottom:1px solid #eee;font-weight:600;">' + (row.metric_value !== null ? row.metric_value : 'N/A') + '</td>' +
                          '<td style="padding:6px;border-bottom:1px solid #eee;font-size:11px;color:#666;">' + escapeHtml(row.test_time || '-') + '</td>';
            tbody.appendChild(tr);
        });

        if (typeof console !== 'undefined') console.log('[TPMS] Popup updated successfully');
    }).catch(function(err) {
        if (typeof console !== 'undefined') console.error('[TPMS] Error:', err.message || err);
        document.getElementById('trendTitle').innerHTML = 'Error loading trend data';
        var tbody = document.getElementById('trendTable').querySelector('tbody');
        tbody.innerHTML = '<tr><td colspan="4" style="padding:20px;text-align:center;color:#f44336;">' + (err.message || err) + '</td></tr>';
    });
}
