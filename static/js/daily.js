// Daily view page JavaScript

let dailyData = [];

async function loadCalendar() {
    try {
        const resp = await fetch('/api/daily?days=90');
        dailyData = await resp.json();

        const container = document.getElementById('calendar-heatmap');

        if (dailyData.length === 0) {
            container.innerHTML = '<p>No data available yet.</p>';
            return;
        }

        // Create calendar grid
        container.innerHTML = dailyData.map(day => {
            const hasFogData = day.pm_slump !== null;
            const isFog = day.pm_slump === true;

            let bgColor = '#e5e7eb'; // grey - no data
            if (hasFogData) {
                bgColor = isFog ? '#fee' : '#efe'; // red or green
            }

            const sleepScore = day.sleep_score || '';

            return `
                <div
                    onclick="showDayDetail('${day.date}')"
                    style="
                        background-color: ${bgColor};
                        border: 1px solid var(--border-color);
                        padding: 0.5rem;
                        cursor: pointer;
                        text-align: center;
                        border-radius: 4px;
                        font-size: 0.75rem;
                    "
                    title="${day.date}"
                >
                    ${new Date(day.date).getDate()}<br>
                    ${sleepScore ? `<small>${sleepScore}</small>` : ''}
                </div>
            `;
        }).reverse().join('');

    } catch (error) {
        console.error('Error loading calendar:', error);
        document.getElementById('calendar-heatmap').innerHTML = '<p class="error">Failed to load calendar</p>';
    }
}

function showDayDetail(dateStr) {
    const day = dailyData.find(d => d.date === dateStr);
    if (!day) return;

    const container = document.getElementById('day-detail-content');
    const detailDiv = document.getElementById('day-detail');

    detailDiv.style.display = 'block';

    // Create a readable summary
    const fields = Object.entries(day)
        .filter(([key, value]) => value !== null && key !== 'date')
        .map(([key, value]) => {
            const label = key.replace(/_/g, ' ');
            let displayValue = value;

            if (typeof value === 'boolean') {
                displayValue = value ? 'Yes' : 'No';
            } else if (typeof value === 'number') {
                displayValue = value.toFixed(2);
            }

            return `<p><strong>${label}:</strong> ${displayValue}</p>`;
        });

    container.innerHTML = `
        <h3>${dateStr}</h3>
        <div style="columns: 2; column-gap: 2rem;">
            ${fields.join('')}
        </div>
    `;

    // Scroll to detail
    detailDiv.scrollIntoView({ behavior: 'smooth' });
}

// Load on page load
document.addEventListener('DOMContentLoaded', loadCalendar);
