// Correlations page JavaScript

async function loadCorrelations() {
    try {
        const resp = await fetch('/api/correlations');
        const correlations = await resp.json();

        if (correlations.length === 0) {
            document.getElementById('correlation-table').innerHTML =
                '<p>Insufficient data for correlations. Need at least 7 days with PM slump tracking.</p>';
            return;
        }

        // Create bar chart (top 15 correlations)
        const top15 = correlations.slice(0, 15);
        const ctx = document.getElementById('correlation-chart').getContext('2d');

        new Chart(ctx, {
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
        const tableContainer = document.getElementById('correlation-table');
        tableContainer.innerHTML = '<table style="width: 100%; border-collapse: collapse;">' +
            '<thead><tr>' +
            '<th style="text-align: left; padding: 0.5rem;">Metric</th>' +
            '<th style="text-align: right; padding: 0.5rem;">r</th>' +
            '<th style="text-align: right; padding: 0.5rem;">Strength</th>' +
            '<th style="text-align: right; padding: 0.5rem;">Fog Day Avg</th>' +
            '<th style="text-align: right; padding: 0.5rem;">Clear Day Avg</th>' +
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
        document.getElementById('correlation-table').innerHTML = '<p class="error">Failed to load correlations</p>';
    }
}

// Load on page load
document.addEventListener('DOMContentLoaded', loadCorrelations);
