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

// ... (navigation logic remains) ...

// Robust Date Parsing
function parseTrendDate(dateStr) {
    if (!dateStr) return new Date();
    // Handle various ISO formats from backend (YYYY-MM-DD or YYYY-MM-DDTHH:MM...)
    // Ensure we parse as UTC if 'Z' is missing to match backend behavior
    let s = String(dateStr);

    // Quick checks for common formats
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return new Date(s + 'T00:00:00Z');
    if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(s)) return new Date(s.replace(' ', 'T') + ':00Z');
    if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(s)) return new Date(s.replace(' ', 'T') + 'Z');

    if (!s.endsWith('Z') && s.includes('T')) s += 'Z';
    return new Date(s);
}

// Load Trend Chart
async function loadTrend(days = 7, startDate = null, endDate = null) {
    // console.log('loadTrend', days, startDate, endDate);
    try {
        // Determine Granularity
        let granularity = 'day';
        if (days == 1) granularity = 'hour';
        if (days == 365) granularity = 'month';
        if (startDate && endDate) {
            // Heuristic: if range < 3 days -> hour, else day
            const start = new Date(startDate);
            const end = new Date(endDate);
            const diffDays = (end - start) / (1000 * 60 * 60 * 24);
            if (diffDays <= 3) granularity = 'hour';
        }

        // For "Today" (days=1), use local date string
        if (days === 1 && !startDate && !endDate) {
            const today = new Date();
            const year = today.getFullYear();
            const month = String(today.getMonth() + 1).padStart(2, '0');
            const day = String(today.getDate()).padStart(2, '0');
            startDate = endDate = `${year}-${month}-${day}`;
        }

        const daysParam = (startDate && endDate) ? 0 : days;

        // Timezone Offset (Negated for backend compatibility)
        // EST = +300 in JS -> send -300 to backend
        const timezoneOffset = -new Date().getTimezoneOffset();

        let msgUrl = `/api/v1/admin/messages-trend?days=${daysParam}&granularity=${granularity}&timezone_offset=${timezoneOffset}`;
        let fbUrl = `/api/v1/admin/feedback-trend?days=${daysParam}&granularity=${granularity}&timezone_offset=${timezoneOffset}`;

        if (startDate && endDate) {
            const rangeParam = `&start_date=${startDate}&end_date=${endDate}`;
            msgUrl += rangeParam;
            fbUrl += rangeParam;
        }

        // Parallel Fetch with individual error handling
        const [msgRes, fbRes] = await Promise.allSettled([
            fetch(msgUrl),
            fetch(fbUrl)
        ]);

        const dataMsg = msgRes.status === 'fulfilled' ? await msgRes.value.json() : { trend: [] };
        const dataFb = fbRes.status === 'fulfilled' ? await fbRes.value.json() : { trend: [], baseline_up: 0, baseline_down: 0 };

        if (msgRes.status === 'rejected') console.error('Message fetch failed', msgRes.reason);
        if (fbRes.status === 'rejected') console.error('Feedback fetch failed', fbRes.reason);

        // Calculate Totals (Today Only)
        const totalMsgEl = document.getElementById('trendTotalMsg');
        const totalSatEl = document.getElementById('trendTotalSat');

        if (totalMsgEl && totalSatEl) {
            if (days === 1) {
                const msgSum = dataMsg.trend.reduce((a, b) => a + b.count, 0);
                totalMsgEl.textContent = `(Total: ${msgSum})`;

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

        // Prepare Labels
        const labels = dataMsg.trend.map(t => {
            const d = parseTrendDate(t.date);
            if (granularity === 'hour' || granularity === '15min') return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', hour12: true });
            if (granularity === 'month') return d.toLocaleDateString('en-US', { month: 'short', year: 'numeric', timeZone: 'UTC' });
            return d.toLocaleDateString('en-US', { timeZone: 'UTC' });
        });

        // --- Chart 1: Messages ---
        const ctxEl1 = document.getElementById('trendChart');
        const noDataEl = document.getElementById('noTrendData');

        if (ctxEl1) {
            // Memory Leak Fix: Destroy and nullify old chart
            if (window.myTrendChart) {
                window.myTrendChart.destroy();
                window.myTrendChart = null;
            }

            const hasData = dataMsg.trend && dataMsg.trend.length > 0 && !dataMsg.trend.every(t => t.count === 0);
            if (noDataEl) noDataEl.style.display = hasData ? 'none' : 'block';

            const ctx1 = ctxEl1.getContext('2d');
            const msgDataset = dataMsg.trend.map(t => t.count);

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
                        x: { type: 'category', grid: { display: false } }
                    }
                }
            });
        }

        // --- Chart 2: Satisfaction ---
        const ctxEl2 = document.getElementById('feedbackChart');
        if (ctxEl2) {
            if (window.myFeedbackChart) {
                window.myFeedbackChart.destroy();
                window.myFeedbackChart = null;
            }
            const ctx2 = ctxEl2.getContext('2d');

            let cumulativeUp = dataFb.baseline_up || 0;
            let cumulativeTotal = (dataFb.baseline_up || 0) + (dataFb.baseline_down || 0);
            const now = new Date();

            const satDataset = dataFb.trend.map(t => {
                const d = parseTrendDate(t.date);
                if (d > now && (granularity === 'hour' || granularity === 'day')) return null;
                cumulativeUp += t.up;
                cumulativeTotal += (t.up + t.down);
                return cumulativeTotal > 0 ? ((cumulativeUp / cumulativeTotal) * 100).toFixed(1) : 0;
            });

            // Extend to "now" for Today view
            if (days === 1 && satDataset.length > 0) {
                const lastRate = satDataset[satDataset.length - 1];
                if (lastRate !== null) {
                    labels.push(now.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', hour12: true }));
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
                        x: { type: 'category', grid: { display: false } }
                    }
                }
            });
        }

    } catch (e) {
        console.error('Trend Error:', e);
    }
}

// ... helper functions ...

// Fix Event Listeners to pass correct params
document.getElementById('periodFilter').addEventListener('change', (e) => {
    const val = e.target.value;
    if (val === 'custom') {
        document.getElementById('customDateRange').style.display = 'flex';
    } else {
        document.getElementById('customDateRange').style.display = 'none';
        loadFeedback();
        // Pass the correct 'days' value based on filter selection
        let days = 7;
        if (val === 'day') days = 1;
        if (val === 'month') days = 30; // Approximation or separate logic needed? 
        // Admin dashboard currently doesn't map periodFilter to trend days perfectly
        // But let's assume 'periodFilter' controls the FEEDBACK list, and trend chart might stay at 7?
        // Wait, current UI has separate buttons for Trend (Today, Last Week...).
        // periodFilter is for the Feedback List below.
        // So loadTrend should probably NOT be called here, or called with current Trend state.
        // For now, let's just NOT call loadTrend() here to avoid resetting it?
        // Or if we do, adhere to the separate trend buttons.
        // Actually line 467 called loadTrend() which would reset trend chart to 7 days when I filter feedback list?
        // That seems wrong. Let's remove loadTrend() from here to decouple them.
        // The user can update trend chart via the top buttons.
    }
});

// Fix Apply Date Button (for Feedback List)
document.getElementById('applyDateBtn').addEventListener('click', () => {
    loadFeedback();
    // Don't reload trend, let trend chart be independent or have its own apply button
});

// Export button logic remains...


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
loadTrend(1); // Default to "Today" view