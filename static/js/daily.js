// Daily view page JavaScript - Month-based navigation with year heatmap

// ============================================
// STATE
// ============================================

let monthCache = {};       // { "2026-02": [DailySummary, ...], ... }
let calendarCache = {};    // { 2026: [CalendarDaySummary, ...], ... }
let currentYear = new Date().getFullYear();
let currentMonth = new Date().getMonth() + 1; // 1-indexed
let selectedDate = null;
let selectedIndex = -1;
let currentMonthData = [];  // data for the displayed month

const MONTH_NAMES = [
    '', 'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
];

const MONTH_SHORT = [
    '', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
];

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

function monthKey(year, month) {
    return `${year}-${String(month).padStart(2, '0')}`;
}

function daysInMonth(year, month) {
    return new Date(year, month, 0).getDate();
}

// ============================================
// DATA LOADING
// ============================================

async function fetchMonth(year, month) {
    const key = monthKey(year, month);
    if (monthCache[key]) return monthCache[key];

    const days = daysInMonth(year, month);
    const start = `${year}-${String(month).padStart(2, '0')}-01`;
    const end = `${year}-${String(month).padStart(2, '0')}-${String(days).padStart(2, '0')}`;

    const resp = await fetch(`/api/daily?start=${start}&end=${end}`);
    const data = await resp.json();
    monthCache[key] = data;

    // Evict old cache entries if > 6 months cached
    const keys = Object.keys(monthCache);
    if (keys.length > 6) {
        delete monthCache[keys[0]];
    }

    return data;
}

async function fetchCalendarYear(year) {
    if (calendarCache[year]) return calendarCache[year];

    const resp = await fetch(`/api/daily/calendar?year=${year}`);
    const data = await resp.json();
    calendarCache[year] = data;
    return data;
}

async function fetchNotableDays(year, month) {
    const resp = await fetch(`/api/daily/notable?year=${year}&month=${month}`);
    return await resp.json();
}

function prefetchAdjacentMonth(year, month, direction) {
    let targetMonth = month + direction;
    let targetYear = year;
    if (targetMonth < 1) { targetMonth = 12; targetYear--; }
    if (targetMonth > 12) { targetMonth = 1; targetYear++; }

    const key = monthKey(targetYear, targetMonth);
    if (!monthCache[key]) {
        // Fire and forget
        fetchMonth(targetYear, targetMonth);
    }
}

// ============================================
// CALENDAR RENDERING
// ============================================

function formatHabitName(name) {
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

async function renderMonth(year, month) {
    currentYear = year;
    currentMonth = month;

    // Update header
    document.getElementById('month-label').textContent =
        `${MONTH_NAMES[month]} ${year}`;

    const container = document.getElementById('calendar-grid');
    container.innerHTML = '<p class="loading">Loading...</p>';

    try {
        const data = await fetchMonth(year, month);
        currentMonthData = data;

        if (data.length === 0) {
            container.innerHTML = '<p class="empty-state">No data available.</p>';
            renderNotableDays([]);
            return;
        }

        // Add empty cells for alignment to start on correct day of week
        const firstDate = parseLocalDate(data[0].date);
        let startDay = firstDate.getDay() - 1;
        if (startDay < 0) startDay = 6;

        let html = '';
        for (let i = 0; i < startDay; i++) {
            html += '<div class="calendar-cell no-data" style="visibility: hidden;"></div>';
        }

        data.forEach((day, index) => {
            html += renderCalendarCell(day, index);
        });

        container.innerHTML = html;

        // If selected date is in this month, re-select it
        if (selectedDate) {
            const idx = data.findIndex(d => d.date === selectedDate);
            if (idx >= 0) {
                selectDay(selectedDate, idx);
            }
        }

        // Prefetch adjacent month
        prefetchAdjacentMonth(year, month, -1);
        prefetchAdjacentMonth(year, month, 1);

        // Load notable days
        const notable = await fetchNotableDays(year, month);
        renderNotableDays(notable);

    } catch (error) {
        console.error('Error loading month:', error);
        container.innerHTML = '<p class="error">Failed to load calendar data</p>';
    }
}

// ============================================
// YEAR HEATMAP
// ============================================

function getHeatmapColor(sleepScore) {
    if (sleepScore === null || sleepScore === undefined) return 'var(--bg-tertiary)';
    if (sleepScore >= 80) return 'var(--color-positive)';
    if (sleepScore >= 65) return '#4ea85c';
    if (sleepScore >= 50) return 'var(--color-warning)';
    return 'var(--color-negative)';
}

async function renderYearHeatmap(year) {
    document.getElementById('year-label').textContent = year;

    const container = document.getElementById('year-heatmap');
    container.innerHTML = '<p class="loading">Loading...</p>';

    try {
        const data = await fetchCalendarYear(year);

        // Group by week (ISO weeks, starting Monday)
        let html = '<div class="heatmap-grid">';

        data.forEach(day => {
            const d = parseLocalDate(day.date);
            const dayMonth = d.getMonth() + 1;
            const isCurrentMonth = (dayMonth === currentMonth && d.getFullYear() === currentYear);
            const currentMonthClass = isCurrentMonth ? 'current-month' : '';

            html += `<div class="heatmap-cell ${currentMonthClass}"
                          style="background: ${getHeatmapColor(day.sleep_score)}"
                          title="${formatShortDate(day.date)}: ${day.sleep_score ?? 'No data'}${day.has_slump ? ' (Slump)' : ''}"
                          onclick="jumpToDate('${day.date}')"></div>`;
        });

        html += '</div>';
        container.innerHTML = html;

        // Render month tabs
        renderMonthTabs(year);

    } catch (error) {
        console.error('Error loading year heatmap:', error);
        container.innerHTML = '<p class="error">Failed to load year data</p>';
    }
}

function renderMonthTabs(year) {
    const container = document.getElementById('month-tabs');
    let html = '';

    for (let m = 1; m <= 12; m++) {
        const activeClass = (m === currentMonth && year === currentYear) ? 'active' : '';
        html += `<button class="month-tab ${activeClass}"
                         onclick="jumpToMonth(${year}, ${m})">${MONTH_SHORT[m]}</button>`;
    }

    container.innerHTML = html;
}

// ============================================
// NOTABLE DAYS
// ============================================

function renderNotableDays(notable) {
    const container = document.getElementById('notable-days');

    if (!notable || notable.length === 0) {
        container.innerHTML = '';
        return;
    }

    let html = '<h3>Notable Days</h3><ul class="notable-list">';

    notable.forEach(item => {
        const d = parseLocalDate(item.date);
        const dayNum = d.getDate();
        const monthShort = MONTH_SHORT[d.getMonth() + 1];

        html += `<li class="notable-item" onclick="jumpToDate('${item.date}')">
            <span class="notable-date">${dayNum} ${monthShort}</span>
            <span class="notable-desc">${item.description}</span>
        </li>`;
    });

    html += '</ul>';
    container.innerHTML = html;
}

// ============================================
// NAVIGATION
// ============================================

function navigateMonth(direction) {
    let newMonth = currentMonth + direction;
    let newYear = currentYear;

    if (newMonth < 1) { newMonth = 12; newYear--; }
    if (newMonth > 12) { newMonth = 1; newYear++; }

    renderMonth(newYear, newMonth);

    // Update heatmap current-month highlight
    if (newYear !== currentYear) {
        renderYearHeatmap(newYear);
    } else {
        updateHeatmapHighlight();
        renderMonthTabs(newYear);
    }
}

function navigateYear(direction) {
    const newYear = currentYear + direction;
    // Don't navigate beyond current year
    if (newYear > new Date().getFullYear()) return;
    if (newYear < 2020) return;

    currentYear = newYear;
    renderYearHeatmap(newYear);
    renderMonth(newYear, currentMonth);
}

function jumpToMonth(year, month) {
    if (year !== currentYear) {
        currentYear = year;
        renderYearHeatmap(year);
    }
    currentMonth = month;
    renderMonth(year, month);
    updateHeatmapHighlight();
    renderMonthTabs(year);
}

function jumpToDate(dateStr) {
    const d = parseLocalDate(dateStr);
    const year = d.getFullYear();
    const month = d.getMonth() + 1;

    selectedDate = dateStr;
    updateHash(dateStr);

    if (year !== currentYear) {
        currentYear = year;
        renderYearHeatmap(year);
    }

    if (month !== currentMonth || year !== currentYear) {
        currentMonth = month;
        renderMonth(year, month).then(() => {
            const idx = currentMonthData.findIndex(d => d.date === dateStr);
            if (idx >= 0) selectDay(dateStr, idx);
        });
        updateHeatmapHighlight();
        renderMonthTabs(year);
    } else {
        const idx = currentMonthData.findIndex(d => d.date === dateStr);
        if (idx >= 0) selectDay(dateStr, idx);
    }
}

function updateHeatmapHighlight() {
    document.querySelectorAll('.heatmap-cell').forEach(cell => {
        cell.classList.remove('current-month');
    });

    // Re-apply highlight based on current month data
    const calData = calendarCache[currentYear];
    if (!calData) return;

    const cells = document.querySelectorAll('.heatmap-cell');
    calData.forEach((day, i) => {
        const d = parseLocalDate(day.date);
        if (d.getMonth() + 1 === currentMonth && cells[i]) {
            cells[i].classList.add('current-month');
        }
    });
}

// ============================================
// DAY SELECTION & NAVIGATION
// ============================================

function selectDay(dateStr, index) {
    selectedDate = dateStr;
    selectedIndex = index;
    updateHash(dateStr);

    // Update calendar selection
    document.querySelectorAll('.calendar-cell').forEach(cell => {
        cell.classList.remove('selected');
    });

    const cells = document.querySelectorAll('.calendar-cell');
    const firstDate = parseLocalDate(currentMonthData[0].date);
    let startDay = firstDate.getDay() - 1;
    if (startDay < 0) startDay = 6;
    const cellIndex = index + startDay;

    if (cells[cellIndex]) {
        cells[cellIndex].classList.add('selected');
    }

    // Show detail section
    const detailSection = document.getElementById('detail-section');
    if (detailSection) detailSection.classList.add('visible');

    renderDayDetail(currentMonthData[index]);
}

function navigateDay(direction) {
    const newIndex = selectedIndex + direction;

    if (newIndex >= 0 && newIndex < currentMonthData.length) {
        selectDay(currentMonthData[newIndex].date, newIndex);
    } else if (newIndex < 0) {
        // Go to previous month's last day
        navigateMonth(-1);
        // After month loads, select last day
        setTimeout(() => {
            if (currentMonthData.length > 0) {
                const lastIdx = currentMonthData.length - 1;
                selectDay(currentMonthData[lastIdx].date, lastIdx);
            }
        }, 200);
    } else {
        // Go to next month's first day
        navigateMonth(1);
        setTimeout(() => {
            if (currentMonthData.length > 0) {
                selectDay(currentMonthData[0].date, 0);
            }
        }, 200);
    }
}

// Keyboard navigation
document.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft') {
        if (selectedIndex !== -1) {
            navigateDay(-1);
            e.preventDefault();
        }
    } else if (e.key === 'ArrowRight') {
        if (selectedIndex !== -1) {
            navigateDay(1);
            e.preventDefault();
        }
    } else if (e.key === 'PageUp') {
        navigateMonth(-1);
        e.preventDefault();
    } else if (e.key === 'PageDown') {
        navigateMonth(1);
        e.preventDefault();
    }
});

// ============================================
// URL HASH STATE
// ============================================

function updateHash(dateStr) {
    if (window.location.hash !== '#' + dateStr) {
        history.pushState(null, '', '#' + dateStr);
    }
}

function readHash() {
    const hash = window.location.hash.slice(1);
    if (/^\d{4}-\d{2}-\d{2}$/.test(hash)) {
        return hash;
    }
    return null;
}

window.addEventListener('popstate', () => {
    const dateStr = readHash();
    if (dateStr) {
        jumpToDate(dateStr);
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

function renderSpo2Card(day) {
    const spo2Class = getScoreClass(day.spo2_overnight_avg, 92, 95);
    const hasDips = day.spo2_dips_below_94 !== null && day.spo2_dips_below_94 > 0;
    const dipsClass = hasDips ? 'warning' : '';

    return `
        <div class="metric-card">
            <div class="card-header spo2">
                <span class="card-icon">&#128168;</span>
                <span class="card-title">Blood Oxygen</span>
            </div>
            <div class="primary-metric">
                <span class="metric-value ${spo2Class}">${formatNum(day.spo2_overnight_avg, 1)}</span>
                <span class="metric-unit">% avg</span>
            </div>
            <div class="secondary-metrics">
                <div class="metric-row">
                    <span class="metric-label">Minimum</span>
                    <span class="metric-value">${formatNum(day.spo2_overnight_min)}%</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Maximum</span>
                    <span class="metric-value">${formatNum(day.spo2_overnight_max)}%</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Dips &lt;94%</span>
                    <span class="metric-value ${dipsClass}">${day.spo2_dips_below_94 ?? '-'}</span>
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
    const samples = day.bb_samples || [];

    const sampleRows = samples.map(s => `
                <div class="metric-row">
                    <span class="metric-label">${s.time}</span>
                    <span class="metric-value">${s.value}</span>
                </div>
    `).join('');

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
                ${sampleRows}
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

    const detailDate = document.getElementById('detail-date');
    if (detailDate) detailDate.textContent = formatDate(day.date);

    const habitsBanner = document.getElementById('habits-banner');
    if (habitsBanner) habitsBanner.innerHTML = renderHabitsBanner(day);

    const metricsGrid = document.getElementById('metrics-grid');
    if (!metricsGrid) return;
    metricsGrid.innerHTML = '';

    requestAnimationFrame(() => {
        metricsGrid.innerHTML = `
            ${renderSleepCard(day)}
            ${renderHrvCard(day)}
            ${renderSpo2Card(day)}
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

async function init() {
    // Check URL hash for a specific date
    const hashDate = readHash();

    if (hashDate) {
        const d = parseLocalDate(hashDate);
        currentYear = d.getFullYear();
        currentMonth = d.getMonth() + 1;
        selectedDate = hashDate;
    }

    // Load year heatmap and month in parallel
    await Promise.all([
        renderYearHeatmap(currentYear),
        renderMonth(currentYear, currentMonth),
    ]);

    // Auto-select: hash date, or most recent day with data
    if (hashDate) {
        const idx = currentMonthData.findIndex(d => d.date === hashDate);
        if (idx >= 0) selectDay(hashDate, idx);
    } else if (currentMonthData.length > 0) {
        const recentWithData = [...currentMonthData].reverse().find(d =>
            d.sleep_score !== null || (d.habits && d.habits.length > 0)
        );
        if (recentWithData) {
            const idx = currentMonthData.indexOf(recentWithData);
            selectDay(recentWithData.date, idx);
        }
    }
}

document.addEventListener('DOMContentLoaded', init);
