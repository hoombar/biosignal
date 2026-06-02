(function () {
    'use strict';

    const els = {};
    let templates = [];

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
            target_sets: type === 'strength' ? 3 : null,
            target_reps: type === 'strength' ? 12 : null,
            target_weight: null,
            target_weight_unit: type === 'strength' ? 'kg' : null,
            target_duration_minutes: type === 'cardio' ? 8 : null,
            target_intensity: '',
            target_speed: null,
            notes: '',
        };
    }

    function renderActivityRow(activity = emptyActivity()) {
        const type = activity.activity_type || 'strength';
        return `
            <div class="gym-settings-activity" data-activity-row>
                <select class="settings-input" data-field="activity_type" aria-label="Activity type">
                    <option value="strength" ${type === 'strength' ? 'selected' : ''}>Strength</option>
                    <option value="cardio" ${type === 'cardio' ? 'selected' : ''}>Cardio</option>
                    <option value="freeform" ${type === 'freeform' ? 'selected' : ''}>Freeform</option>
                </select>
                <input type="text" class="settings-input gym-settings-name" data-field="name" placeholder="Activity name" value="${escapeHtml(activity.name)}" required>
                <input type="number" class="settings-input" data-field="target_sets" min="0" step="1" placeholder="Sets" value="${escapeHtml(activity.target_sets ?? '')}">
                <input type="number" class="settings-input" data-field="target_reps" min="0" step="1" placeholder="Reps" value="${escapeHtml(activity.target_reps ?? '')}">
                <input type="number" class="settings-input" data-field="target_weight" min="0" step="0.5" placeholder="Weight" value="${escapeHtml(activity.target_weight ?? '')}">
                <input type="text" class="settings-input" data-field="target_weight_unit" placeholder="Unit" value="${escapeHtml(activity.target_weight_unit ?? '')}">
                <input type="number" class="settings-input" data-field="target_duration_minutes" min="0" step="0.5" placeholder="Minutes" value="${escapeHtml(activity.target_duration_minutes ?? '')}">
                <input type="text" class="settings-input" data-field="target_intensity" placeholder="Level / intensity" value="${escapeHtml(activity.target_intensity ?? '')}">
                <input type="number" class="settings-input" data-field="target_speed" min="0" step="0.5" placeholder="Speed/RPM" value="${escapeHtml(activity.target_speed ?? '')}">
                <input type="text" class="settings-input gym-settings-notes" data-field="notes" placeholder="Notes" value="${escapeHtml(activity.notes ?? '')}">
                <button type="button" class="btn-secondary" data-action="remove-activity">Remove</button>
            </div>
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
                    <button type="button" class="btn-secondary" data-action="archive-template" data-template-id="${template.id}" ${template.archived ? 'disabled' : ''}>Archive</button>
                </div>
            </article>
        `).join('');
    }

    async function loadTemplates() {
        templates = await fetchJson('/api/gym/templates?include_archived=true');
        renderTemplateList();
    }

    function resetForm() {
        els.id.value = '';
        els.name.value = '';
        els.description.value = '';
        els.activities.innerHTML = renderActivityRow(emptyActivity('cardio')) + renderActivityRow(emptyActivity('strength'));
        setStatus('');
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

    function numberOrNull(value) {
        const trimmed = String(value || '').trim();
        return trimmed === '' ? null : Number(trimmed);
    }

    function textOrNull(value) {
        const trimmed = String(value || '').trim();
        return trimmed === '' ? null : trimmed;
    }

    function readActivity(row) {
        const data = {};
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

    function bindEvents() {
        els.form.addEventListener('submit', saveTemplate);
        els.reset.addEventListener('click', resetForm);
        els.refresh.addEventListener('click', loadTemplates);
        els.addActivity.addEventListener('click', () => {
            els.activities.insertAdjacentHTML('beforeend', renderActivityRow());
        });
        els.activities.addEventListener('click', (event) => {
            const button = event.target.closest('[data-action="remove-activity"]');
            if (!button) return;
            button.closest('[data-activity-row]').remove();
            if (!els.activities.querySelector('[data-activity-row]')) {
                els.activities.insertAdjacentHTML('beforeend', renderActivityRow());
            }
        });
        els.list.addEventListener('click', (event) => {
            const button = event.target.closest('[data-action]');
            if (!button) return;
            if (button.dataset.action === 'edit-template') editTemplate(button.dataset.templateId);
            if (button.dataset.action === 'archive-template') archiveTemplate(button.dataset.templateId);
        });
    }

    async function init() {
        els.form = document.getElementById('gym-template-form');
        els.id = document.getElementById('gym-template-id');
        els.name = document.getElementById('gym-template-name');
        els.description = document.getElementById('gym-template-description');
        els.activities = document.getElementById('gym-template-activities');
        els.addActivity = document.getElementById('gym-add-activity');
        els.reset = document.getElementById('gym-template-reset');
        els.refresh = document.getElementById('gym-template-refresh');
        els.status = document.getElementById('gym-template-status');
        els.list = document.getElementById('gym-template-list');
        if (!els.form) return;
        bindEvents();
        resetForm();
        try {
            await loadTemplates();
        } catch (err) {
            setStatus(`Failed to load gym templates: ${err.message}`, 'err');
        }
    }

    document.addEventListener('DOMContentLoaded', init);
})();
