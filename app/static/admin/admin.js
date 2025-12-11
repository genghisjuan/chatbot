/**
 * Admin Analytics Dashboard
 * 
 * Handles data visualization, user interactions, and API communication
 * for the analytics admin interface.
 */

// =============================================================================
// CONSTANTS & STATE
// =============================================================================

const API_BASE = '/api/v1/admin';
const CHART_COLORS = {
    primary: '#667eea',
    success: '#10b981',
    warning: '#f59e0b',
    danger: '#ef4444',
    purple: '#8b5cf6',
    green: '#48bb78',
    grid: '#2d3748'
};

const paginationState = {
    positive: { currentPage: 1, totalCount: 0, pageSize: 12 },
    negative: { currentPage: 1, totalCount: 0, pageSize: 12 }
};

// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================

/**
 * Helper to fetch JSON data with error handling.
 */
async function fetchAPI(endpoint) {
    const res = await fetch(endpoint);
    if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    }
    return res.json();
}

/**
 * Format currency with appropriate precision.
 */
function formatCurrency(val) {
    if (!val || val === 0) return '$0.00';
    if (val < 0.0001) return '$' + val.toFixed(6);
    if (val < 0.01) return '$' + val.toFixed(4);
    return '$' + val.toFixed(2);
}

/**
 * Format large numbers with commas.
 */
function formatNumber(val) {
    return (val || 0).toLocaleString();
}

/**
 * Show/Hide loading state for an element.
 */
function showLoading(element) {
    if (element) {
        element.classList.add('loading');
        element.setAttribute('aria-busy', 'true');
    }
}

function hideLoading(element) {
    if (element) {
        element.classList.remove('loading');
        element.setAttribute('aria-busy', 'false');
    }
}

/**
 * Show error message to user (console + potential toast).
 */
function showError(message) {
    console.error('User-facing error:', message);
}

/**
 * Escape HTML to prevent XSS.
 */
function escapeHtml(unsafe) {
    if (!unsafe) return '';
    return String(unsafe)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

/**
 * Format response text as markdown (using marked.js).
 */
function formatResponse(text) {
    if (!text) return '';
    if (typeof marked === 'undefined' || !marked.parse) {
        return escapeHtml(text);
    }
    try {
        return marked.parse(text);
    } catch (e) {
        console.error('Markdown parse error:', e);
        return escapeHtml(text);
    }
}

/**
 * Parse trend date helpers.
 */
function parseTrendDate(dateStr) {
    if (!dateStr) return null;
    dateStr = String(dateStr);

    // Normalize to ISO format (append 'Z' if missing and not explicitly local)
    if (!dateStr.includes('T')) {
        if (dateStr.length === 10) dateStr += 'T00:00:00'; // YYYY-MM-DD
        else if (dateStr.length === 13) dateStr = dateStr.replace(' ', 'T') + ':00:00'; // YYYY-MM-DD HH
        else if (dateStr.length === 16) dateStr = dateStr.replace(' ', 'T') + ':00'; // YYYY-MM-DD HH:MM
    }
    if (!dateStr.endsWith('Z')) dateStr += 'Z'; // Treat as UTC
    return new Date(dateStr);
}

// =============================================================================
// DATA FETCHING & RENDERING
// =============================================================================

/**
 * Load Summary Stats (Cards).
 */
async function loadStats(params = {}) {
    try {
        const query = new URLSearchParams(params).toString();
        const data = await fetchAPI(`${API_BASE}/summary?${query}`);

        if (!data) throw new Error('Empty data');

        const updates = [
            ['statDaily', data.messages_today],
            ['statWeekly', data.messages_week],
            ['statMonthly', data.messages_month],
            ['statPositive', data.positive_percentage != null ? data.positive_percentage + '%' : '--%'],
            ['statNegative', data.negative_percentage != null ? data.negative_percentage + '%' : '--%']
        ];

        updates.forEach(([id, val]) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        });

    } catch (e) {
        showError(`Failed to load stats: ${e.message}`);
        document.querySelectorAll('.stat-value').forEach(el => {
            if (el.textContent === '--') el.textContent = 'Error';
        });
    }
}

/**
 * Load Spend Stats.
 */
async function loadSpend() {
    try {
        const data = await fetchAPI(`${API_BASE}/spend`);

        // Update Stats Cards
        ['today', 'week', 'month', 'all_time'].forEach(key => {
            const el = document.getElementById(`spend${key.charAt(0).toUpperCase() + key.slice(1).replace('_', '')}`);
            if (el) el.textContent = formatCurrency(data[key]);
        });

        // Update Token Counts
        const elQuery = document.getElementById('spendQueryCount');
        if (elQuery) elQuery.textContent = formatNumber(data.all_time_queries);

        ['input', 'output', 'embedding'].forEach(type => {
            const tokens = data.all_time_tokens?.[type] || 0;
            const el = document.getElementById(`spend${type.charAt(0).toUpperCase() + type.slice(1)}Tokens`);
            if (el) el.textContent = formatNumber(tokens);
        });

        // Pricing Info
        if (data.pricing) {
            const elIn = document.getElementById('pricingInput');
            const elOut = document.getElementById('pricingOutput');
            if (elIn) elIn.textContent = data.pricing.input_per_1m;
            if (elOut) elOut.textContent = data.pricing.output_per_1m;
        }

        // Calculate Average
        const elAvg = document.getElementById('spendAvg');
        if (elAvg) {
            const total = data.all_time || 0;
            const count = data.all_time_queries || 1;
            elAvg.textContent = formatCurrency(total / count);
        }

    } catch (e) {
        showError(`Failed to load spend: ${e.message}`);
    }
}

// =============================================================================
// FEEDBACK & PAGINATION LOGIC
// =============================================================================

/**
 * Load both feedback tabs (resetting to page 1).
 */
async function loadFeedback(params = {}) {
    // Reset pagination
    paginationState.positive.currentPage = 1;
    paginationState.negative.currentPage = 1;

    // Load both tabs parallel
    await Promise.all([
        loadFeedbackTab('positive', params),
        loadFeedbackTab('negative', params)
    ]);

    // Update controls
    updatePaginationControls('positive');
    updatePaginationControls('negative');
}

/**
 * Load specific feedback tab.
 */
async function loadFeedbackTab(sentiment, params = {}) {
    const rating = sentiment === 'positive' ? 'up' : 'down';
    const containerId = `${sentiment}Content`;
    const state = paginationState[sentiment];

    const container = document.getElementById(containerId);
    if (!container) return;

    try {
        const query = new URLSearchParams(params);
        query.set('rating', rating);
        query.set('page', state.currentPage);
        query.set('page_size', state.pageSize);

        const data = await fetchAPI(`${API_BASE}/feedback?${query.toString()}`);

        state.totalCount = data.totalCount || 0;
        renderFeedbackCards(data.items || [], containerId);

    } catch (e) {
        console.error(`Error loading ${sentiment}:`, e);
        showError(`Failed to load ${sentiment}: ${e.message}`);
        container.innerHTML = `<div class="empty-state">Unable to load feedback. Server reported: ${e.message}</div>`;
    }
}

/**
 * Change page for the given tab.
 */
async function changePage(sentiment, direction) {
    const state = paginationState[sentiment];
    const maxPage = Math.ceil(state.totalCount / state.pageSize);
    const newPage = state.currentPage + direction;

    if (newPage < 1 || newPage > maxPage) return;

    state.currentPage = newPage;

    // Re-apply current global filters
    const params = getGlobalFilterParams();
    await loadFeedbackTab(sentiment, params);
    updatePaginationControls(sentiment);
}

/**
 * Determine active tab and change page (Warning: used by HTML onclick).
 */
function changePageForActiveTab(direction) {
    const activeTab = document.querySelector('.tab.active');
    if (!activeTab) return;
    changePage(activeTab.dataset.tab, direction);
}

/**
 * Update logic for pagination buttons visibility.
 */
function updatePaginationControls(sentiment) {
    const activeTab = document.querySelector('.tab.active');
    if (!activeTab || activeTab.dataset.tab !== sentiment) return; // Only update if visible

    const state = paginationState[sentiment];
    const totalPages = Math.ceil(state.totalCount / state.pageSize);
    const controls = document.getElementById('feedbackPagination');

    if (!controls) return;

    if (state.totalCount <= state.pageSize) {
        controls.style.display = 'none';
        return;
    }

    controls.style.display = 'flex';

    const prevBtn = controls.querySelector('.prev-btn');
    const nextBtn = controls.querySelector('.next-btn');
    const pageInfo = controls.querySelector('.page-info');

    if (prevBtn) prevBtn.disabled = state.currentPage === 1;
    if (nextBtn) nextBtn.disabled = state.currentPage >= totalPages;
    if (pageInfo) pageInfo.textContent = `Page ${state.currentPage} of ${totalPages}`;
}

/**
 * Render list of feedback cards.
 */
function renderFeedbackCards(items, containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    container.innerHTML = '';

    if (!items.length) {
        container.innerHTML = '<div class="empty-state">No feedback found for this period.</div>';
        return;
    }

    items.forEach(item => {
        const card = document.createElement('div');
        card.className = 'feedback-detail-card';

        // Parse date
        let dateStr = 'Unknown Date';
        if (item.timestamp) {
            dateStr = new Date(item.timestamp).toLocaleString();
        }

        card.innerHTML = `
            <div class="feedback-header">
                <div>
                    <span class="feedback-icon ${item.rating === 'up' ? 'positive' : 'negative'}">
                        <i class="fas fa-thumbs-${item.rating === 'up' ? 'up' : 'down'}"></i>
                    </span>
                    <span class="feedback-date">${dateStr}</span>
                </div>
                <i class="fas fa-chevron-down expand-icon"></i>
            </div>
            <div class="feedback-body">
                <div class="feedback-section-title">User Query</div>
                <div class="feedback-user-query">${escapeHtml(item.user_query)}</div>
                
                <div class="feedback-section-title">AI Response</div>
                <div class="feedback-bot-response">
                    <div class="markdown-body">${formatResponse(item.bot_response || '')}</div>
                </div>
            </div>
        `;

        card.querySelector('.feedback-header').addEventListener('click', function () {
            this.parentElement.classList.toggle('expanded');
        });

        container.appendChild(card);
    });
}

// =============================================================================
// TREND CHARTS
// =============================================================================

async function loadTrend(days = 7, startDate = null, endDate = null) {
    try {
        // Granularity Logic
        let granularity = 'day';
        if (days === 1) granularity = 'hour';
        if (days === 365) granularity = 'month';
        if (days === 'custom' && startDate === endDate) granularity = 'hour';

        // Auto-set today date if days=1
        if (days === 1 && !startDate) {
            const today = new Date().toISOString().split('T')[0];
            startDate = endDate = today;
        }

        const offset = -new Date().getTimezoneOffset();
        const params = new URLSearchParams({
            days: days === 'custom' ? 0 : days,
            granularity: granularity,
            timezone_offset: offset
        });

        if (startDate && endDate) {
            params.set('start_date', startDate);
            params.set('end_date', endDate);
        }

        const [msgData, fbData] = await Promise.all([
            fetchAPI(`${API_BASE}/messages-trend?${params}`),
            fetchAPI(`${API_BASE}/feedback-trend?${params}`)
        ]);

        renderTrendChart(msgData.trend, granularity);
        renderSatisfactionChart(fbData, granularity, days === 1);
        updateTrendTotals(msgData.trend, fbData, days === 1);

    } catch (e) {
        showError(`Trend error: ${e.message}`);
        ['noTrendData', 'trendError', 'feedbackError'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.style.display = 'block';
        });
    }
}

function renderTrendChart(trendData, granularity) {
    const ctx = document.getElementById('trendChart')?.getContext('2d');
    if (!ctx) return;

    if (window.myTrendChart) window.myTrendChart.destroy();

    const labels = trendData.map(t => formatTrendLabel(t.date, granularity));
    const data = trendData.map(t => t.count);

    window.myTrendChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Messages',
                data: data,
                backgroundColor: CHART_COLORS.primary,
                borderRadius: 4,
                barPercentage: 0.6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: true, grid: { color: CHART_COLORS.grid } },
                x: { display: true, grid: { display: false } }
            }
        }
    });

    const noData = document.getElementById('noTrendData');
    if (noData) noData.style.display = data.some(v => v > 0) ? 'none' : 'block';
}

function renderSatisfactionChart(fbData, granularity, showRealtime) {
    const ctx = document.getElementById('feedbackChart')?.getContext('2d');
    if (!ctx) return;

    if (window.myFeedbackChart) window.myFeedbackChart.destroy();

    const trend = fbData.trend || [];
    let cumulativeUp = fbData.baseline_up || 0;
    let cumulativeTotal = cumulativeUp + (fbData.baseline_down || 0);

    const labels = [];
    const points = [];

    trend.forEach(t => {
        cumulativeUp += t.up;
        cumulativeTotal += (t.up + t.down);
        labels.push(formatTrendLabel(t.date, granularity));
        points.push(cumulativeTotal > 0 ? ((cumulativeUp / cumulativeTotal) * 100).toFixed(1) : 0);
    });

    window.myFeedbackChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Satisfaction %',
                data: points,
                borderColor: CHART_COLORS.green,
                backgroundColor: 'rgba(72, 187, 120, 0.1)',
                tension: 0.1,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: true, max: 100, ticks: { callback: v => v + '%' }, grid: { color: CHART_COLORS.grid } },
                x: { display: true, grid: { display: false } }
            }
        }
    });
}

function updateTrendTotals(msgTrend, fbData, isToday) {
    const elMsg = document.getElementById('trendTotalMsg');
    const elSat = document.getElementById('trendTotalSat');
    if (!elMsg || !elSat) return;

    if (!isToday) {
        elMsg.textContent = '';
        elSat.textContent = '';
        return;
    }

    const totalMsg = msgTrend.reduce((sum, t) => sum + t.count, 0);

    // Total Sat Calculation
    const totalUp = (fbData.baseline_up || 0) + (fbData.trend || []).reduce((s, t) => s + t.up, 0);
    const totalDown = (fbData.baseline_down || 0) + (fbData.trend || []).reduce((s, t) => s + t.down, 0);
    const total = totalUp + totalDown;
    const sat = total > 0 ? ((totalUp / total) * 100).toFixed(1) : 0;

    elMsg.textContent = `(${totalMsg})`;
    elSat.textContent = `(${sat}%)`;
}

function formatTrendLabel(dateStr, granularity) {
    const d = parseTrendDate(dateStr);
    if (!d) return '';

    if (granularity === 'hour') return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    if (granularity === 'month') return d.toLocaleDateString('en-US', { month: 'short' });
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
}

function getGlobalFilterParams() {
    const period = document.getElementById('periodFilter')?.value;
    const params = { timezone_offset: -new Date().getTimezoneOffset() };

    if (period === 'custom') {
        params.start_date = document.getElementById('startDate')?.value;
        params.end_date = document.getElementById('endDate')?.value;
        params.period = 'custom';
    } else {
        params.period = period;
    }
    return params;
}

// =============================================================================
// INITIALIZATION
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {

    // 1. Navigation (Tabs)
    const navItems = document.querySelectorAll('.nav-item');
    const sections = ['overview', 'trends', 'spend'];

    navItems.forEach(item => {
        item.addEventListener('click', () => {
            const view = item.dataset.view;
            if (!view) return;

            // UI Updates
            navItems.forEach(n => n.classList.remove('active'));
            item.classList.add('active');

            sections.forEach(s => {
                const el = document.getElementById(s);
                if (el) el.classList.toggle('active', s === view);
            });

            document.getElementById('viewTitle').textContent = item.textContent.trim();

            // Data Triggers
            if (view === 'trends') loadTrend(1);
            if (view === 'spend') loadSpend();
        });
    });

    // 2. Feedback Tabs (Positive/Negative)
    const fbTabs = document.querySelectorAll('.tab');
    fbTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            fbTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            const sentiment = tab.dataset.tab;
            ['positiveContent', 'negativeContent'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.classList.toggle('active', id.startsWith(sentiment));
            });

            updatePaginationControls(sentiment);
        });
    });

    // 3. Global Time Filter
    const filter = document.getElementById('periodFilter');
    if (filter) {
        filter.addEventListener('change', (e) => {
            const isCustom = e.target.value === 'custom';
            const picker = document.getElementById('customDateRange');
            if (picker) picker.style.display = isCustom ? 'flex' : 'none';
            if (!isCustom) refreshAll();
        });
    }

    document.getElementById('applyDateBtn')?.addEventListener('click', refreshAll);

    // 4. Export
    document.getElementById('exportBtn')?.addEventListener('click', () => {
        const params = getGlobalFilterParams();
        const query = new URLSearchParams(params).toString();
        window.location.href = `${API_BASE}/feedback/export?${query}`;
    });

    // Initial Load
    refreshAll();

    // Helper to refresh everything
    function refreshAll() {
        const params = getGlobalFilterParams();
        loadStats(params);
        loadFeedback(params);
        loadTrend(1);
    }

    console.log('Admin JS Loaded & Cleaned');
});

// Expose checks for inline HTML handlers
window.changePageForActiveTab = changePageForActiveTab;
