/**
 * Indeed PK Scraper — Frontend Application Logic
 * Handles API interactions, DOM updates, polling, and UI state.
 */

const API_BASE = window.location.origin;

// ── State ─────────────────────────────────────────────────────────
let currentScrapeId = null;
let pollInterval = null;
let allJobs = [];

// ── DOM Ready ─────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    loadStats();
    loadResults();
    loadAlerts();
    loadSchedules();
    loadAnalytics();
    setupEventListeners();
});

// ── Event Listeners ───────────────────────────────────────────────
function setupEventListeners() {
    // Search form
    document.getElementById('scrape-form').addEventListener('submit', (e) => {
        e.preventDefault();
        startScrape();
    });

    // Alert form
    document.getElementById('alert-form')?.addEventListener('submit', (e) => {
        e.preventDefault();
        createAlert();
    });

    // Schedule form
    document.getElementById('schedule-form')?.addEventListener('submit', (e) => {
        e.preventDefault();
        createSchedule();
    });

    // Proxy toggle
    document.getElementById('proxy-toggle').addEventListener('click', () => {
        const toggle = document.getElementById('proxy-toggle');
        const panel = document.getElementById('proxy-panel');
        toggle.classList.toggle('open');
        panel.classList.toggle('open');
    });

    // Export button
    document.getElementById('btn-export').addEventListener('click', exportExcel);

    // Export Sheets button
    document.getElementById('btn-export-sheets')?.addEventListener('click', exportSheets);

    // Clear button
    document.getElementById('btn-clear').addEventListener('click', clearResults);

    // Refresh logs
    document.getElementById('btn-refresh-logs').addEventListener('click', loadLogs);

    // Modal close
    document.getElementById('modal-close').addEventListener('click', closeModal);
    document.getElementById('modal-overlay').addEventListener('click', (e) => {
        if (e.target === document.getElementById('modal-overlay')) {
            closeModal();
        }
    });

    // Keyboard shortcut
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeModal();
    });
}

// ── API: Start Scrape ─────────────────────────────────────────────
async function startScrape() {
    const keyword = document.getElementById('search-input').value.trim();
    if (!keyword) {
        showToast('Please enter a job title keyword', 'error');
        return;
    }

    // Parse proxies
    const proxyText = document.getElementById('proxy-textarea')?.value.trim();
    let proxies = null;
    if (proxyText) {
        proxies = proxyText
            .split('\n')
            .map(p => p.trim())
            .filter(p => p.length > 0);
    }

    // Disable button
    const btn = document.getElementById('btn-scrape');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Starting...';

    try {
        const response = await fetch(`${API_BASE}/api/scrape`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ keyword, proxies }),
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'Failed to start scrape');
        }

        const data = await response.json();
        currentScrapeId = data.scrape_id;

        showToast(`Scraping started for "${keyword}"`, 'success');
        showProgress(data);
        startPolling();

    } catch (error) {
        showToast(error.message, 'error');
        btn.disabled = false;
        btn.innerHTML = '🔍 Start Scraping';
    }
}

// ── Polling ───────────────────────────────────────────────────────
function startPolling() {
    stopPolling();
    pollInterval = setInterval(async () => {
        if (!currentScrapeId) return;

        try {
            const response = await fetch(
                `${API_BASE}/api/scrape/${currentScrapeId}/status`
            );
            if (!response.ok) return;

            const data = await response.json();
            updateProgress(data);

            if (data.status === 'completed' || data.status === 'failed') {
                stopPolling();
                onScrapeComplete(data);
            }
        } catch (e) {
            console.error('Polling error:', e);
        }
    }, 2000);
}

function stopPolling() {
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
}

// ── Progress UI ───────────────────────────────────────────────────
function showProgress(data) {
    const section = document.getElementById('progress-section');
    section.classList.add('active');
    updateProgress(data);
}

function updateProgress(data) {
    // Status indicator
    const indicator = document.getElementById('status-indicator');
    indicator.className = `status-indicator ${data.status}`;

    const statusText = document.getElementById('status-text');
    const statusMap = {
        starting: 'Initializing...',
        running: 'Scraping in progress...',
        completed: 'Scrape completed!',
        failed: 'Scrape failed',
    };
    statusText.textContent = statusMap[data.status] || data.status;

    // Stats
    document.getElementById('prog-pages').textContent = data.pages_scraped || 0;
    document.getElementById('prog-found').textContent = data.jobs_found || 0;
    document.getElementById('prog-saved').textContent = data.jobs_saved || 0;
    document.getElementById('prog-errors').textContent = data.errors || 0;

    // Progress bar (estimate)
    const bar = document.getElementById('progress-bar');
    if (data.status === 'completed') {
        bar.style.width = '100%';
    } else if (data.jobs_found > 0) {
        // Estimate: each detail page takes time, so progress = saved / found
        const pct = Math.min(
            90,
            ((data.jobs_saved + data.errors) / Math.max(data.jobs_found, 1)) * 100
        );
        bar.style.width = `${Math.max(pct, 5)}%`;
    } else if (data.pages_scraped > 0) {
        bar.style.width = '10%';
    } else {
        bar.style.width = '2%';
    }

    // Message
    if (data.message) {
        document.getElementById('progress-message').textContent = data.message;
        document.getElementById('progress-message').style.display = 'block';
    }
}

function onScrapeComplete(data) {
    const btn = document.getElementById('btn-scrape');
    btn.disabled = false;
    btn.innerHTML = '🔍 Start Scraping';

    if (data.status === 'completed') {
        showToast(data.message || 'Scrape completed!', 'success');
    } else {
        showToast(data.message || 'Scrape failed', 'error');
    }

    // Refresh results and stats
    loadResults();
    loadStats();
    loadLogs();
}

// ── API: Load Results ─────────────────────────────────────────────
async function loadResults() {
    try {
        const response = await fetch(`${API_BASE}/api/results`);
        if (!response.ok) throw new Error('Failed to load results');

        const data = await response.json();
        allJobs = data.jobs || [];
        renderResults(allJobs);
        updateResultsCount(data.total);

    } catch (error) {
        console.error('Load results error:', error);
    }
}

function renderResults(jobs) {
    const tbody = document.getElementById('results-body');
    const empty = document.getElementById('empty-state');

    if (!jobs || jobs.length === 0) {
        tbody.innerHTML = '';
        empty.style.display = 'block';
        return;
    }

    empty.style.display = 'none';

    tbody.innerHTML = jobs.map((job, idx) => `
        <tr>
            <td class="title-cell">${escapeHtml(job.title)}</td>
            <td class="company-cell">${escapeHtml(job.company)}</td>
            <td>${escapeHtml(job.location)}</td>
            <td><span class="badge date">${escapeHtml(job.date_posted)}</span></td>
            <td><span class="badge type">${escapeHtml(job.job_type || 'N/A')}</span></td>
            <td>
                <div class="description-preview" onclick="viewJobDetail(${idx})">
                    ${escapeHtml(truncate(job.description, 120))}
                </div>
            </td>
            <td>
                ${job.apply_link
                    ? `<a href="${escapeHtml(job.apply_link)}" target="_blank" rel="noopener" class="apply-link">
                        Apply →
                       </a>`
                    : '<span style="color: var(--text-muted)">N/A</span>'
                }
            </td>
        </tr>
    `).join('');
}

function updateResultsCount(total) {
    document.getElementById('results-count').innerHTML =
        `Showing <span>${total}</span> job${total !== 1 ? 's' : ''}`;
}

// ── API: Export Excel ─────────────────────────────────────────────
async function exportExcel() {
    try {
        showToast('Generating Excel file...', 'info');

        const response = await fetch(`${API_BASE}/api/results/export`);
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'No jobs to export');
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;

        // Extract filename from Content-Disposition header
        const cd = response.headers.get('Content-Disposition');
        const filenameMatch = cd && cd.match(/filename="?(.+?)"?$/);
        a.download = filenameMatch ? filenameMatch[1] : 'indeed_pk_jobs.xlsx';

        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);

        showToast('Excel downloaded successfully!', 'success');
    } catch (error) {
        showToast(error.message, 'error');
    }
}

// ── API: Export Google Sheets ──────────────────────────────────────
async function exportSheets() {
    try {
        showToast('Exporting to Google Sheets. This might take a moment...', 'info');

        const btn = document.getElementById('btn-export-sheets');
        const originalText = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span> Exporting...';

        const response = await fetch(`${API_BASE}/api/results/export/sheets`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to export to Google Sheets');
        }

        const data = await response.json();
        
        // Open the Google Sheet URL
        if (data.url) {
            window.open(data.url, '_blank');
            showToast('Google Sheet created successfully!', 'success');
        }

        btn.disabled = false;
        btn.innerHTML = originalText;
    } catch (error) {
        showToast(error.message, 'error');
        const btn = document.getElementById('btn-export-sheets');
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '📈 Export to Google Sheets';
        }
    }
}

// ── API: Clear Results ────────────────────────────────────────────
async function clearResults() {
    if (!confirm('Are you sure you want to delete all scraped results?')) return;

    try {
        const response = await fetch(`${API_BASE}/api/results`, {
            method: 'DELETE',
        });

        if (!response.ok) throw new Error('Failed to clear results');

        showToast('All results cleared', 'success');
        loadResults();
        loadStats();
    } catch (error) {
        showToast(error.message, 'error');
    }
}

// ── API: Load Stats ───────────────────────────────────────────────
async function loadStats() {
    try {
        const response = await fetch(`${API_BASE}/api/stats`);
        if (!response.ok) return;

        const data = await response.json();
        document.getElementById('stat-total-jobs').textContent = data.total_jobs || 0;
        document.getElementById('stat-companies').textContent = data.unique_companies || 0;

        if (data.latest_scrape) {
            const d = new Date(data.latest_scrape);
            document.getElementById('stat-latest').textContent = d.toLocaleDateString('en-PK', {
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
            });
        } else {
            document.getElementById('stat-latest').textContent = 'Never';
        }
        
        loadAnalytics();
    } catch (e) {
        console.error('Stats error:', e);
    }
}

// ── API: Load Logs ────────────────────────────────────────────────
async function loadLogs() {
    try {
        const response = await fetch(`${API_BASE}/api/logs?lines=100`);
        if (!response.ok) return;

        const data = await response.json();
        const container = document.getElementById('logs-content');
        container.textContent = data.logs || 'No logs yet.';
        container.scrollTop = container.scrollHeight;
    } catch (e) {
        console.error('Logs error:', e);
    }
}

// ── Modal: View Job Detail ────────────────────────────────────────
function viewJobDetail(index) {
    const job = allJobs[index];
    if (!job) return;

    document.getElementById('modal-title').textContent = job.title;

    const body = document.getElementById('modal-body');
    body.innerHTML = `
        <span class="detail-label">Company</span>
        <div class="detail-value">${escapeHtml(job.company || 'N/A')}</div>

        <span class="detail-label">Location</span>
        <div class="detail-value">${escapeHtml(job.location || 'N/A')}</div>

        <span class="detail-label">Date Posted</span>
        <div class="detail-value">${escapeHtml(job.date_posted || 'N/A')}</div>

        <span class="detail-label">Job Type</span>
        <div class="detail-value">${escapeHtml(job.job_type || 'N/A')}</div>

        <span class="detail-label">Full Description</span>
        <div class="detail-value">${escapeHtml(job.description || 'No description available')}</div>

        <span class="detail-label">Apply Link</span>
        <div class="detail-value">
            ${job.apply_link
                ? `<a href="${escapeHtml(job.apply_link)}" target="_blank" rel="noopener" class="apply-link">${escapeHtml(job.apply_link)}</a>`
                : 'N/A'
            }
        </div>

        <span class="detail-label">Source URL</span>
        <div class="detail-value">
            <a href="${escapeHtml(job.source_url)}" target="_blank" rel="noopener" class="apply-link">${escapeHtml(job.source_url)}</a>
        </div>
    `;

    document.getElementById('modal-overlay').classList.add('active');
}

function closeModal() {
    document.getElementById('modal-overlay').classList.remove('active');
}

// ── Toast Notifications ───────────────────────────────────────────
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');

    const icons = {
        success: '✓',
        error: '✗',
        info: 'ℹ',
    };

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span>${icons[type] || 'ℹ'}</span> ${escapeHtml(message)}`;

    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('removing');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// ── Utility Functions ─────────────────────────────────────────────
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function truncate(text, maxLen = 100) {
    if (!text) return '';
    if (text.length <= maxLen) return text;
    return text.substring(0, maxLen) + '...';
}

// --- API: Email Alerts ---
async function loadAlerts() {
    try {
        const response = await fetch(`${API_BASE}/api/alerts`);
        if (!response.ok) throw new Error('Failed to fetch alerts');
        const alerts = await response.json();
        renderAlerts(alerts);
    } catch (err) {
        console.error(err);
        showToast('Error loading alerts', 'error');
    }
}

async function createAlert() {
    const email = document.getElementById('alert-email').value.trim();
    const keyword = document.getElementById('alert-keyword').value.trim();
    if (!email || !keyword) return;

    const btn = document.getElementById('btn-create-alert');
    btn.disabled = true;

    try {
        const response = await fetch(`${API_BASE}/api/alerts`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, keyword })
        });
        if (!response.ok) throw new Error('Failed to create alert');
        showToast('Alert created successfully', 'success');
        document.getElementById('alert-email').value = '';
        document.getElementById('alert-keyword').value = '';
        loadAlerts();
    } catch (err) {
        console.error(err);
        showToast('Error creating alert', 'error');
    } finally {
        btn.disabled = false;
    }
}

async function deleteAlert(id) {
    if (!confirm('Are you sure you want to delete this alert?')) return;
    try {
        const response = await fetch(`${API_BASE}/api/alerts/${id}`, { method: 'DELETE' });
        if (!response.ok) throw new Error('Failed to delete alert');
        showToast('Alert deleted', 'success');
        loadAlerts();
    } catch (err) {
        console.error(err);
        showToast('Error deleting alert', 'error');
    }
}

function renderAlerts(alerts) {
    const tbody = document.getElementById('alerts-body');
    if (!tbody) return;
    
    if (alerts.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--text-secondary);">No email alerts set up.</td></tr>';
        return;
    }

    tbody.innerHTML = alerts.map(alert => `
        <tr>
            <td>${escapeHtml(alert.email)}</td>
            <td>${escapeHtml(alert.keyword)}</td>
            <td>${new Date(alert.created_at).toLocaleDateString()}</td>
            <td>
                <button class="btn btn-danger btn-sm" onclick="deleteAlert('${alert.id}')" style="padding: 4px 8px; font-size: 0.8rem;">Delete</button>
            </td>
        </tr>
    `).join('');
}

// --- API: Schedules ---
async function loadSchedules() {
    try {
        const response = await fetch(`${API_BASE}/api/schedules`);
        if (!response.ok) throw new Error('Failed to fetch schedules');
        const schedules = await response.json();
        renderSchedules(schedules);
    } catch (err) {
        console.error(err);
        showToast('Error loading schedules', 'error');
    }
}

async function createSchedule() {
    const keyword = document.getElementById('schedule-keyword').value.trim();
    const frequency = document.getElementById('schedule-frequency').value;
    const proxyText = document.getElementById('proxy-textarea')?.value.trim();
    
    if (!keyword) return;

    let proxies = null;
    if (proxyText) {
        proxies = proxyText.split('\n').map(p => p.trim()).filter(p => p.length > 0);
    }

    const btn = document.getElementById('btn-create-schedule');
    btn.disabled = true;

    try {
        const response = await fetch(`${API_BASE}/api/schedules`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ keyword, frequency, proxies })
        });
        if (!response.ok) throw new Error('Failed to create schedule');
        showToast('Schedule created successfully', 'success');
        document.getElementById('schedule-keyword').value = '';
        loadSchedules();
    } catch (err) {
        console.error(err);
        showToast('Error creating schedule', 'error');
    } finally {
        btn.disabled = false;
    }
}

async function deleteSchedule(id) {
    if (!confirm('Are you sure you want to delete this schedule?')) return;
    try {
        const response = await fetch(`${API_BASE}/api/schedules/${id}`, { method: 'DELETE' });
        if (!response.ok) throw new Error('Failed to delete schedule');
        showToast('Schedule deleted', 'success');
        loadSchedules();
    } catch (err) {
        console.error(err);
        showToast('Error deleting schedule', 'error');
    }
}

function renderSchedules(schedules) {
    const tbody = document.getElementById('schedules-body');
    if (!tbody) return;
    
    if (schedules.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--text-secondary);">No active schedules.</td></tr>';
        return;
    }

    tbody.innerHTML = schedules.map(s => `
        <tr>
            <td>${escapeHtml(s.keyword)}</td>
            <td style="text-transform: capitalize;">${escapeHtml(s.frequency)}</td>
            <td>${s.next_run_at ? new Date(s.next_run_at).toLocaleString() : 'Now'}</td>
            <td>
                <button class="btn btn-danger btn-sm" onclick="deleteSchedule('${s.id}')" style="padding: 4px 8px; font-size: 0.8rem;">Delete</button>
            </td>
        </tr>
    `).join('');
}
let locationsChartInstance = null;
let jobTypesChartInstance = null;

async function loadAnalytics() {
    try {
        const res = await fetch(`${API_BASE}/api/analytics`);
        if (!res.ok) throw new Error('Failed to load analytics');
        const data = await res.json();
        renderCharts(data);
    } catch (e) {
        console.error(e);
    }
}

function renderCharts(data) {
    const locCtx = document.getElementById('locations-chart');
    const typeCtx = document.getElementById('job-types-chart');
    if (!locCtx || !typeCtx) return;

    if (locationsChartInstance) locationsChartInstance.destroy();
    if (jobTypesChartInstance) jobTypesChartInstance.destroy();

    const chartOptions = {
        responsive: true,
        plugins: {
            legend: {
                labels: { color: '#e0e0e0' }
            }
        },
        scales: {
            y: { ticks: { color: '#a0a0a0' }, grid: { color: 'rgba(255,255,255,0.1)' } },
            x: { ticks: { color: '#a0a0a0' }, grid: { color: 'rgba(255,255,255,0.1)' } }
        }
    };

    locationsChartInstance = new Chart(locCtx, {
        type: 'bar',
        data: {
            labels: data.locations.map(d => d.label),
            datasets: [{
                label: 'Jobs by Location',
                data: data.locations.map(d => d.count),
                backgroundColor: 'rgba(52, 152, 219, 0.6)',
                borderColor: 'rgba(52, 152, 219, 1)',
                borderWidth: 1
            }]
        },
        options: chartOptions
    });

    jobTypesChartInstance = new Chart(typeCtx, {
        type: 'pie',
        data: {
            labels: data.job_types.map(d => d.label),
            datasets: [{
                label: 'Jobs by Type',
                data: data.job_types.map(d => d.count),
                backgroundColor: [
                    'rgba(46, 204, 113, 0.6)',
                    'rgba(155, 89, 182, 0.6)',
                    'rgba(241, 196, 15, 0.6)',
                    'rgba(230, 126, 34, 0.6)',
                    'rgba(231, 76, 60, 0.6)'
                ],
                borderWidth: 1,
                borderColor: 'rgba(255,255,255,0.1)'
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { position: 'right', labels: { color: '#e0e0e0' } }
            }
        }
    });
}
