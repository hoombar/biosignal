// Insights page JavaScript

let habitSettings = [];
let analysisController = null;

function getHabitLabel(habitName) {
    const setting = habitSettings.find(h => h.habit_name === habitName);
    return (setting && setting.display_name) || habitName.replace(/_/g, ' ');
}

async function loadHabits() {
    try {
        const resp = await fetch('/api/settings/habits');
        habitSettings = await resp.json();
        const habitNames = habitSettings.map(h => h.habit_name);

        const select = document.getElementById('target-habit');
        if (!habitNames || habitNames.length === 0) {
            select.innerHTML = '<option value="">No habits found</option>';
            return;
        }

        select.innerHTML = habitNames.map(name =>
            `<option value="${name}">${getHabitLabel(name)}</option>`
        ).join('');

    } catch (error) {
        console.error('Error loading habits:', error);
        habitSettings = [];
        document.getElementById('target-habit').innerHTML = '<option value="">No habits found</option>';
    }
}

function getTargetHabit() {
    return document.getElementById('target-habit').value || null;
}

async function loadInsights(targetHabit, signal) {
    const container = document.getElementById('insights-list');
    container.innerHTML = '<p class="loading loading--with-spinner">Loading insights...</p>';

    if (!targetHabit) {
        container.innerHTML = '<p>No habits available for analysis yet.</p>';
        return;
    }

    try {
        const resp = await fetch(
            `/api/insights?target_habit=${encodeURIComponent(targetHabit)}`,
            { signal },
        );
        if (!resp.ok) {
            throw new Error(`HTTP ${resp.status}`);
        }
        const insights = await resp.json();
        if (signal.aborted) return;

        if (insights.length === 0) {
            const select = document.getElementById('target-habit');
            const label = select.options[select.selectedIndex]?.text || getHabitLabel(targetHabit);
            container.innerHTML = `<p>No insights yet. Need at least 7 days of <strong>${label}</strong> data.</p>`;
            return;
        }

        container.innerHTML = insights.map(insight => {
            const icon = insight.confidence === 'high' ? '✓' :
                        insight.confidence === 'medium' ? '!' : '?';
            const color = insight.confidence === 'high' ? 'var(--success-color)' :
                         insight.confidence === 'medium' ? 'var(--warning-color)' :
                         'var(--text-secondary)';

            return `
                <div style="margin-bottom: 1.5rem; padding: 1rem; border: 1px solid var(--border-color); border-radius: 6px;">
                    <div style="display: flex; align-items: start; gap: 1rem;">
                        <div style="font-size: 1.5rem; color: ${color};">${icon}</div>
                        <div style="flex: 1;">
                            <p style="margin: 0; font-size: 1.1rem;">${insight.text}</p>
                            <p style="margin: 0.5rem 0 0; font-size: 0.875rem; color: var(--text-secondary);">
                                Confidence: ${insight.confidence}
                                ${insight.effect_size ? ` • Effect size: ${insight.effect_size.toFixed(2)}` : ''}
                            </p>
                        </div>
                    </div>
                </div>
            `;
        }).join('');

    } catch (error) {
        if (signal.aborted || error.name === 'AbortError') return;
        console.error('Error loading insights:', error);
        container.innerHTML = '<p class="error">Failed to load insights</p>';
    }
}

async function loadPatterns(targetHabit, signal) {
    const container = document.getElementById('patterns-list');
    container.innerHTML = '<p class="loading loading--with-spinner">Loading patterns...</p>';

    if (!targetHabit) {
        container.innerHTML = '<p>No habits available for pattern analysis yet.</p>';
        return;
    }

    try {
        const resp = await fetch(
            `/api/patterns?target_habit=${encodeURIComponent(targetHabit)}`,
            { signal },
        );
        if (!resp.ok) {
            throw new Error(`HTTP ${resp.status}`);
        }
        const patterns = await resp.json();
        if (signal.aborted) return;

        if (patterns.length === 0) {
            container.innerHTML = '<p>No patterns detected yet.</p>';
            return;
        }

        container.innerHTML = '<table style="width: 100%; border-collapse: collapse;">' +
            '<thead><tr>' +
            '<th style="text-align: left; padding: 0.5rem;">Condition</th>' +
            '<th style="text-align: right; padding: 0.5rem;">Probability</th>' +
            '<th style="text-align: right; padding: 0.5rem;">Baseline</th>' +
            '<th style="text-align: right; padding: 0.5rem;">Relative Risk</th>' +
            '<th style="text-align: right; padding: 0.5rem;">Sample Size</th>' +
            '</tr></thead><tbody>' +
            patterns.map(p => `
                <tr style="border-top: 1px solid var(--border-color);">
                    <td style="padding: 0.5rem;">${p.description}</td>
                    <td style="text-align: right; padding: 0.5rem;">${(p.probability * 100).toFixed(0)}%</td>
                    <td style="text-align: right; padding: 0.5rem;">${(p.baseline_probability * 100).toFixed(0)}%</td>
                    <td style="text-align: right; padding: 0.5rem; font-weight: bold; color: ${p.relative_risk > 1 ? 'var(--danger-color)' : 'var(--success-color)'};">
                        ${p.relative_risk.toFixed(2)}x
                    </td>
                    <td style="text-align: right; padding: 0.5rem;">${p.sample_size}</td>
                </tr>
            `).join('') +
            '</tbody></table>';

    } catch (error) {
        if (signal.aborted || error.name === 'AbortError') return;
        console.error('Error loading patterns:', error);
        container.innerHTML = '<p class="error">Failed to load patterns</p>';
    }
}

function exportData(format, days) {
    window.location.href = `/api/export?format=${format}&days=${days}`;
}

async function loadAll() {
    if (analysisController) analysisController.abort();
    analysisController = new AbortController();

    const targetHabit = getTargetHabit();
    const { signal } = analysisController;
    await Promise.all([
        loadInsights(targetHabit, signal),
        loadPatterns(targetHabit, signal),
    ]);
}

// Load on page load
document.addEventListener('DOMContentLoaded', async () => {
    await loadHabits();
    await loadAll();
});
