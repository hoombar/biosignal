/**
 * Shared habit-panel rendering used by /log (full edit mode) and /daily
 * (compact view-only mode).
 *
 * Public API:
 *   renderHabitsPanel(day, opts)     → HTML string for the whole panel
 *   bindHabitsPanel(container, opts) → wire click handlers (edit mode only)
 *
 * ``opts`` for renderHabitsPanel:
 *   mode: 'edit' (default) | 'view'
 *
 * ``opts`` for bindHabitsPanel:
 *   onValueChange(date, habitName, habitType, newValue) → called after a
 *     successful PUT so the host page can update its caches and re-render.
 *
 * Depends on: habit-config.js (getHabitDisplay, getHabitAccentColor).
 * Pulls active habits from window._activeHabits (loaded by loadHabitsList).
 */

(function (global) {
    'use strict';

    function _toTitleCase(snake) {
        return snake.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
    }

    // 'good' | 'bad' | 'neutral' — derived purely from is_negative + target.
    function dayPolarity(def, value, logged) {
        const target = def.target_value;
        if (def.is_negative) {
            const over = target == null ? value > 0 : value > target;
            return over ? 'bad' : 'good';
        }
        if (!logged) return 'neutral';
        if (target == null) return value > 0 ? 'good' : 'neutral';
        return value >= target ? 'good' : 'neutral';
    }

    function renderStreakPill(def) {
        const streak = Number(def.streak ?? 0);
        const hit = Number(def.completion_hit ?? 0);
        const total = Number(def.completion_total ?? 0);
        if (streak === 0 && hit === 0) return '';
        const targetText = def.target_value != null
            ? (def.is_negative ? `≤ ${def.target_value}` : `≥ ${def.target_value}`)
            : (def.is_negative ? 'avoid' : 'any');
        const periodText = def.period === 'day' ? 'days' : (def.period === 'week' ? 'weeks' : 'months');
        const tooltip = `${streak} ${periodText} in a row · ${hit}/${total} recent · target ${targetText}`;
        return `
            <span class="habit-streak-pill" title="${tooltip}">
                <span class="habit-streak-flame" aria-hidden="true">🔥</span>${streak}
                <span class="habit-streak-sep" aria-hidden="true">·</span>${hit}/${total}
            </span>
        `;
    }

    function renderHabitControl(def, value, logged, accent, polarity) {
        if (def.habit_type === 'binary') {
            const onText = logged && value > 0 ? 'Yes' : 'No';
            const onClass = logged && value > 0 ? 'habit-toggle--on' : '';
            const isBad = def.is_negative && logged && value > 0;
            const bg = isBad ? 'var(--color-negative, #dc2626)' : accent;
            const styleAttr = logged && value > 0
                ? ` style="background:${bg};border-color:${bg};color:white;"`
                : '';
            return `
                <button type="button"
                        class="habit-toggle ${onClass}"
                        data-action="toggle-binary"
                        aria-pressed="${logged && value > 0}"
                        ${styleAttr}>
                    ${onText}
                </button>
            `;
        }
        let valueColor;
        if (polarity === 'bad') valueColor = 'var(--color-negative, #dc2626)';
        else if (polarity === 'good') valueColor = accent;
        else valueColor = 'var(--text-muted)';
        return `
            <div class="habit-counter">
                <button type="button" class="habit-counter-btn" data-action="counter-dec" aria-label="Decrease" ${value <= 0 ? 'disabled' : ''}>−</button>
                <span class="habit-counter-value" style="color:${valueColor};">${logged ? value : '·'}</span>
                <button type="button" class="habit-counter-btn" data-action="counter-inc" aria-label="Increase">+</button>
            </div>
        `;
    }

    function renderViewValue(def, value, logged, accent, polarity) {
        if (def.habit_type === 'binary') {
            const text = logged && value > 0 ? 'Yes' : (logged ? 'No' : '–');
            let cls = 'habit-view-value';
            if (logged && value > 0) {
                cls += def.is_negative ? ' habit-view-value--bad' : ' habit-view-value--good';
            } else if (logged) {
                cls += ' habit-view-value--muted';
            } else {
                cls += ' habit-view-value--muted';
            }
            return `<span class="${cls}">${text}</span>`;
        }
        const text = logged ? value : '–';
        let cls = 'habit-view-value';
        if (polarity === 'bad') cls += ' habit-view-value--bad';
        else if (polarity === 'good') cls += ' habit-view-value--good';
        else cls += ' habit-view-value--muted';
        return `<span class="${cls}">${text}</span>`;
    }

    function _activeHabitsSorted() {
        const definitions = (global._activeHabits || []);
        return [...definitions].sort((a, b) => {
            if (a.sort_order !== b.sort_order) return a.sort_order - b.sort_order;
            return a.name.localeCompare(b.name);
        });
    }

    function renderHabitsPanel(day, opts) {
        opts = opts || {};
        const mode = opts.mode || 'edit';
        const sorted = _activeHabitsSorted();
        if (sorted.length === 0) {
            return '<p class="habits-empty">No habits configured. Add one in <a href="/settings">Settings</a>.</p>';
        }

        const valueByName = Object.fromEntries((day.habits || []).map(h => [h.name, h.value]));

        return sorted.map(def => {
            const accent = def.color || (typeof getHabitAccentColor === 'function' ? getHabitAccentColor(def.name) : '#4488ff');
            const label = def.display_name || _toTitleCase(def.name);
            const emojiHtml = def.emoji
                ? `<span class="habit-emoji" aria-hidden="true">${def.emoji}</span>`
                : '';

            const logged = Object.prototype.hasOwnProperty.call(valueByName, def.name);
            const value = logged ? Number(valueByName[def.name]) : 0;
            const polarity = dayPolarity(def, value, logged);

            if (mode === 'view') {
                const itemClass = [
                    'habit-view-item',
                    polarity === 'bad' ? 'habit-view-item--bad' : '',
                    !logged ? 'habit-view-item--unlogged' : '',
                ].filter(Boolean).join(' ');
                return `
                    <div class="${itemClass}" style="border-left: 2px solid ${accent};">
                        <div class="habit-view-header">
                            ${emojiHtml}<span class="habit-view-label">${label}</span>
                        </div>
                        ${renderViewValue(def, value, logged, accent, polarity)}
                    </div>
                `;
            }

            // edit mode
            const itemClass = [
                'habit-sidebar-item',
                logged ? '' : 'habit-sidebar-item--unlogged',
                polarity === 'bad' ? 'habit-sidebar-item--bad' : '',
            ].filter(Boolean).join(' ');
            return `
                <div class="${itemClass}"
                     style="border-left: 2px solid ${accent};"
                     data-habit-id="${def.id}"
                     data-habit-name="${def.name}"
                     data-habit-type="${def.habit_type}"
                     data-date="${day.date}">
                    <div class="habit-sidebar-header">
                        ${emojiHtml}
                        <span class="habit-sidebar-label">${label}</span>
                        ${renderStreakPill(def)}
                    </div>
                    ${renderHabitControl(def, value, logged, accent, polarity)}
                </div>
            `;
        }).join('');
    }

    async function _putValue(habitItem, newValue, onValueChange) {
        const date = habitItem.dataset.date;
        const habitId = habitItem.dataset.habitId;
        const habitType = habitItem.dataset.habitType;
        const habitName = habitItem.dataset.habitName;

        habitItem.classList.add('habit-sidebar-item--saving');
        try {
            const resp = await fetch(`/api/habits/log/${date}/${habitId}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({value: newValue}),
            });
            if (!resp.ok) {
                const detail = await resp.text();
                console.error('Failed to log habit:', detail);
                return;
            }
            if (typeof onValueChange === 'function') {
                onValueChange(date, habitName, habitType, newValue);
            }
        } finally {
            habitItem.classList.remove('habit-sidebar-item--saving');
        }
    }

    function bindHabitsPanel(container, opts) {
        opts = opts || {};
        if (!container) return;
        container.addEventListener('click', (event) => {
            const button = event.target.closest('button[data-action]');
            if (!button) return;
            const item = button.closest('.habit-sidebar-item');
            if (!item) return;

            const action = button.dataset.action;

            if (action === 'toggle-binary') {
                const currentlyOn = button.getAttribute('aria-pressed') === 'true';
                _putValue(item, currentlyOn ? 0 : 1, opts.onValueChange);
                return;
            }

            if (action === 'counter-inc' || action === 'counter-dec') {
                const valueSpan = item.querySelector('.habit-counter-value');
                const current = Number(valueSpan?.textContent);
                const safeCurrent = Number.isFinite(current) ? current : 0;
                const next = action === 'counter-inc' ? safeCurrent + 1 : safeCurrent - 1;
                if (next < 0) return;
                _putValue(item, next, opts.onValueChange);
            }
        });
    }

    global.HabitPanel = {
        renderHabitsPanel,
        bindHabitsPanel,
        renderStreakPill,
        dayPolarity,
        _toTitleCase,
    };
})(window);
