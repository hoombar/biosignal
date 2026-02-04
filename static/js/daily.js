// Daily view page JavaScript - Data-forward redesign

let dailyData = [];
let selectedDate = null;
let selectedIndex = -1;

// ============================================
// UTILITY FUNCTIONS
// ============================================

function formatDate(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-GB', {
        weekday: 'long',
        day: 'numeric',
        month: 'short',
        year: 'numeric'
    });
}

function formatShortDate(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-GB', {
        day: 'numeric',
        month: 'short'
    });
}

function getDayName(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-GB', { weekday: 'short' }).slice(0, 2);
}

function formatHours(hours) {
    if (hours === null || hours === undefined) return '-';
    const h = Math.floor(hours);
    const m = Math.round((hours - h) * 60);
    return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

function formatPct(value) {
    if (value === null || value === undefined) return '-';
    return `${Math.round(value)}%`;
}

function formatNum(value, decimals = 0) {
    if (value === null || value === undefined) return '-';
    return decimals > 0 ? value.toFixed(decimals) : Math.round(value).toLocaleString();
}

function formatBool(value) {
    if (value === null || value === undefined) return '-';
    return value ? 'Yes' : 'No';
}

function getScoreClass(value, lowThresh, highThresh) {
    if (value === null || value === undefined) return '';
    if (value >= highThresh) return 'good';
    if (value >= lowThresh) return 'warning';
    return 'bad';
}

// ============================================
// CALENDAR RENDERING
// ============================================

function renderCalendarCell(day, index) {
    const date = new Date(day.date);
    const dateNum = date.getDate();
    const dayName = getDayName(day.date);

    // Determine habit dot classes
    const pmClass = day.pm_slump === null ? 'empty' :
                    day.pm_slump ? 'pm-slump' : 'pm-clear';

    const coffeeClass = day.coffee_count === null ? 'empty' :
                        day.coffee_count > 0 ? 'coffee' : 'empty';

    const beerClass = day.beer_count === null ? 'empty' :
                      day.beer_count > 0 ? 'beer' : 'empty';

    const healthyClass = day.healthy_lunch === null ? 'empty' :
                         day.healthy_lunch ? 'healthy' : 'empty';

    const carbsClass = day.carb_heavy_lunch === null ? 'empty' :
                       day.carb_heavy_lunch ? 'carbs' : 'empty';

    const hasData = day.sleep_score !== null || day.pm_slump !== null;
    const noDataClass = hasData ? '' : 'no-data';
    const selectedClass = selectedDate === day.date ? 'selected' : '';

    return `
        <div class="calendar-cell ${noDataClass} ${selectedClass}"
             onclick="selectDay('${day.date}', ${index})"
             title="${formatShortDate(day.date)}">
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <span class="date-num">${dateNum}</span>
                ${day.sleep_score ? `<span class="sleep-score">${day.sleep_score}</span>` : ''}
            </div>
            <div class="habit-strip">
                <span class="habit-dot ${pmClass}" title="PM Slump"></span>
                <span class="habit-dot ${coffeeClass}" title="Coffee: ${day.coffee_count ?? '-'}"></span>
                <span class="habit-dot ${beerClass}" title="Beer: ${day.beer_count ?? '-'}"></span>
                <span class="habit-dot ${healthyClass}" title="Healthy Lunch"></span>
                <span class="habit-dot ${carbsClass}" title="Carb-heavy"></span>
            </div>
        </div>
    `;
}

async function loadCalendar() {
    try {
        const resp = await fetch('/api/daily?days=90');
        dailyData = await resp.json();

        const container = document.getElementById('calendar-grid');

        if (dailyData.length === 0) {
            container.innerHTML = '<p class="empty-state">No data available yet.</p>';
            return;
        }

        // Reverse to show oldest first, then render
        const sortedData = [...dailyData].reverse();

        // Add empty cells for alignment to start on correct day of week
        const firstDate = new Date(sortedData[0].date);
        // getDay() returns 0 for Sunday, we want Monday = 0
        let startDay = firstDate.getDay() - 1;
        if (startDay < 0) startDay = 6; // Sunday becomes 6

        let html = '';

        // Add empty spacer cells
        for (let i = 0; i < startDay; i++) {
            html += '<div class="calendar-cell no-data" style="visibility: hidden;"></div>';
        }

        // Render each day
        sortedData.forEach((day, index) => {
            // Find actual index in original dailyData (which is newest first)
            const actualIndex = dailyData.length - 1 - index;
            html += renderCalendarCell(day, actualIndex);
        });

        container.innerHTML = html;

        // Auto-select the most recent day with data
        const recentWithData = dailyData.find(d =>
            d.sleep_score !== null || d.pm_slump !== null
        );
        if (recentWithData) {
            const idx = dailyData.indexOf(recentWithData);
            selectDay(recentWithData.date, idx);
        }

    } catch (error) {
        console.error('Error loading calendar:', error);
        document.getElementById('calendar-grid').innerHTML =
            '<p class="error">Failed to load calendar data</p>';
    }
}

// ============================================
// DAY SELECTION & NAVIGATION
// ============================================

function selectDay(dateStr, index) {
    selectedDate = dateStr;
    selectedIndex = index;

    // Update calendar selection
    document.querySelectorAll('.calendar-cell').forEach(cell => {
        cell.classList.remove('selected');
    });

    // Find and select the clicked cell
    const cells = document.querySelectorAll('.calendar-cell');
    // Convert index from dailyData (newest first) to display order (oldest first)
    const displayIndex = dailyData.length - 1 - index;
    // Account for spacer cells
    const firstDate = new Date([...dailyData].reverse()[0].date);
    let startDay = firstDate.getDay() - 1;
    if (startDay < 0) startDay = 6;
    const cellIndex = displayIndex + startDay;

    if (cells[cellIndex]) {
        cells[cellIndex].classList.add('selected');
    }

    // Show detail section
    const detailSection = document.getElementById('detail-section');
    detailSection.classList.add('visible');

    // Render detail
    renderDayDetail(dailyData[index]);
}

function navigateDay(direction) {
    const newIndex = selectedIndex - direction; // subtract because dailyData is newest-first
    if (newIndex >= 0 && newIndex < dailyData.length) {
        selectDay(dailyData[newIndex].date, newIndex);
    }
}

// Keyboard navigation
document.addEventListener('keydown', (e) => {
    if (selectedIndex === -1) return;

    if (e.key === 'ArrowLeft') {
        navigateDay(-1);
        e.preventDefault();
    } else if (e.key === 'ArrowRight') {
        navigateDay(1);
        e.preventDefault();
    }
});

// ============================================
// DAY DETAIL RENDERING
// ============================================

function renderHabitsBanner(day) {
    const pmStatus = day.pm_slump === null ? '' :
                     day.pm_slump ? 'slump' : 'clear';
    const pmText = day.pm_slump === null ? '-' :
                   day.pm_slump ? 'Slump' : 'Clear';

    return `
        <div class="habit-item ${pmStatus}">
            <span class="habit-indicator"></span>
            <span class="habit-label">PM Slump</span>
            <span class="habit-value">${pmText}</span>
        </div>
        <div class="habit-item">
            <span class="habit-icon">&#9749;</span>
            <span class="habit-label">Coffee</span>
            <span class="habit-value">${day.coffee_count ?? '-'}</span>
        </div>
        <div class="habit-item">
            <span class="habit-icon">&#127866;</span>
            <span class="habit-label">Beer</span>
            <span class="habit-value">${day.beer_count ?? '-'}</span>
        </div>
        <div class="habit-item">
            <span class="habit-icon">&#129367;</span>
            <span class="habit-label">Healthy Lunch</span>
            <span class="habit-value">${formatBool(day.healthy_lunch)}</span>
        </div>
        <div class="habit-item">
            <span class="habit-icon">&#127837;</span>
            <span class="habit-label">Carb-heavy</span>
            <span class="habit-value">${formatBool(day.carb_heavy_lunch)}</span>
        </div>
    `;
}

function renderSleepCard(day) {
    const scoreClass = getScoreClass(day.sleep_score, 60, 75);

    return `
        <div class="metric-card">
            <div class="card-header sleep">
                <span class="card-icon">&#9790;</span>
                <span class="card-title">Sleep</span>
            </div>
            <div class="primary-metric">
                <span class="metric-value ${scoreClass}">${day.sleep_score ?? '-'}</span>
                <span class="metric-unit">score</span>
            </div>
            <div class="secondary-metrics">
                <div class="metric-row">
                    <span class="metric-label">Duration</span>
                    <span class="metric-value">${formatHours(day.sleep_hours)}</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Deep Sleep</span>
                    <span class="metric-value">${formatPct(day.deep_sleep_pct)}</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">REM Sleep</span>
                    <span class="metric-value">${formatPct(day.rem_sleep_pct)}</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Efficiency</span>
                    <span class="metric-value">${formatPct(day.sleep_efficiency)}</span>
                </div>
            </div>
        </div>
    `;
}

function renderHrvCard(day) {
    const hrvClass = getScoreClass(day.hrv_overnight_avg, 30, 50);

    return `
        <div class="metric-card">
            <div class="card-header hrv">
                <span class="card-icon">&#10084;</span>
                <span class="card-title">HRV</span>
            </div>
            <div class="primary-metric">
                <span class="metric-value ${hrvClass}">${formatNum(day.hrv_overnight_avg, 0)}</span>
                <span class="metric-unit">ms avg</span>
            </div>
            <div class="secondary-metrics">
                <div class="metric-row">
                    <span class="metric-label">Minimum</span>
                    <span class="metric-value">${formatNum(day.hrv_overnight_min, 0)} ms</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Slope</span>
                    <span class="metric-value">${day.hrv_rmssd_slope !== null ? (day.hrv_rmssd_slope > 0 ? '+' : '') + day.hrv_rmssd_slope.toFixed(2) : '-'}</span>
                </div>
            </div>
        </div>
    `;
}

function renderHeartRateCard(day) {
    return `
        <div class="metric-card">
            <div class="card-header heart">
                <span class="card-icon">&#9829;</span>
                <span class="card-title">Heart Rate</span>
            </div>
            <div class="primary-metric">
                <span class="metric-value">${formatNum(day.resting_hr)}</span>
                <span class="metric-unit">bpm resting</span>
            </div>
            <div class="secondary-metrics">
                <div class="metric-row">
                    <span class="metric-label">Morning Avg</span>
                    <span class="metric-value">${formatNum(day.hr_morning_avg, 0)} bpm</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Afternoon Avg</span>
                    <span class="metric-value">${formatNum(day.hr_afternoon_avg, 0)} bpm</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">2pm Window</span>
                    <span class="metric-value">${formatNum(day.hr_2pm_window, 0)} bpm</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Max 24h</span>
                    <span class="metric-value">${formatNum(day.hr_max_24h)} bpm</span>
                </div>
            </div>
        </div>
    `;
}

function renderBodyBatteryCard(day) {
    // Create mini sparkline data from body battery readings
    const bbValues = [day.bb_wakeup, day.bb_9am, day.bb_12pm, day.bb_2pm, day.bb_6pm].filter(v => v !== null);
    const bbLabels = ['Wake', '9am', '12pm', '2pm', '6pm'];

    return `
        <div class="metric-card">
            <div class="card-header battery">
                <span class="card-icon">&#9889;</span>
                <span class="card-title">Body Battery</span>
            </div>
            <div class="primary-metric">
                <span class="metric-value">${formatNum(day.bb_wakeup)}</span>
                <span class="metric-unit">at wake</span>
            </div>
            <div class="secondary-metrics">
                <div class="metric-row">
                    <span class="metric-label">9am</span>
                    <span class="metric-value">${formatNum(day.bb_9am)}</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">12pm</span>
                    <span class="metric-value">${formatNum(day.bb_12pm)}</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">2pm</span>
                    <span class="metric-value">${formatNum(day.bb_2pm)}</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">6pm</span>
                    <span class="metric-value">${formatNum(day.bb_6pm)}</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Daily Min</span>
                    <span class="metric-value">${formatNum(day.bb_daily_min)}</span>
                </div>
            </div>
        </div>
    `;
}

function renderStressCard(day) {
    const stressClass = day.stress_afternoon_avg !== null && day.stress_afternoon_avg > 50 ? 'warning' : '';

    return `
        <div class="metric-card">
            <div class="card-header stress">
                <span class="card-icon">&#128200;</span>
                <span class="card-title">Stress</span>
            </div>
            <div class="primary-metric">
                <span class="metric-value ${stressClass}">${formatNum(day.stress_afternoon_avg, 0)}</span>
                <span class="metric-unit">afternoon avg</span>
            </div>
            <div class="secondary-metrics">
                <div class="metric-row">
                    <span class="metric-label">Morning Avg</span>
                    <span class="metric-value">${formatNum(day.stress_morning_avg, 0)}</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">2pm Window</span>
                    <span class="metric-value">${formatNum(day.stress_2pm_window, 0)}</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Peak</span>
                    <span class="metric-value">${formatNum(day.stress_peak)}</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">High Stress</span>
                    <span class="metric-value">${day.high_stress_minutes ?? '-'} min</span>
                </div>
            </div>
        </div>
    `;
}

function renderActivityCard(day) {
    const trainingBadge = day.had_training ?
        `<span style="background: var(--color-activity); color: var(--bg-primary); padding: 2px 8px; border-radius: 4px; font-size: 0.625rem; font-weight: 600; text-transform: uppercase;">${day.training_type || 'Training'}</span>` : '';

    return `
        <div class="metric-card">
            <div class="card-header activity">
                <span class="card-icon">&#127939;</span>
                <span class="card-title">Activity</span>
                ${trainingBadge}
            </div>
            <div class="primary-metric">
                <span class="metric-value">${formatNum(day.steps_total)}</span>
                <span class="metric-unit">steps</span>
            </div>
            <div class="secondary-metrics">
                <div class="metric-row">
                    <span class="metric-label">Morning Steps</span>
                    <span class="metric-value">${formatNum(day.steps_morning)}</span>
                </div>
                ${day.had_training ? `
                <div class="metric-row">
                    <span class="metric-label">Training Duration</span>
                    <span class="metric-value">${formatNum(day.training_duration_min, 0)} min</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Training Avg HR</span>
                    <span class="metric-value">${formatNum(day.training_avg_hr)} bpm</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Intensity</span>
                    <span class="metric-value">${day.training_intensity || '-'}</span>
                </div>
                ` : `
                <div class="metric-row">
                    <span class="metric-label">Training</span>
                    <span class="metric-value">None</span>
                </div>
                `}
            </div>
        </div>
    `;
}

function renderDayDetail(day) {
    // Update date header
    document.getElementById('detail-date').textContent = formatDate(day.date);

    // Update habits banner
    document.getElementById('habits-banner').innerHTML = renderHabitsBanner(day);

    // Update metrics grid - force re-render for animations
    const metricsGrid = document.getElementById('metrics-grid');
    metricsGrid.innerHTML = '';

    // Small delay to allow CSS animation reset
    requestAnimationFrame(() => {
        metricsGrid.innerHTML = `
            ${renderSleepCard(day)}
            ${renderHrvCard(day)}
            ${renderHeartRateCard(day)}
            ${renderBodyBatteryCard(day)}
            ${renderStressCard(day)}
            ${renderActivityCard(day)}
        `;
    });
}

// ============================================
// INITIALIZATION
// ============================================

document.addEventListener('DOMContentLoaded', loadCalendar);
