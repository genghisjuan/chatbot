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
            fetchData();
        });
    });

    document.getElementById('refreshBtn').addEventListener('click', fetchData);
    document.getElementById('exportBtn').addEventListener('click', handleExport);
}

// --- Date Filters ---

function initDateFilters() {
    const select = document.getElementById('rangeSelect');
    const customDiv = document.getElementById('customDateInputs');

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
    setText('kpi-conversations', formatNum(data.total_conversations));
    setText('kpi-queries', formatNum(data.total_queries));
    setText('kpi-avg-queries', data.avg_queries_per_conversation);

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

        const date = new Date(item.timestamp).toLocaleString();

        el.innerHTML = `
            <div class="feedback-summary">
                <div>
                    <strong>${escapeHTML(item.user_query.substring(0, 60))}...</strong>
                </div>
                <div class="fb-meta">
                    ${date} <i class="fas fa-chevron-down"></i>
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

function renderTrends(data) {
    // 1. Volume Chart
    renderChart('chartVolume', 'line', {
        labels: data.message_volume.labels,
        datasets: [
            {
                label: 'Queries',
                data: data.message_volume.queries,
                borderColor: '#3b82f6',
                tension: 0.3
            },
            {
                label: 'Conversations',
                data: data.message_volume.conversations,
                borderColor: '#10b981',
                tension: 0.3
            }
        ]
    });

    // 2. Feedback Chart
    renderChart('chartFeedback', 'bar', {
        labels: data.feedback_trend.labels,
        datasets: [
            {
                label: 'Positive %',
                data: data.feedback_trend.positive_rate,
                backgroundColor: '#10b981'
            },
            {
                label: 'Negative %',
                data: data.feedback_trend.negative_rate,
                backgroundColor: '#ef4444'
            }
        ]
    });

    // 3. Category Chart
    const cats = Object.entries(data.categories); // [['hw', 10], ...]
    renderChart('chartCategories', 'doughnut', {
        labels: cats.map(c => titleCase(c[0])),
        datasets: [{
            data: cats.map(c => c[1]),
            backgroundColor: [
                '#3b82f6', '#10b981', '#f59e0b', '#ef4444',
                '#8b5cf6', '#ec4899', '#6366f1', '#64748b'
            ]
        }]
    });
}

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
            scales: type === 'doughnut' ? {} : {
                x: {
                    type: 'time',
                    time: { unit: 'day', displayFormats: { day: 'MMM d' } }
                },
                y: { beginAtZero: true }
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
