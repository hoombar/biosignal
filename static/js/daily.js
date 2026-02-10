// Daily view page JavaScript - Data-forward redesign

let dailyData = [];
let selectedDate = null;
let selectedIndex = -1;

// ============================================
// UTILITY FUNCTIONS
// ============================================

function parseLocalDate(dateStr) {
    const [year, month, day] = dateStr.split('-').map(Number);
    return new Date(year, month - 1, day);
}

function formatDate(dateStr) {
    const date = parseLocalDate(dateStr);
    return date.toLocaleDateString('en-GB', {
        weekday: 'long',
        day: 'numeric',
        month: 'short',
        year: 'numeric'
    });
}

function formatShortDate(dateStr) {
    const date = parseLocalDate(dateStr);
    return date.toLocaleDateString('en-GB', {
        day: 'numeric',
        month: 'short'
    });
}

function getDayName(dateStr) {
    const date = parseLocalDate(dateStr);
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

function formatHabitName(name) {
    // Convert snake_case to Title Case
    return name.split('_').map(word =>
        word.charAt(0).toUpperCase() + word.slice(1)
    ).join(' ');
}

function getHabitValue(habits, name) {
    if (!habits) return null;
    const habit = habits.find(h => h.name === name);
    return habit ? habit.value : null;
}

function renderCalendarCell(day, index) {
    const date = parseLocalDate(day.date);
    const dateNum = date.getDate();
    const dayName = getDayName(day.date);

    // Check for key habits for the calendar dot display
    const pmSlump = getHabitValue(day.habits, 'afternoon_slump');
    const coffee = getHabitValue(day.habits, 'coffee');
    const beer = getHabitValue(day.habits, 'beer');

    const pmClass = pmSlump === null ? 'empty' :
                    pmSlump > 0 ? 'pm-slump' : 'pm-clear';

    const coffeeClass = coffee === null ? 'empty' :
                        coffee > 0 ? 'coffee' : 'empty';

    const beerClass = beer === null ? 'empty' :
                      beer > 0 ? 'beer' : 'empty';

    const hasData = day.sleep_score !== null || (day.habits && day.habits.length > 0);
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
                <span class="habit-dot ${pmClass}" title="PM Slump: ${pmSlump ?? '-'}"></span>
                <span class="habit-dot ${coffeeClass}" title="Coffee: ${coffee ?? '-'}"></span>
                <span class="habit-dot ${beerClass}" title="Beer: ${beer ?? '-'}"></span>
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

        // dailyData is already oldest-first from API, use directly
        const sortedData = dailyData;

        // Add empty cells for alignment to start on correct day of week
        const firstDate = parseLocalDate(sortedData[0].date);
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
            html += renderCalendarCell(day, index);
        });

        container.innerHTML = html;

        // Auto-select the most recent day with data (search from end since oldest-first)
        const recentWithData = [...dailyData].reverse().find(d =>
            d.sleep_score !== null || (d.habits && d.habits.length > 0)
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
    // Account for spacer cells at the start
    const firstDate = parseLocalDate(dailyData[0].date);
    let startDay = firstDate.getDay() - 1;
    if (startDay < 0) startDay = 6;
    const cellIndex = index + startDay;

    if (cells[cellIndex]) {
        cells[cellIndex].classList.add('selected');
    }

    // Show detail section
    const detailSection = document.getElementById('detail-section');
    if (detailSection) detailSection.classList.add('visible');

    // Render detail
    renderDayDetail(dailyData[index]);
}

function navigateDay(direction) {
    const newIndex = selectedIndex + direction; // add because dailyData is oldest-first
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
    if (!day.habits || day.habits.length === 0) {
        return '<div class="habit-item"><span class="habit-label">No habits tracked</span></div>';
    }

    return day.habits.map(habit => {
        // Special styling for afternoon_slump (outcome metric)
        if (habit.name === 'afternoon_slump') {
            const status = habit.value > 0 ? 'slump' : 'clear';
            const text = habit.value > 0 ? 'Slump' : 'Clear';
            return `
                <div class="habit-item ${status}">
                    <span class="habit-indicator"></span>
                    <span class="habit-label">PM Slump</span>
                    <span class="habit-value">${text}</span>
                </div>
            `;
        }

        // Regular habits
        return `
            <div class="habit-item">
                <span class="habit-label">${formatHabitName(habit.name)}</span>
                <span class="habit-value">${habit.value}</span>
            </div>
        `;
    }).join('');
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
    if (!day) return;

    // Update date header
    const detailDate = document.getElementById('detail-date');
    if (detailDate) detailDate.textContent = formatDate(day.date);

    // Update habits banner
    const habitsBanner = document.getElementById('habits-banner');
    if (habitsBanner) habitsBanner.innerHTML = renderHabitsBanner(day);

    // Update metrics grid - force re-render for animations
    const metricsGrid = document.getElementById('metrics-grid');
    if (!metricsGrid) return;
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
