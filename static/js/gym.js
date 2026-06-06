(function () {
    'use strict';

    const state = {
        date: '',
        templates: [],
        session: null,
    };

    const els = {};

    function todayIso() {
        const now = new Date();
        const tzOffset = now.getTimezoneOffset() * 60000;
        return new Date(now.getTime() - tzOffset).toISOString().slice(0, 10);
    }

    function escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function compactNumber(value) {
        if (value == null || value === '') return '';
        const number = Number(value);
        if (!Number.isFinite(number)) return String(value);
        return Number.isInteger(number) ? String(number) : String(number).replace(/0+$/, '').replace(/\.$/, '');
    }

    function plannedSummary(activity) {
        if (activity.activity_type === 'strength') {
            const parts = [];
            if (activity.planned_weight != null) {
                parts.push(`${compactNumber(activity.planned_weight)} ${activity.planned_weight_unit || 'kg'}`);
            }
            if (activity.planned_sets != null || activity.planned_reps != null) {
                parts.push(`${activity.planned_sets ?? '-'} x ${activity.planned_reps ?? '-'}`);
            }
            return parts.join(' · ') || 'Strength';
        }
        if (activity.activity_type === 'cardio') {
            const parts = [];
            if (activity.planned_duration_minutes != null) parts.push(`${compactNumber(activity.planned_duration_minutes)} min`);
            if (activity.planned_intensity) parts.push(activity.planned_intensity);
            if (activity.planned_speed != null) {
                const unit = activity.planned_weight_unit ? ` ${activity.planned_weight_unit}` : '';
                parts.push(`${compactNumber(activity.planned_speed)}${unit}`);
            }
            return parts.join(' · ') || 'Cardio';
        }
        if (activity.activity_type === 'mobility') {
            const parts = [];
            if (activity.planned_duration_minutes != null) parts.push(`${compactNumber(activity.planned_duration_minutes)} min`);
            if (activity.planned_intensity) parts.push(activity.planned_intensity);
            return parts.join(' · ') || 'Mobility';
        }
        return activity.planned_notes || 'Freeform activity';
    }

    function templateSummary(template) {
        const count = template.activities?.length || 0;
        return `${count} ${count === 1 ? 'activity' : 'activities'}`;
    }

    function setStatus(message, isError) {
        els.status.textContent = message || '';
        els.status.style.display = message ? '' : 'none';
        els.status.classList.toggle('gym-status--error', Boolean(isError));
    }

    async function fetchJson(url, options) {
        const resp = await fetch(url, options);
        if (!resp.ok) {
            const detail = await resp.text();
            throw new Error(detail || `HTTP ${resp.status}`);
        }
        if (resp.status === 204) return null;
        return resp.json();
    }

    async function loadTemplates() {
        state.templates = await fetchJson('/api/gym/templates');
    }

    async function loadSession() {
        state.session = await fetchJson(`/api/gym/session?date=${encodeURIComponent(state.date)}`);
    }

    async function refresh() {
        setStatus('Loading gym session…');
        els.session.style.display = 'none';
        els.start.style.display = 'none';
        try {
            await Promise.all([loadTemplates(), loadSession()]);
            render();
            setStatus('');
        } catch (err) {
            console.error('Failed to load gym page', err);
            setStatus('Could not load gym session data.', true);
        }
    }

    function render() {
        if (state.session) {
            renderSession();
            els.session.style.display = '';
            els.start.style.display = 'none';
            return;
        }
        renderStart();
        els.session.style.display = 'none';
        els.start.style.display = '';
    }

    function renderStart() {
        if (state.templates.length === 0) {
            els.templateList.innerHTML = `
                <div class="gym-empty">
                    <h3>No gym plans yet</h3>
                    <p>Create a gym template in <a href="/settings">Settings</a>, then come back here to start logging.</p>
                </div>
            `;
            return;
        }
        els.templateList.innerHTML = state.templates.map(template => `
            <button type="button" class="gym-template-card" data-template-id="${template.id}">
                <span class="gym-template-title">${escapeHtml(template.name)}</span>
                <span class="gym-template-meta">${escapeHtml(templateSummary(template))}</span>
            </button>
        `).join('');
    }

    function renderSession() {
        const session = state.session;
        const activities = session.activities || [];
        const completed = activities.filter(activity => activity.completed).length;
        const finished = session.completed_at != null;
        els.session.innerHTML = `
            <div class="gym-session-header">
                <div>
                    <p class="gym-kicker">${finished ? 'Finished session' : 'Active session'}</p>
                    <h2>${escapeHtml(session.template_name_snapshot)}</h2>
                    <p>${completed} / ${activities.length} complete</p>
                </div>
                <button type="button" class="gym-finish-btn" data-action="finish-session" ${finished ? 'disabled' : ''}>
                    ${finished ? 'Finished' : 'Finish'}
                </button>
            </div>
            <div class="gym-activity-list">
                ${activities.map(renderActivity).join('')}
            </div>
        `;
    }

    function renderActivity(activity) {
        const checked = activity.completed ? 'checked' : '';
        const doneClass = activity.completed ? ' gym-activity--done' : '';
        return `
            <article class="gym-activity${doneClass}" data-activity-id="${activity.id}">
                <label class="gym-activity-main">
                    <input type="checkbox" data-action="toggle-activity" ${checked}>
                    <span>
                        <span class="gym-activity-name">${escapeHtml(activity.name_snapshot)}</span>
                        <span class="gym-activity-plan">${escapeHtml(plannedSummary(activity))}</span>
                    </span>
                </label>
                <div class="gym-rating" aria-label="Exercise rating">
                    ${['easy', 'normal', 'hard'].map(rating => `
                        <button type="button"
                                class="gym-rating-btn ${activity.rating === rating ? 'gym-rating-btn--active' : ''}"
                                data-action="rate-activity"
                                data-rating="${rating}">
                            ${rating}
                        </button>
                    `).join('')}
                </div>
                <details class="gym-adjust">
                    <summary>Adjust</summary>
                    ${renderAdjustFields(activity)}
                    <label class="gym-note-label">
                        Note
                        <textarea data-field="notes" rows="2">${escapeHtml(activity.notes || '')}</textarea>
                    </label>
                    <button type="button" class="gym-save-adjust" data-action="save-activity">Save changes</button>
                </details>
            </article>
        `;
    }

    function renderAdjustFields(activity) {
        if (activity.activity_type === 'strength') {
            return `
                <div class="gym-adjust-grid">
                    ${numberField('actual_weight', 'Weight', activity.actual_weight)}
                    ${selectField('actual_weight_unit', 'Unit', activity.actual_weight_unit || activity.planned_weight_unit || 'kg', ['kg', 'lbs'])}
                    ${numberField('actual_sets', 'Sets', activity.actual_sets)}
                    ${numberField('actual_reps', 'Reps', activity.actual_reps)}
                </div>
            `;
        }
        if (activity.activity_type === 'cardio') {
            return `
                <div class="gym-adjust-grid">
                    ${numberField('actual_duration_minutes', 'Minutes', activity.actual_duration_minutes)}
                    ${textField('actual_intensity', 'Intensity', activity.actual_intensity)}
                    ${numberField('actual_speed', 'Speed/RPM', activity.actual_speed)}
                    ${selectField('actual_weight_unit', 'Unit', activity.actual_weight_unit || activity.planned_weight_unit || 'kph', ['kph', 'mph', 'rpm'])}
                </div>
            `;
        }
        if (activity.activity_type === 'mobility') {
            return `
                <div class="gym-adjust-grid">
                    ${numberField('actual_duration_minutes', 'Minutes', activity.actual_duration_minutes)}
                    ${textField('actual_intensity', 'Intensity', activity.actual_intensity)}
                </div>
            `;
        }
        return '';
    }

    function numberField(field, label, value) {
        return `
            <label>
                ${label}
                <input type="number" step="0.5" min="0" data-field="${field}" value="${escapeHtml(value ?? '')}">
            </label>
        `;
    }

    function textField(field, label, value) {
        return `
            <label>
                ${label}
                <input type="text" data-field="${field}" value="${escapeHtml(value ?? '')}">
            </label>
        `;
    }

    function selectField(field, label, value, options) {
        return `
            <label>
                ${label}
                <select data-field="${field}">
                    ${options.map(option => `<option value="${option}" ${value === option ? 'selected' : ''}>${option}</option>`).join('')}
                </select>
            </label>
        `;
    }

    async function startSession(templateId) {
        setStatus('Starting session…');
        try {
            state.session = await fetchJson('/api/gym/sessions', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({date: state.date, template_id: Number(templateId)}),
            });
            render();
            setStatus('');
        } catch (err) {
            console.error('Failed to start gym session', err);
            setStatus('Could not start session. Check whether this date already has one.', true);
        }
    }

    async function updateActivity(activityId, patch) {
        const activity = state.session.activities.find(item => item.id === Number(activityId));
        if (!activity) return;
        Object.assign(activity, patch);
        renderSession();
        try {
            const updated = await fetchJson(`/api/gym/session-activities/${activityId}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(patch),
            });
            Object.assign(activity, updated);
            renderSession();
        } catch (err) {
            console.error('Failed to update gym activity', err);
            setStatus('Could not save activity update.', true);
            await loadSession();
            render();
        }
    }

    async function finishSession() {
        if (!state.session) return;
        setStatus('Finishing session…');
        try {
            state.session = await fetchJson(`/api/gym/sessions/${state.session.id}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({completed: true}),
            });
            render();
            setStatus('');
        } catch (err) {
            console.error('Failed to finish gym session', err);
            setStatus('Could not finish session.', true);
        }
    }

    function collectActivityPatch(card) {
        const patch = {};
        card.querySelectorAll('[data-field]').forEach(input => {
            const value = input.value.trim();
            if (input.type === 'number') {
                patch[input.dataset.field] = value === '' ? null : Number(value);
            } else {
                patch[input.dataset.field] = value === '' ? null : value;
            }
        });
        return patch;
    }

    function bindEvents() {
        els.date.addEventListener('change', () => {
            state.date = els.date.value || todayIso();
            refresh();
        });

        els.templateList.addEventListener('click', (event) => {
            const card = event.target.closest('[data-template-id]');
            if (!card) return;
            startSession(card.dataset.templateId);
        });

        els.session.addEventListener('click', (event) => {
            const actionEl = event.target.closest('[data-action]');
            if (!actionEl) return;
            const action = actionEl.dataset.action;
            if (action === 'finish-session') {
                finishSession();
                return;
            }
            const card = actionEl.closest('[data-activity-id]');
            if (!card) return;
            const activityId = card.dataset.activityId;
            if (action === 'rate-activity') {
                updateActivity(activityId, {rating: actionEl.dataset.rating});
            }
            if (action === 'save-activity') {
                updateActivity(activityId, collectActivityPatch(card));
            }
        });

        els.session.addEventListener('change', (event) => {
            if (event.target.dataset.action !== 'toggle-activity') return;
            const card = event.target.closest('[data-activity-id]');
            if (!card) return;
            updateActivity(card.dataset.activityId, {completed: event.target.checked});
        });
    }

    function init() {
        els.date = document.getElementById('gym-date');
        els.status = document.getElementById('gym-status');
        els.session = document.getElementById('gym-session');
        els.start = document.getElementById('gym-start');
        els.templateList = document.getElementById('gym-template-list');
        if (!els.date || !els.status || !els.session || !els.start || !els.templateList) return;
        state.date = todayIso();
        els.date.value = state.date;
        bindEvents();
        refresh();
    }

    document.addEventListener('DOMContentLoaded', init);
})();
