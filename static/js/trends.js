// Trends page JavaScript

let trendsData = [];
let chart = null;

async function loadTrends() {
    try {
        const resp = await fetch('/api/daily?days=90');
        trendsData = await resp.json();

        updateChart();

    } catch (error) {
        console.error('Error loading trends:', error);
    }
}

function calculateRollingAverage(data, windowSize = 7) {
    const result = [];
    for (let i = 0; i < data.length; i++) {
        const start = Math.max(0, i - windowSize + 1);
        const window = data.slice(start, i + 1);
        const validValues = window.filter(v => v !== null && v !== undefined);
        const avg = validValues.length > 0 ?
            validValues.reduce((a, b) => a + b, 0) / validValues.length : null;
        result.push(avg);
    }
    return result;
}

function updateChart() {
    const showFog = document.getElementById('check-fog').checked;
    const showSleep = document.getElementById('check-sleep').checked;
    const showHrv = document.getElementById('check-hrv').checked;
    const showSpo2 = document.getElementById('check-spo2').checked;
    const showBb = document.getElementById('check-bb').checked;

    const labels = trendsData.map(d => d.date);
    const datasets = [];

    if (showFog) {
        const fogValues = trendsData.map(d => {
            const h = d.habits?.find(h => h.name === 'pm_slump');
            return h != null ? (h.value === 1 || h.value === true ? 1 : 0) : null;
        });
        const fogRolling = calculateRollingAverage(fogValues);

        datasets.push({
            label: 'PM Slump (7-day avg)',
            data: fogRolling,
            borderColor: 'rgb(220, 38, 38)',
            backgroundColor: 'rgba(220, 38, 38, 0.1)',
            yAxisID: 'y-score',
        });
    }

    if (showSleep) {
        datasets.push({
            label: 'Sleep Score',
            data: trendsData.map(d => d.sleep_score),
            borderColor: 'rgb(37, 99, 235)',
            backgroundColor: 'rgba(37, 99, 235, 0.1)',
            yAxisID: 'y-score',
        });
    }

    if (showHrv) {
        datasets.push({
            label: 'HRV Overnight Avg',
            data: trendsData.map(d => d.hrv_overnight_avg),
            borderColor: 'rgb(22, 163, 74)',
            backgroundColor: 'rgba(22, 163, 74, 0.1)',
            yAxisID: 'y-hrv',
        });
    }

    if (showSpo2) {
        datasets.push({
            label: 'SpO2 Overnight Avg',
            data: trendsData.map(d => d.spo2_overnight_avg),
            borderColor: 'rgb(56, 189, 248)',
            backgroundColor: 'rgba(56, 189, 248, 0.1)',
            yAxisID: 'y-spo2',
        });
    }

    if (showBb) {
        datasets.push({
            label: 'Body Battery (daily min)',
            data: trendsData.map(d => d.bb_daily_min),
            borderColor: 'rgb(234, 88, 12)',
            backgroundColor: 'rgba(234, 88, 12, 0.1)',
            yAxisID: 'y-score',
        });
    }

    if (chart) {
        chart.destroy();
    }

    const ctx = document.getElementById('trends-chart').getContext('2d');
    chart = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            scales: {
                'y-score': {
                    type: 'linear',
                    display: showFog || showSleep || showBb,
                    position: 'left',
                    min: 0,
                    max: 100,
                    title: { display: true, text: 'Score (0-100)' }
                },
                'y-hrv': {
                    type: 'linear',
                    display: showHrv,
                    position: 'right',
                    grid: { drawOnChartArea: false },
                    title: { display: true, text: 'HRV (ms)' }
                },
                'y-spo2': {
                    type: 'linear',
                    display: showSpo2,
                    position: 'right',
                    min: 85,
                    max: 100,
                    grid: { drawOnChartArea: false },
                    title: { display: true, text: 'SpO2 (%)' }
                }
            }
        }
    });
}

// Load on page load
document.addEventListener('DOMContentLoaded', loadTrends);
