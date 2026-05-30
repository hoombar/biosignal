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
let calendarHabitNames = [];

const CALENDAR_DOT_LIMIT = 3;
const POLLEN_TYPES = [
    { key: 'alder', label: 'Alder' },
    { key: 'birch', label: 'Birch' },
    { key: 'grass', label: 'Grass' },
    { key: 'mugwort', label: 'Mugwort' },
    { key: 'olive', label: 'Olive' },
    { key: 'ragweed', label: 'Ragweed' },
];

const HR_FIRST_ACTIVITY_TYPES = new Set([
    'boxing',
    'mixed_martial_arts',
    'strength_training',
    'indoor_cardio',
    'yoga',
    'pilates',
    'table_tennis',
    'platform_tennis',
    'tennis_v2',
]);

const ACTIVITY_ICONS = {
    boxing: '&#129354;',
    cycling: '&#128692;',
    gravel_cycling: '&#128692;',
    indoor_cycling: '&#128692;',
    lap_swimming: '&#127946;',
    mixed_martial_arts: '&#129355;',
    open_water_swimming: '&#127946;',
    running: '&#127939;',
    strength_training: '&#127947;',
    swimming: '&#127946;',
    table_tennis: '&#127955;',
    tennis_v2: '&#127934;',
    walking: '&#128694;',
};

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

function formatClockMinutes(minutes) {
    if (minutes === null || minutes === undefined) return '-';
    const total = Math.round(minutes);
    const h = Math.floor(total / 60) % 24;
    const m = total % 60;
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

function formatDaylightMinutes(minutes) {
    if (minutes === null || minutes === undefined) return '-';
    return formatHours(minutes / 60);
}

function formatPct(value) {
    if (value === null || value === undefined) return '-';
    return `${Math.round(value)}%`;
}

function formatNum(value, decimals = 0) {
    if (value === null || value === undefined) return '-';
    return decimals > 0 ? value.toFixed(decimals) : Math.round(value).toLocaleString();
}

function formatDistanceMeters(meters) {
    if (meters === null || meters === undefined) return '-';
    if (meters >= 1000) return `${(meters / 1000).toFixed(1)} km`;
    return `${formatNum(meters)} m`;
}

function formatPollenValue(value) {
    if (value === null || value === undefined) return '-';
    const rounded = Math.round(value * 10) / 10;
    return Number.isInteger(rounded) ? rounded.toLocaleString() : rounded.toFixed(1);
}

function formatWeatherValue(value, unit = '', decimals = 0) {
    if (value === null || value === undefined) return '-';
    const rounded = decimals > 0 ? Number(value).toFixed(decimals) : Math.round(value).toLocaleString();
    return `${rounded}${unit}`;
}

function formatBool(value) {
    if (value === null || value === undefined) return '-';
    return value ? 'Yes' : 'No';
}

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>'"]/g, ch => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        "'": '&#39;',
        '"': '&quot;',
    }[ch]));
}

function titleCase(value) {
    return String(value || 'other')
        .replace(/_/g, ' ')
        .replace(/\b\w/g, ch => ch.toUpperCase());
}

function getActivityIcon(activityType) {
    return ACTIVITY_ICONS[activityType] || '&#127941;';
}

function hasMeaningfulActivityDistance(session) {
    return session.distance_meters !== null
        && session.distance_meters !== undefined
        && Number(session.distance_meters) > 0
        && !HR_FIRST_ACTIVITY_TYPES.has(session.activity_type);
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

function getHabitValue(habits, name) {
    if (!habits) return null;
    const habit = habits.find(h => h.name === name);
    return habit ? habit.value : null;
}

function getHabitAccentColor(habitName) {
    const display = getHabitDisplay(habitName);
    return display.color || getHabitColor(habitName);
}

function getCalendarHabitNames(data) {
    const names = new Set();
    data.forEach(day => {
        (day.habits || []).forEach(h => names.add(h.name));
    });

    return [...names]
        .sort((a, b) => {
            const da = getHabitDisplay(a);
            const db = getHabitDisplay(b);
            if (da.sort_order !== db.sort_order) return da.sort_order - db.sort_order;
            return a.localeCompare(b);
        })
        .slice(0, CALENDAR_DOT_LIMIT);
}

function renderCalendarLegend(habitNames) {
    const container = document.getElementById('calendar-legend');
    if (!container) return;

    if (!habitNames.length) {
        container.innerHTML = '<span class="legend-item">No tracked habits this month</span>';
        return;
    }

    container.innerHTML = habitNames.map(habitName => {
        const display = getHabitDisplay(habitName);
        const color = getHabitAccentColor(habitName);
        return `
            <div class="legend-item">
                <span class="legend-dot" style="background: ${color}"></span>
                <span>${display.label}</span>
            </div>
        `;
    }).join('');
}

function renderCalendarCell(day, index) {
    const date = parseLocalDate(day.date);
    const dateNum = date.getDate();
    const habitDots = calendarHabitNames.map(habitName => {
        const value = getHabitValue(day.habits, habitName);
        const numeric = Number(value);
        const isPositive = value !== null && !Number.isNaN(numeric) && numeric > 0;
        const color = isPositive ? getHabitAccentColor(habitName) : 'var(--text-muted)';
        const opacity = value === null ? 0.25 : isPositive ? 1 : 0.45;
        const label = getHabitDisplay(habitName).label;
        return `
            <span
                class="habit-dot"
                style="background: ${color}; opacity: ${opacity};"
                title="${label}: ${value ?? '-'}"
            ></span>
        `;
    }).join('');

    const contexts = day.contexts || [];
    const contextLabel = contexts.map(context => context.title).filter(Boolean).join(', ');
    const contextMarker = contexts.length
        ? `<span class="context-cell-marker" title="Context: ${escapeHtml(contextLabel)}">C</span>`
        : '';
    const hasData = day.sleep_score !== null
        || (day.habits && day.habits.length > 0)
        || contexts.length > 0;
    const noDataClass = hasData ? '' : 'no-data';
    const selectedClass = selectedDate === day.date ? 'selected' : '';

    return `
        <div class="calendar-cell ${noDataClass} ${selectedClass}"
             onclick="selectDay('${day.date}', ${index})"
             title="${formatShortDate(day.date)}${contextLabel ? ` - Context: ${escapeHtml(contextLabel)}` : ''}">
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <span class="date-num">${dateNum}</span>
                ${day.sleep_score ? `<span class="sleep-score">${day.sleep_score}</span>` : ''}
            </div>
            ${contextMarker}
            <div class="habit-strip">${habitDots}</div>
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
        calendarHabitNames = getCalendarHabitNames(data);
        renderCalendarLegend(calendarHabitNames);

        if (data.length === 0) {
            container.innerHTML = '<p class="empty-state">No data available.</p>';
            renderCalendarLegend([]);
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
                          title="${formatShortDate(day.date)}: ${day.sleep_score ?? 'No data'}${day.has_habit_event ? ' (Habit event)' : ''}"
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

function renderHabitsPanel(day) {
    return `
        <div class="daily-habits">
            <h3 class="habits-panel-title">Habits</h3>
            ${HabitPanel.renderHabitsPanel(day, { mode: 'view' })}
        </div>
    `;
}

function titleSlot(slot) {
    return slot.charAt(0).toUpperCase() + slot.slice(1);
}

function renderSupplementSnapshot(day) {
    const supplements = day.supplements || [];
    if (!supplements.length) return '';
    return `
        <div class="daily-supplements">
            <h3 class="habits-panel-title">Supplements</h3>
            ${supplements.map(log => {
                const items = (log.snapshot || []).map(item => item.name).filter(Boolean);
                return `
                    <div class="daily-supplement-item ${log.completed ? 'daily-supplement-item--done' : ''}">
                        <div class="daily-supplement-title">
                            <span>${titleSlot(log.slot)}</span>
                            <span>${log.completed ? 'Done' : 'Skipped'}</span>
                        </div>
                        <div class="daily-supplement-items">${items.length ? items.join(', ') : 'No items'}</div>
                    </div>
                `;
            }).join('')}
        </div>
    `;
}

function renderContextSummary(day) {
    const contexts = day.contexts || [];
    if (!contexts.length) return '';

    const contextRows = contexts.map(context => {
        const range = context.start_date === context.end_date
            ? context.start_date
            : `${context.start_date} to ${context.end_date}`;
        const tags = (context.tags || []).map(tag => (
            `<span class="daily-context-tag">${escapeHtml(tag)}</span>`
        )).join('');
        return `
            <div class="daily-context-item ${context.exclude_from_baseline ? 'daily-context-item--excluded' : ''}">
                <div class="daily-context-item-header">
                    <span class="daily-context-category">${titleCase(context.category)}</span>
                    ${context.exclude_from_baseline ? '<span class="daily-context-baseline">Excluded from baseline</span>' : ''}
                </div>
                <div class="daily-context-title">${titleCase(context.title)}</div>
                <div class="daily-context-meta">${escapeHtml(range)}${context.intensity ? ` · ${titleCase(context.intensity)} intensity` : ''}</div>
                ${context.notes ? `<div class="daily-context-notes">${escapeHtml(context.notes)}</div>` : ''}
                ${tags ? `<div class="daily-context-tags">${tags}</div>` : ''}
            </div>
        `;
    }).join('');

    return `
        <div class="daily-context-summary">
            <div class="daily-context-header">
                <h3>Context</h3>
                <a href="/log#${day.date || ''}" title="Edit context on Log">Edit&nbsp;&rarr;</a>
            </div>
            ${contextRows}
        </div>
    `;
}

function _patchDayCache(dateStr, habitName, habitType, newValue) {
    const [year, month] = dateStr.split('-').map(Number);
    const key = monthKey(year, month);
    const monthData = monthCache[key];
    if (!monthData) return;
    const day = monthData.find(d => d.date === dateStr);
    if (!day) return;
    if (!day.habits) day.habits = [];
    const existing = day.habits.find(h => h.name === habitName);
    if (existing) {
        existing.value = newValue;
    } else {
        day.habits.push({name: habitName, value: newValue, type: habitType});
    }
}

function _rerenderSelectedDay() {
    if (selectedIndex < 0 || !currentMonthData[selectedIndex]) return;
    renderDayDetail(currentMonthData[selectedIndex]);
}

function renderMetricDetails(rows) {
    return `
            <details class="metric-details">
                <summary class="metric-details-summary">Details</summary>
                <div class="secondary-metrics">
                    ${rows}
                </div>
            </details>
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
            ${renderMetricDetails(`
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
            `)}
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
            ${renderMetricDetails(`
                <div class="metric-row">
                    <span class="metric-label">Minimum</span>
                    <span class="metric-value">${formatNum(day.hrv_overnight_min, 0)} ms</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Slope</span>
                    <span class="metric-value">${day.hrv_rmssd_slope !== null ? (day.hrv_rmssd_slope > 0 ? '+' : '') + day.hrv_rmssd_slope.toFixed(2) : '-'}</span>
                </div>
            `)}
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
            ${renderMetricDetails(`
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
            `)}
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
            ${renderMetricDetails(`
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
            `)}
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
            ${renderMetricDetails(`
                ${sampleRows}
                <div class="metric-row">
                    <span class="metric-label">Daily Min</span>
                    <span class="metric-value">${formatNum(day.bb_daily_min)}</span>
                </div>
            `)}
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
            ${renderMetricDetails(`
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
            `)}
        </div>
    `;
}

function renderActivityCard(day) {
    const walkBadge = day.had_likely_brisk_walk ?
        `<span style="background: var(--color-positive); color: var(--bg-primary); padding: 2px 8px; border-radius: 4px; font-size: 0.625rem; font-weight: 600; text-transform: uppercase;">Likely brisk walk</span>` : '';
    const sessions = day.activity_sessions || [];
    const trainingCards = sessions.length ? sessions.map(session => renderActivitySessionCard(session)).join('') : day.had_training ? `
        <div class="metric-card">
            <div class="card-header activity">
                <span class="card-icon">&#127947;</span>
                <span class="card-title">Training Sessions</span>
            </div>
            <div class="primary-metric">
                <span class="metric-value">${titleCase(day.training_type || 'Training')}</span>
                <span class="metric-unit">${day.training_intensity || 'training'}</span>
            </div>
            ${renderMetricDetails(`
                <div class="metric-row">
                    <span class="metric-label">Duration</span>
                    <span class="metric-value">${formatNum(day.training_duration_min, 0)} min</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Avg HR</span>
                    <span class="metric-value">${formatNum(day.training_avg_hr)} bpm</span>
                </div>
            `)}
        </div>
    ` : '';

    return `
        <div class="metric-card">
            <div class="card-header activity">
                <span class="card-icon">&#127939;</span>
                <span class="card-title">Steps</span>
                ${walkBadge}
            </div>
            <div class="primary-metric">
                <span class="metric-value">${formatNum(day.steps_total)}</span>
                <span class="metric-unit">steps</span>
            </div>
            ${renderMetricDetails(`
                <div class="metric-row">
                    <span class="metric-label"><strong>Steps</strong></span>
                    <span class="metric-value"></span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Morning Steps</span>
                    <span class="metric-value">${formatNum(day.steps_morning)}</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Peak 45 min</span>
                    <span class="metric-value">${formatNum(day.steps_peak_45min)}</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Brisk walk windows</span>
                    <span class="metric-value">${day.walk_hr_elevated_45min_windows ?? 0} x 45m</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Step-only 30m blocks</span>
                    <span class="metric-value">${day.steps_walking_30min_blocks ?? 0}</span>
                </div>
                ${day.walk_peak_45min_hr_delta !== null && day.walk_peak_45min_hr_delta !== undefined ? `
                <div class="metric-row">
                    <span class="metric-label">Walk HR lift</span>
                    <span class="metric-value">+${formatNum(day.walk_peak_45min_hr_delta)} bpm</span>
                </div>
                ` : ''}
            `)}
        </div>
        ${trainingCards}
    `;
}

function renderActivitySessionCard(session) {
    const hasDistance = hasMeaningfulActivityDistance(session);
    const hasLaps = session.laps !== null && session.laps !== undefined;
    const hasMaxHr = session.max_hr !== null && session.max_hr !== undefined;
    const hasAvgHr = session.avg_hr !== null && session.avg_hr !== undefined;
    const durationText = `${formatNum(session.duration_min)} min`;
    const primaryValue = hasDistance
        ? (session.distance_meters / 1000).toFixed(1)
        : hasMaxHr
            ? formatNum(session.max_hr)
            : formatNum(session.duration_min);
    const primaryUnit = hasDistance
        ? `km${hasLaps ? ` · ${formatNum(session.laps)} laps` : ''}`
        : hasMaxHr
            ? 'bpm max'
            : 'min';

    return `
        <div class="metric-card">
            <div class="card-header activity">
                <span class="card-icon">${getActivityIcon(session.activity_type)}</span>
                <span class="card-title">${titleCase(session.activity_type)}</span>
            </div>
            <div class="primary-metric">
                <span class="metric-value">${primaryValue}</span>
                <span class="metric-unit">${primaryUnit}</span>
            </div>
            ${renderMetricDetails(`
                ${session.start_time ? `
                <div class="metric-row">
                    <span class="metric-label">Start</span>
                    <span class="metric-value">${session.start_time}</span>
                </div>
                ` : ''}
                <div class="metric-row">
                    <span class="metric-label">Duration</span>
                    <span class="metric-value">${durationText}</span>
                </div>
                ${hasDistance ? `
                <div class="metric-row">
                    <span class="metric-label">Distance</span>
                    <span class="metric-value">${formatDistanceMeters(session.distance_meters)}</span>
                </div>
                ` : ''}
                ${hasLaps ? `
                <div class="metric-row">
                    <span class="metric-label">Laps</span>
                    <span class="metric-value">${formatNum(session.laps)} laps</span>
                </div>
                ` : ''}
                ${hasAvgHr ? `
                <div class="metric-row">
                    <span class="metric-label">Avg HR</span>
                    <span class="metric-value">${formatNum(session.avg_hr)} bpm</span>
                </div>
                ` : ''}
                ${hasMaxHr ? `
                <div class="metric-row">
                    <span class="metric-label">Max HR</span>
                    <span class="metric-value">${formatNum(session.max_hr)} bpm</span>
                </div>
                ` : ''}
                ${session.calories !== null && session.calories !== undefined ? `
                <div class="metric-row">
                    <span class="metric-label">Calories</span>
                    <span class="metric-value">${formatNum(session.calories)}</span>
                </div>
                ` : ''}
            `)}
        </div>
    `;
}

function renderLightCard(day) {
    return `
        <div class="metric-card">
            <div class="card-header light">
                <span class="card-icon">&#9728;</span>
                <span class="card-title">Light</span>
            </div>
            <div class="primary-metric">
                <span class="metric-value">${formatDaylightMinutes(day.daylight_minutes)}</span>
                <span class="metric-unit">daylight</span>
            </div>
            ${renderMetricDetails(`
                <div class="metric-row">
                    <span class="metric-label">Sunrise</span>
                    <span class="metric-value">${formatClockMinutes(day.sunrise_minutes_after_midnight)}</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Sunset</span>
                    <span class="metric-value">${formatClockMinutes(day.sunset_minutes_after_midnight)}</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Solar Noon</span>
                    <span class="metric-value">${formatClockMinutes(day.solar_noon_minutes_after_midnight)}</span>
                </div>
            `)}
        </div>
    `;
}

function getPollenReadings(day) {
    return POLLEN_TYPES.map(type => ({
        ...type,
        avg: day[`${type.key}_pollen_avg`],
        max: day[`${type.key}_pollen_max`],
    })).filter(reading => reading.avg !== null && reading.avg !== undefined
        || reading.max !== null && reading.max !== undefined);
}

function renderPollenCard(day) {
    const readings = getPollenReadings(day);
    const peak = readings
        .filter(reading => reading.max !== null && reading.max !== undefined)
        .sort((a, b) => b.max - a.max)[0];

    const rows = readings.length > 0 ? readings.map(reading => `
                <div class="metric-row">
                    <span class="metric-label">${reading.label}</span>
                    <span class="metric-value">${formatPollenValue(reading.avg)} / ${formatPollenValue(reading.max)}</span>
                </div>
    `).join('') : `
                <div class="metric-row">
                    <span class="metric-label">Status</span>
                    <span class="metric-value">No data</span>
                </div>
    `;

    return `
        <div class="metric-card">
            <div class="card-header pollen">
                <span class="card-icon">&#127793;</span>
                <span class="card-title">Pollen</span>
            </div>
            <div class="primary-metric">
                <span class="metric-value">${peak ? formatPollenValue(peak.max) : '-'}</span>
                <span class="metric-unit">${peak ? `${peak.label} peak` : 'peak grains/m3'}</span>
            </div>
            ${renderMetricDetails(`
                <div class="metric-row">
                    <span class="metric-label">Avg / Max</span>
                    <span class="metric-value">grains/m3</span>
                </div>
                ${rows}
            `)}
        </div>
    `;
}

function hasWeatherData(day) {
    return [
        day.temperature_2m_avg,
        day.temperature_2m_min,
        day.temperature_2m_max,
        day.apparent_temperature_avg,
        day.apparent_temperature_max,
        day.relative_humidity_2m_avg,
        day.relative_humidity_2m_max,
        day.dew_point_2m_avg,
        day.precipitation_sum,
        day.rain_sum,
        day.wind_speed_10m_max,
        day.cloud_cover_avg,
    ].some(value => value !== null && value !== undefined);
}

function renderWeatherCard(day) {
    const hasData = hasWeatherData(day);
    const tempRange = day.temperature_2m_min !== null && day.temperature_2m_min !== undefined
        && day.temperature_2m_max !== null && day.temperature_2m_max !== undefined
        ? `${Math.round(day.temperature_2m_min)}-${Math.round(day.temperature_2m_max)}°C`
        : formatWeatherValue(day.temperature_2m_avg, '°C');

    return `
        <div class="metric-card">
            <div class="card-header weather">
                <span class="card-icon">&#127782;</span>
                <span class="card-title">Weather</span>
            </div>
            <div class="primary-metric">
                <span class="metric-value">${hasData ? tempRange : '-'}</span>
                <span class="metric-unit">${hasData ? 'home weather' : 'No data'}</span>
            </div>
            ${renderMetricDetails(`
                <div class="metric-row">
                    <span class="metric-label">Feels max</span>
                    <span class="metric-value">${formatWeatherValue(day.apparent_temperature_max, '°C')}</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Humidity</span>
                    <span class="metric-value">${formatWeatherValue(day.relative_humidity_2m_avg, '%')} / ${formatWeatherValue(day.relative_humidity_2m_max, '%')}</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Precipitation</span>
                    <span class="metric-value">${formatWeatherValue(day.precipitation_sum, ' mm', 1)}${day.precipitation_hours !== null && day.precipitation_hours !== undefined ? ` over ${formatWeatherValue(day.precipitation_hours, 'h')}` : ''}</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Wind max</span>
                    <span class="metric-value">${formatWeatherValue(day.wind_speed_10m_max, ' km/h')}</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Cloud cover</span>
                    <span class="metric-value">${formatWeatherValue(day.cloud_cover_avg, '%')}</span>
                </div>
            `)}
        </div>
    `;
}

function renderDayDetail(day) {
    if (!day) return;

    const detailDate = document.getElementById('detail-date');
    if (detailDate) detailDate.textContent = formatDate(day.date);

    const habitsList = document.getElementById('habits-list');
    if (habitsList) habitsList.innerHTML = `${renderSupplementSnapshot(day)}${renderHabitsPanel(day)}`;

    const editLink = document.getElementById('habits-edit-link');
    if (editLink) editLink.href = `/log#${day.date}`;

    const metricsGrid = document.getElementById('metrics-grid');
    if (!metricsGrid) return;
    metricsGrid.innerHTML = '';

    requestAnimationFrame(() => {
        metricsGrid.innerHTML = `
            ${renderContextSummary(day)}
            ${renderSleepCard(day)}
            ${renderHrvCard(day)}
            ${renderSpo2Card(day)}
            ${renderHeartRateCard(day)}
            ${renderBodyBatteryCard(day)}
            ${renderStressCard(day)}
            ${renderActivityCard(day)}
            ${renderLightCard(day)}
            ${renderPollenCard(day)}
            ${renderWeatherCard(day)}
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

    // Load habit config + habit definitions first so the panel can render.
    await Promise.all([loadHabitConfig(), loadHabitsList()]);
    window._activeHabits = await loadHabitsList();

    // Delegate click handling for the habits panel (one listener for the page).
    const habitsList = document.getElementById('habits-list');
    if (habitsList) {
        HabitPanel.bindHabitsPanel(habitsList, {
            onValueChange: (date, habitName, habitType, newValue) => {
                _patchDayCache(date, habitName, habitType, newValue);
                _rerenderSelectedDay();
            },
        });
    }

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
