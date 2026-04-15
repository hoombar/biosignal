// Correlations page JavaScript

const TARGET_STORAGE_KEY = 'biosignal_correlation_target';
const LEGACY_HABIT_STORAGE_KEY = 'biosignal_target_habit';

let correlationChart = null;
let metricMetadata = {};

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
    try {
        // Fetch metadata here as well so the selector is independent of legend-load timing.
        if (Object.keys(metricMetadata).length === 0) {
            const metadataResp = await fetch('/api/export/metadata');
            const metadataBody = await metadataResp.json();
            metricMetadata = metadataBody.features || {};
        }

        const habitsResp = await fetch('/api/habits/names');
        const habitNames = await habitsResp.json();

        const select = document.getElementById('target-habit');
        const metricTargets = buildMetricTargetOptions();
        const habitTargets = habitNames
            .slice()
            .sort((a, b) => a.localeCompare(b))
            .map(name => `habit:${name}`);

        let html = '<option value="">-- Select a target --</option>';

        if (metricTargets.length > 0) {
            html += '<option value="" disabled>──────── Metrics ────────</option>';
            html += metricTargets.map(key =>
                `<option value="${key}">Metric: ${formatTargetOptionLabel(key)}</option>`
            ).join('');
        }
        if (habitTargets.length > 0) {
            html += '<option value="" disabled>──────── Habits ────────</option>';
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
        }
    } catch (error) {
        console.error('Error loading correlation targets:', error);
        document.getElementById('target-habit').innerHTML = '<option value="">Failed to load targets</option>';
    }
}

async function loadCorrelations() {
    const select = document.getElementById('target-habit');
    const target = select.value;
    const tableContainer = document.getElementById('correlation-table');

    if (!target) {
        tableContainer.innerHTML = '<p>Select a target to see correlations</p>';
        return;
    }

    localStorage.setItem(TARGET_STORAGE_KEY, target);
    tableContainer.innerHTML = '<p class="loading">Loading correlations...</p>';

    try {
        const resp = await fetch(`/api/correlations?target=${encodeURIComponent(target)}`);
        if (!resp.ok) {
            throw new Error(`HTTP ${resp.status}`);
        }
        const correlations = await resp.json();

        if (correlations.length === 0) {
            tableContainer.innerHTML = '<p>Insufficient data for correlations. Need at least 5 days with this target tracked.</p>';
            return;
        }

        if (correlationChart) {
            correlationChart.destroy();
        }

        const top15 = correlations.slice(0, 15);
        const ctx = document.getElementById('correlation-chart').getContext('2d');

        correlationChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: top15.map(c => formatMetricName(c.metric)),
                datasets: [{
                    label: 'Correlation Coefficient',
                    data: top15.map(c => c.coefficient),
                    backgroundColor: top15.map(c =>
                        c.coefficient > 0 ? 'rgba(54, 162, 235, 0.5)' : 'rgba(255, 159, 64, 0.5)'
                    ),
                    borderColor: top15.map(c =>
                        c.coefficient > 0 ? 'rgba(54, 162, 235, 1)' : 'rgba(255, 159, 64, 1)'
                    ),
                    borderWidth: 1,
                }],
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        beginAtZero: true,
                        min: -1,
                        max: 1,
                    },
                },
            },
        });

        const positiveLabel = correlations[0].positive_label || 'Positive target';
        const negativeLabel = correlations[0].negative_label || 'Negative target';

        tableContainer.innerHTML = '<table style="width: 100%; border-collapse: collapse;">' +
            '<thead><tr>' +
            '<th style="text-align: left; padding: 0.5rem;">Metric</th>' +
            '<th style="text-align: right; padding: 0.5rem;">r</th>' +
            '<th style="text-align: right; padding: 0.5rem;">Strength</th>' +
            `<th style="text-align: right; padding: 0.5rem;">${positiveLabel} Avg</th>` +
            `<th style="text-align: right; padding: 0.5rem;">${negativeLabel} Avg</th>` +
            '<th style="text-align: right; padding: 0.5rem;">Difference</th>' +
            '<th style="text-align: right; padding: 0.5rem;">n</th>' +
            '</tr></thead><tbody>' +
            correlations.map(c => {
                const tooltip = getMetricTooltip(c.metric);
                const titleAttr = tooltip ? ` title="${tooltip}"` : '';
                return `
                <tr style="border-top: 1px solid var(--border-color);">
                    <td style="padding: 0.5rem; cursor: help;"${titleAttr}>${formatMetricName(c.metric)}</td>
                    <td style="text-align: right; padding: 0.5rem; font-weight: bold;">${c.coefficient.toFixed(3)}</td>
                    <td style="text-align: right; padding: 0.5rem;">${c.strength}</td>
                    <td style="text-align: right; padding: 0.5rem;">${c.fog_day_avg !== null ? c.fog_day_avg.toFixed(1) : '-'}</td>
                    <td style="text-align: right; padding: 0.5rem;">${c.clear_day_avg !== null ? c.clear_day_avg.toFixed(1) : '-'}</td>
                    <td style="text-align: right; padding: 0.5rem;">${c.difference_pct !== null ? c.difference_pct.toFixed(1) + '%' : '-'}</td>
                    <td style="text-align: right; padding: 0.5rem;">${c.n}</td>
                </tr>
            `;
            }).join('') +
            '</tbody></table>';

    } catch (error) {
        console.error('Error loading correlations:', error);
        tableContainer.innerHTML = '<p class="error">Failed to load correlations</p>';
    }
}

document.addEventListener('DOMContentLoaded', async () => {
    await loadMetricMetadata();
    loadTargetSelector();
});
