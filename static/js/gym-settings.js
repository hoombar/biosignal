(function () {
    'use strict';

    const els = {};
    let templates = [];
    let activities = [];

    function escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function setStatus(message, kind) {
        els.status.textContent = message || '';
        els.status.className = kind ? `save-status save-status--${kind}` : 'save-status';
    }

    async function fetchJson(url, options) {
        const resp = await fetch(url, options);
        if (!resp.ok) {
            const errBody = await resp.json().catch(() => ({}));
            throw new Error(errBody.detail || `HTTP ${resp.status}`);
        }
        if (resp.status === 204) return null;
        return resp.json();
    }

    function emptyActivity(type = 'strength') {
        return {
            activity_type: type,
            name: '',
            target_sets: ['strength', 'mobility'].includes(type) ? 3 : null,
            target_reps: ['strength', 'mobility'].includes(type) ? 12 : null,
            target_weight: null,
            target_weight_unit: type === 'strength' ? 'kg' : (type === 'cardio' ? 'kph' : null),
            target_duration_minutes: type === 'cardio' ? 8 : null,
            target_intensity: '',
            target_speed: null,
            notes: '',
        };
    }

    function renderActivityRow(activity = emptyActivity()) {
        const type = ['strength', 'cardio', 'mobility'].includes(activity.activity_type)
            ? activity.activity_type
            : 'mobility';
        const activityIdAttr = activity.activity_id ? ` data-activity-id="${activity.activity_id}"` : '';
        return `
            <div class="gym-settings-activity" data-activity-row data-activity-type="${type}"${activityIdAttr}>
                <div class="gym-settings-activity-header">
                    <label class="gym-settings-field">
                        <span>Type</span>
                        <select class="settings-input" data-action="change-activity-type">
                            ${['strength', 'cardio', 'mobility'].map(option => `
                                <option value="${option}" ${type === option ? 'selected' : ''}>${typeLabel(option)}</option>
                            `).join('')}
                        </select>
                    </label>
                    <div class="gym-settings-activity-actions" aria-label="Activity actions">
                        <button type="button" class="gym-settings-icon-btn" data-action="move-activity-up" aria-label="Move activity up">↑</button>
                        <button type="button" class="gym-settings-icon-btn" data-action="move-activity-down" aria-label="Move activity down">↓</button>
                        <button type="button" class="gym-settings-icon-btn gym-settings-icon-btn--danger" data-action="remove-activity" aria-label="Remove activity">×</button>
                    </div>
                </div>
                <div class="gym-settings-activity-fields">
                    <div class="gym-settings-activity-main">
                        <label class="gym-settings-field gym-settings-field--name">
                            <span>Name</span>
                            <input type="text" class="settings-input gym-settings-name" data-field="name" placeholder="Activity name" value="${escapeHtml(activity.name)}" required>
                        </label>
                    </div>
                    <div class="gym-settings-activity-details">
                        ${activityFieldsHtml(activity, type)}
                    </div>
                </div>
            </div>
        `;
    }

    function typeLabel(type) {
        return type.charAt(0).toUpperCase() + type.slice(1);
    }

    function showActivityTypeChooser() {
        const existing = els.activities.querySelector('[data-activity-type-chooser]');
        if (existing) {
            existing.remove();
            return;
        }
        els.activities.insertAdjacentHTML('beforeend', `
            <div class="gym-activity-type-chooser" data-activity-type-chooser>
                <button type="button" class="btn-secondary gym-activity-type-choice" data-action="choose-activity-type" data-activity-type="strength">Add strength</button>
                <button type="button" class="btn-secondary gym-activity-type-choice" data-action="choose-activity-type" data-activity-type="cardio">Add cardio</button>
                <button type="button" class="btn-secondary gym-activity-type-choice" data-action="choose-activity-type" data-activity-type="mobility">Add mobility</button>
            </div>
        `);
    }

    function activityFieldsHtml(activity, type) {
        if (type === 'strength') {
            return `
                ${fieldHtml('target_sets', 'Sets', 'number', activity.target_sets, {step: '1'})}
                ${fieldHtml('target_reps', 'Reps', 'number', activity.target_reps, {step: '1'})}
                ${fieldHtml('target_weight', 'Weight', 'number', activity.target_weight, {step: '0.5'})}
                ${unitSelectHtml('target_weight_unit', 'Unit', activity.target_weight_unit, ['kg', 'lbs'])}
            `;
        }
        if (type === 'cardio') {
            return `
                ${fieldHtml('target_duration_minutes', 'Minutes', 'number', activity.target_duration_minutes, {step: '0.5'})}
                ${fieldHtml('target_intensity', 'Intensity', 'text', activity.target_intensity)}
                ${fieldHtml('target_speed', 'Speed', 'number', activity.target_speed, {step: '0.5'})}
                ${unitSelectHtml('target_weight_unit', 'Unit', activity.target_weight_unit, ['kph', 'mph', 'rpm'])}
            `;
        }
        return `
            ${fieldHtml('target_sets', 'Sets', 'number', activity.target_sets, {step: '1'})}
            ${fieldHtml('target_reps', 'Reps', 'number', activity.target_reps, {step: '1'})}
        `;
    }

    function fieldHtml(field, label, type, value, options = {}) {
        const step = options.step ? ` step="${options.step}"` : '';
        const min = type === 'number' ? ' min="0"' : '';
        const wideClass = options.wide ? ' gym-settings-field--wide' : '';
        return `
            <label class="gym-settings-field${wideClass}">
                <span>${label}</span>
                <input type="${type}" class="settings-input" data-field="${field}"${min}${step} value="${escapeHtml(value ?? '')}">
            </label>
        `;
    }

    function unitSelectHtml(field, label, value, units) {
        const selected = value || units[0];
        return `
            <label class="gym-settings-field">
                <span>${label}</span>
                <select class="settings-input" data-field="${field}">
                    ${units.map(unit => `<option value="${unit}" ${selected === unit ? 'selected' : ''}>${unit}</option>`).join('')}
                </select>
            </label>
        `;
    }

    function renderTemplateList() {
        if (templates.length === 0) {
            els.list.innerHTML = '<p class="settings-desc">No gym templates yet. Create your first current plan here.</p>';
            return;
        }
        els.list.innerHTML = templates.map(template => `
            <article class="gym-settings-template ${template.archived ? 'gym-settings-template--archived' : ''}">
                <div>
                    <h4>${escapeHtml(template.name)}</h4>
                    <p>${template.activities.length} ${template.activities.length === 1 ? 'activity' : 'activities'}${template.archived ? ' · archived' : ''}</p>
                </div>
                <div class="gym-settings-template-actions">
                    <button type="button" class="btn-secondary" data-action="edit-template" data-template-id="${template.id}">Edit</button>
                    ${template.archived
                        ? `<button type="button" class="btn-secondary" data-action="unarchive-template" data-template-id="${template.id}">Unarchive</button>`
                        : `<button type="button" class="btn-secondary" data-action="archive-template" data-template-id="${template.id}">Archive</button>`}
                </div>
            </article>
        `).join('');
    }

    async function loadTemplates() {
        templates = await fetchJson('/api/gym/templates?include_archived=true');
        renderTemplateList();
    }

    async function loadActivities() {
        activities = await fetchJson('/api/gym/activities?include_archived=true');
        renderActivityList();
    }

    function renderActivityList() {
        if (!els.activityList) return;
        const visible = activities;
        if (visible.length === 0) {
            els.activityList.innerHTML = '<p class="settings-desc">No saved activities yet. Add common exercises here, or create them while logging a session.</p>';
            return;
        }
        els.activityList.innerHTML = visible.map(activity => `
            <article class="gym-settings-template ${activity.archived ? 'gym-settings-template--archived' : ''}">
                <div>
                    <h4>${escapeHtml(activity.name)}</h4>
                    <p>${typeLabel(activity.activity_type)}${activity.archived ? ' · archived' : ''}</p>
                </div>
                <div class="gym-settings-template-actions">
                    <button type="button" class="btn-secondary" data-action="edit-activity" data-activity-id="${activity.id}">Edit</button>
                    ${activity.archived ? '' : `<button type="button" class="btn-secondary" data-action="archive-activity" data-activity-id="${activity.id}">Archive</button>`}
                </div>
            </article>
        `).join('');
    }

    function resetForm() {
        els.id.value = '';
        els.name.value = '';
        els.description.value = '';
        els.activities.innerHTML = '';
        setStatus('');
    }

    function resetActivityForm() {
        els.activityId.value = '';
        els.activityEditor.innerHTML = renderActivityRow(emptyActivity('strength'));
        setActivityStatus('');
    }

    function setActivityStatus(message, kind) {
        els.activityStatus.textContent = message || '';
        els.activityStatus.className = kind ? `save-status save-status--${kind}` : 'save-status';
    }

    function editTemplate(templateId) {
        const template = templates.find(row => row.id === Number(templateId));
        if (!template) return;
        els.id.value = template.id;
        els.name.value = template.name;
        els.description.value = template.description || '';
        els.activities.innerHTML = (template.activities.length ? template.activities : [emptyActivity()])
            .map(renderActivityRow)
            .join('');
        setStatus(`Editing ${template.name}`);
    }

    function editActivity(activityId) {
        const activity = activities.find(row => row.id === Number(activityId));
        if (!activity) return;
        els.activityId.value = activity.id;
        els.activityEditor.innerHTML = renderActivityRow(activity);
        setActivityStatus(`Editing ${activity.name}`);
    }

    function numberOrNull(value) {
        const trimmed = String(value || '').trim();
        return trimmed === '' ? null : Number(trimmed);
    }

    function textOrNull(value) {
        const trimmed = String(value || '').trim();
        return trimmed === '' ? null : trimmed;
    }

    function readActivity(row) {
        const data = {activity_type: row.dataset.activityType};
        if (row.dataset.activityId) data.activity_id = Number(row.dataset.activityId);
        row.querySelectorAll('[data-field]').forEach(input => {
            const field = input.dataset.field;
            if ([
                'target_sets',
                'target_reps',
                'target_weight',
                'target_duration_minutes',
                'target_speed',
            ].includes(field)) {
                data[field] = numberOrNull(input.value);
            } else {
                data[field] = textOrNull(input.value);
            }
        });
        data.name = data.name || '';
        return normalizeActivityForType(data);
    }

    function readLibraryActivity() {
        const row = els.activityEditor.querySelector('[data-activity-row]');
        return row ? readActivity(row) : emptyActivity('strength');
    }

    function normalizeActivityForType(data) {
        if (data.activity_type === 'strength') {
            data.target_weight_unit = ['kg', 'lbs'].includes(data.target_weight_unit) ? data.target_weight_unit : 'kg';
            data.target_duration_minutes = null;
            data.target_intensity = null;
            data.target_speed = null;
        } else if (data.activity_type === 'cardio') {
            data.target_weight_unit = ['kph', 'mph', 'rpm'].includes(data.target_weight_unit) ? data.target_weight_unit : 'kph';
            data.target_sets = null;
            data.target_reps = null;
            data.target_weight = null;
        } else if (data.activity_type === 'mobility') {
            data.target_weight = null;
            data.target_weight_unit = null;
            data.target_duration_minutes = null;
            data.target_intensity = null;
            data.target_speed = null;
            data.notes = null;
        }
        return data;
    }

    function readPayload() {
        return {
            name: els.name.value.trim(),
            description: textOrNull(els.description.value),
            activities: Array.from(els.activities.querySelectorAll('[data-activity-row]'))
                .map(readActivity)
                .filter(activity => activity.name),
        };
    }

    async function saveTemplate(event) {
        event.preventDefault();
        const id = els.id.value;
        const payload = readPayload();
        if (!payload.name) {
            setStatus('Template name is required', 'err');
            return;
        }
        if (payload.activities.length === 0) {
            setStatus('Add at least one activity', 'err');
            return;
        }
        setStatus('Saving…');
        try {
            await fetchJson(id ? `/api/gym/templates/${id}` : '/api/gym/templates', {
                method: id ? 'PUT' : 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload),
            });
            await loadTemplates();
            resetForm();
            setStatus('Saved', 'ok');
        } catch (err) {
            setStatus(err.message, 'err');
        }
    }

    async function saveActivity(event) {
        event.preventDefault();
        const id = els.activityId.value;
        const payload = readLibraryActivity();
        delete payload.activity_id;
        if (!payload.name) {
            setActivityStatus('Activity name is required', 'err');
            return;
        }
        setActivityStatus('Saving…');
        try {
            await fetchJson(id ? `/api/gym/activities/${id}` : '/api/gym/activities', {
                method: id ? 'PUT' : 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload),
            });
            await loadActivities();
            resetActivityForm();
            setActivityStatus('Saved', 'ok');
        } catch (err) {
            setActivityStatus(err.message, 'err');
        }
    }

    async function archiveTemplate(templateId) {
        setStatus('Archiving…');
        try {
            await fetchJson(`/api/gym/templates/${templateId}`, {method: 'DELETE'});
            await loadTemplates();
            if (els.id.value === String(templateId)) resetForm();
            setStatus('Archived', 'ok');
        } catch (err) {
            setStatus(err.message, 'err');
        }
    }

    async function unarchiveTemplate(templateId) {
        setStatus('Unarchiving…');
        try {
            await fetchJson(`/api/gym/templates/${templateId}/unarchive`, {method: 'POST'});
            await loadTemplates();
            setStatus('Unarchived', 'ok');
        } catch (err) {
            setStatus(err.message, 'err');
        }
    }

    async function archiveActivity(activityId) {
        setActivityStatus('Archiving…');
        try {
            await fetchJson(`/api/gym/activities/${activityId}`, {method: 'DELETE'});
            await loadActivities();
            if (els.activityId.value === String(activityId)) resetActivityForm();
            setActivityStatus('Archived', 'ok');
        } catch (err) {
            setActivityStatus(err.message, 'err');
        }
    }

    function showSavedActivityChooser() {
        const existing = els.activities.querySelector('[data-saved-activity-chooser]');
        if (existing) {
            existing.remove();
            return;
        }
        const activeActivities = activities.filter(activity => !activity.archived);
        const html = activeActivities.length === 0
            ? '<p class="settings-desc">No saved activities available yet.</p>'
            : activeActivities.map(activity => `
                <article class="gym-settings-template gym-settings-template--selectable">
                    <div>
                        <h4>${escapeHtml(activity.name)}</h4>
                        <p>${typeLabel(activity.activity_type)}</p>
                    </div>
                    <button type="button" class="btn-secondary" data-action="choose-saved-activity" data-activity-id="${activity.id}">Add</button>
                </article>
            `).join('');
        els.activities.insertAdjacentHTML('beforeend', `
            <div class="gym-activity-type-chooser" data-saved-activity-chooser>${html}</div>
        `);
    }

    function changeActivityType(row, type) {
        const current = readActivity(row);
        const replacement = emptyActivity(type);
        replacement.name = current.name || '';
        row.replaceWith(document.createRange().createContextualFragment(renderActivityRow(replacement)));
    }

    function bindEvents() {
        els.activityForm.addEventListener('submit', saveActivity);
        els.activityReset.addEventListener('click', resetActivityForm);
        els.activityRefresh.addEventListener('click', loadActivities);
        els.activityList.addEventListener('click', (event) => {
            const button = event.target.closest('[data-action]');
            if (!button) return;
            if (button.dataset.action === 'edit-activity') editActivity(button.dataset.activityId);
            if (button.dataset.action === 'archive-activity') archiveActivity(button.dataset.activityId);
        });
        els.activityEditor.addEventListener('change', (event) => {
            if (event.target.dataset.action !== 'change-activity-type') return;
            const row = event.target.closest('[data-activity-row]');
            if (row) changeActivityType(row, event.target.value);
        });
        els.form.addEventListener('submit', saveTemplate);
        els.reset.addEventListener('click', resetForm);
        els.refresh.addEventListener('click', loadTemplates);
        els.addSavedActivity.addEventListener('click', showSavedActivityChooser);
        els.addActivity.addEventListener('click', showActivityTypeChooser);
        els.activities.addEventListener('change', (event) => {
            if (event.target.dataset.action !== 'change-activity-type') return;
            const row = event.target.closest('[data-activity-row]');
            if (row) changeActivityType(row, event.target.value);
        });
        els.activities.addEventListener('click', (event) => {
            const button = event.target.closest('[data-action]');
            if (!button) return;
            if (button.dataset.action === 'choose-saved-activity') {
                const chooser = button.closest('[data-saved-activity-chooser]');
                const activity = activities.find(row => row.id === Number(button.dataset.activityId));
                if (!activity) return;
                chooser.insertAdjacentHTML('beforebegin', renderActivityRow({...activity, activity_id: activity.id}));
                chooser.remove();
                return;
            }
            if (button.dataset.action === 'choose-activity-type') {
                const chooser = button.closest('[data-activity-type-chooser]');
                const type = button.dataset.activityType;
                chooser.insertAdjacentHTML('beforebegin', renderActivityRow(emptyActivity(type)));
                chooser.remove();
                return;
            }
            const row = button.closest('[data-activity-row]');
            if (!row) return;
            if (button.dataset.action === 'move-activity-up') {
                const previous = row.previousElementSibling;
                if (previous) els.activities.insertBefore(row, previous);
                return;
            }
            if (button.dataset.action === 'move-activity-down') {
                const next = row.nextElementSibling;
                if (next) els.activities.insertBefore(next, row);
                return;
            }
            if (button.dataset.action !== 'remove-activity') return;
            row.remove();
        });
        els.list.addEventListener('click', (event) => {
            const button = event.target.closest('[data-action]');
            if (!button) return;
            if (button.dataset.action === 'edit-template') editTemplate(button.dataset.templateId);
            if (button.dataset.action === 'archive-template') archiveTemplate(button.dataset.templateId);
            if (button.dataset.action === 'unarchive-template') unarchiveTemplate(button.dataset.templateId);
        });
    }

    async function init() {
        els.activityForm = document.getElementById('gym-activity-form');
        els.activityId = document.getElementById('gym-activity-id');
        els.activityEditor = document.getElementById('gym-activity-editor');
        els.activityReset = document.getElementById('gym-activity-reset');
        els.activityRefresh = document.getElementById('gym-activity-refresh');
        els.activityStatus = document.getElementById('gym-activity-status');
        els.activityList = document.getElementById('gym-activity-list');
        els.form = document.getElementById('gym-template-form');
        els.id = document.getElementById('gym-template-id');
        els.name = document.getElementById('gym-template-name');
        els.description = document.getElementById('gym-template-description');
        els.activities = document.getElementById('gym-template-activities');
        els.addSavedActivity = document.getElementById('gym-add-saved-activity');
        els.addActivity = document.getElementById('gym-add-activity');
        els.reset = document.getElementById('gym-template-reset');
        els.refresh = document.getElementById('gym-template-refresh');
        els.status = document.getElementById('gym-template-status');
        els.list = document.getElementById('gym-template-list');
        if (!els.form) return;
        bindEvents();
        resetActivityForm();
        resetForm();
        try {
            await Promise.all([loadActivities(), loadTemplates()]);
        } catch (err) {
            setStatus(`Failed to load gym data: ${err.message}`, 'err');
        }
    }

    document.addEventListener('DOMContentLoaded', init);
})();
