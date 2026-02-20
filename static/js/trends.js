// Trends page JavaScript — expanded metric system

// ─── State ────────────────────────────────────────────────────────────────────
let trendsData = [];
let metricMetadata = {};   // { key: { description, unit, category } }
let habitNames = [];
let activeMetrics = new Set();
let metricColors = {};     // key → hex color (persistent per key)
let chart = null;
let paletteIndex = 0;

const PALETTE = [
    '#4488ff', '#dc2626', '#16a34a', '#f59e0b',
    '#a78bfa', '#34d399', '#38bdf8', '#f87171',
    '#fbbf24', '#fb923c', '#60a5fa', '#e879f9',
];

const CATEGORY_DOT_COLORS = {
    'Sleep':        '#a78bfa',
    'HRV':          '#34d399',
    'SpO2':         '#38bdf8',
    'Heart Rate':   '#f87171',
    'Body Battery': '#fbbf24',
    'Stress':       '#fb923c',
    'Activity':     '#60a5fa',
    'Habits':       '#e879f9',
};

const CATEGORY_ORDER = ['Sleep', 'HRV', 'SpO2', 'Heart Rate', 'Body Battery', 'Stress', 'Activity', 'Habits'];

// ─── Initialization ───────────────────────────────────────────────────────────
async function init() {
    try {
        const [dailyResp, metaResp, habitsResp] = await Promise.all([
            fetch('/api/daily?days=90'),
            fetch('/api/export/metadata'),
            fetch('/api/habits/names'),
        ]);

        trendsData = await dailyResp.json();
        const metaData = await metaResp.json();
        metricMetadata = metaData.features || {};
        habitNames = await habitsResp.json();

        buildHabitSelector();
        buildMetricPicker();
        activateDefaults();
        updateChart();
    } catch (err) {
        console.error('Failed to initialise trends:', err);
    }
}

// ─── Color assignment ─────────────────────────────────────────────────────────
function assignColor(key) {
    if (!metricColors[key]) {
        metricColors[key] = PALETTE[paletteIndex % PALETTE.length];
        paletteIndex++;
    }
    return metricColors[key];
}

// ─── Default active metrics ───────────────────────────────────────────────────
function activateDefaults() {
    // Check pm_slump first
    if (habitNames.includes('pm_slump')) {
        enableMetric('habit:pm_slump');
    }
    // Then sleep_score
    if (trendsData.some(d => d.sleep_score != null)) {
        enableMetric('sleep_score');
    }
}

function enableMetric(key) {
    assignColor(key);
    activeMetrics.add(key);
    const cb = document.getElementById('cb-' + keyToId(key));
    if (cb) cb.checked = true;
    refreshSwatch(key);
}

// ─── ID helpers ───────────────────────────────────────────────────────────────
function keyToId(key) {
    // Convert metric key to a safe DOM id fragment
    return key.replace(/[^a-zA-Z0-9_-]/g, '_');
}

// ─── Habit selector (top bar) ─────────────────────────────────────────────────
function buildHabitSelector() {
    const select = document.getElementById('correlate-habit');
    select.innerHTML = '<option value="">-- Select habit --</option>' +
        habitNames.map(name =>
            `<option value="${name}">${name.replace(/_/g, ' ')}</option>`
        ).join('');
}

async function onCorrelateHabitChange() {
    const target = document.getElementById('correlate-habit').value;
    const content = document.getElementById('suggestions-content');

    if (!target) {
        content.innerHTML = '<p style="color: var(--text-muted); font-size: 0.875rem;">Select a habit above to see suggestions.</p>';
        return;
    }

    content.innerHTML = '<p class="loading" style="padding: 1rem 0; font-size: 0.875rem;">Loading…</p>';

    try {
        const resp = await fetch(`/api/correlations?target_habit=${encodeURIComponent(target)}&min_days=5`);
        const correlations = await resp.json();

        if (!correlations.length) {
            content.innerHTML = '<p style="color: var(--text-muted); font-size: 0.875rem;">Not enough data for correlations yet.</p>';
            return;
        }

        // Filter: |r| > 0.1, exclude the target habit itself, take top 8
        const targetKey = `habit_${target}`;
        const filtered = correlations
            .filter(c => Math.abs(c.coefficient) > 0.1 && c.metric !== targetKey && c.metric !== target)
            .slice(0, 8);

        renderSuggestions(filtered);
    } catch (err) {
        console.error('Failed to load correlations:', err);
        content.innerHTML = '<p class="error">Failed to load suggestions.</p>';
    }
}

function renderSuggestions(correlations) {
    const content = document.getElementById('suggestions-content');

    if (!correlations.length) {
        content.innerHTML = '<p style="color: var(--text-muted); font-size: 0.875rem;">No strong correlates found.</p>';
        return;
    }

    content.innerHTML = correlations.map(c => {
        // Map correlation metric name to our picker key scheme
        const key = c.metric.startsWith('habit_') ? `habit:${c.metric.slice(6)}` : c.metric;
        const isAdded = activeMetrics.has(key);
        const r = c.coefficient;
        const barColor = r > 0 ? '#4488ff' : '#fb923c';
        const barWidth = (Math.abs(r) * 100).toFixed(0);
        const label = key.startsWith('habit:')
            ? key.slice(6).replace(/_/g, ' ')
            : key.replace(/_/g, ' ');
        const safeId = 'sug-' + keyToId(key);
        const safeKey = key.replace(/\\/g, '\\\\').replace(/'/g, "\\'");

        return `
            <div class="suggestion-card${isAdded ? ' added' : ''}" id="${safeId}">
                <div class="suggestion-info">
                    <div class="suggestion-name" title="${c.strength} correlation (n=${c.n})">${label}</div>
                    <div class="suggestion-bar-wrap">
                        <div class="suggestion-bar" style="width: ${barWidth}%; background: ${barColor};"></div>
                    </div>
                </div>
                <span class="suggestion-r">${r >= 0 ? '+' : ''}${r.toFixed(2)}</span>
                <button class="suggestion-add-btn"
                        onclick="addSuggestion('${safeKey}')"
                        ${isAdded ? 'disabled' : ''}>
                    ${isAdded ? '✓' : '+ Add'}
                </button>
            </div>
        `;
    }).join('');
}

function addSuggestion(key) {
    // Open the relevant accordion section
    let catId;
    if (key.startsWith('habit:')) {
        catId = 'Habits';
    } else {
        const meta = metricMetadata[key];
        catId = meta ? meta.category : null;
    }
    if (catId) {
        const section = document.getElementById('acc-' + catId.replace(/\s/g, '-'));
        if (section && !section.classList.contains('open')) {
            section.classList.add('open');
        }
    }

    // Check the checkbox and activate the metric
    const cb = document.getElementById('cb-' + keyToId(key));
    if (cb && !cb.checked) {
        cb.checked = true;
        onMetricToggle(key, true);
    }

    // Update the suggestion card appearance
    const card = document.getElementById('sug-' + keyToId(key));
    if (card) {
        card.classList.add('added');
        const btn = card.querySelector('.suggestion-add-btn');
        if (btn) {
            btn.textContent = '✓';
            btn.disabled = true;
        }
    }
}

// ─── Metric picker accordion ──────────────────────────────────────────────────
function buildMetricPicker() {
    const container = document.getElementById('metric-accordion');
    container.innerHTML = '';

    // Group metadata keys by category, skipping non-chartable text fields
    const categories = {};
    for (const [key, meta] of Object.entries(metricMetadata)) {
        const unit = meta.unit || '';
        if (unit === 'text' || unit === 'low/medium/high') continue;  // skip text/categorical fields
        const cat = meta.category || 'Other';
        if (!categories[cat]) categories[cat] = [];
        categories[cat].push({ key, ...meta });
    }

    // Add Habits category from live habit names
    if (habitNames.length > 0) {
        categories['Habits'] = habitNames.map(name => ({
            key: `habit:${name}`,
            description: name.replace(/_/g, ' '),
            unit: 'habit',
            category: 'Habits',
        }));
    }

    for (const cat of CATEGORY_ORDER) {
        const metrics = categories[cat];
        if (!metrics || metrics.length === 0) continue;

        const dotColor = CATEGORY_DOT_COLORS[cat] || '#888';
        const catIdAttr = cat.replace(/\s/g, '-');
        const isOpen = cat === 'Sleep' || cat === 'Habits';

        const section = document.createElement('div');
        section.className = 'accordion-section' + (isOpen ? ' open' : '');
        section.id = 'acc-' + catIdAttr;

        section.innerHTML = `
            <button class="accordion-header" onclick="toggleAccordion('${catIdAttr}')">
                <span class="cat-dot" style="background: ${dotColor};"></span>
                ${cat}
                <span class="accordion-chevron">▶</span>
            </button>
            <div class="accordion-body">
                ${metrics.map(m => buildCheckboxHtml(m.key, m)).join('')}
            </div>
        `;

        container.appendChild(section);
    }

    // Refresh swatches for any already-active metrics
    for (const key of activeMetrics) {
        refreshSwatch(key);
        const cb = document.getElementById('cb-' + keyToId(key));
        if (cb) cb.checked = true;
    }
}

function buildCheckboxHtml(key, meta) {
    const label = key.startsWith('habit:')
        ? key.slice(6).replace(/_/g, ' ')
        : key.replace(/_/g, ' ');
    const title = meta.description + (meta.unit && meta.unit !== 'habit' ? ` (${meta.unit})` : '');
    const domId = keyToId(key);
    const safeKey = key.replace(/\\/g, '\\\\').replace(/'/g, "\\'");

    return `
        <label class="metric-checkbox-label" title="${title}">
            <input type="checkbox" id="cb-${domId}"
                   onchange="onMetricToggle('${safeKey}', this.checked)">
            <span class="metric-color-swatch" id="swatch-${domId}"></span>
            ${label}
        </label>
    `;
}

function toggleAccordion(catId) {
    const section = document.getElementById('acc-' + catId);
    if (section) section.classList.toggle('open');
}

function refreshSwatch(key) {
    const el = document.getElementById('swatch-' + keyToId(key));
    if (!el) return;
    const color = metricColors[key];
    el.style.background = color || 'var(--border-strong)';
}

// ─── Metric toggle ────────────────────────────────────────────────────────────
function onMetricToggle(key, checked) {
    if (checked) {
        assignColor(key);
        activeMetrics.add(key);
        refreshSwatch(key);
    } else {
        activeMetrics.delete(key);
        refreshSwatch(key);
    }
    updateChart();
}

// ─── Data helpers ─────────────────────────────────────────────────────────────
function getMetricValues(key) {
    if (key.startsWith('habit:')) {
        const habitName = key.slice(6);
        return trendsData.map(d => {
            const h = (d.habits || []).find(h => h.name === habitName);
            if (h == null) return null;
            const v = h.value;
            if (v === null || v === undefined) return null;
            if (typeof v === 'boolean') return v ? 1 : 0;
            const n = Number(v);
            return isNaN(n) ? null : n;
        });
    }
    return trendsData.map(d => {
        const v = d[key];
        if (v === null || v === undefined) return null;
        if (typeof v === 'boolean') return v ? 1 : 0;
        const n = Number(v);
        return isNaN(n) ? null : n;
    });
}

function isBinaryValues(values) {
    const nonNull = values.filter(v => v !== null);
    return nonNull.length > 0 && nonNull.every(v => v === 0 || v === 1);
}

function getAxisForKey(key, values) {
    if (key.startsWith('habit:')) {
        // Binary boolean habits → score axis (scaled 0–100); numeric counts → count axis
        return isBinaryValues(values) ? 'y-score' : 'y-count';
    }
    const meta = metricMetadata[key];
    const unit = meta ? meta.unit : '';
    if (unit === '0-100' || unit === '%' || unit === 'boolean') return 'y-score';
    if (['ms', 'ms/reading', 'bpm', 'bpm/min'].includes(unit)) return 'y-hrv';
    return 'y-count';
}

function getMetricLabel(key) {
    if (key.startsWith('habit:')) {
        const name = key.slice(6).replace(/_/g, ' ');
        return name + ' (7d avg)';
    }
    const meta = metricMetadata[key];
    return meta ? meta.description : key.replace(/_/g, ' ');
}

// ─── Rolling average ──────────────────────────────────────────────────────────
function calculateRollingAverage(data, windowSize = 7) {
    const result = [];
    for (let i = 0; i < data.length; i++) {
        const start = Math.max(0, i - windowSize + 1);
        const window = data.slice(start, i + 1);
        const valid = window.filter(v => v !== null && v !== undefined);
        result.push(valid.length > 0
            ? valid.reduce((a, b) => a + b, 0) / valid.length
            : null);
    }
    return result;
}

// ─── Hex → rgba helper ────────────────────────────────────────────────────────
function hexToRgba(hex, alpha) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

// ─── Chart update ─────────────────────────────────────────────────────────────
function updateChart() {
    if (!trendsData.length) return;

    const labels = trendsData.map(d => d.date);
    const datasets = [];
    const useRolling = document.getElementById('rolling-avg-toggle').checked;

    let showScore = false;
    let showHrv = false;
    let showCount = false;

    for (const key of activeMetrics) {
        const rawValues = getMetricValues(key);
        const binary = isBinaryValues(rawValues);
        const axis = getAxisForKey(key, rawValues);
        const color = metricColors[key] || '#888888';

        // Apply rolling average for binary metrics when the toggle is on
        let displayValues = rawValues;
        if (useRolling && binary) {
            displayValues = calculateRollingAverage(rawValues);
        }

        // Scale 0/1 binary metrics to 0–100 for the score axis
        let chartValues = displayValues;
        if (axis === 'y-score' && binary) {
            chartValues = displayValues.map(v => v !== null ? v * 100 : null);
        }

        datasets.push({
            label: getMetricLabel(key),
            data: chartValues,
            borderColor: color,
            backgroundColor: hexToRgba(color, 0.1),
            yAxisID: axis,
            tension: 0.3,
            pointRadius: 0,
            pointHoverRadius: 4,
            borderWidth: 1.5,
            spanGaps: true,
        });

        if (axis === 'y-score') showScore = true;
        else if (axis === 'y-hrv') showHrv = true;
        else showCount = true;
    }

    if (chart) chart.destroy();

    const ctx = document.getElementById('trends-chart').getContext('2d');
    chart = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        color: '#8888a0',
                        font: { size: 11 },
                        boxWidth: 14,
                        padding: 10,
                    },
                },
            },
            scales: {
                x: {
                    ticks: {
                        color: '#555566',
                        maxTicksLimit: 12,
                        font: { size: 10 },
                    },
                    grid: { color: '#2a2a38' },
                },
                'y-score': {
                    type: 'linear',
                    display: showScore,
                    position: 'left',
                    min: 0,
                    max: 100,
                    title: {
                        display: true,
                        text: 'Score (0–100)',
                        color: '#8888a0',
                        font: { size: 10 },
                    },
                    ticks: { color: '#555566', font: { size: 10 } },
                    grid: { color: '#2a2a38' },
                },
                'y-hrv': {
                    type: 'linear',
                    display: showHrv,
                    position: 'right',
                    title: {
                        display: true,
                        text: 'bpm / ms',
                        color: '#8888a0',
                        font: { size: 10 },
                    },
                    ticks: { color: '#555566', font: { size: 10 } },
                    grid: { drawOnChartArea: false },
                },
                'y-count': {
                    type: 'linear',
                    display: showCount,
                    position: 'right',
                    title: {
                        display: true,
                        text: 'Count / Steps / Min',
                        color: '#8888a0',
                        font: { size: 10 },
                    },
                    ticks: { color: '#555566', font: { size: 10 } },
                    grid: { drawOnChartArea: false },
                },
            },
        },
    });
}

// ─── Entry point ──────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', init);
