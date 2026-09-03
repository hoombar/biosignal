(function () {
    'use strict';

    const state = {
        date: '',
        templates: [],
        activities: [],
        session: null,
    };

    const pendingSaves = new Map();
    const PENDING_RETRY_MS = 5000;

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

    function activitySummary(activity) {
        if (activity.activity_type === 'strength') {
            const parts = [];
            const weight = activity.actual_weight ?? activity.planned_weight;
            const sets = activity.actual_sets ?? activity.planned_sets;
            const reps = activity.actual_reps ?? activity.planned_reps;
            if (weight != null) {
                parts.push(`${compactNumber(weight)} ${activity.actual_weight_unit || activity.planned_weight_unit || 'kg'}`);
            }
            if (sets != null || reps != null) {
                parts.push(`${sets ?? '-'} x ${reps ?? '-'}`);
            }
            return parts.join(' · ') || 'Strength';
        }
        if (activity.activity_type === 'cardio') {
            const parts = [];
            const duration = activity.actual_duration_minutes ?? activity.planned_duration_minutes;
            const intensity = activity.actual_intensity ?? activity.planned_intensity;
            const speed = activity.actual_speed ?? activity.planned_speed;
            if (duration != null) parts.push(`${compactNumber(duration)} min`);
            if (intensity) parts.push(intensity);
            if (speed != null) {
                const unit = activity.actual_weight_unit || activity.planned_weight_unit;
                parts.push(`${compactNumber(speed)}${unit ? ` ${unit}` : ''}`);
            }
            return parts.join(' · ') || 'Cardio';
        }
        if (activity.activity_type === 'mobility') {
            const parts = [];
            const weight = activity.actual_weight ?? activity.planned_weight;
            const sets = activity.actual_sets ?? activity.planned_sets;
            const reps = activity.actual_reps ?? activity.planned_reps;
            if (weight != null) {
                parts.push(`${compactNumber(weight)} ${activity.actual_weight_unit || activity.planned_weight_unit || 'kg'}`);
            }
            if (sets != null || reps != null) {
                parts.push(`${sets ?? '-'} x ${reps ?? '-'}`);
            }
            return parts.join(' · ') || 'Mobility';
        }
        return activity.planned_notes || 'Freeform activity';
    }

    function templateSummary(template) {
        const count = template.activities?.length || 0;
        return `${count} ${count === 1 ? 'activity' : 'activities'}`;
    }

    function setStatus(message, isError, isLoading) {
        els.status.textContent = message || '';
        els.status.style.display = message ? '' : 'none';
        els.status.classList.toggle('gym-status--error', Boolean(isError));
        els.status.classList.toggle('loading', Boolean(isLoading));
        els.status.classList.toggle('loading--with-spinner', Boolean(isLoading));
    }

    function retryDelay() {
        return new Promise(resolve => setTimeout(resolve, 350));
    }

    async function fetchJson(url, options = {}) {
        const method = (options.method || 'GET').toUpperCase();
        const attempts = ['GET', 'PUT', 'PATCH'].includes(method) ? 2 : 1;
        let lastError;
        for (let attempt = 0; attempt < attempts; attempt += 1) {
            try {
                const resp = await fetch(url, options);
                if (!resp.ok) {
                    const detail = await resp.text();
                    const error = new Error(detail || `HTTP ${resp.status}`);
                    error.retryable = resp.status >= 500;
                    throw error;
                }
                if (resp.status === 204) return null;
                return resp.json();
            } catch (error) {
                lastError = error;
                const retryable = error instanceof TypeError || error.name === 'TypeError' || error.retryable;
                if (!retryable || attempt === attempts - 1) throw error;
                await retryDelay();
            }
        }
        throw lastError;
    }

    async function loadTemplates() {
        state.templates = await fetchJson('/api/gym/templates');
    }

    async function loadActivities() {
        state.activities = await fetchJson('/api/gym/activities');
    }

    async function loadSession() {
        state.session = await fetchJson(`/api/gym/session?date=${encodeURIComponent(state.date)}`);
    }

    async function goToPreviousSession() {
        setStatus('Finding previous session…');
        try {
            const previous = await fetchJson(`/api/gym/sessions/previous?before=${encodeURIComponent(state.date)}`);
            if (!previous || !previous.date) {
                setStatus('No previous session.');
                return;
            }
            state.date = previous.date;
            els.date.value = previous.date;
            await refresh();
        } catch (err) {
            console.error('Failed to find previous gym session', err);
            setStatus('Could not find previous session.', true);
        }
    }

    async function refresh() {
        setStatus('Loading gym session…', false, true);
        els.session.style.display = 'none';
        els.start.style.display = 'none';
        try {
            await Promise.all([loadTemplates(), loadActivities(), loadSession()]);
            applyPendingSavesToState();
            render();
            setStatus('');
        } catch (err) {
            console.error('Failed to load gym page', err);
            setStatus('Could not load gym session data.', true);
        }
    }

    function applyPendingSavesToState() {
        if (!state.session) return;
        state.session.activities.forEach(activity => {
            const pending = pendingSaves.get(activity.id);
            if (pending) Object.assign(activity, pending.patch);
        });
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
            ${pendingSaves.size ? `
                <div class="gym-unsaved-banner" role="status">
                    You have unsaved changes. Retrying in the background…
                </div>
            ` : ''}
            <div class="gym-session-header">
                <div>
                    <p class="gym-kicker">${finished ? 'Finished session' : 'Active session'}</p>
                    <h2>${escapeHtml(session.template_name_snapshot)}</h2>
                    <p>${completed} / ${activities.length} complete</p>
                </div>
                <div class="gym-session-actions">
                    <button type="button" class="btn-secondary" data-action="delete-session">
                        ${finished ? 'Discard session' : 'Cancel session'}
                    </button>
                    <button type="button" class="gym-finish-btn" data-action="finish-session" ${finished ? 'disabled' : ''}>
                        ${finished ? 'Finished' : 'Finish'}
                    </button>
                </div>
            </div>
            <div class="gym-activity-list">
                ${activities.map(renderActivity).join('')}
            </div>
            ${finished ? '' : renderAddActivity()}
        `;
    }

    function typeLabel(type) {
        return type.charAt(0).toUpperCase() + type.slice(1);
    }

    function renderAddActivity() {
        return `
            <details class="gym-add-session-activity">
                <summary>Add activity</summary>
                <div class="gym-add-session-activity-panel">
                    <label>
                        Saved activity
                        <select data-add-field="activity_id">
                            <option value="">Custom activity</option>
                            ${state.activities.map(activity => `
                                <option value="${activity.id}">${escapeHtml(activity.name)} (${typeLabel(activity.activity_type)})</option>
                            `).join('')}
                        </select>
                    </label>
                    <label>
                        Type
                        <select data-add-field="activity_type">
                            <option value="strength">Strength</option>
                            <option value="cardio">Cardio</option>
                            <option value="mobility">Mobility</option>
                        </select>
                    </label>
                    <label>
                        Name
                        <input type="text" data-add-field="name" placeholder="Activity name">
                    </label>
                    <div class="gym-add-session-fields" data-add-fields>
                        ${renderAddFields('strength')}
                    </div>
                    <label class="gym-note-label">
                        Note
                        <textarea data-add-field="notes" rows="2" placeholder="Optional note"></textarea>
                    </label>
                    <p class="gym-add-save-library">Custom activities are saved for later.</p>
                    <button type="button" class="gym-save-adjust" data-action="add-session-activity">Add activity</button>
                </div>
            </details>
        `;
    }

    function renderAddFields(type) {
        if (type === 'strength') {
            return `
                <div class="gym-adjust-grid">
                    ${numberAddField('target_weight', 'Weight')}
                    ${selectAddField('target_weight_unit', 'Unit', 'kg', ['kg', 'lbs'])}
                    ${numberAddField('target_sets', 'Sets')}
                    ${numberAddField('target_reps', 'Reps')}
                </div>
            `;
        }
        if (type === 'cardio') {
            return `
                <div class="gym-adjust-grid">
                    ${numberAddField('target_duration_minutes', 'Minutes')}
                    ${textAddField('target_intensity', 'Intensity')}
                    ${numberAddField('target_speed', 'Speed/RPM')}
                    ${selectAddField('target_weight_unit', 'Unit', 'kph', ['kph', 'mph', 'rpm'])}
                </div>
            `;
        }
        if (type === 'mobility') {
            return `
                <div class="gym-adjust-grid">
                    ${numberAddField('target_weight', 'Weight')}
                    ${selectAddField('target_weight_unit', 'Unit', 'kg', ['kg', 'lbs'])}
                    ${numberAddField('target_sets', 'Sets')}
                    ${numberAddField('target_reps', 'Reps')}
                </div>
            `;
        }
        return `
            <div class="gym-adjust-grid">
                ${numberAddField('target_sets', 'Sets')}
                ${numberAddField('target_reps', 'Reps')}
            </div>
        `;
    }

    function numberAddField(field, label) {
        return `
            <label>
                ${label}
                <input type="number" step="0.5" min="0" data-add-field="${field}">
            </label>
        `;
    }

    function textAddField(field, label) {
        return `
            <label>
                ${label}
                <input type="text" data-add-field="${field}">
            </label>
        `;
    }

    function selectAddField(field, label, value, options) {
        return `
            <label>
                ${label}
                <select data-add-field="${field}">
                    ${options.map(option => `<option value="${option}" ${value === option ? 'selected' : ''}>${option}</option>`).join('')}
                </select>
            </label>
        `;
    }

    function previousPerformanceLine(activity) {
        if (!activity.completed || !activity.previous_performance) return '';
        const previous = activity.previous_performance;
        const summary = activitySummary({
            activity_type: activity.substitution_activity_type || activity.activity_type,
            actual_sets: previous.sets,
            actual_reps: previous.reps,
            actual_weight: previous.weight,
            actual_weight_unit: previous.weight_unit,
            actual_duration_minutes: previous.duration_minutes,
            actual_intensity: previous.intensity,
            actual_speed: previous.speed,
        });
        const felt = previous.rating ? ` · felt ${previous.rating}` : '';
        return `<span class="gym-activity-previous">Last time (${escapeHtml(previous.date)}): ${escapeHtml(summary)}${escapeHtml(felt)}</span>`;
    }

    function renderActivity(activity) {
        const checked = activity.completed ? 'checked' : '';
        const doneClass = activity.completed ? ' gym-activity--done' : '';
        const unsavedClass = pendingSaves.has(activity.id) ? ' gym-activity--unsaved' : '';
        const performed = activity.substitution_name_snapshot
            ? {...activity, activity_type: activity.substitution_activity_type, name_snapshot: activity.substitution_name_snapshot}
            : activity;
        return `
            <article class="gym-activity${doneClass}${unsavedClass}" data-activity-id="${activity.id}">
                <label class="gym-activity-main">
                    <input type="checkbox" data-action="toggle-activity" ${checked}>
                    <span>
                        <span class="gym-activity-name">${escapeHtml(performed.name_snapshot)}${pendingSaves.has(activity.id) ? ' <span class="gym-unsaved-chip">Unsaved</span>' : ''}</span>
                        ${activity.substitution_name_snapshot ? `<span class="gym-activity-plan">Instead of ${escapeHtml(activity.name_snapshot)}</span>` : ''}
                        <span class="gym-activity-plan">${escapeHtml(activitySummary(performed))}</span>
                        ${previousPerformanceLine(activity)}
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
                    ${renderAdjustFields(performed)}
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
                    ${numberField('actual_weight', 'Weight', activity.actual_weight)}
                    ${selectField('actual_weight_unit', 'Unit', activity.actual_weight_unit || activity.planned_weight_unit || 'kg', ['kg', 'lbs'])}
                    ${numberField('actual_sets', 'Sets', activity.actual_sets)}
                    ${numberField('actual_reps', 'Reps', activity.actual_reps)}
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

    function matchingTemplateActivity(activity) {
        if (activity.substitution_activity_id) return null;
        const template = state.templates.find(item => item.id === state.session?.template_id);
        if (!template) return null;
        const templateActivity = template.activities.find(item => item.sort_order === activity.sort_order);
        return templateActivity ? {template, templateActivity} : null;
    }

    function completedTemplatePatch(activity) {
        if (activity.activity_type === 'strength') {
            return {
                target_sets: activity.actual_sets,
                target_reps: activity.actual_reps,
                target_weight: activity.actual_weight,
                target_weight_unit: activity.actual_weight_unit || activity.planned_weight_unit,
            };
        }
        if (activity.activity_type === 'cardio') {
            return {
                target_duration_minutes: activity.actual_duration_minutes,
                target_intensity: activity.actual_intensity,
                target_speed: activity.actual_speed,
                target_weight_unit: activity.actual_weight_unit || activity.planned_weight_unit,
            };
        }
        return {
            target_sets: activity.actual_sets,
            target_reps: activity.actual_reps,
            target_weight: activity.actual_weight,
            target_weight_unit: activity.actual_weight_unit || activity.planned_weight_unit,
        };
    }

    function hasTemplateChanges(templateActivity, patch) {
        return Object.entries(patch).some(([field, value]) => (templateActivity[field] ?? null) !== (value ?? null));
    }

    async function maybeUpdateTemplateFromActivity(activity) {
        const match = matchingTemplateActivity(activity);
        if (!match) return;
        const {template, templateActivity} = match;
        const patch = completedTemplatePatch(activity);
        if (!hasTemplateChanges(templateActivity, patch)) return;
        if (!window.confirm('Update the template with these completed values?')) return;
        setStatus('Updating template…');
        try {
            const activities = template.activities.map(item => (
                item.id === templateActivity.id ? {...item, ...patch} : item
            ));
            const updated = await fetchJson(`/api/gym/templates/${template.id}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    name: template.name,
                    description: template.description,
                    activities,
                }),
            });
            Object.assign(template, updated);
            setStatus('Template updated.');
        } catch (err) {
            console.error('Failed to update gym template from completed activity', err);
            setStatus('Activity saved, but the template could not be updated.', true);
        }
    }

    async function updateActivity(activityId, patch, options = {}) {
        const numericId = Number(activityId);
        const activity = state.session.activities.find(item => item.id === numericId);
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
            const allComplete = state.session.activities.length > 0
                && state.session.activities.every(item => item.completed && item.rating);
            if (allComplete && !state.session.completed_at) state.session.completed_at = new Date().toISOString();
            renderSession();
            if (options.promptTemplateUpdate) await maybeUpdateTemplateFromActivity(activity);
        } catch (err) {
            console.error('Failed to update gym activity', err);
            const transient = err instanceof TypeError || err.name === 'TypeError' || err.retryable;
            if (transient) {
                markPendingSave(numericId, patch);
                return;
            }
            setStatus('Could not save activity update. Check your connection and try again.', true);
            try {
                await loadSession();
                applyPendingSavesToState();
                render();
            } catch (reloadError) {
                console.error('Failed to reload gym session after save error', reloadError);
            }
        }
    }

    function markPendingSave(activityId, patch) {
        const existing = pendingSaves.get(activityId);
        const entry = existing || {patch: {}, timer: null};
        entry.patch = {...entry.patch, ...patch};
        pendingSaves.set(activityId, entry);
        renderSession();
        setStatus('Could not save yet. Your edit is kept and will retry in the background.', true);
        schedulePendingRetry(activityId);
    }

    function schedulePendingRetry(activityId) {
        const entry = pendingSaves.get(activityId);
        if (!entry || entry.timer) return;
        entry.timer = setTimeout(() => {
            entry.timer = null;
            retryPendingSave(activityId);
        }, PENDING_RETRY_MS);
    }

    async function retryPendingSave(activityId) {
        const entry = pendingSaves.get(activityId);
        if (!entry || !state.session) return;
        try {
            const updated = await fetchJson(`/api/gym/session-activities/${activityId}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(entry.patch),
            });
            const activity = state.session.activities.find(item => item.id === activityId);
            if (activity) Object.assign(activity, updated);
            pendingSaves.delete(activityId);
            if (!pendingSaves.size) setStatus('Pending changes saved.');
            renderSession();
        } catch (err) {
            console.error('Background save retry failed', err);
            const transient = err instanceof TypeError || err.name === 'TypeError' || err.retryable;
            if (transient) {
                schedulePendingRetry(activityId);
                return;
            }
            pendingSaves.delete(activityId);
            setStatus('Could not save activity update. Check your connection and try again.', true);
            try {
                await loadSession();
                applyPendingSavesToState();
                render();
            } catch (reloadError) {
                console.error('Failed to reload gym session after save error', reloadError);
            }
        }
    }

    async function addSessionActivity(panel) {
        if (!state.session) return;
        const payload = collectAddActivityPayload(panel);
        setStatus('Adding activity…');
        try {
            const added = await fetchJson(`/api/gym/sessions/${state.session.id}/activities`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload),
            });
            state.session.activities.push(added);
            if (!payload.activity_id) await loadActivities();
            renderSession();
            setStatus('');
        } catch (err) {
            console.error('Failed to add gym activity', err);
            setStatus('Could not add activity.', true);
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

    async function deleteSession() {
        if (!state.session) return;
        const finished = state.session.completed_at != null;
        const message = finished
            ? 'Discard this finished gym session? This will permanently delete the session log and all activity details for this date.'
            : 'Cancel this gym session? This will delete the session log for this date.';
        if (!window.confirm(message)) return;
        setStatus(finished ? 'Discarding session…' : 'Cancelling session…');
        try {
            await fetchJson(`/api/gym/sessions/${state.session.id}`, {method: 'DELETE'});
            pendingSaves.clear();
            state.session = null;
            render();
            setStatus('');
        } catch (err) {
            console.error('Failed to discard gym session', err);
            setStatus(finished ? 'Could not discard session.' : 'Could not cancel session.', true);
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

    function collectAddActivityPayload(panel) {
        const payload = {};
        panel.querySelectorAll('[data-add-field]').forEach(input => {
            const field = input.dataset.addField;
            if (field === 'activity_id') {
                if (input.value) payload.activity_id = Number(input.value);
                return;
            }
            if (payload.activity_id && !['save_to_library'].includes(field)) return;
            if (input.type === 'checkbox') {
                payload[field] = input.checked;
                return;
            }
            const value = input.value.trim();
            if (input.type === 'number') {
                payload[field] = value === '' ? null : Number(value);
            } else {
                payload[field] = value === '' ? null : value;
            }
        });
        if (payload.activity_id) delete payload.save_to_library;
        return payload;
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

        els.previous.addEventListener('click', () => {
            goToPreviousSession();
        });

        window.addEventListener('beforeunload', (event) => {
            if (!pendingSaves.size) return;
            event.preventDefault();
            event.returnValue = '';
        });

        els.session.addEventListener('click', (event) => {
            const actionEl = event.target.closest('[data-action]');
            if (!actionEl) return;
            const action = actionEl.dataset.action;
            if (action === 'finish-session') {
                finishSession();
                return;
            }
            if (action === 'delete-session') {
                deleteSession();
                return;
            }
            if (action === 'add-session-activity') {
                const panel = actionEl.closest('.gym-add-session-activity-panel');
                if (panel) addSessionActivity(panel);
                return;
            }
            const card = actionEl.closest('[data-activity-id]');
            if (!card) return;
            const activityId = card.dataset.activityId;
            if (action === 'rate-activity') {
                updateActivity(activityId, {rating: actionEl.dataset.rating});
            }
            if (action === 'save-activity') {
                updateActivity(
                    activityId,
                    collectActivityPatch(card),
                    {promptTemplateUpdate: true},
                );
            }
        });

        els.session.addEventListener('change', (event) => {
            if (event.target.dataset.addField === 'activity_type') {
                const panel = event.target.closest('.gym-add-session-activity-panel');
                const fields = panel?.querySelector('[data-add-fields]');
                if (fields) fields.innerHTML = renderAddFields(event.target.value);
                return;
            }
            if (event.target.dataset.action !== 'toggle-activity') return;
            const card = event.target.closest('[data-activity-id]');
            if (!card) return;
            const patch = event.target.checked
                ? {...collectActivityPatch(card), completed: true}
                : {completed: false};
            updateActivity(
                card.dataset.activityId,
                patch,
                {promptTemplateUpdate: event.target.checked},
            );
        });
    }

    function init() {
        els.date = document.getElementById('gym-date');
        els.status = document.getElementById('gym-status');
        els.session = document.getElementById('gym-session');
        els.start = document.getElementById('gym-start');
        els.templateList = document.getElementById('gym-template-list');
        els.previous = document.getElementById('gym-previous');
        if (!els.date || !els.status || !els.session || !els.start || !els.templateList || !els.previous) return;
        state.date = todayIso();
        els.date.value = state.date;
        bindEvents();
        refresh();
    }

    document.addEventListener('DOMContentLoaded', init);
})();
