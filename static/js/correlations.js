// Correlations page JavaScript

const TARGET_STORAGE_KEY = 'biosignal_correlation_target';
const LEGACY_HABIT_STORAGE_KEY = 'biosignal_target_habit';
const SORT_KEY = 'biosignal_correlation_sort';

let metricMetadata = {};
let lastCorrelations = [];

function isNumericTargetMeta(meta) {
    const unit = (meta && meta.unit) || '';
    return unit !== 'text' && unit !== 'low/medium/high';
}

function formatMetricName(metricName) {
    if (metricName.startsWith('habit_')) {
        return metricName.slice(6).replace(/_/g, ' ');
    }
    return metricName.replace(/_/g, ' ');
}

function formatTargetOptionLabel(value) {
    if (value.startsWith('habit:')) {
        return value.slice(6).replace(/_/g, ' ');
    }
    return value.replace(/_/g, ' ');
}

function targetDisplayLabel(value) {
    if (!value) return '—';
    if (value.startsWith('habit:')) {
        return `Habit: ${value.slice(6).replace(/_/g, ' ')}`;
    }
    return `Metric: ${value.replace(/_/g, ' ')}`;
}

async function loadMetricMetadata() {
    try {
        const resp = await fetch('/api/export/metadata');
        const data = await resp.json();
        metricMetadata = data.features || {};
        renderLegend();
    } catch (error) {
        console.error('Error loading metric metadata:', error);
    }
}

function renderLegend() {
    const container = document.getElementById('legend-content');
    if (!container || Object.keys(metricMetadata).length === 0) return;

    const categories = {};
    for (const [key, meta] of Object.entries(metricMetadata)) {
        const cat = meta.category || 'Other';
        if (!categories[cat]) categories[cat] = [];
        categories[cat].push({ key, ...meta });
    }

    let html = '';
    for (const [category, metrics] of Object.entries(categories)) {
        html += `<div class="legend-category">
            <h4>${category}</h4>
            <table>
                <tbody>
                    ${metrics.map(m => `
                        <tr>
                            <td class="legend-metric">${m.key.replace(/_/g, ' ')}</td>
                            <td class="legend-desc">${m.description}</td>
                            <td class="legend-unit">${m.unit}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>`;
    }

    container.innerHTML = html;
}

function toggleLegend() {
    const content = document.getElementById('legend-content');
    const button = document.querySelector('.legend-toggle');
    if (content.style.display === 'none') {
        content.style.display = 'block';
        button.classList.add('expanded');
    } else {
        content.style.display = 'none';
        button.classList.remove('expanded');
    }
}

function getMetricTooltip(metricName) {
    const lookupKey = metricName.startsWith('habit_') ? metricName.slice(6) : metricName;
    const meta = metricMetadata[lookupKey];
    if (meta) {
        return `${meta.description} (${meta.unit})`;
    }
    return '';
}

function buildMetricTargetOptions() {
    const metricEntries = Object.entries(metricMetadata)
        .filter(([, meta]) => meta.category !== 'Habits' && isNumericTargetMeta(meta))
        .sort((a, b) => {
            const catA = a[1].category || '';
            const catB = b[1].category || '';
            if (catA !== catB) return catA.localeCompare(catB);
            return a[0].localeCompare(b[0]);
        });

    return metricEntries.map(([key]) => key);
}

async function loadTargetSelector() {
    const select = document.getElementById('target-habit');
    let metricTargets = [];
    let habitTargets = [];

    try {
        const targetsResp = await fetch('/api/correlation-targets');
        if (!targetsResp.ok) {
            throw new Error(`HTTP ${targetsResp.status}`);
        }
        const allTargets = await targetsResp.json();

        metricTargets = allTargets
            .filter(t => t.kind === 'metric')
            .map(t => t.target);
        habitTargets = allTargets
            .filter(t => t.kind === 'habit')
            .map(t => t.target);
    } catch (error) {
        console.warn('Correlation targets endpoint unavailable, falling back to client-built target list:', error);
        try {
            if (Object.keys(metricMetadata).length === 0) {
                const metadataResp = await fetch('/api/export/metadata');
                const metadataBody = await metadataResp.json();
                metricMetadata = metadataBody.features || {};
            }

            const habitsResp = await fetch('/api/habits/names');
            const habitNames = await habitsResp.json();

            metricTargets = buildMetricTargetOptions();
            habitTargets = habitNames
                .slice()
                .sort((a, b) => a.localeCompare(b))
                .map(name => `habit:${name}`);
        } catch (fallbackError) {
            console.error('Error loading fallback correlation targets:', fallbackError);
            select.innerHTML = '<option value="">Failed to load targets</option>';
            return;
        }
    }

    let html = '<option value="">-- Select a target --</option>';

    if (metricTargets.length > 0) {
        html += '<option value="" disabled>Metrics</option>';
        html += metricTargets.map(key =>
            `<option value="${key}">Metric: ${formatTargetOptionLabel(key)}</option>`
        ).join('');
    }
    if (habitTargets.length > 0) {
        html += '<option value="" disabled>Habits</option>';
        html += habitTargets.map(key =>
            `<option value="${key}">Habit: ${formatTargetOptionLabel(key)}</option>`
        ).join('');
    }

    select.innerHTML = html;

    let savedTarget = localStorage.getItem(TARGET_STORAGE_KEY);
    if (!savedTarget) {
        const legacyHabit = localStorage.getItem(LEGACY_HABIT_STORAGE_KEY);
        if (legacyHabit) {
            savedTarget = `habit:${legacyHabit}`;
        }
    }

    const validValues = new Set([...metricTargets, ...habitTargets]);
    if (savedTarget && validValues.has(savedTarget)) {
        select.value = savedTarget;
        loadCorrelations();
    } else {
        updateTargetDisplays('');
    }
}

function updateTargetDisplays(target) {
    const label = targetDisplayLabel(target);
    const subtitleLabel = document.getElementById('corr-target-label');
    const pillLabel = document.getElementById('corr-target-pill-label');
    if (subtitleLabel) subtitleLabel.textContent = label;
    if (pillLabel) pillLabel.textContent = target ? label : 'Select target';
}

function getSortMode() {
    const v = localStorage.getItem(SORT_KEY);
    return v === 'signed' || v === 'n' ? v : 'abs';
}

function applyView(correlations) {
    const sort = getSortMode();
    let rows = correlations.slice();
    if (sort === 'abs') {
        rows.sort((a, b) => Math.abs(b.coefficient) - Math.abs(a.coefficient));
    } else if (sort === 'signed') {
        rows.sort((a, b) => b.coefficient - a.coefficient);
    } else if (sort === 'n') {
        rows.sort((a, b) => b.n - a.n);
    }
    return rows;
}

function dotDiameterForN(n) {
    const safe = Math.max(1, n || 1);
    const d = 5 + Math.log2(safe) * 1.3;
    return Math.max(5, Math.min(13, d));
}

function lollipopHTML(coef, n) {
    const isPos = coef >= 0;
    const clamped = Math.max(-1, Math.min(1, coef));
    const xPct = 50 + clamped * 50;
    const polarity = isPos ? 'corr-pol-pos' : 'corr-pol-neg';
    const stemLeft = Math.min(50, xPct);
    const stemWidth = Math.abs(xPct - 50);
    const dotSize = dotDiameterForN(n);
    const ticks = [0, 25, 50, 75, 100]
        .map(t => `<span class="corr-tick" style="left:${t}%"></span>`)
        .join('');
    return `
        <span class="corr-lollipop ${polarity}">
            <span class="corr-baseline"></span>
            ${ticks}
            <span class="corr-stem" style="left:${stemLeft}%;width:${stemWidth}%"></span>
            <span class="corr-dot-marker" style="left:${xPct}%;width:${dotSize}px;height:${dotSize}px"></span>
        </span>
    `;
}

function formatSignedR(coef) {
    const sign = coef >= 0 ? '+' : '−';
    return `${sign}${Math.abs(coef).toFixed(3)}`;
}

function renderRows() {
    const container = document.getElementById('correlation-rows');
    const metricCountEl = document.getElementById('corr-metric-count');
    const dayCountEl = document.getElementById('corr-day-count');

    if (!container) return;

    const rows = applyView(lastCorrelations);

    if (lastCorrelations.length === 0) {
        container.innerHTML = '<p class="loading">Select a target to see correlations</p>';
        if (metricCountEl) metricCountEl.textContent = '0';
        if (dayCountEl) dayCountEl.textContent = '0';
        return;
    }

    if (rows.length === 0) {
        container.innerHTML = '<p class="loading">No metrics match the current filter.</p>';
    } else {
        container.innerHTML = rows.map((c, i) => {
            const dim = c.n < 15 ? ' corr-row--dim' : '';
            const rClass = c.coefficient >= 0 ? 'r-pos' : 'r-neg';
            const tooltip = getMetricTooltip(c.metric);
            const titleAttr = tooltip ? ` title="${tooltip.replace(/"/g, '&quot;')}"` : '';
            return `
                <div class="corr-row${dim}">
                    <span class="corr-col-index">${String(i + 1).padStart(2, '0')}</span>
                    <span class="corr-col-metric"${titleAttr}>${formatMetricName(c.metric)}</span>
                    <span class="corr-col-chart">${lollipopHTML(c.coefficient, c.n)}</span>
                    <span class="corr-col-r ${rClass}">${formatSignedR(c.coefficient)}</span>
                    <span class="corr-col-n">n=${c.n}</span>
                    <span class="corr-col-strength">${(c.strength || '').toUpperCase()}</span>
                </div>
            `;
        }).join('');
    }

    if (metricCountEl) metricCountEl.textContent = String(rows.length);
    if (dayCountEl) {
        const maxN = lastCorrelations.reduce((m, c) => Math.max(m, c.n || 0), 0);
        dayCountEl.textContent = String(maxN);
    }
}

function syncPillStates() {
    const sort = getSortMode();
    document.querySelectorAll('.corr-sort').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.sort === sort);
    });
}

function bindControls() {
    document.querySelectorAll('.corr-sort').forEach(btn => {
        btn.addEventListener('click', () => {
            localStorage.setItem(SORT_KEY, btn.dataset.sort);
            syncPillStates();
            renderRows();
        });
    });

    const targetPill = document.getElementById('corr-target-pill');
    const picker = document.getElementById('corr-target-picker');
    if (targetPill && picker) {
        targetPill.addEventListener('click', () => {
            const isHidden = picker.hasAttribute('hidden');
            if (isHidden) {
                picker.removeAttribute('hidden');
                const select = document.getElementById('target-habit');
                if (select) select.focus();
            } else {
                picker.setAttribute('hidden', '');
            }
        });
    }

    const select = document.getElementById('target-habit');
    if (select) {
        select.addEventListener('change', () => {
            if (picker) picker.setAttribute('hidden', '');
        });
    }
}

async function loadCorrelations() {
    const select = document.getElementById('target-habit');
    const target = select.value;
    const container = document.getElementById('correlation-rows');

    updateTargetDisplays(target);

    if (!target) {
        lastCorrelations = [];
        renderRows();
        return;
    }

    localStorage.setItem(TARGET_STORAGE_KEY, target);
    container.innerHTML = '<p class="loading">Loading correlations...</p>';

    try {
        const resp = await fetch(`/api/correlations?target=${encodeURIComponent(target)}`);
        if (!resp.ok) {
            throw new Error(`HTTP ${resp.status}`);
        }
        const correlations = await resp.json();

        if (correlations.length === 0) {
            lastCorrelations = [];
            container.innerHTML = '<p class="loading">Insufficient data for correlations. Need at least 5 days with this target tracked.</p>';
            const metricCountEl = document.getElementById('corr-metric-count');
            const dayCountEl = document.getElementById('corr-day-count');
            if (metricCountEl) metricCountEl.textContent = '0';
            if (dayCountEl) dayCountEl.textContent = '0';
            return;
        }

        lastCorrelations = correlations;
        renderRows();
    } catch (error) {
        console.error('Error loading correlations:', error);
        container.innerHTML = '<p class="error">Failed to load correlations</p>';
    }
}

document.addEventListener('DOMContentLoaded', async () => {
    syncPillStates();
    bindControls();
    await loadMetricMetadata();
    loadTargetSelector();
});
