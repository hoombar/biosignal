/**
 * Habit display configuration.
 *
 * Fetches user-configured labels and emojis from /api/settings/habits
 * and provides helpers for rendering habits across the app.
 *
 * Usage:
 *   await loadHabitConfig();
 *   const display = getHabitDisplay('custom_habit');
 *   // => { label: 'Custom Habit', emoji: '✅', color: '#4488ff' }
 */

let _habitConfigMap = null;
const _habitFallbackPalette = [
    '#4488ff', '#dc2626', '#16a34a', '#f59e0b',
    '#a78bfa', '#34d399', '#38bdf8', '#f87171',
    '#fbbf24', '#fb923c', '#60a5fa', '#e879f9',
];

/**
 * Load the habit display config from the API.
 * Call this once on page load before rendering habits.
 * Safe to call multiple times — fetches only on first call.
 */
async function loadHabitConfig() {
    if (_habitConfigMap !== null) return;
    try {
        const resp = await fetch('/api/settings/habits');
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const configs = await resp.json();
        _habitConfigMap = {};
        configs.forEach(c => {
            _habitConfigMap[c.habit_name] = c;
        });
    } catch (err) {
        console.warn('Could not load habit config, using defaults:', err);
        _habitConfigMap = {};
    }
}

/**
 * Get display attributes for a habit.
 * Returns saved config values, falling back to auto-generated label and no emoji.
 *
 * @param {string} habitName - snake_case habit name (as stored in DB)
 * @returns {{ label: string, emoji: string|null, color: string, sort_order: number }}
 */
function getHabitDisplay(habitName) {
    const cfg = _habitConfigMap?.[habitName];
    const label = cfg?.display_name || _toTitleCase(habitName);
    const emoji = cfg?.emoji || null;
    const color = cfg?.color || _fallbackColorForHabit(habitName);
    const sort_order = cfg?.sort_order ?? 0;
    return { label, emoji, color, sort_order };
}

function getHabitColor(habitName) {
    return getHabitDisplay(habitName).color;
}

/**
 * Format a habit's value for display.
 *
 * Boolean habits (type === 'boolean'): renders "Yes"/"No".
 * Counter habits: renders the numeric value.
 * Unknown types: renders raw value.
 *
 * @param {{ name: string, value: number, type: string }} habit
 * @returns {string}
 */
function formatHabitValue(habit) {
    if (habit.type === 'boolean') {
        return habit.value > 0 ? 'Yes' : 'No';
    }
    return String(habit.value);
}

function _toTitleCase(snakeName) {
    return snakeName.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

function _fallbackColorForHabit(habitName) {
    let hash = 0;
    for (let i = 0; i < habitName.length; i++) {
        hash = ((hash << 5) - hash) + habitName.charCodeAt(i);
        hash |= 0;
    }
    const idx = Math.abs(hash) % _habitFallbackPalette.length;
    return _habitFallbackPalette[idx];
}
