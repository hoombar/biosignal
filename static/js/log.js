// /log — focused single-day habit logging.
// State: which date we're viewing. Today = local-date in browser TZ. The user
// can page back indefinitely; the next button is disabled at today.

(function () {
    'use strict';

    const habitsEl = document.getElementById('log-habits');
    const supplementsEl = document.getElementById('log-supplements');
    const loadingEl = document.getElementById('log-loading');
    const errorEl = document.getElementById('log-error');
    const emptyEl = document.getElementById('log-empty');
    const dateEl = document.getElementById('log-date');
    const dateRelEl = document.getElementById('log-date-rel');
    const prevBtn = document.getElementById('log-prev');
    const nextBtn = document.getElementById('log-next');

    function readHashDate() {
        const hash = window.location.hash.slice(1);
        if (/^\d{4}-\d{2}-\d{2}$/.test(hash)) {
            // Don't honor hashes pointing into the future.
            if (hash <= todayLocal()) return hash;
        }
        return null;
    }

    let currentDate = readHashDate() || todayLocal();
    // Cache fetched days so flipping back/forth doesn't refetch.
    const dayCache = {};  // { 'YYYY-MM-DD': {date, habits: [{name, value, type}]} }
    let supplementSlots = [];

    function todayLocal() {
        const d = new Date();
        return formatLocalDate(d);
    }

    function formatLocalDate(d) {
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return `${y}-${m}-${day}`;
    }

    function parseLocalDate(s) {
        const [y, m, d] = s.split('-').map(Number);
        return new Date(y, m - 1, d);
    }

    function formatHumanDate(s) {
        const d = parseLocalDate(s);
        return d.toLocaleDateString(undefined, {
            weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
        });
    }

    function relativeLabel(s) {
        const today = todayLocal();
        if (s === today) return 'Today';
        const yesterday = formatLocalDate(new Date(Date.now() - 86400000));
        if (s === yesterday) return 'Yesterday';
        const diffDays = Math.round((parseLocalDate(today) - parseLocalDate(s)) / 86400000);
        if (diffDays > 0 && diffDays < 7) return `${diffDays} days ago`;
        return '';
    }

    function shiftDate(s, deltaDays) {
        const d = parseLocalDate(s);
        d.setDate(d.getDate() + deltaDays);
        return formatLocalDate(d);
    }

    async function loadDay(dateStr) {
        if (dayCache[dateStr]) return dayCache[dateStr];
        const resp = await fetch(`/api/daily?start=${dateStr}&end=${dateStr}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        // /api/daily returns an array; pick the matching row or build an empty stub.
        const entry = (data && data.length > 0)
            ? data[0]
            : { date: dateStr, habits: [] };
        dayCache[dateStr] = entry;
        return entry;
    }

    async function loadSupplementConfig() {
        try {
            const resp = await fetch('/api/supplements/config');
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            supplementSlots = data.slots || [];
        } catch (err) {
            console.warn('Could not load supplements:', err);
            supplementSlots = [];
        }
    }

    function patchCache(dateStr, habitName, habitType, newValue) {
        const day = dayCache[dateStr];
        if (!day) return;
        if (!day.habits) day.habits = [];
        const existing = day.habits.find(h => h.name === habitName);
        if (existing) {
            existing.value = newValue;
        } else {
            day.habits.push({ name: habitName, value: newValue, type: habitType });
        }
    }

    async function refreshActiveHabits() {
        // Re-fetch /api/habits/list so streak/completion numbers update after a log.
        try {
            const resp = await fetch('/api/habits/list');
            if (resp.ok) {
                window._activeHabits = await resp.json();
            }
        } catch (err) {
            console.warn('Could not refresh active habits:', err);
        }
    }

    function titleSlot(slot) {
        return slot.charAt(0).toUpperCase() + slot.slice(1);
    }

    function renderSupplementsPanel(day) {
        if (!supplementSlots.length) return '';
        const logsBySlot = Object.fromEntries((day.supplements || []).map(log => [log.slot, log]));

        return `
            <section class="supplement-panel" aria-label="Supplements">
                <div class="supplement-panel-header">
                    <h2>Supplements</h2>
                    <a href="/settings" title="Edit supplements">Edit</a>
                </div>
                <div class="supplement-slot-grid">
                    ${supplementSlots.map(slotDef => {
                        const log = logsBySlot[slotDef.slot];
                        const completed = !!log?.completed;
                        const snapshot = log?.snapshot || slotDef.items || [];
                        const itemNames = snapshot.map(item => item.name).filter(Boolean);
                        const detail = itemNames.length ? itemNames.join(', ') : 'No supplements configured';
                        return `
                            <button type="button"
                                    class="supplement-slot ${completed ? 'supplement-slot--done' : ''}"
                                    data-slot="${slotDef.slot}"
                                    aria-pressed="${completed}">
                                <span class="supplement-slot-title">${titleSlot(slotDef.slot)}</span>
                                <span class="supplement-slot-count">${itemNames.length} item${itemNames.length === 1 ? '' : 's'}</span>
                                <span class="supplement-slot-items">${detail}</span>
                            </button>
                        `;
                    }).join('')}
                </div>
            </section>
        `;
    }

    async function render(dateStr, options = {}) {
        const updateUrl = options.updateUrl === true;
        currentDate = dateStr;
        if (updateUrl && window.location.hash.slice(1) !== dateStr) {
            history.replaceState(null, '', `#${dateStr}`);
        }
        dateEl.textContent = formatHumanDate(dateStr);
        dateRelEl.textContent = relativeLabel(dateStr);
        nextBtn.disabled = (dateStr >= todayLocal());

        loadingEl.style.display = '';
        errorEl.style.display = 'none';
        habitsEl.style.display = 'none';
        supplementsEl.style.display = 'none';
        emptyEl.style.display = 'none';

        try {
            const day = await loadDay(dateStr);
            supplementsEl.innerHTML = renderSupplementsPanel(day);
            habitsEl.innerHTML = HabitPanel.renderHabitsPanel(day, { mode: 'edit' });
            loadingEl.style.display = 'none';
            const hasSupplements = supplementSlots.some(slot => (slot.items || []).length > 0);
            if ((window._activeHabits || []).length === 0 && !hasSupplements) {
                emptyEl.style.display = '';
            } else {
                supplementsEl.style.display = supplementSlots.length ? '' : 'none';
                habitsEl.style.display = '';
            }
        } catch (err) {
            loadingEl.style.display = 'none';
            errorEl.textContent = `Failed to load: ${err.message}`;
            errorEl.style.display = '';
        }
    }

    prevBtn.addEventListener('click', () => render(shiftDate(currentDate, -1), { updateUrl: true }));
    nextBtn.addEventListener('click', () => {
        const next = shiftDate(currentDate, 1);
        if (next > todayLocal()) return;  // safety; button is also disabled
        render(next, { updateUrl: true });
    });

    document.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
        if (e.key === 'ArrowLeft') { prevBtn.click(); }
        else if (e.key === 'ArrowRight' && !nextBtn.disabled) { nextBtn.click(); }
    });

    HabitPanel.bindHabitsPanel(habitsEl, {
        onValueChange: async (date, habitName, habitType, newValue) => {
            patchCache(date, habitName, habitType, newValue);
            // Re-fetch streak/completion data, then re-render.
            await refreshActiveHabits();
            render(currentDate);
        },
    });

    supplementsEl.addEventListener('click', async (event) => {
        const button = event.target.closest('button[data-slot]');
        if (!button) return;
        const slot = button.dataset.slot;
        const completed = button.getAttribute('aria-pressed') === 'true';
        button.disabled = true;
        try {
            const method = completed ? 'DELETE' : 'PUT';
            const options = method === 'PUT'
                ? {
                    method,
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({completed: true}),
                }
                : {method};
            const resp = await fetch(`/api/supplements/log/${currentDate}/${slot}`, options);
            if (!resp.ok) {
                const detail = await resp.text();
                console.error('Failed to log supplement slot:', detail);
                return;
            }
            delete dayCache[currentDate];
            await refreshActiveHabits();
            render(currentDate);
        } finally {
            button.disabled = false;
        }
    });

    (async function init() {
        await Promise.all([loadHabitConfig(), loadHabitsList(), loadSupplementConfig()]);
        window._activeHabits = await loadHabitsList();
        await render(currentDate);
    })();
})();
