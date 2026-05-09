// Overview page JavaScript

const STORAGE_KEY = 'biosignal_target_habit';

async function loadHabitSelector() {
    try {
        const resp = await fetch('/api/habits/names');
        const habitNames = await resp.json();

        const select = document.getElementById('target-habit');
        const savedHabit = localStorage.getItem(STORAGE_KEY);

        select.innerHTML = '<option value="">-- Select a habit --</option>' +
            habitNames.map(name =>
                `<option value="${name}" ${name === savedHabit ? 'selected' : ''}>${name.replace(/_/g, ' ')}</option>`
            ).join('');

        // Load correlations if a habit was previously selected
        if (savedHabit && habitNames.includes(savedHabit)) {
            loadCorrelations();
        }
    } catch (error) {
        console.error('Error loading habit names:', error);
        document.getElementById('target-habit').innerHTML = '<option value="">Failed to load habits</option>';
    }
}

async function loadCorrelations() {
    const select = document.getElementById('target-habit');
    const targetHabit = select.value;
    const container = document.getElementById('top-correlates');

    if (!targetHabit) {
        container.innerHTML = '<p>Select a habit to see correlations</p>';
        return;
    }

    // Save selection
    localStorage.setItem(STORAGE_KEY, targetHabit);

    container.innerHTML = '<p class="loading">Loading correlations...</p>';

    try {
        const corrResp = await fetch(`/api/correlations?target_habit=${encodeURIComponent(targetHabit)}`);
        const correlations = await corrResp.json();

        const top3 = correlations.slice(0, 3);

        if (top3.length === 0) {
            container.innerHTML = '<p>Insufficient data for correlations (need at least 5 days)</p>';
        } else {
            container.innerHTML = top3.map(c => `
                <div style="margin-bottom: 1rem; padding: 1rem; border-left: 3px solid var(--primary-color);">
                    <strong>${c.metric.replace(/_/g, ' ')}</strong><br>
                    Correlation: ${c.coefficient.toFixed(3)} (${c.strength})<br>
                    ${c.fog_day_avg !== null ? `Positive days: ${c.fog_day_avg.toFixed(1)}, Negative days: ${c.clear_day_avg.toFixed(1)}` : ''}
                </div>
            `).join('');
        }
    } catch (error) {
        console.error('Error loading correlations:', error);
        container.innerHTML = '<p class="error">Failed to load correlations</p>';
    }
}

async function loadOverview() {
    // Load habit selector first
    await loadHabitSelector();

    try {
        // Load daily summaries
        const dailyResp = await fetch('/api/daily?days=365');
        const dailyData = await dailyResp.json();

        // Count days with any habit data
        const daysWithData = dailyData.filter(d => d.habits && d.habits.length > 0);

        // Calculate stats based on selected habit
        const targetHabit = document.getElementById('target-habit').value;
        let fogDays = [];
        let filteredDays = daysWithData;

        if (targetHabit) {
            filteredDays = daysWithData.filter(d => {
                const habit = d.habits.find(h => h.name === targetHabit);
                return habit !== undefined;
            });
            fogDays = filteredDays.filter(d => {
                const habit = d.habits.find(h => h.name === targetHabit);
                return habit && habit.value === 1;
            });
        }

        document.getElementById('total-days').textContent = filteredDays.length;
        document.getElementById('fog-days').textContent = fogDays.length;

        const fogPct = filteredDays.length > 0 ? (fogDays.length / filteredDays.length * 100).toFixed(1) : 0;
        document.getElementById('fog-pct').textContent = fogPct + '%';

        // Calculate current streak of negative (clear) days
        let streak = 0;
        if (targetHabit) {
            for (let i = filteredDays.length - 1; i >= 0; i--) {
                const habit = filteredDays[i].habits.find(h => h.name === targetHabit);
                if (habit && habit.value === 0) {
                    streak++;
                } else {
                    break;
                }
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
