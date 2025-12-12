/**
 * Juna Admin Dashboard Logic
 * Handles API integration, Charts, and UI State.
 */

// --- Configuration ---
const API_BASE = '/api/v1/admin';
const REFRESH_INTERVAL = 60000; // 60s

// --- State ---
const state = {
    view: 'overview',
    range: 'today',
    startDate: null,
    endDate: null,

    // Volume Chart Metric
    volumeMetric: 'queries',

    // Feedback
    fbRating: 1, // 1 (pos) or -1 (neg)
    fbPage: 1,
    fbSearch: '',

    // Auto Refresh
    refreshTimer: null,
    loading: false
};

// --- Initialization ---

document.addEventListener('DOMContentLoaded', () => {
    // Restore View
    const savedView = localStorage.getItem('admin_view');
    if (savedView) {
        state.view = savedView;
        document.querySelectorAll('.view-section').forEach(s => s.classList.remove('active'));
        document.getElementById(`view-${savedView}`).classList.add('active');
    } else {
        // If no saved view, default to 'overview' and activate it
        state.view = 'overview';
        document.getElementById('view-overview').classList.add('active');
    }

    // UPDATE: Set body attribute for CSS scoping
    document.body.dataset.view = state.view;

    // Restore Chart Metric (for Trends page)
    const savedMetric = localStorage.getItem('admin_chart_metric');
    const allowedMetrics = ['queries', 'positive', 'negative'];
    if (savedMetric && allowedMetrics.includes(savedMetric)) {
        state.volumeMetric = savedMetric;

        // Update active tab (if tabs are present)
        document.querySelectorAll('.chart-tab').forEach(tab => {
            tab.classList.remove('active');
            if (tab.dataset.metric === savedMetric) {
                tab.classList.add('active');
            }
        });
    }

    // Set UI Active State for navigation items based on restored view
    document.querySelectorAll('.nav-item').forEach(item => {
        if (item.dataset.view === state.view) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });


    initNavigation();
    initDateFilters();
    initFeedbackControls();

    // Initial Load
    fetchData();

    // Auto Refresh
    startAutoRefresh();
});

// --- Navigation ---

function initNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            // Update UI
            navItems.forEach(n => n.classList.remove('active'));
            item.classList.add('active');

            // Switch View
            const view = item.dataset.view;
            document.querySelectorAll('.view-section').forEach(s => s.classList.remove('active'));
            document.getElementById(`view-${view}`).classList.add('active');

            state.view = view;
            document.body.dataset.view = view; // UPDATE: CSS Scoping
            localStorage.setItem('admin_view', view);

            fetchData();
        });
    });

    document.getElementById('refreshBtn').addEventListener('click', fetchData);
    document.getElementById('exportBtn').addEventListener('click', handleExport);

    // Tab switching for Volume chart metrics
    document.querySelectorAll('.chart-tab').forEach(tab => {
        tab.addEventListener('click', (e) => {
            const metric = e.target.dataset.metric;

            // Update active state
            document.querySelectorAll('.chart-tab').forEach(t => t.classList.remove('active'));
            e.target.classList.add('active');

            // Update state and re-render chart
            state.volumeMetric = metric;
            localStorage.setItem('admin_chart_metric', metric); // Persist selection
            updateVolumeChart(metric);
        });
    });
}

// ... existing code ...

// --- Date Filters ---


function initDateFilters() {
    const select = document.getElementById('rangeSelect');
    const customDiv = document.getElementById('customDateInputs');

    // SYNC STATE WITH DROPDOWN ON INIT (Fix for refresh preserving filter)
    state.range = select.value;

    select.addEventListener('change', (e) => {
        state.range = e.target.value;
        if (state.range === 'custom') {
            customDiv.style.display = 'flex';
        } else {
            customDiv.style.display = 'none';
            fetchData();
        }
    });

    document.getElementById('applyCustomBtn').addEventListener('click', () => {
        state.startDate = document.getElementById('startDate').value;
        state.endDate = document.getElementById('endDate').value;

        if (!state.startDate || !state.endDate) {
            showError("Please select both start and end dates");
            return;
        }
        fetchData();
    });
}

function getQueryParams() {
    const p = new URLSearchParams({ range: state.range });
    if (state.range === 'custom') {
        p.append('start_date', state.startDate);
        p.append('end_date', state.endDate);
    }
    return p;
}

// --- Data Fetching ---

async function fetchData() {
    if (state.loading) return;
    setLoading(true);
    hideError();

    try {
        const params = getQueryParams();

        // 1. Always load summary for the header badges/KPIs? 
        // Or per view. Let's load generic data based on view.
        // Actually, to keep sidebar responsive, usually we fetch per view.

        if (state.view === 'overview') {
            const summary = await fetchAPI(`/summary?${params}`);
            renderOverview(summary);

            // Load feedback separately
            loadFeedback();
        }
        else if (state.view === 'trends') {
            const trends = await fetchAPI(`/trends?${params}`);
            renderTrends(trends);
        }
        else if (state.view === 'spend') {
            const spend = await fetchAPI(`/spend?${params}`);
            renderSpend(spend);
        }

    } catch (err) {
        showError(err.message);
    } finally {
        setLoading(false);
    }
}

async function fetchAPI(endpoint) {
    const res = await fetch(`${API_BASE}${endpoint}`);
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `API Error: ${res.status}`);
    }
    return res.json();
}

// --- Rendering: Overview ---

function renderOverview(data) {
    setText('kpi-queries', formatNum(data.total_queries));

    setText('kpi-phone-esc', data.phone_escalations);
    setText('kpi-email-esc', data.email_escalations);

    setText('kpi-pos-count', formatNum(data.positive_feedback_count));
    setText('kpi-pos-rate', `${data.positive_feedback_rate}%`);

    setText('kpi-neg-count', formatNum(data.negative_feedback_count));
    setText('kpi-neg-rate', `${data.negative_feedback_rate}%`);
}

// --- Rendering: Feedback ---

function initFeedbackControls() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            state.fbRating = parseInt(e.target.dataset.rating);
            state.fbPage = 1;
            loadFeedback();
        });
    });

    // Debounced Search
    let timeout;
    document.getElementById('feedbackSearch').addEventListener('input', (e) => {
        state.fbSearch = e.target.value;
        state.fbPage = 1;
        clearTimeout(timeout);
        timeout = setTimeout(loadFeedback, 500);
    });

    document.getElementById('prevPage').addEventListener('click', () => {
        if (state.fbPage > 1) {
            state.fbPage--;
            loadFeedback();
        }
    });

    document.getElementById('nextPage').addEventListener('click', () => {
        state.fbPage++;
        loadFeedback();
    });
}

async function loadFeedback() {
    const params = getQueryParams();
    params.append('rating', state.fbRating);
    params.append('page', state.fbPage);
    params.append('page_size', 20);
    if (state.fbSearch) params.append('search', state.fbSearch);

    try {
        const data = await fetchAPI(`/feedback?${params}`);
        renderFeedbackList(data);
    } catch (err) {
        console.error("Failed to load feedback", err);
        // Don't separate error UI for this part, just log
    }
}

function renderFeedbackList(data) {
    const container = document.getElementById('feedbackList');
    container.innerHTML = '';

    if (data.items.length === 0) {
        container.innerHTML = '<div style="padding: 20px; text-align: center; color: #666;">No feedback found.</div>';
    }

    data.items.forEach(item => {
        const el = document.createElement('div');
        el.className = 'feedback-item';
        el.onclick = () => el.classList.toggle('expanded');

        // Backend returns UTC timestamp without Z, so add it for proper parsing
        const utcTimestamp = item.timestamp.endsWith('Z') ? item.timestamp : item.timestamp + 'Z';
        const date = new Date(utcTimestamp);

        // Display in EST timezone
        const dateStr = new Intl.DateTimeFormat('en-US', {
            timeZone: 'America/New_York',
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: true
        }).format(date);

        el.innerHTML = `
            <div class="feedback-summary">
                <div>
                    <strong>${escapeHTML(item.user_query.substring(0, 60))}...</strong>
                </div>
                <div class="fb-meta">
                    ${dateStr} <i class="fas fa-chevron-down"></i>
                </div>
            </div>
            <div class="fb-details">
                <div class="fb-query">
                    <span class="fb-label">Query</span>
                    ${escapeHTML(item.user_query)}
                </div>
                <div class="fb-response">
                    <span class="fb-label">Response</span>
                    ${escapeHTML(item.bot_response)}
                </div>
            </div>
        `;
        container.appendChild(el);
    });

    // Pagination
    document.getElementById('pageInfo').innerText = `Page ${data.page} of ${data.pages || 1}`;
    document.getElementById('prevPage').disabled = data.page <= 1;
    document.getElementById('nextPage').disabled = data.page >= data.pages;
}

// --- Rendering: Trends (Charts) ---

let charts = {};
let trendsData = null; // Cache for tab switching

function renderTrends(data) {
    // Cache data globally for tab switching
    trendsData = data;

    // 1. Volume Chart with current metric
    updateVolumeChart(state.volumeMetric);

    // 2. Category Chart (full width now)
    const cats = Object.entries(data.categories); // [['Hardware/Device', 10], ...]
    const categoryData = cats.map(c => c[1]);
    const totalCount = categoryData.reduce((sum, val) => sum + val, 0);

    // PRIORITY-BASED CATEGORY COLOR MAPPING
    const categoryColorMap = {
        'outage': '#EF4444',
        'payment': '#7C3AED',
        'network/connectivity': '#F97316',
        'hardware/device': '#A16207',
        'software/application': '#EAB308',
        'billing': '#22C55E',
        'product info': '#3B82F6',
        'general inquiry': '#9CA3AF'
    };

    // Map colors to categories
    const catColors = cats.map(([categoryName]) => {
        const normalized = categoryName.toLowerCase().replace(/\s+/g, '/');
        return categoryColorMap[normalized] || '#9CA3AF';
    });

    // GENERATE CUSTOM LEGEND (Inline Header)
    const legendContainer = document.getElementById('categoryLegend');
    if (legendContainer) {
        legendContainer.innerHTML = '';
        cats.forEach(([categoryName], index) => {
            const label = titleCase(categoryName);
            const color = catColors[index];

            const item = document.createElement('div');
            item.className = 'legend-item';
            item.innerHTML = `<div class="legend-dot" style="background-color: ${color}"></div>${label}`;
            legendContainer.appendChild(item);
        });
    }

    renderChart('chartCategories', 'doughnut', {
        labels: cats.map(c => titleCase(c[0])),
        datasets: [{
            data: categoryData,
            borderWidth: 0, // UPDATE: Remove white borders
            hoverBorderWidth: 0,
            borderColor: 'transparent',
            backgroundColor: catColors
        }]
    }, {
        plugins: {
            tooltip: {
                callbacks: {
                    label: function (context) {
                        const label = context.label || '';
                        const value = context.parsed || 0;
                        const percent = totalCount > 0 ? ((value / totalCount) * 100).toFixed(1) : 0;
                        return `${label}: ${value} (${percent}%)`;
                    }
                }
            },
            legend: {
                display: false // DISABLE CHARTJS LEGEND (Handled custom inline)
            }
        }
    });
}

function updateVolumeChart(metric) {
    if (!trendsData) return;

    // Map range to time unit (must match backend granularity)
    let timeUnit;
    switch (state.range) {
        case 'today':
            timeUnit = 'hour';
            break;
        case 'week':
        case 'month':
            timeUnit = 'day';
            break;
        case 'year':
            timeUnit = 'month';
            break;
        default:
            timeUnit = 'day'; // Safe fallback
    }

    const labels = trendsData.message_volume.labels;

    let dataset, yAxisConfig;

    // Common axis styles
    const axisStyles = {
        grid: { color: 'rgba(255, 255, 255, 0.05)' }, // UPDATE: Visible grid
        ticks: { color: '#9ca3af' }
    };

    // Y-Axis config factory
    const createYAxis = (title) => ({
        beginAtZero: true,
        suggestedMax: 5,
        title: { display: true, text: title, color: '#9ca3af' },
        ...axisStyles
    });

    switch (metric) {
        case 'queries':
            dataset = {
                label: 'Queries',
                data: trendsData.message_volume.queries,
                borderColor: '#3b82f6',
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                fill: false,
                tension: 0.3
            };
            yAxisConfig = createYAxis('Count');
            break;

        case 'positive':
            dataset = {
                label: 'Positive Feedback',
                data: trendsData.feedback_trend.positive_count,
                borderColor: '#10b981',
                backgroundColor: 'rgba(16, 185, 129, 0.2)',
                fill: true,
                tension: 0.3
            };
            yAxisConfig = createYAxis('Count');
            break;

        case 'negative':
            dataset = {
                label: 'Negative Feedback',
                data: trendsData.feedback_trend.negative_count,
                borderColor: '#ef4444',
                backgroundColor: 'rgba(239, 68, 68, 0.2)',
                fill: true,
                tension: 0.3
            };
            yAxisConfig = createYAxis('Count');
            break;
    }

    const config = {
        labels: labels,
        datasets: [dataset]
    };

    const options = {
        plugins: {
            legend: {
                display: false // Hide the legend toggle
            }
        },
        scales: {
            x: {
                type: 'time',
                time: {
                    unit: timeUnit,
                    displayFormats: {
                        hour: 'h a',        // "12 AM", "1 PM"
                        day: 'MMM d',       // "Dec 11", "Dec 12"
                        month: 'MMM'        // "Jan", "Feb", "Mar"
                    }
                },
                ...axisStyles
            },
            y: yAxisConfig
        }
    };

    // Check if chart exists
    if (charts.chartVolume) {
        // Update existing chart (no re-mount)
        charts.chartVolume.data = config;
        charts.chartVolume.options.scales.x.time.unit = timeUnit; // Update time unit
        charts.chartVolume.options.scales.y = yAxisConfig;

        // Explicitly update grid colors if chart exists
        charts.chartVolume.options.scales.x.grid = axisStyles.grid;
        charts.chartVolume.options.scales.y.grid = axisStyles.grid;

        charts.chartVolume.update();
    } else {
        // Initial render
        renderChart('chartVolume', 'line', config, options);
    }
}


document.addEventListener('DOMContentLoaded', () => {
    // Navigation Logic
    // -------------------------------------------------------------------------
    function showPage(pageId) {
        // Update Sidebar
        document.querySelectorAll('.sidebar li').forEach(li => li.classList.remove('active'));
        const activeLink = document.querySelector(`.sidebar li[onclick*="'${pageId}'"]`);
        if (activeLink) activeLink.classList.add('active');

        // Update Content
        document.querySelectorAll('.page-section').forEach(el => el.classList.remove('active'));
        document.getElementById(pageId).classList.add('active');

        // Save state
        localStorage.setItem('admin_active_page', pageId);

        // Refresh Data if needed
        if (pageId === 'overview') loadOverview();
        if (pageId === 'trends') loadTrends();
        if (pageId === 'spend') loadSpend();
    }

    // Load initial state
    const savedPage = localStorage.getItem('admin_active_page') || 'overview';
    showPage(savedPage);
});

// Chart.js Helpers

function renderChart(id, type, data, options = {}) {
    const ctx = document.getElementById(id).getContext('2d');
    if (charts[id]) {
        charts[id].destroy();
    }

    charts[id] = new Chart(ctx, {
        type: type,
        data: data,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            elements: {
                arc: {
                    borderWidth: 0 // Global fallback for no borders
                }
            },
            ...options
        }
    });
}

// --- Rendering: Spend ---

function renderSpend(data) {
    setText('spend-total', `$${data.total_spend}`);
    setText('spend-tokens', `$${data.token_cost}`);
    setText('spend-avg', `$${data.avg_per_query}`);

    const tbody = document.getElementById('tokenTableBody');
    const bd = data.breakdown;

    tbody.innerHTML = `
        <tr><td>Total Queries</td><td>${formatNum(bd.queries)}</td></tr>
        <tr><td>Input Tokens</td><td>${formatNum(bd.input_tokens)}</td></tr>
        <tr><td>Output Tokens</td><td>${formatNum(bd.output_tokens)}</td></tr>
        <tr><td>Embedding Tokens</td><td>${formatNum(bd.embedding_tokens)}</td></tr>
    `;
}

// --- Utilities ---

function handleExport() {
    const params = getQueryParams();
    window.location.href = `${API_BASE}/feedback/export?${params}`;
}

function startAutoRefresh() {
    if (state.refreshTimer) clearInterval(state.refreshTimer);
    state.refreshTimer = setInterval(() => {
        // Only refresh if tab is visible to save resources
        if (!document.hidden && !state.loading) {
            console.log("Auto-refreshing...");
            fetchData();
            // Check alerts silently
            fetchAPI('/run-alert-check').catch(e => console.warn(e));
        }
    }, REFRESH_INTERVAL);
}

function setLoading(bool) {
    state.loading = bool;
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) overlay.style.display = bool ? 'flex' : 'none';
}

function showError(msg) {
    const banner = document.getElementById('errorBanner');
    document.getElementById('errorMessage').innerText = msg;
    banner.style.display = 'flex';
}

function hideError() {
    document.getElementById('errorBanner').style.display = 'none';
}

function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.innerText = val !== undefined && val !== null ? val : '-';
}

function formatNum(n) {
    return new Intl.NumberFormat().format(n);
}

function escapeHTML(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function titleCase(str) {
    return str.replace(/\b\w/g, s => s.toUpperCase());
}
