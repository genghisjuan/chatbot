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

// Navigation Logic
document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
        const viewId = item.dataset.view;

        // Update Sidebar
        document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
        item.classList.add('active');

        // Update View
        document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
        document.getElementById(viewId).classList.add('active');

        // Update Title
        const titles = {
            'overview': 'Overview',
            'trends': 'Trends',
            'spend': 'Spend'
        };
        document.getElementById('viewTitle').textContent = titles[viewId] || 'Analytics';

        // Trigger Load
        if (viewId === 'trends') loadTrend(1);
        if (viewId === 'spend') loadSpend();
    });
});

// Tab Logic
document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        const tabId = tab.dataset.tab;

        // Update Tabs
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');

        // Update Content
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        document.getElementById(tabId + 'Content').classList.add('active');
    });
});
document.getElementById('currentDate').textContent = new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });

// Load Stats
async function loadStats() {
    try {
        const data = await (await fetch('/api/v1/admin/summary')).json();
        document.getElementById('statDaily').textContent = data.messages_today;
        document.getElementById('statWeekly').textContent = data.messages_week;
        document.getElementById('statMonthly').textContent = data.messages_month;
        document.getElementById('statPositive').textContent = data.positive_feedback_score + '%';
        document.getElementById('statNegative').textContent = data.negative_feedback_score + '%';
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

        // Format currency
        const fmt = (val) => {
            if (!val || val === 0) return '$0.00';
            if (val < 0.0001) return '$' + val.toFixed(6);
            if (val < 0.01) return '$' + val.toFixed(4);
            return '$' + val.toFixed(2);
        };
        const fmtTokens = (val) => val.toLocaleString();

        // Update cards - ONLY Totals
        document.getElementById('spendToday').textContent = fmt(data.today.cost);
        document.getElementById('spendWeek').textContent = fmt(data.week.cost);
        document.getElementById('spendMonth').textContent = fmt(data.month.cost);
        document.getElementById('spendAllTime').textContent = fmt(data.all_time.cost);

        document.getElementById('spendAvg').textContent = fmt(data.avg_cost_per_query);

        // Token breakdown
        document.getElementById('spendQueryCount').textContent = fmtTokens(data.all_time.query_count);
        document.getElementById('spendInputTokens').textContent = fmtTokens(data.all_time.input_tokens);
        document.getElementById('spendOutputTokens').textContent = fmtTokens(data.all_time.output_tokens);
        if (document.getElementById('spendEmbeddingTokens')) {
            document.getElementById('spendEmbeddingTokens').textContent = fmtTokens(data.all_time.embedding_tokens);
        }

        // Pricing info
        document.getElementById('pricingInput').textContent = data.pricing.input_per_1m;
        document.getElementById('pricingOutput').textContent = data.pricing.output_per_1m;
    } catch (e) {
        console.error('Error loading spend:', e);
    }
}



// Load Categories Chart
async function loadCategories() {
    try {
        const data = await (await fetch('/api/v1/admin/top-categories?days=30&limit=5')).json();
        const ctx = document.getElementById('categoriesChart').getContext('2d');

        new Chart(ctx, {
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
    } catch (e) { console.error(e); }
}

// Format Response (Markdown)
function formatResponse(text) {
    if (!text) return '';
    return marked.parse(text);
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
        // Parse as UTC and convert to local timezone
        const date = new Date(item.timestamp + 'Z').toLocaleString();
        const card = document.createElement('div');
        card.className = 'feedback-detail-card';

        // Truncated preview
        const queryPreview = escapeHtml(item.user_query.length > 60 ? item.user_query.substring(0, 60) + '...' : item.user_query);

        card.innerHTML = `
                    <div class="feedback-header" onclick="this.parentElement.classList.toggle('expanded')">
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
                            <div class="markdown-body">${formatResponse(item.bot_response)}</div>
                        </div>
                    </div>
                `;
        container.appendChild(card);
    });
}

// Load Feedback
async function loadFeedback() {
    const period = document.getElementById('periodFilter').value;
    let url = '/api/v1/admin/feedback?limit=100';

    if (period === 'custom') {
        const start = document.getElementById('startDate').value;
        const end = document.getElementById('endDate').value;
        if (start && end) {
            url += `&start_date=${start}&end_date=${end}`;
        }
    } else if (period) {
        url += `&period=${period}`;
    }

    // Load Positive
    try {
        const resPos = await fetch(`${url}&rating=up`);
        const dataPos = await resPos.json();
        renderFeedbackCards(dataPos.feedback, 'positiveContent');
    } catch (e) { console.error(e); }

    // Load Negative
    try {
        const resNeg = await fetch(`${url}&rating=down`);
        const dataNeg = await resNeg.json();
        renderFeedbackCards(dataNeg.feedback, 'negativeContent');
    } catch (e) { console.error(e); }
}

function parseTrendDate(dateStr) {
    if (!dateStr) return new Date();
    dateStr = String(dateStr);
    // Backend returns naive UTC timestamps - add 'Z' to parse as UTC
    if (!dateStr.includes('T')) {
        if (dateStr.length === 7) return new Date(dateStr + '-01T00:00:00Z');
        if (dateStr.length === 10) return new Date(dateStr + 'T00:00:00Z');
        if (dateStr.length === 13) return new Date(dateStr.replace(' ', 'T') + ':00:00Z');
        if (dateStr.length === 16) return new Date(dateStr.replace(' ', 'T') + ':00Z');
    }
    // If already ISO format, append Z if not present
    if (!dateStr.endsWith('Z')) dateStr += 'Z';
    return new Date(dateStr);
}

// Load Trend Chart
// Load Trend Chart
async function loadTrend(days = 7, startDate = null, endDate = null) {
    console.log('loadTrend called with days:', days);
    try {
        // Determine Granularity
        let granularity = 'day';
        if (days == 1) granularity = 'hour';
        if (days == 365) granularity = 'month';
        if (days === 'custom' && startDate && endDate && startDate === endDate) {
            granularity = 'hour';
        }

        const daysParam = (days === 'custom') ? 0 : days;

        // URLs
        let msgUrl = `/api/v1/admin/messages-trend?days=${daysParam}&granularity=${granularity}`;
        let fbUrl = `/api/v1/admin/feedback-trend?days=${daysParam}&granularity=${granularity}`;

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

        // Time Scale - Let Chart.js auto-scale (no fixed bounds)

        // Prepare Labels (Category Fallback)


        const labels = dataMsg.trend.map(t => {
            const d = parseTrendDate(t.date);
            if (granularity === 'hour' || granularity === '15min') return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', hour12: true });
            if (granularity === 'month') return d.toLocaleDateString([], { month: 'short', year: 'numeric' });
            return d.toLocaleDateString();
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
            if (window.myTrendChart) window.myTrendChart.destroy();

            if (!dataMsg.trend || dataMsg.trend.length === 0 || dataMsg.trend.every(t => t.count === 0)) {
                if (noDataEl) noDataEl.style.display = 'block';
            } else {
                if (noDataEl) noDataEl.style.display = 'none';
            }

            const ctx1 = ctxEl1.getContext('2d');

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
            if (window.myFeedbackChart) window.myFeedbackChart.destroy();
            const ctx2 = ctxEl2.getContext('2d');

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
            if (days === 1 && satDataset.length > 0) {
                const lastRate = satDataset[satDataset.length - 1];
                if (lastRate !== null) {
                    const nowLabel = now.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', hour12: true });
                    labels.push(nowLabel);
                    satDataset.push(lastRate);
                }
            }

            window.myFeedbackChart = new Chart(ctx2, {
                type: 'line',
                data: {
                    labels: labels,
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
    btn.classList.add('active');

    const customRange = document.getElementById('trendCustomDateRange');
    if (days === 'custom') {
        customRange.style.display = 'flex';
    } else {
        customRange.style.display = 'none';
        loadTrend(days);
    }
}

function applyTrendCustomDate() {
    const start = document.getElementById('trendStartDate').value;
    const end = document.getElementById('trendEndDate').value;
    if (start && end) {
        loadTrend('custom', start, end);
    } else {
        alert('Please select start and end dates');
    }
}



// Event Listeners
document.getElementById('periodFilter').addEventListener('change', (e) => {
    const val = e.target.value;
    if (val === 'custom') {
        document.getElementById('customDateRange').style.display = 'flex';
    } else {
        document.getElementById('customDateRange').style.display = 'none';
        loadFeedback();
        loadTrend();
    }
});

document.getElementById('applyDateBtn').addEventListener('click', () => {
    loadFeedback();
    loadTrend();
});

document.getElementById('exportBtn').addEventListener('click', () => {
    const period = document.getElementById('periodFilter').value;
    let url = '/api/v1/admin/feedback/export';
    if (period === 'custom') {
        const start = document.getElementById('startDate').value;
        const end = document.getElementById('endDate').value;
        url += `?start_date=${start}&end_date=${end}`;
    } else if (period) {
        url += `?period=${period}`;
    }
    window.location.href = url;
});

document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

        tab.classList.add('active');
        const target = tab.dataset.tab; // 'positive' or 'negative'
        document.getElementById(target + 'Content').classList.add('active');
    });
});

// Init
loadStats();
loadFeedback();
loadTrend();