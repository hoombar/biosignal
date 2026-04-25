// Trends page JavaScript — expanded metric system

// ─── State ────────────────────────────────────────────────────────────────────
let trendsData = [];
let metricMetadata = {};   // { key: { description, unit, category } }
let habitSettings = [];
let habitNames = [];
let activeMetrics = new Set();
let metricColors = {};     // key → hex color (persistent per key)
let chart = null;
let paletteIndex = 0;
let selectedRangeDays = 14;
let selectedStart = null;
let selectedEnd = null;

const ALLOWED_RANGE_DAYS = new Set([7, 14, 30, 60, 90]);
const DEFAULT_RANGE_DAYS = 14;

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
        const [metaResp, habitSettingsResp] = await Promise.all([
            fetch('/api/export/metadata'),
            fetch('/api/settings/habits'),
        ]);

        const metaData = await metaResp.json();
        metricMetadata = metaData.features || {};
        habitSettings = await habitSettingsResp.json();
        habitNames = habitSettings.map(h => h.habit_name);

        buildHabitSelector();
        initializeRangeControls();
        await applyPresetRange(DEFAULT_RANGE_DAYS);
    } catch (err) {
        console.error('Failed to initialise trends:', err);
    }
}

function formatDateForInput(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
}

function dateFromIso(isoDate) {
    return new Date(`${isoDate}T00:00:00`);
}

function setDateInputs(startIso, endIso) {
    const startInput = document.getElementById('range-start');
    const endInput = document.getElementById('range-end');
    if (startInput) startInput.value = startIso;
    if (endInput) endInput.value = endIso;
}

function setPresetChipState(activeDaysOrNull) {
    for (const days of ALLOWED_RANGE_DAYS) {
        const chip = document.getElementById(`range-chip-${days}`);
        if (!chip) continue;
        chip.classList.toggle('active', activeDaysOrNull === days);
    }
}

function initializeRangeControls() {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const start = new Date(today);
    start.setDate(start.getDate() - (DEFAULT_RANGE_DAYS - 1));

    selectedStart = formatDateForInput(start);
    selectedEnd = formatDateForInput(today);
    selectedRangeDays = DEFAULT_RANGE_DAYS;

    setDateInputs(selectedStart, selectedEnd);
    setPresetChipState(DEFAULT_RANGE_DAYS);
}

async function fetchDailySummariesForWindow(startIso, endIso) {
    const resp = await fetch(`/api/daily?start=${encodeURIComponent(startIso)}&end=${encodeURIComponent(endIso)}`);
    if (!resp.ok) {
        throw new Error(`Failed to fetch daily summaries (${resp.status})`);
    }
    trendsData = await resp.json();
}

async function reloadRangeWindow(startIso, endIso) {
    await fetchDailySummariesForWindow(startIso, endIso);
    buildMetricPicker();
    if (activeMetrics.size === 0) {
        activateDefaults();
    }
    updateChart();
}

async function refreshSuggestionsIfNeeded() {
    if (document.getElementById('correlate-habit').value) {
        await onCorrelateHabitChange();
    }
}

async function applyPresetRange(days) {
    const safeDays = ALLOWED_RANGE_DAYS.has(days) ? days : DEFAULT_RANGE_DAYS;
    const end = new Date();
    end.setHours(0, 0, 0, 0);
    const start = new Date(end);
    start.setDate(start.getDate() - (safeDays - 1));

    selectedStart = formatDateForInput(start);
    selectedEnd = formatDateForInput(end);
    selectedRangeDays = safeDays;

    setDateInputs(selectedStart, selectedEnd);
    setPresetChipState(safeDays);

    await reloadRangeWindow(selectedStart, selectedEnd);
    await refreshSuggestionsIfNeeded();
}

async function onRangePresetClick(days) {
    try {
        await applyPresetRange(days);
    } catch (err) {
        console.error('Failed to apply preset range:', err);
    }
}

function onCustomRangeInputChange() {
    // User is adjusting custom window; clear preset highlight until apply.
    setPresetChipState(null);
}

async function applyCustomRange() {
    const startInput = document.getElementById('range-start');
    const endInput = document.getElementById('range-end');
    const startIso = startInput ? startInput.value : '';
    const endIso = endInput ? endInput.value : '';

    if (!startIso || !endIso) {
        alert('Please choose both a start and end date.');
        return;
    }

    const start = dateFromIso(startIso);
    const end = dateFromIso(endIso);
    if (start > end) {
        alert('Start date must be on or before end date.');
        return;
    }

    selectedStart = startIso;
    selectedEnd = endIso;

    const days = Math.floor((end - start) / (24 * 3600 * 1000)) + 1;
    if (ALLOWED_RANGE_DAYS.has(days)) {
        selectedRangeDays = days;
        setPresetChipState(days);
    } else {
        selectedRangeDays = null;
        setPresetChipState(null);
    }

    try {
        await reloadRangeWindow(startIso, endIso);
        await refreshSuggestionsIfNeeded();
    } catch (err) {
        console.error('Failed to apply custom range:', err);
    }
}

// ─── Color assignment ─────────────────────────────────────────────────────────
function assignColor(key) {
    if (!metricColors[key]) {
        if (key.startsWith('habit:')) {
            const habitColor = getHabitColorSetting(key.slice(6));
            if (habitColor) {
                metricColors[key] = habitColor;
                return metricColors[key];
            }
        }
        metricColors[key] = PALETTE[paletteIndex % PALETTE.length];
        paletteIndex++;
    }
    return metricColors[key];
}

// ─── Default active metrics ───────────────────────────────────────────────────
function activateDefaults() {
    if (habitNames.length > 0) {
        enableMetric(`habit:${habitNames[0]}`);
    }
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
    return key.replace(/[^a-zA-Z0-9_-]/g, '_');
}

function getHabitSetting(name) {
    return habitSettings.find(h => h.habit_name === name);
}

function getHabitLabel(name) {
    const setting = getHabitSetting(name);
    return (setting && setting.display_name) || name.replace(/_/g, ' ');
}

function getHabitColorSetting(name) {
    const setting = getHabitSetting(name);
    return (setting && setting.color) || null;
}

// ─── Habit range detection ────────────────────────────────────────────────────
// HabitSync stores all habits with type="counter" regardless of whether they are
// binary (0/1) or a real count (0-N). We can't use habit.type to
// distinguish them. Instead, inspect the actual data: if every non-null value is
// 0 or 1 the habit is binary; if any value exceeds 1 it's a count metric.
function isHabitBinary(habitName) {
    const values = trendsData
        .map(d => (d.habits || []).find(h => h.name === habitName))
        .filter(h => h != null)
        .map(h => {
            const n = Number(h.value);
            return isNaN(n) ? null : n;
        })
        .filter(v => v !== null);
    return values.length > 0 && values.every(v => v === 0 || v === 1);
}

// ─── Habit selector (top bar) ─────────────────────────────────────────────────
function buildHabitSelector() {
    const select = document.getElementById('correlate-habit');
    select.innerHTML = '<option value="">-- Select habit --</option>' +
        habitNames.map(name =>
            `<option value="${name}">${getHabitLabel(name)}</option>`
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
        const key = c.metric.startsWith('habit_') ? `habit:${c.metric.slice(6)}` : c.metric;
        const isAdded = activeMetrics.has(key);
        const r = c.coefficient;
        const barColor = r > 0 ? '#4488ff' : '#fb923c';
        const barWidth = (Math.abs(r) * 100).toFixed(0);
        const label = key.startsWith('habit:')
            ? getHabitLabel(key.slice(6))
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

    const cb = document.getElementById('cb-' + keyToId(key));
    if (cb && !cb.checked) {
        cb.checked = true;
        onMetricToggle(key, true);
    }

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

    const categories = {};
    for (const [key, meta] of Object.entries(metricMetadata)) {
        const unit = meta.unit || '';
        if (unit === 'text' || unit === 'low/medium/high') continue;
        const cat = meta.category || 'Other';
        if (!categories[cat]) categories[cat] = [];
        categories[cat].push({ key, ...meta });
    }

    if (habitNames.length > 0) {
        categories['Habits'] = habitNames.map(name => ({
            key: `habit:${name}`,
            description: getHabitLabel(name),
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

    for (const key of activeMetrics) {
        refreshSwatch(key);
        const cb = document.getElementById('cb-' + keyToId(key));
        if (cb) cb.checked = true;
    }
}

function buildCheckboxHtml(key, meta) {
    const label = key.startsWith('habit:')
        ? getHabitLabel(key.slice(6))
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
    el.style.background = metricColors[key] || 'var(--border-strong)';
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

// Axis assignment.
// Axes: y-score (0–100), y-hrv (bpm/ms), y-count (steps/min/large counts),
//       y-binary (0–1 stepped, "No/Yes"), y-numeric (auto-scaled small counts).
function getAxisForKey(key) {
    if (key.startsWith('habit:')) {
        // Use actual data values to distinguish binary (0/1) from count (0-N) habits,
        // since HabitSync stores all habits as type="counter" regardless of range.
        return isHabitBinary(key.slice(6)) ? 'y-binary' : 'y-numeric';
    }
    const meta = metricMetadata[key];
    const unit = meta ? meta.unit : '';
    if (unit === 'boolean') return 'y-binary';
    if (unit === '0-100' || unit === '%') return 'y-score';
    if (['ms', 'ms/reading', 'bpm', 'bpm/min'].includes(unit)) return 'y-hrv';
    return 'y-count';
}

function getMetricLabel(key) {
    if (key.startsWith('habit:')) {
        return getHabitLabel(key.slice(6));
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

// ─── Habit lanes (below main chart) ───────────────────────────────────────────
// Chart.js plugin: after each layout pass, sync the habit lanes container's
// horizontal padding with the main chart's plot area so day cells line up
// under the same x-positions as the chart points.
const habitLaneAlignmentPlugin = {
    id: 'habitLaneAlignment',
    afterLayout(chartInstance) {
        const lanes = document.getElementById('habit-lanes');
        if (!lanes || !chartInstance.chartArea) return;
        const { left, right } = chartInstance.chartArea;
        const total = chartInstance.width;
        lanes.style.setProperty('--lane-label-width', `${left}px`);
        lanes.style.paddingRight = `${Math.max(0, total - right)}px`;
    },
};


function buildRollingPath(values) {
    // Build an SVG path d-string in viewBox units (x = day index, y = 0..1)
    // for the 7-day rolling frequency. Breaks the path on null gaps so we
    // don't draw straight lines across days with no data.
    const rolling = calculateRollingAverage(values, 7);
    let d = '';
    let started = false;
    rolling.forEach((v, i) => {
        if (v === null || v === undefined) {
            started = false;
            return;
        }
        const clamped = Math.min(1, Math.max(0, v));
        const x = (i + 0.5).toFixed(3);
        const y = (1 - clamped).toFixed(4);
        d += (started ? ' L' : 'M') + x + ',' + y;
        started = true;
    });
    return d;
}

function renderHabitLanes() {
    const container = document.getElementById('habit-lanes');
    if (!container) return;

    const habitKeys = [...activeMetrics].filter(k => k.startsWith('habit:'));

    if (habitKeys.length === 0 || trendsData.length === 0) {
        container.classList.add('is-empty');
        container.innerHTML = '';
        return;
    }
    container.classList.remove('is-empty');
    container.style.setProperty('--day-count', trendsData.length);

    const dates = trendsData.map(d => d.date);
    const showRolling = document.getElementById('rolling-avg-toggle').checked;
    const dayCount = trendsData.length;

    container.innerHTML = habitKeys.map(key => {
        const habitName = key.slice(6);
        const color = metricColors[key] || getHabitColorSetting(habitName) || '#888888';
        const label = getHabitLabel(habitName);
        const values = getMetricValues(key); // null | 0 | positive number

        const cells = values.map((v, i) => {
            let state;
            if (v === null) state = 'null';
            else if (v > 0) state = 'on';
            else state = 'off';
            return `<span class="habit-cell ${state}" title="${dates[i]}: ${v ?? '—'}"></span>`;
        }).join('');

        // Rolling line only on binary habits; counts won't fit a 0..1 axis.
        let rollingSvg = '';
        if (showRolling && isHabitBinary(habitName)) {
            const d = buildRollingPath(values);
            if (d) {
                rollingSvg = `<svg class="habit-lane-rolling" viewBox="0 0 ${dayCount} 1" preserveAspectRatio="none"><path d="${d}" /></svg>`;
            }
        }

        return `
            <div class="habit-lane" data-habit="${habitName}" style="--cell-color: ${color}; --day-count: ${dayCount};">
                <div class="habit-lane-label" title="${label}">${label}</div>
                <div class="habit-lane-cells">${cells}${rollingSvg}</div>
            </div>
        `;
    }).join('');
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
    let showBinary = false;

    for (const key of activeMetrics) {
        // Habits live in their own lanes below the chart, never on the main canvas.
        if (key.startsWith('habit:')) continue;

        const rawValues = getMetricValues(key);
        const axis = getAxisForKey(key);
        const color = metricColors[key] || '#888888';
        const bgColor = hexToRgba(color, 0.1);
        const label = getMetricLabel(key);

        if (axis === 'y-binary') {
            // Stepped raw line — clearly shows yes/no per day, alternating patterns visible
            datasets.push({
                label,
                data: rawValues,
                borderColor: color,
                backgroundColor: bgColor,
                yAxisID: 'y-binary',
                stepped: 'before',
                pointRadius: 0,
                pointHoverRadius: 4,
                borderWidth: 1.5,
                spanGaps: false,
                tension: 0,
            });

            // Optional dotted frequency overlay (0–1) when toggle is on
            if (useRolling) {
                const rolled = calculateRollingAverage(rawValues);
                datasets.push({
                    label: label + ' (7d)',
                    data: rolled,
                    borderColor: color,
                    backgroundColor: 'transparent',
                    yAxisID: 'y-binary',
                    tension: 0.4,
                    pointRadius: 0,
                    pointHoverRadius: 3,
                    borderWidth: 1,
                    borderDash: [4, 3],
                    spanGaps: true,
                });
            }

            showBinary = true;

        } else {
            // Smooth line for all non-binary metrics (score, hrv, count, numeric habits)
            datasets.push({
                label,
                data: rawValues,
                borderColor: color,
                backgroundColor: bgColor,
                yAxisID: axis,
                tension: 0.3,
                pointRadius: 0,
                pointHoverRadius: 4,
                borderWidth: 1.5,
                spanGaps: true,
            });

            if (axis === 'y-score') showScore = true;
            else if (axis === 'y-hrv') showHrv = true;
            else if (axis === 'y-count') showCount = true;
        }
    }

    renderHabitLanes();

    if (chart) chart.destroy();

    const ctx = document.getElementById('trends-chart').getContext('2d');
    chart = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets },
        plugins: [habitLaneAlignmentPlugin],
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
                'y-binary': {
                    type: 'linear',
                    display: showBinary,
                    position: 'right',
                    min: -0.15,
                    max: 1.2,
                    title: {
                        display: true,
                        text: 'Yes / No',
                        color: '#8888a0',
                        font: { size: 10 },
                    },
                    ticks: {
                        color: '#555566',
                        font: { size: 10 },
                        stepSize: 1,
                        callback: v => v === 0 ? 'No' : v === 1 ? 'Yes' : null,
                    },
                    grid: { drawOnChartArea: false },
                },
            },
        },
    });
}

// ─── Entry point ──────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', init);
