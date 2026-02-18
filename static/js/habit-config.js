/**
 * Habit display configuration.
 *
 * Fetches user-configured labels and emojis from /api/settings/habits
 * and provides helpers for rendering habits across the app.
 *
 * Usage:
 *   await loadHabitConfig();
 *   const display = getHabitDisplay('afternoon_slump');
 *   // => { label: 'Low energy afternoon', emoji: '😮‍💨' }
 */

let _habitConfigMap = null;

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
 * @returns {{ label: string, emoji: string|null, sort_order: number }}
 */
function getHabitDisplay(habitName) {
    const cfg = _habitConfigMap?.[habitName];
    const label = cfg?.display_name || _toTitleCase(habitName);
    const emoji = cfg?.emoji || null;
    const sort_order = cfg?.sort_order ?? 0;
    return { label, emoji, sort_order };
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
