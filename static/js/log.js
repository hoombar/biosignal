// /log — focused single-day habit logging.
// State: which date we're viewing. Today = local-date in browser TZ. The user
// can page back indefinitely; the next button is disabled at today.

(function () {
    'use strict';

    const habitsEl = document.getElementById('log-habits');
    const contextEl = document.getElementById('log-context');
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

    function readContextId() {
        const match = (window.location.search || '').match(/[?&]context=(\d+)/);
        return match ? match[1] : null;
    }

    let currentDate = readHashDate() || todayLocal();
    // Cache fetched days so flipping back/forth doesn't refetch.
    const dayCache = {};  // { 'YYYY-MM-DD': {date, habits: [{name, value, type}]} }
    let supplementSlots = [];
    let editingContextId = readContextId();

    function clearDayCache() {
        Object.keys(dayCache).forEach(key => delete dayCache[key]);
    }

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

    function renderPreservingScroll(dateStr) {
        const scrollX = window.scrollX || 0;
        const scrollY = window.scrollY || 0;
        return render(dateStr).then(() => {
            if (typeof window.scrollTo === 'function') {
                window.scrollTo(scrollX, scrollY);
            }
        });
    }

    function titleSlot(slot) {
        return slot.charAt(0).toUpperCase() + slot.slice(1);
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

    function renderContextPanel(day) {
        const contexts = day.contexts || [];
        const editingEvent = contexts.find(event => String(event.id) === editingContextId) || null;
        if (editingContextId !== null && !editingEvent) editingContextId = null;
        const formEvent = editingEvent || {};
        const formCategory = formEvent.category || 'travel';
        const categoryOptions = [
            ['travel', 'Travel'],
            ['conference', 'Conference'],
            ['illness', 'Illness'],
            ['stress', 'Stress'],
            ['vacation', 'Vacation'],
            ['recovery', 'Recovery'],
            ['other', 'Other'],
        ].map(([value, label]) => (
            `<option value="${value}"${formCategory === value ? ' selected' : ''}>${label}</option>`
        )).join('');
        const summaryText = contexts.length
            ? `${contexts.length} context${contexts.length === 1 ? '' : 's'}: ${contexts.map(event => event.title).join(', ')}`
            : 'Context';
        const summaryHint = contexts.length
            ? 'Saved for this date range'
            : 'Optional travel, conference, illness, or other non-baseline notes';
        const eventsHtml = contexts.length ? contexts.map(event => {
            const range = event.start_date === event.end_date
                ? event.start_date
                : `${event.start_date} to ${event.end_date}`;
            return `
                <article class="context-event ${event.exclude_from_baseline ? 'context-event--excluded' : ''}">
                    <div class="context-event-main">
                        <span class="context-category">${titleCase(event.category)}</span>
                        <h3>${escapeHtml(event.title)}</h3>
                        <p>${escapeHtml(range)}</p>
                        ${event.notes ? `<p class="context-notes">${escapeHtml(event.notes)}</p>` : ''}
                    </div>
                    <div class="context-event-actions">
                        <button type="button" data-context-edit="${event.id}" aria-label="Edit context event">Edit</button>
                        <button type="button" class="context-delete" data-context-delete="${event.id}" aria-label="Delete context event">Remove</button>
                    </div>
                </article>
            `;
        }).join('') : '<p class="context-empty">No outlier context for this day.</p>';

        return `
            <details class="context-panel"${editingEvent ? ' open' : ''}>
                <summary class="context-panel-summary">
                    <div>
                        <h2>${escapeHtml(summaryText)}</h2>
                        <p>${escapeHtml(summaryHint)}</p>
                    </div>
                    ${day.baseline_excluded ? '<span class="context-baseline">Excluded from baseline</span>' : ''}
                </summary>
                <div class="context-panel-body">
                    <p class="context-help">
                        Use this when the day is not part of your normal baseline, like travel, a conference, illness,
                        unusual stress, or sleeping somewhere unfamiliar. Saved context appears on Daily and marked
                        days can be excluded from baseline calculations.
                    </p>
                    <div class="context-event-list">${eventsHtml}</div>
                    <form class="context-form" id="context-form"${editingEvent ? ` data-context-id="${editingEvent.id}"` : ''}>
                        <input type="text" name="title" value="${escapeHtml(formEvent.title || '')}" placeholder="Conference abroad, hotel sleep, long flight" required maxlength="120">
                        <div class="context-form-grid">
                            <label>Start <input type="date" name="start_date" value="${escapeHtml(formEvent.start_date || currentDate)}" required></label>
                            <label>End <input type="date" name="end_date" value="${escapeHtml(formEvent.end_date || currentDate)}" required></label>
                            <label>Category
                                <select name="category">
                                    ${categoryOptions}
                                </select>
                            </label>
                        </div>
                        <textarea name="notes" rows="2" placeholder="Optional note: what changed, and why this day may not compare fairly to normal days">${escapeHtml(formEvent.notes || '')}</textarea>
                        <label class="context-baseline-toggle">
                            <input type="checkbox" name="exclude_from_baseline"${editingEvent ? (editingEvent.exclude_from_baseline ? ' checked' : '') : ' checked'}>
                            Treat this date range as non-baseline
                        </label>
                        <div class="context-form-actions">
                            <button type="submit" class="context-submit">${editingEvent ? 'Update context' : 'Add context'}</button>
                            ${editingEvent ? '<button type="button" data-context-cancel>Cancel</button>' : ''}
                        </div>
                    </form>
                </div>
            </details>
        `;
    }

    function renderSupplementsPanel(day) {
        if (!supplementSlots.length) return '';
        const logsBySlot = Object.fromEntries((day.supplements || []).map(log => [log.slot, log]));
        const visibleSlots = supplementSlots.filter(slotDef => {
            const configured = (slotDef.items || []).length > 0;
            const logged = Object.prototype.hasOwnProperty.call(logsBySlot, slotDef.slot);
            return configured || logged;
        });
        if (!visibleSlots.length) return '';

        return `
            <section class="supplement-panel" aria-label="Supplements">
                <div class="supplement-panel-header">
                    <h2>Supplements</h2>
                    <a href="/settings" title="Edit supplements">Edit</a>
                </div>
                <div class="supplement-slot-grid">
                    ${visibleSlots.map(slotDef => {
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
        if (dateStr !== currentDate) editingContextId = null;
        currentDate = dateStr;
        if (updateUrl && window.location.hash.slice(1) !== dateStr) {
            history.replaceState(null, '', `#${dateStr}`);
        }
        dateEl.textContent = formatHumanDate(dateStr);
        dateRelEl.textContent = relativeLabel(dateStr);
        nextBtn.disabled = (dateStr >= todayLocal());

        loadingEl.style.display = '';
        errorEl.style.display = 'none';
        contextEl.style.display = 'none';
        habitsEl.style.display = 'none';
        supplementsEl.style.display = 'none';
        emptyEl.style.display = 'none';

        try {
            const day = await loadDay(dateStr);
            contextEl.innerHTML = renderContextPanel(day);
            supplementsEl.innerHTML = renderSupplementsPanel(day);
            habitsEl.innerHTML = HabitPanel.renderHabitsPanel(day, { mode: 'edit' });
            loadingEl.style.display = 'none';
            contextEl.style.display = '';
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
            renderPreservingScroll(currentDate);
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

    contextEl.addEventListener('submit', async (event) => {
        if (event.target.id !== 'context-form') return;
        event.preventDefault();
        const form = event.target;
        const submit = form.querySelector('button[type="submit"]');
        const formData = new FormData(form);
        const contextId = form.dataset?.contextId || null;
        const body = {
            title: formData.get('title'),
            start_date: formData.get('start_date'),
            end_date: formData.get('end_date'),
            category: formData.get('category') || 'other',
            exclude_from_baseline: formData.get('exclude_from_baseline') === 'on',
            notes: formData.get('notes') || null,
        };
        if (!contextId) {
            body.tags = [];
            body.intensity = null;
        }
        submit.disabled = true;
        try {
            const resp = await fetch(contextId ? `/api/context-events/${contextId}` : '/api/context-events', {
                method: contextId ? 'PATCH' : 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(body),
            });
            if (!resp.ok) {
                const detail = await resp.text();
                console.error(`Failed to ${contextId ? 'update' : 'create'} context event:`, detail);
                return;
            }
            editingContextId = null;
            clearDayCache();
            render(currentDate);
        } finally {
            submit.disabled = false;
        }
    });

    contextEl.addEventListener('click', async (event) => {
        const editButton = event.target.closest('button[data-context-edit]');
        if (editButton) {
            editingContextId = editButton.dataset.contextEdit;
            contextEl.innerHTML = renderContextPanel(dayCache[currentDate] || {});
            return;
        }

        const cancelButton = event.target.closest('button[data-context-cancel]');
        if (cancelButton) {
            editingContextId = null;
            contextEl.innerHTML = renderContextPanel(dayCache[currentDate] || {});
            return;
        }

        const button = event.target.closest('button[data-context-delete]');
        if (!button) return;
        button.disabled = true;
        try {
            const resp = await fetch(`/api/context-events/${button.dataset.contextDelete}`, {method: 'DELETE'});
            if (!resp.ok) {
                const detail = await resp.text();
                console.error('Failed to delete context event:', detail);
                return;
            }
            if (editingContextId === button.dataset.contextDelete) editingContextId = null;
            clearDayCache();
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
