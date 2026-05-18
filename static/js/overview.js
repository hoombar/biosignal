// Overview page JavaScript

function formatName(value) {
    return String(value || '').replace(/^habit_/, '').replace(/^supplement_/, '').replace(/_/g, ' ');
}

function signalText(c) {
    if (c.summary) return c.summary;
    const metric = formatName(c.metric);
    const target = c.target_label || formatName(c.target_feature || c.target);
    const direction = Number(c.coefficient) >= 0 ? 'higher' : 'lower';
    return `When ${metric} is higher, ${target} tends to be ${direction}`;
}

function confidenceLabel(c) {
    return c.confidence ? `${c.confidence} confidence` : `${c.strength || 'signal'} signal`;
}

async function loadCorrelationSnapshot() {
    const container = document.getElementById('top-correlates');
    container.innerHTML = '<p class="loading">Loading unexpected signals...</p>';

    try {
        const corrResp = await fetch('/api/correlation-snapshot?limit=5&min_abs=0.3&min_days=14');
        if (!corrResp.ok) {
            throw new Error(`Correlation snapshot request failed (${corrResp.status})`);
        }
        const snapshot = await corrResp.json();
        if (!Array.isArray(snapshot)) {
            throw new Error('Correlation snapshot response was not a list');
        }

        if (snapshot.length === 0) {
            container.innerHTML = '<p>No unexpected strong correlations found yet.</p>';
        } else {
            container.innerHTML = snapshot.map(c => `
                <div style="margin-bottom: 1rem; padding: 1rem; border-left: 3px solid var(--primary-color);">
                    <strong>${signalText(c)}</strong><br>
                    ${confidenceLabel(c)} · r=${Number(c.coefficient).toFixed(3)}, n=${c.n}
                </div>
            `).join('');
        }
    } catch (error) {
        console.error('Error loading correlation snapshot:', error);
        container.innerHTML = '<p class="error">Failed to load unexpected signals</p>';
    }
}

async function loadOverview() {
    loadCorrelationSnapshot();

    try {
        // Load daily summaries
        const dailyResp = await fetch('/api/daily?days=365');
        const dailyData = await dailyResp.json();

        // Count days with any habit data
        const daysWithData = dailyData.filter(d => d.habits && d.habits.length > 0);

        let filteredDays = daysWithData;
        const eventDays = daysWithData.filter(d => d.habits.some(h => Number(h.value) !== 0));

        document.getElementById('total-days').textContent = filteredDays.length;
        document.getElementById('fog-days').textContent = eventDays.length;

        const fogPct = filteredDays.length > 0 ? (eventDays.length / filteredDays.length * 100).toFixed(1) : 0;
        document.getElementById('fog-pct').textContent = fogPct + '%';

        // Calculate current streak of days without any non-zero habit event.
        let streak = 0;
        for (let i = filteredDays.length - 1; i >= 0; i--) {
            const hasEvent = filteredDays[i].habits.some(h => Number(h.value) !== 0);
            if (!hasEvent) {
                streak++;
            } else {
                break;
            }
        }
        document.getElementById('clear-streak').textContent = streak + ' days';

    } catch (error) {
        console.error('Error loading overview:', error);
    }

}

// Load on page load
document.addEventListener('DOMContentLoaded', () => {
    loadOverview();
});
