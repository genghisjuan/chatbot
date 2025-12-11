/**
 * Admin Analytics Dashboard
 * 
 * Handles data visualization, user interactions, and API communication
 * for the analytics admin interface.
 */

// =============================================================================
// CONSTANTS
// =============================================================================

const API_BASE = '/api/v1/admin';
const DEFAULT_CHART_COLORS = {
    primary: '#667eea',
    success: '#10b981',
    warning: '#f59e0b',
    danger: '#ef4444',
    purple: '#8b5cf6',
    green: '#48bb78'
};
const CHART_GRID_COLOR = '#2d3748';
const MAX_QUERY_LENGTH_PREVIEW = 60;

// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================

/**
 * Escape HTML to prevent XSS attacks.
 * @param {string} unsafe - Potentially unsafe string
 * @returns {string} HTML-escaped string
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
 * Format currency with appropriate precision.
 * @param {number} val - Numeric value
 * @returns {string} Formatted currency string
 */
function formatCurrency(val) {
    if (!val || val === 0) return '$0.00';
    if (val < 0.0001) return '$' + val.toFixed(6);
    if (val < 0.01) return '$' + val.toFixed(4);
    return '$' + val.toFixed(2);
}

/**
 * Format large numbers with commas.
 * @param {number} val - Numeric value
 * @returns {string} Formatted number string
 */
function formatNumber(val) {
    return (val || 0).toLocaleString();
}

/**
 * Show loading state for an element.
 * @param {HTMLElement} element - Target element
 */
function showLoading(element) {
    if (!element) return;
    element.classList.add('loading');
    element.setAttribute('aria-busy', 'true');
}

/**
 * Hide loading state for an element.
 * @param {HTMLElement} element - Target element
 */
function hideLoading(element) {
    if (!element) return;
    element.classList.remove('loading');
    element.setAttribute('aria-busy', 'false');
}

/**
 * Show error message to user.
 * @param {string} message - Error message to display
 */
function showError(message) {
    console.error('User-facing error:', message);
    // Could implement toast notification here
}

// =============================================================================
// DATE PARSING FUNCTIONS
// =============================================================================

/**
 * Parse trend date string from backend into Date object.
 * Handles multiple formats: ISO, YYYY-MM-DD, YYYY-MM-DD HH:MM, YYYY-MM.
 * 
 * @param {string} dateStr - Date string from backend
 * @returns {Date|null} Parsed Date object or null if invalid
 */
function parseTrendDate(dateStr) {
    if (!dateStr) {
        console.warn('parseTrendDate received invalid input:', dateStr);
        return null;
    }

    dateStr = String(dateStr);

    // Backend returns naive UTC timestamps - add 'Z' to parse as UTC
    if (!dateStr.includes('T')) {
        // Handle YYYY-MM format (month data)
        if (dateStr.length === 7) return new Date(dateStr + '-01T00:00:00Z');
        // Handle YYYY-MM-DD format (day data)
        if (dateStr.length === 10) return new Date(dateStr + 'T00:00:00Z');
        // Handle YYYY-MM-DD HH format (hour data)
        if (dateStr.length === 13) return new Date(dateStr.replace(' ', 'T') + ':00:00Z');
        // Handle YYYY-MM-DD HH:MM format (minute data)
        if (dateStr.length === 16) return new Date(dateStr.replace(' ', 'T') + ':00Z');
    }

    // If already ISO format, append Z if not present
    if (!dateStr.endsWith('Z')) dateStr += 'Z';
    return new Date(dateStr);
}

/**
 * Format response text as markdown.
 * Requires marked.js library.
 * 
 * @param {string} text - Markdown text
 * @returns {string} Rendered HTML
 */
function formatResponse(text) {
    if (!text) return '';

    // Check if marked library is available
    if (typeof marked === 'undefined' || !marked.parse) {
        console.error('Marked library not loaded');
        return escapeHtml(text); // Fallback to escaped text
    }

    try {
        return marked.parse(text);
    } catch (e) {
        console.error('Error parsing markdown:', e);
        return escapeHtml(text);
    }
}

// =============================================================================
// DATA FETCHING FUNCTIONS
// =============================================================================

/**
 * Load summary statistics for dashboard cards.
 * @param {Object} params - Filter parameters
 */
async function loadStats(params = {}) {
    try {
        const query = new URLSearchParams(params).toString();
        const response = await fetch(`${API_BASE}/summary?${query}`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();

        // Validate data structure
        if (!data) {
            throw new Error('Invalid response data');
        }

        // Update DOM elements with null-safety
        const updates = [
            ['statDaily', data.messages_today],
            ['statWeekly', data.messages_week],
            ['statMonthly', data.messages_month],
            ['statPositive', data.positive_feedback_score + '%'],
            ['statNegative', data.negative_feedback_score + '%']
        ];

        updates.forEach(([id, value]) => {
            const el = document.getElementById(id);
            if (el && value !== undefined) {
                el.textContent = value;
            }
        });
    } catch (e) {
        console.error('Failed to load stats:', e);
        showError('Failed to load statistics. Please refresh the page.');

        // Mark visible error state
        document.querySelectorAll('.stat-value').forEach(el => {
            if (el.textContent === '--') el.textContent = 'Error';
        });
    }
}

/**
 * Load spend statistics for Spend page.
 */
async function loadSpend() {
    try {
        const response = await fetch(`${API_BASE}/spend`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        console.log('Spend Data:', data);

        // Validate data structure
        if (!data || !data.today || !data.week || !data.month ||
            !data.all_time || !data.pricing) {
            throw new Error('Invalid spend data structure');
        }

        // Update summary cards
        const summaryUpdates = [
            ['spendToday', formatCurrency(data.today.cost)],
            ['spendWeek', formatCurrency(data.week.cost)],
            ['spendMonth', formatCurrency(data.month.cost)],
            ['spendAllTime', formatCurrency(data.all_time.cost)],
            ['spendAvg', formatCurrency(data.avg_cost_per_query)]
        ];

        summaryUpdates.forEach(([id, value]) => {
            const el = document.getElementById(id);
            if (el) el.textContent = value;
        });

        // Update token breakdown
        const tokenUpdates = [
            ['spendQueryCount', formatNumber(data.all_time.query_count)],
            ['spendInputTokens', formatNumber(data.all_time.input_tokens)],
            ['spendOutputTokens', formatNumber(data.all_time.output_tokens)],
            ['spendEmbeddingTokens', formatNumber(data.all_time.embedding_tokens)]
        ];

        tokenUpdates.forEach(([id, value]) => {
            const el = document.getElementById(id);
            if (el) el.textContent = value;
        });

        // Update pricing info
        const pricingUpdates = [
            ['pricingInput', data.pricing.input_per_1m],
            ['pricingOutput', data.pricing.output_per_1m]
        ];

        pricingUpdates.forEach(([id, value]) => {
            const el = document.getElementById(id);
            if (el) el.textContent = value;
        });
    } catch (e) {
        console.error('Error loading spend:', e);
        showError('Failed to load spend statistics.');
    }
}

/**
 * Load top categories chart.
 */
async function loadCategories() {
    try {
        const response = await fetch(`${API_BASE}/top-categories?days=30&limit=5`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        const canvasEl = document.getElementById('categoriesChart');
        if (!canvasEl) {
            console.warn('Canvas element "categoriesChart" not found');
            return;
        }

        const ctx = canvasEl.getContext('2d');

        // Destroy existing chart to prevent memory leaks
        if (window.myCategoriesChart) {
            window.myCategoriesChart.destroy();
            window.myCategoriesChart = null;
        }

        window.myCategoriesChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: data.categories.map(c => c.category),
                datasets: [{
                    data: data.categories.map(c => c.count),
                    backgroundColor: Object.values(DEFAULT_CHART_COLORS).slice(0, 5),
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                        labels: { color: '#9ca3af', boxWidth: 10 }
                    }
                },
                cutout: '70%'
            }
        });
    } catch (e) {
        console.error('Error loading categories:', e);
        showError('Failed to load category chart.');
    }
}

/**
 * Render feedback cards in a container.
 * 
 * @param {Array} feedbackList - Array of feedback items
 * @param {string} containerId - ID of container element
 */
function renderFeedbackCards(feedbackList, containerId) {
    const container = document.getElementById(containerId);
    if (!container) {
        console.warn(`Container "${containerId}" not found`);
        return;
    }

    container.innerHTML = '';

    if (!feedbackList || feedbackList.length === 0) {
        container.innerHTML = '<div class="empty-state">No feedback found for this period.</div>';
        return;
    }

    feedbackList.forEach(item => {
        // Validate item structure
        if (!item || !item.timestamp || !item.user_query) {
            console.warn('Invalid feedback item:', item);
            return; // Skip this item
        }

        // Parse and format timestamp
        const date = escapeHtml(new Date(item.timestamp).toLocaleString());
        const card = document.createElement('div');
        card.className = 'feedback-detail-card';

        // Truncated preview
        const queryPreview = escapeHtml(
            item.user_query.length > MAX_QUERY_LENGTH_PREVIEW
                ? item.user_query.substring(0, MAX_QUERY_LENGTH_PREVIEW) + '...'
                : item.user_query
        );

        // Build rating indicator HTML
        let ratingHtml = '';
        if (item.rating === 'up') {
            ratingHtml = '<span class="rating-indicator" style="color: #10b981; margin-left: 8px; font-size: 16px;" title="Positive feedback"><i class="fas fa-thumbs-up"></i></span>';
        } else if (item.rating === 'down') {
            ratingHtml = '<span class="rating-indicator" style="color: #ef4444; margin-left: 8px; font-size: 16px;" title="Negative feedback"><i class="fas fa-thumbs-down"></i></span>';
        }

        card.innerHTML = `
            <div class="feedback-header">
                <div class="feedback-meta">
                    <span class="feedback-time">${date}</span>${ratingHtml}
                </div>
                <div class="feedback-query-preview">${queryPreview}</div>
                <i class="fas fa-chevron-down feedback-expand-icon"></i>
            </div>
            <div class="feedback-content">
                <div class="feedback-section-title">User Query</div>
                <div class="feedback-full-query">
                    <p>${escapeHtml(item.user_query)}</p>
                </div>
                
                <div class="feedback-section-title">AI Response</div>
                <div class="feedback-bot-response">
                    <div class="markdown-body">${formatResponse(item.bot_response || '')}</div>
                </div>
            </div>
        `;

        // Add click handler for expand/collapse
        const header = card.querySelector('.feedback-header');
        if (header) {
            header.addEventListener('click', function () {
                this.parentElement.classList.toggle('expanded');
            });
        }

        container.appendChild(card);
    });
}

// =============================================================================
// PAGINATION STATE (Per-tab)
// =============================================================================

const paginationState = {
    positive: {
        currentPage: 1,
        totalCount: 0,
        pageSize: 12
    },
    negative: {
        currentPage: 1,
        totalCount: 0,
        pageSize: 12
    }
};

/**
 * Load feedback data with filters and pagination.
 * Loads both Positive and Negative tabs separately with their own pagination.
 * @param {Object} params - Filter parameters
 */
async function loadFeedback(params = {}) {
    // Reset both tabs to page 1 when filters change
    paginationState.positive.currentPage = 1;
    paginationState.negative.currentPage = 1;

    await loadFeedbackTab('positive', params);
    await loadFeedbackTab('negative', params);

    // Update pagination controls visibility for both tabs
    updatePaginationControls('positive');
    updatePaginationControls('negative');
}

/**
 * Load feedback for a specific tab (positive or negative).
 * @param {string} sentiment - 'positive' or 'negative'
 * @param {Object} params - Filter parameters
 */
async function loadFeedbackTab(sentiment, params = {}) {
    const rating = sentiment === 'positive' ? 'up' : 'down';
    const containerId = sentiment === 'positive' ? 'positiveContent' : 'negativeContent';
    const state = paginationState[sentiment];

    try {
        const queryParams = new URLSearchParams(params);
        queryParams.set('rating', rating);
        queryParams.set('page', state.currentPage);
        queryParams.set('page_size', state.pageSize);

        const response = await fetch(`${API_BASE}/feedback?${queryParams.toString()}`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();

        // Update pagination state
        state.totalCount = data.totalCount || 0;

        // Render feedback cards
        renderFeedbackCards(data.items || [], containerId);

    } catch (e) {
        console.error(`Error loading ${sentiment} feedback:`, e);
        showError(`Failed to load ${sentiment} feedback.`);
        document.getElementById(containerId).innerHTML = `<div class="empty-state">Failed to load ${sentiment} feedback.</div>`;
    }
}

/**
 * Change page for a specific tab.
 * @param {string} sentiment - 'positive' or 'negative'
 * @param {number} direction - 1 for next, -1 for previous
 */
async function changePage(sentiment, direction) {
    const state = paginationState[sentiment];
    const newPage = state.currentPage + direction;
    const maxPage = Math.ceil(state.totalCount / state.pageSize);

    // Validate page bounds
    if (newPage < 1 || newPage > maxPage) {
        return;
    }

    state.currentPage = newPage;

    // Get current filter params from global filter
    const periodEl = document.getElementById('periodFilter');
    const period = periodEl.value;
    const params = {
        period: period,
        timezone_offset: -new Date().getTimezoneOffset()
    };

    if (period === 'custom') {
        const start = document.getElementById('startDate').value;
        const end = document.getElementById('endDate').value;
        if (start && end) {
            params.start_date = start;
            params.end_date = end;
        }
    }

    // Load data for this tab only
    await loadFeedbackTab(sentiment, params);

    // Update pagination controls
    updatePaginationControls(sentiment);
}

/**
 * Update pagination controls visibility and state for a tab.
 * Shows controls only if totalCount > 12.
 * @param {string} sentiment - 'positive' or 'negative'
 */
function updatePaginationControls(sentiment) {
    const state = paginationState[sentiment];
    const totalPages = Math.ceil(state.totalCount / state.pageSize);

    // Get the unified pagination controls in header
    const controlsEl = document.getElementById('feedbackPagination');

    if (!controlsEl) {
        console.warn('Pagination controls not found: feedbackPagination');
        return;
    }

    // Check if this tab is currently active
    const activeTab = document.querySelector('.tab.active');
    const isActiveTab = activeTab && activeTab.dataset.tab === sentiment;

    // Only update controls if this is the active tab
    if (!isActiveTab) {
        return;
    }

    // Show controls only if more than 1 page
    if (totalPages <= 1) {
        controlsEl.style.display = 'none';
        return;
    }

    controlsEl.style.display = 'flex';

    // Update button states
    const prevBtn = controlsEl.querySelector('.prev-btn');
    const nextBtn = controlsEl.querySelector('.next-btn');
    const pageInfo = controlsEl.querySelector('.page-info');

    if (prevBtn) {
        prevBtn.disabled = state.currentPage === 1;
    }

    if (nextBtn) {
        nextBtn.disabled = state.currentPage >= totalPages;
    }

    if (pageInfo) {
        pageInfo.textContent = `Page ${state.currentPage} of ${totalPages}`;
    }
}

/**
 * Change page for the currently active tab.
 * Called from the unified pagination controls in the header.
 * @param {number} direction - 1 for next, -1 for previous
 */
async function changePageForActiveTab(direction) {
    // Determine which tab is active
    const activeTab = document.querySelector('.tab.active');
    if (!activeTab) return;

    const sentiment = activeTab.dataset.tab;

    // Use the existing changePage logic
    await changePage(sentiment, direction);
}

/**
 * Load trend charts (messages + satisfaction).
 * @param {Object} params - Filter parameters
 */
async function loadTrend(params = {}) {
    try {
        // Prepare Query
        const query = new URLSearchParams(params).toString();

        console.log('Fetching trend data with:', query);
        const [msgRes, fbRes] = await Promise.all([
            fetch(`${API_BASE}/messages-trend?${query}`),
            fetch(`${API_BASE}/feedback-trend?${query}`)
        ]);

        if (!msgRes.ok || !fbRes.ok) {
            throw new Error('Failed to fetch trend data');
        }

        const dataMsg = await msgRes.json();
        const dataFb = await fbRes.json();

        // Validate data structure
        if (!dataMsg || !dataMsg.trend || !Array.isArray(dataMsg.trend)) {
            console.error('Invalid message trend data structure');
            return;
        }
        if (!dataFb || !dataFb.trend || !Array.isArray(dataFb.trend)) {
            console.error('Invalid feedback trend data structure');
            return;
        }

        // Render Message Chart
        renderMessageChart(dataMsg.trend, params.period);

        // Render Satisfaction Chart
        renderSatisfactionChart(dataFb.trend, params.period);

    } catch (e) {
        console.error('Trend Error:', e);
        showError('Failed to load trend data.');
    }
}

/**
 * Helper to render Message Chart
 */
function renderMessageChart(trendData, period) {
    const ctxEl = document.getElementById('trendChart');
    const noDataEl = document.getElementById('noTrendData');

    if (!ctxEl) return;

    if (window.myTrendChart) {
        window.myTrendChart.destroy();
        window.myTrendChart = null;
    }

    const ctx = ctxEl.getContext('2d');
    if (!ctx) {
        console.error('Failed to get 2D context for trendChart');
        return;
    }

    // Check for no data
    if (!trendData || trendData.length === 0 || trendData.every(t => t.count === 0)) {
        if (noDataEl) noDataEl.style.display = 'block';
        return; // Don't render chart if no data
    } else {
        if (noDataEl) noDataEl.style.display = 'none';
    }

    const labels = trendData.map(t => {
        const d = parseTrendDate(t.date);
        if (!d) return '(Invalid Date)';
        if (period === 'today' || period === 'custom') return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        return d.toLocaleDateString();
    });

    const data = trendData.map(t => t.count !== undefined ? t.count : 0);

    window.myTrendChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Messages',
                data: data,
                backgroundColor: DEFAULT_CHART_COLORS.primary,
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: {
                    type: 'category',
                    grid: { display: false },
                    ticks: { color: '#9ca3af' }
                },
                y: {
                    beginAtZero: true,
                    grid: { color: CHART_GRID_COLOR },
                    ticks: { color: '#9ca3af' }
                }
            }
        }
    });
}

/**
 * Helper to render Satisfaction Chart
 */
function renderSatisfactionChart(trendData, period) {
    const ctxEl = document.getElementById('feedbackChart');
    if (!ctxEl) return;

    if (window.myFeedbackChart) {
        window.myFeedbackChart.destroy();
        window.myFeedbackChart = null;
    }

    const ctx = ctxEl.getContext('2d');
    if (!ctx) {
        console.error('Failed to get 2D context for feedbackChart');
        return;
    }

    // Calculate Satisfaction %
    const dataset = trendData.map(t => {
        const total = t.up + t.down;
        return total > 0 ? ((t.up / total) * 100).toFixed(1) : 0;
    });

    const labels = trendData.map(t => {
        const d = parseTrendDate(t.date);
        if (!d) return '(Invalid Date)';
        if (period === 'today' || period === 'custom') return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        return d.toLocaleDateString();
    });

    window.myFeedbackChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Satisfaction %',
                data: dataset,
                borderColor: DEFAULT_CHART_COLORS.green,
                backgroundColor: 'rgba(72, 187, 120, 0.1)',
                fill: true,
                tension: 0,
                stepped: true,
                borderWidth: 2,
                pointRadius: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    grid: { color: CHART_GRID_COLOR },
                    ticks: { callback: v => v + '%', color: '#9ca3af' }
                },
                x: {
                    type: 'category',
                    grid: { display: false },
                    ticks: { color: '#9ca3af' }
                }
            }
        }
    });
}

/**
 * Apply the currently selected global filters.
 */
function applyGlobalFilter() {
    const periodEl = document.getElementById('periodFilter');
    const period = periodEl.value;
    const params = {
        period: period,
        timezone_offset: -new Date().getTimezoneOffset()
    };

    const customRange = document.getElementById('customDateRange');

    if (period === 'custom') {
        if (customRange) customRange.style.display = 'flex';
        const start = document.getElementById('startDate').value;
        const end = document.getElementById('endDate').value;
        if (start && end) {
            params.start_date = start;
            params.end_date = end;
        } else {
            // If custom is selected but dates are not, don't load data yet.
            // The user needs to select dates and click apply.
            return;
        }
    } else {
        if (customRange) customRange.style.display = 'none';
        // Ensure custom date params are not sent if not 'custom' period
        delete params.start_date;
        delete params.end_date;
    }

    console.log('Applying Global Filter:', params);
    loadStats(params);
    loadFeedback(params);
    loadTrend(params);
}


// =============================================================================
// INITIALIZATION
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {

    // Global Filter Events
    const periodSelect = document.getElementById('periodFilter');
    if (periodSelect) {
        periodSelect.addEventListener('change', applyGlobalFilter);
    }

    const applyBtn = document.getElementById('applyDateBtn');
    if (applyBtn) {
        applyBtn.addEventListener('click', applyGlobalFilter);
    }

    // Navigation Logic
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', () => {
            const viewId = item.dataset.view;
            if (!viewId) {
                console.warn('Nav item missing data-view attribute');
                return;
            }

            // Update Sidebar
            document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
            item.classList.add('active');

            // Update View
            const viewEl = document.getElementById(viewId);
            if (viewEl) {
                document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
                viewEl.classList.add('active');
            }

            // Update Title
            const titles = {
                'overview': 'Overview',
                'trends': 'Trends',
                'spend': 'Spend'
            };
            const viewTitleEl = document.getElementById('viewTitle');
            if (viewTitleEl) {
                viewTitleEl.textContent = titles[viewId] || 'Analytics';
            }

            // Trigger Load (only for views that don't use global filter)
            if (viewId === 'spend') loadSpend();
            // Other views (overview, trends) are handled by applyGlobalFilter
        });
    });

    // Tab Logic (for feedback section)
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const tabId = tab.dataset.tab;
            if (!tabId) {
                console.warn('Tab missing data-tab attribute');
                return;
            }

            // Update Tabs
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            // Update Content
            const tabContentEl = document.getElementById(tabId + 'Content');
            if (tabContentEl) {
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                tabContentEl.classList.add('active');
            }

            // Update pagination controls for the newly active tab
            updatePaginationControls(tabId);
        });
    });
    // Display current date
    const currentDateEl = document.getElementById('currentDate');
    if (currentDateEl) {
        currentDateEl.textContent = new Date().toLocaleDateString('en-US', {
            weekday: 'long',
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        });
    }

    // Export button logic
    const exportBtnEl = document.getElementById('exportBtn');
    if (exportBtnEl) {
        exportBtnEl.addEventListener('click', () => {
            const periodEl = document.getElementById('periodFilter');
            const period = periodEl.value;
            let url = `${API_BASE}/feedback/export`;

            // Append filters
            const params = new URLSearchParams();
            if (period === 'custom') {
                const start = document.getElementById('startDate').value;
                const end = document.getElementById('endDate').value;
                if (start && end) {
                    params.append('start_date', start);
                    params.append('end_date', end);
                } else {
                    showError("Please select a date range to export.");
                    return;
                }
            } else {
                params.append('period', period);
            }

            // Add timezone offset
            params.append('timezone_offset', -new Date().getTimezoneOffset());

            window.location.href = `${url}?${params.toString()}`;
        });
    }


    // Initial Load
    applyGlobalFilter();

    console.log('Admin dashboard initialized');
});
