// HTML escaping for XSS protection
function escapeHtml(unsafe) {
    if (!unsafe) return '';
    return String(unsafe)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {

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

            // Trigger Load
            if (viewId === 'trends') loadTrend(1);
            if (viewId === 'spend') loadSpend();
        });
    });

    // Tab Logic
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
        });
    });
    const currentDateEl = document.getElementById('currentDate');
    if (currentDateEl) {
        currentDateEl.textContent = new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
    }

    // Load Stats
    async function loadStats() {
        try {
            const data = await (await fetch('/api/v1/admin/summary')).json();

            // Validate data structure
            if (!data) {
                throw new Error('Invalid response data');
            }

            const statDailyEl = document.getElementById('statDaily');
            const statWeeklyEl = document.getElementById('statWeekly');
            const statMonthlyEl = document.getElementById('statMonthly');
            const statPositiveEl = document.getElementById('statPositive');
            const statNegativeEl = document.getElementById('statNegative');

            if (statDailyEl && data.messages_today !== undefined) {
                statDailyEl.textContent = data.messages_today;
            }
            if (statWeeklyEl && data.messages_week !== undefined) {
                statWeeklyEl.textContent = data.messages_week;
            }
            if (statMonthlyEl && data.messages_month !== undefined) {
                statMonthlyEl.textContent = data.messages_month;
            }
            if (statPositiveEl && data.positive_feedback_score !== undefined) {
                statPositiveEl.textContent = data.positive_feedback_score + '%';
            }
            if (statNegativeEl && data.negative_feedback_score !== undefined) {
                statNegativeEl.textContent = data.negative_feedback_score + '%';
            }
        } catch (e) {
            console.error('Failed to load stats:', e);
            document.querySelectorAll('.stat-value').forEach(el => {
                if (el.textContent === '--') el.textContent = 'Error';
            });
        }
    }

    // Load Spend Stats

    async function loadSpend() {
        try {
            const data = await (await fetch('/api/v1/admin/spend')).json();
            console.log('Spend Data:', data);

            // Validate data structure
            if (!data || !data.today || !data.week || !data.month || !data.all_time || !data.pricing) {
                throw new Error('Invalid spend data structure');
            }

            // Format currency
            const fmt = (val) => {
                if (!val || val === 0) return '$0.00';
                if (val < 0.0001) return '$' + val.toFixed(6);
                if (val < 0.01) return '$' + val.toFixed(4);
                return '$' + val.toFixed(2);
            };
            const fmtTokens = (val) => (val || 0).toLocaleString();

            // Update cards - ONLY Totals with null checks
            const spendTodayEl = document.getElementById('spendToday');
            const spendWeekEl = document.getElementById('spendWeek');
            const spendMonthEl = document.getElementById('spendMonth');
            const spendAllTimeEl = document.getElementById('spendAllTime');
            const spendAvgEl = document.getElementById('spendAvg');

            if (spendTodayEl) spendTodayEl.textContent = fmt(data.today.cost);
            if (spendWeekEl) spendWeekEl.textContent = fmt(data.week.cost);
            if (spendMonthEl) spendMonthEl.textContent = fmt(data.month.cost);
            if (spendAllTimeEl) spendAllTimeEl.textContent = fmt(data.all_time.cost);
            if (spendAvgEl) spendAvgEl.textContent = fmt(data.avg_cost_per_query);

            // Token breakdown
            const spendQueryCountEl = document.getElementById('spendQueryCount');
            const spendInputTokensEl = document.getElementById('spendInputTokens');
            const spendOutputTokensEl = document.getElementById('spendOutputTokens');
            const spendEmbeddingTokensEl = document.getElementById('spendEmbeddingTokens');

            if (spendQueryCountEl) spendQueryCountEl.textContent = fmtTokens(data.all_time.query_count);
            if (spendInputTokensEl) spendInputTokensEl.textContent = fmtTokens(data.all_time.input_tokens);
            if (spendOutputTokensEl) spendOutputTokensEl.textContent = fmtTokens(data.all_time.output_tokens);
            if (spendEmbeddingTokensEl) spendEmbeddingTokensEl.textContent = fmtTokens(data.all_time.embedding_tokens);

            // Pricing info
            const pricingInputEl = document.getElementById('pricingInput');
            const pricingOutputEl = document.getElementById('pricingOutput');

            if (pricingInputEl) pricingInputEl.textContent = data.pricing.input_per_1m;
            if (pricingOutputEl) pricingOutputEl.textContent = data.pricing.output_per_1m;
        } catch (e) {
            console.error('Error loading spend:', e);
        }
    }



    // Load Categories Chart
    async function loadCategories() {
        try {
            const data = await (await fetch('/api/v1/admin/top-categories?days=30&limit=5')).json();

            const canvasEl = document.getElementById('categoriesChart');
            if (!canvasEl) {
                console.warn('Canvas element "categoriesChart" not found');
                return;
            }

            const ctx = canvasEl.getContext('2d');

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
                        backgroundColor: ['#667eea', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'],
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: 'right', labels: { color: '#9ca3af', boxWidth: 10 } }
                    },
                    cutout: '70%'
                }
            });
        } catch (e) { console.error('Error loading categories:', e); }
    }

    // Format Response (Markdown)
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

    // Render Feedback Cards
    function renderFeedbackCards(feedbackList, containerId) {
        const container = document.getElementById(containerId);
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

            // Backend returns ISO format with timezone offset (e.g., 2025-12-10T23:03:02+00:00)
            const date = escapeHtml(new Date(item.timestamp).toLocaleString());
            const card = document.createElement('div');
            card.className = 'feedback-detail-card';

            // Truncated preview
            const queryPreview = escapeHtml(item.user_query.length > 60 ? item.user_query.substring(0, 60) + '...' : item.user_query);

            card.innerHTML = `
                    <div class="feedback-header">
                        <div class="feedback-meta">
                            <span class="feedback-time">${date}</span>
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

    // Load Feedback
    async function loadFeedback() {
        const periodFilterEl = document.getElementById('periodFilter');
        if (!periodFilterEl) {
            console.warn('periodFilter element not found');
            return;
        }

        const period = periodFilterEl.value;
        let url = '/api/v1/admin/feedback?limit=100';

        if (period === 'custom') {
            const startEl = document.getElementById('startDate');
            const endEl = document.getElementById('endDate');
            if (startEl && endEl) {
                const start = startEl.value;
                const end = endEl.value;
                if (start && end) {
                    url += `&start_date=${start}&end_date=${end}`;
                }
            }
        } else if (period) {
            url += `&period=${period}`;
        }

        // Load Positive
        try {
            const resPos = await fetch(`${url}&rating=up`);
            const dataPos = await resPos.json();
            renderFeedbackCards(dataPos.feedback, 'positiveContent');
        } catch (e) { console.error('Error loading positive feedback:', e); }

        // Load Negative
        try {
            const resNeg = await fetch(`${url}&rating=down`);
            const dataNeg = await resNeg.json();
            renderFeedbackCards(dataNeg.feedback, 'negativeContent');
        } catch (e) { console.error('Error loading negative feedback:', e); }
    }

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

    // Load Trend Chart
    async function loadTrend(days = 7, startDate = null, endDate = null) {
        console.log('loadTrend called with days:', days);
        try {
            // Determine Granularity
            let granularity = 'day';
            if (days === 1) granularity = 'hour';
            if (days === 365) granularity = 'month';
            if (days === 'custom' && startDate && endDate && startDate === endDate) {
                granularity = 'hour';
            }

            //  For "Today" (days=1), send user's local date (backend will adjust for timezone)
            if (days === 1 && !startDate && !endDate) {
                const today = new Date();
                const year = today.getFullYear();
                const month = String(today.getMonth() + 1).padStart(2, '0');
                const day = String(today.getDate()).padStart(2, '0');
                startDate = endDate = `${year}-${month}-${day}`;
            }

            const daysParam = (days === 'custom' || days === 1) ? 0 : days;

            // Get user's timezone offset in minutes
            // JavaScript returns POSITIVE for timezones BEHIND UTC (e.g., EST = +300)
            // Backend expects NEGATIVE for timezones behind UTC (standard convention)
            // So we negate: EST becomes -300
            const timezoneOffset = -new Date().getTimezoneOffset();

            // URLs with timezone offset
            let msgUrl = `/api/v1/admin/messages-trend?days=${daysParam}&granularity=${granularity}&timezone_offset=${timezoneOffset}`;
            let fbUrl = `/api/v1/admin/feedback-trend?days=${daysParam}&granularity=${granularity}&timezone_offset=${timezoneOffset}`;

            if (startDate && endDate) {
                const rangeParam = `&start_date=${startDate}&end_date=${endDate}`;
                msgUrl += rangeParam;
                fbUrl += rangeParam;
            }

            console.log('Fetching trend data...');
            const [msgRes, fbRes] = await Promise.all([
                fetch(msgUrl),
                fetch(fbUrl)
            ]);

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

            // Time Scale - Let Chart.js auto-scale (no fixed bounds)

            // Prepare Labels (Category Fallback)


            const labels = dataMsg.trend.map(t => {
                const d = parseTrendDate(t.date);
                if (!d) return '(Invalid Date)';

                // For hour/15min granularity, show local time (user expects to see their timezone)
                if (granularity === 'hour' || granularity === '15min') {
                    return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', hour12: true });
                }
                // For day/month granularity, use UTC date to avoid timezone offset issues
                if (granularity === 'month') {
                    return d.toLocaleDateString('en-US', { month: 'short', year: 'numeric', timeZone: 'UTC' });
                }
                // Display date in UTC to match backend data
                return d.toLocaleDateString('en-US', { timeZone: 'UTC' });
            });

            // Calculate Totals (Today Only)
            const totalMsgEl = document.getElementById('trendTotalMsg');
            const totalSatEl = document.getElementById('trendTotalSat');

            if (totalMsgEl && totalSatEl) {
                if (days === 1) {
                    // Sum Messages
                    const msgSum = dataMsg.trend.reduce((a, b) => a + b.count, 0);
                    totalMsgEl.textContent = `(Total: ${msgSum})`;

                    // Avg Satisfaction (Cumulative)
                    const upSum = (dataFb.baseline_up || 0) + dataFb.trend.reduce((a, b) => a + b.up, 0);
                    const downSum = (dataFb.baseline_down || 0) + dataFb.trend.reduce((a, b) => a + b.down, 0);
                    const totalVotes = upSum + downSum;
                    const satPct = totalVotes > 0 ? ((upSum / totalVotes) * 100).toFixed(1) : 0;
                    totalSatEl.textContent = `(${satPct}%)`;
                } else {
                    totalMsgEl.textContent = '';
                    totalSatEl.textContent = '';
                }
            }

            // --- Chart 1: Messages ---
            const ctxEl1 = document.getElementById('trendChart');
            const noDataEl = document.getElementById('noTrendData');

            if (ctxEl1) {
                if (window.myTrendChart) {
                    window.myTrendChart.destroy();
                    window.myTrendChart = null;
                }

                if (!dataMsg.trend || dataMsg.trend.length === 0 || dataMsg.trend.every(t => t.count === 0)) {
                    if (noDataEl) noDataEl.style.display = 'block';
                } else {
                    if (noDataEl) noDataEl.style.display = 'none';
                }

                const ctx1 = ctxEl1.getContext('2d');
                if (!ctx1) {
                    console.error('Failed to get 2D context for trendChart');
                    return;
                }

                let msgDataset;
                if (granularity === '15min') {
                    msgDataset = dataMsg.trend.map(t => ({ x: parseTrendDate(t.date), y: t.count }));
                } else {
                    msgDataset = dataMsg.trend.map(t => t.count);
                }

                window.myTrendChart = new Chart(ctx1, {
                    type: 'bar',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: 'Messages',
                            data: msgDataset,
                            backgroundColor: '#667eea',
                            borderRadius: 4,
                            barPercentage: 0.6
                        }]
                    },
                    options: {
                        responsive: true, maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: {
                            y: { beginAtZero: true, grid: { color: '#2d3748' } },
                            x: {
                                type: 'category',
                                grid: { display: false }
                            }
                        }
                    }
                });
            }

            // --- Chart 2: Satisfaction Rate ---
            const ctxEl2 = document.getElementById('feedbackChart');
            if (ctxEl2) {
                if (window.myFeedbackChart) {
                    window.myFeedbackChart.destroy();
                    window.myFeedbackChart = null;
                }

                const ctx2 = ctxEl2.getContext('2d');
                if (!ctx2) {
                    console.error('Failed to get 2D context for feedbackChart');
                    return;
                }

                let cumulativeUp = dataFb.baseline_up || 0;
                let cumulativeTotal = (dataFb.baseline_up || 0) + (dataFb.baseline_down || 0);
                const now = new Date();
                let satDataset = [];

                // Build satisfaction dataset - calculate cumulative rate
                satDataset = dataFb.trend.map(t => {
                    const d = parseTrendDate(t.date);
                    if (d > now && (granularity === 'hour' || granularity === 'day' || granularity === 'month')) return null;
                    cumulativeUp += t.up;
                    cumulativeTotal += (t.up + t.down);
                    return cumulativeTotal > 0 ? ((cumulativeUp / cumulativeTotal) * 100).toFixed(1) : 0;
                });

                // For Today view: Extend satisfaction line to "now" with last known rate
                // (If no new feedback, rate stays the same)
                const feedbackLabels = [...labels];
                if (days === 1 && satDataset.length > 0) {
                    const lastRate = satDataset[satDataset.length - 1];
                    if (lastRate !== null) {
                        const nowLabel = now.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', hour12: true });
                        feedbackLabels.push(nowLabel);
                        satDataset.push(lastRate);
                    }
                }

                window.myFeedbackChart = new Chart(ctx2, {
                    type: 'line',
                    data: {
                        labels: feedbackLabels,
                        datasets: [{
                            label: 'Satisfaction %',
                            data: satDataset,
                            borderColor: '#48bb78',
                            backgroundColor: 'rgba(72, 187, 120, 0.1)',
                            tension: 0,
                            stepped: true,
                            borderWidth: 2,
                            pointRadius: 2,
                            fill: true
                        }]
                    },
                    options: {
                        responsive: true, maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: {
                            y: { beginAtZero: true, max: 100, grid: { color: '#2d3748' }, ticks: { callback: v => v + "%" } },
                            x: {
                                type: 'category',
                                grid: { display: false }
                            }
                        }
                    }
                });
            }

            // --- Chart 3: Placeholder ---
            // No logic yet, just empty canvas remains

        } catch (e) { console.error('Trend Error:', e); }
    }

    function updateTrend(days, btn) {
        document.querySelectorAll('.trend-btn').forEach(b => b.classList.remove('active'));
        if (btn) {
            btn.classList.add('active');
        }

        const customRange = document.getElementById('trendCustomDateRange');
        if (days === 'custom') {
            customRange.style.display = 'flex';
        } else {
            customRange.style.display = 'none';
            loadTrend(days);
        }
    }

    function applyTrendCustomDate() {
        const startEl = document.getElementById('trendStartDate');
        const endEl = document.getElementById('trendEndDate');

        if (!startEl || !endEl) {
            console.warn('Trend date inputs not found');
            return;
        }

        const start = startEl.value;
        const end = endEl.value;

        if (start && end) {
            loadTrend('custom', start, end);
        } else {
            console.warn('Please select both start and end dates');
            // Could add visual feedback here instead of alert
        }
    }



    // Event Listeners
    const periodFilterEl = document.getElementById('periodFilter');
    if (periodFilterEl) {
        periodFilterEl.addEventListener('change', (e) => {
            const val = e.target.value;
            const customDateRangeEl = document.getElementById('customDateRange');

            if (val === 'custom') {
                if (customDateRangeEl) customDateRangeEl.style.display = 'flex';
            } else {
                if (customDateRangeEl) customDateRangeEl.style.display = 'none';
                loadFeedback();
                loadTrend();
            }
        });
    }

    const applyDateBtnEl = document.getElementById('applyDateBtn');
    if (applyDateBtnEl) {
        applyDateBtnEl.addEventListener('click', () => {
            loadFeedback();
            loadTrend();
        });
    }

    const exportBtnEl = document.getElementById('exportBtn');
    if (exportBtnEl) {
        exportBtnEl.addEventListener('click', () => {
            const periodFilterEl2 = document.getElementById('periodFilter');
            if (!periodFilterEl2) return;

            const period = periodFilterEl2.value;
            let url = '/api/v1/admin/feedback/export';

            if (period === 'custom') {
                const startEl = document.getElementById('startDate');
                const endEl = document.getElementById('endDate');
                if (startEl && endEl) {
                    const start = startEl.value;
                    const end = endEl.value;
                    url += `?start_date=${start}&end_date=${end}`;
                }
            } else if (period) {
                url += `?period=${period}`;
            }

            window.location.href = url;
        });
    }

    // Duplicate tab listener removed - already registered at line 40

    // Init
    loadStats();
    loadFeedback();
    loadTrend(1); // Default to "Today" view

}); // End DOMContentLoaded
