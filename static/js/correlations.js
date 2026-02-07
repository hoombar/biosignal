// Correlations page JavaScript

const STORAGE_KEY = 'biosignal_target_habit';
let correlationChart = null;

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
    const tableContainer = document.getElementById('correlation-table');

    if (!targetHabit) {
        tableContainer.innerHTML = '<p>Select a habit to see correlations</p>';
        return;
    }

    // Save selection
    localStorage.setItem(STORAGE_KEY, targetHabit);

    tableContainer.innerHTML = '<p class="loading">Loading correlations...</p>';

    try {
        const resp = await fetch(`/api/correlations?target_habit=${encodeURIComponent(targetHabit)}`);
        const correlations = await resp.json();

        if (correlations.length === 0) {
            tableContainer.innerHTML =
                '<p>Insufficient data for correlations. Need at least 5 days with this habit tracked.</p>';
            return;
        }

        // Destroy existing chart if any
        if (correlationChart) {
            correlationChart.destroy();
        }

        // Create bar chart (top 15 correlations)
        const top15 = correlations.slice(0, 15);
        const ctx = document.getElementById('correlation-chart').getContext('2d');

        correlationChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: top15.map(c => c.metric.replace(/_/g, ' ')),
                datasets: [{
                    label: 'Correlation Coefficient',
                    data: top15.map(c => c.coefficient),
                    backgroundColor: top15.map(c =>
                        c.coefficient > 0 ? 'rgba(54, 162, 235, 0.5)' : 'rgba(255, 159, 64, 0.5)'
                    ),
                    borderColor: top15.map(c =>
                        c.coefficient > 0 ? 'rgba(54, 162, 235, 1)' : 'rgba(255, 159, 64, 1)'
                    ),
                    borderWidth: 1
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        beginAtZero: true,
                        min: -1,
                        max: 1
                    }
                }
            }
        });

        // Create table
        tableContainer.innerHTML = '<table style="width: 100%; border-collapse: collapse;">' +
            '<thead><tr>' +
            '<th style="text-align: left; padding: 0.5rem;">Metric</th>' +
            '<th style="text-align: right; padding: 0.5rem;">r</th>' +
            '<th style="text-align: right; padding: 0.5rem;">Strength</th>' +
            '<th style="text-align: right; padding: 0.5rem;">Positive Avg</th>' +
            '<th style="text-align: right; padding: 0.5rem;">Negative Avg</th>' +
            '<th style="text-align: right; padding: 0.5rem;">Difference</th>' +
            '<th style="text-align: right; padding: 0.5rem;">n</th>' +
            '</tr></thead><tbody>' +
            correlations.map(c => `
                <tr style="border-top: 1px solid var(--border-color);">
                    <td style="padding: 0.5rem;">${c.metric.replace(/_/g, ' ')}</td>
                    <td style="text-align: right; padding: 0.5rem; font-weight: bold;">${c.coefficient.toFixed(3)}</td>
                    <td style="text-align: right; padding: 0.5rem;">${c.strength}</td>
                    <td style="text-align: right; padding: 0.5rem;">${c.fog_day_avg !== null ? c.fog_day_avg.toFixed(1) : '-'}</td>
                    <td style="text-align: right; padding: 0.5rem;">${c.clear_day_avg !== null ? c.clear_day_avg.toFixed(1) : '-'}</td>
                    <td style="text-align: right; padding: 0.5rem;">${c.difference_pct !== null ? c.difference_pct.toFixed(1) + '%' : '-'}</td>
                    <td style="text-align: right; padding: 0.5rem;">${c.n}</td>
                </tr>
            `).join('') +
            '</tbody></table>';

    } catch (error) {
        console.error('Error loading correlations:', error);
        tableContainer.innerHTML = '<p class="error">Failed to load correlations</p>';
    }
}

// Load on page load
document.addEventListener('DOMContentLoaded', loadHabitSelector);
