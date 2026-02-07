// Overview page JavaScript

const STORAGE_KEY = 'biosignal_target_habit';

async function loadHabitSelector() {
    try {
        const resp = await fetch('/api/habits/names');
        const habitNames = await resp.json();

        const select = document.getElementById('target-habit');
        const savedHabit = localStorage.getItem(STORAGE_KEY);

        select.innerHTML = '<option value="">-- Select a habit --</option>' +
            habitNames.map(name =>
                `<option value="${name}" ${name === savedHabit ? 'selected' : ''}>${name.replace(/_/g, ' ')}</option>`
            ).join('');

        // Load correlations if a habit was previously selected
        if (savedHabit && habitNames.includes(savedHabit)) {
            loadCorrelations();
        }
    } catch (error) {
        console.error('Error loading habit names:', error);
        document.getElementById('target-habit').innerHTML = '<option value="">Failed to load habits</option>';
    }
}

async function loadCorrelations() {
    const select = document.getElementById('target-habit');
    const targetHabit = select.value;
    const container = document.getElementById('top-correlates');

    if (!targetHabit) {
        container.innerHTML = '<p>Select a habit to see correlations</p>';
        return;
    }

    // Save selection
    localStorage.setItem(STORAGE_KEY, targetHabit);

    container.innerHTML = '<p class="loading">Loading correlations...</p>';

    try {
        const corrResp = await fetch(`/api/correlations?target_habit=${encodeURIComponent(targetHabit)}`);
        const correlations = await corrResp.json();

        const top3 = correlations.slice(0, 3);

        if (top3.length === 0) {
            container.innerHTML = '<p>Insufficient data for correlations (need at least 5 days)</p>';
        } else {
            container.innerHTML = top3.map(c => `
                <div style="margin-bottom: 1rem; padding: 1rem; border-left: 3px solid var(--primary-color);">
                    <strong>${c.metric.replace(/_/g, ' ')}</strong><br>
                    Correlation: ${c.coefficient.toFixed(3)} (${c.strength})<br>
                    ${c.fog_day_avg !== null ? `Positive days: ${c.fog_day_avg.toFixed(1)}, Negative days: ${c.clear_day_avg.toFixed(1)}` : ''}
                </div>
            `).join('');
        }
    } catch (error) {
        console.error('Error loading correlations:', error);
        container.innerHTML = '<p class="error">Failed to load correlations</p>';
    }
}

async function loadOverview() {
    // Load habit selector first
    await loadHabitSelector();

    try {
        // Load daily summaries
        const dailyResp = await fetch('/api/daily?days=365');
        const dailyData = await dailyResp.json();

        // Count days with any habit data
        const daysWithData = dailyData.filter(d => d.habits && d.habits.length > 0);

        // Calculate stats based on selected habit
        const targetHabit = document.getElementById('target-habit').value;
        let fogDays = [];
        let filteredDays = daysWithData;

        if (targetHabit) {
            filteredDays = daysWithData.filter(d => {
                const habit = d.habits.find(h => h.name === targetHabit);
                return habit !== undefined;
            });
            fogDays = filteredDays.filter(d => {
                const habit = d.habits.find(h => h.name === targetHabit);
                return habit && habit.value === 1;
            });
        }

        document.getElementById('total-days').textContent = filteredDays.length;
        document.getElementById('fog-days').textContent = fogDays.length;

        const fogPct = filteredDays.length > 0 ? (fogDays.length / filteredDays.length * 100).toFixed(1) : 0;
        document.getElementById('fog-pct').textContent = fogPct + '%';

        // Calculate current streak of negative (clear) days
        let streak = 0;
        if (targetHabit) {
            for (let i = filteredDays.length - 1; i >= 0; i--) {
                const habit = filteredDays[i].habits.find(h => h.name === targetHabit);
                if (habit && habit.value === 0) {
                    streak++;
                } else {
                    break;
                }
            }
        }
        document.getElementById('clear-streak').textContent = streak + ' days';

    } catch (error) {
        console.error('Error loading overview:', error);
    }

    // Load sync status
    try {
        const statusResp = await fetch('/api/sync/status');
        const status = await statusResp.json();

        const container = document.getElementById('sync-status');
        container.innerHTML = `
            <p><strong>Last Garmin sync:</strong> ${status.garmin_last_sync ? new Date(status.garmin_last_sync).toLocaleString() : 'Never'} (${status.garmin_status})</p>
            <p><strong>Last HabitSync sync:</strong> ${status.habitsync_last_sync ? new Date(status.habitsync_last_sync).toLocaleString() : 'Never'} (${status.habitsync_status})</p>
        `;
    } catch (error) {
        console.error('Error loading sync status:', error);
    }

    // Check Garmin auth status
    try {
        const authResp = await fetch('/api/garmin/auth/status');
        const authData = await authResp.json();

        if (authData.status !== 'valid') {
            const btn = document.getElementById('sync-btn');
            btn.textContent = 'Set Up Garmin';
            btn.onclick = () => window.location.href = '/setup/garmin';
            btn.style.backgroundColor = 'var(--warning-color)';
        }
    } catch (error) {
        console.error('Error checking Garmin auth:', error);
    }
}

async function triggerSync() {
    const btn = document.getElementById('sync-btn');
    btn.disabled = true;
    btn.textContent = 'Syncing...';

    try {
        await fetch('/api/sync/all', { method: 'POST' });
        alert('Sync started in background. Check status in a moment.');
    } catch (error) {
        alert('Failed to start sync: ' + error.message);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Run Manual Sync';
    }
}

let backfillPollInterval = null;

async function startBackfill() {
    const days = parseInt(document.getElementById('backfill-days').value);
    if (!days || days < 1 || days > 365) {
        alert('Please enter a number between 1 and 365.');
        return;
    }

    const btn = document.getElementById('backfill-btn');
    btn.disabled = true;
    btn.textContent = 'Starting...';

    try {
        const resp = await fetch('/api/sync/backfill', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ days })
        });

        if (resp.status === 409) {
            // Already running, just start polling
            showBackfillProgress();
            pollBackfillStatus();
            return;
        }

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || 'Failed to start backfill');
        }

        showBackfillProgress();
        pollBackfillStatus();

    } catch (error) {
        alert('Failed to start backfill: ' + error.message);
        btn.disabled = false;
        btn.textContent = 'Start Backfill';
    }
}

function showBackfillProgress() {
    document.getElementById('backfill-progress').style.display = 'block';
    document.getElementById('backfill-result').style.display = 'none';
    document.getElementById('backfill-btn').disabled = true;
    document.getElementById('backfill-btn').textContent = 'Backfill Running...';
    document.getElementById('backfill-days').disabled = true;
}

function pollBackfillStatus() {
    if (backfillPollInterval) clearInterval(backfillPollInterval);

    backfillPollInterval = setInterval(async () => {
        try {
            const resp = await fetch('/api/sync/backfill/status');
            const status = await resp.json();

            const done = (status.days_completed || 0) + (status.days_failed || 0);
            const total = status.total_days || 1;
            const pct = Math.round((done / total) * 100);

            const bar = document.getElementById('backfill-bar');
            bar.style.width = pct + '%';

            const text = document.getElementById('backfill-status-text');
            text.textContent = `${done} / ${total} days processed (${status.days_completed || 0} succeeded, ${status.days_failed || 0} failed)`;

            if (!status.is_running && done > 0) {
                clearInterval(backfillPollInterval);
                backfillPollInterval = null;
                onBackfillComplete(status);
            }
        } catch (error) {
            console.error('Error polling backfill status:', error);
        }
    }, 3000);
}

function onBackfillComplete(status) {
    document.getElementById('backfill-btn').disabled = false;
    document.getElementById('backfill-btn').textContent = 'Start Backfill';
    document.getElementById('backfill-days').disabled = false;

    const bar = document.getElementById('backfill-bar');
    bar.style.width = '100%';

    const resultDiv = document.getElementById('backfill-result');
    resultDiv.style.display = 'block';

    const failed = status.days_failed || 0;
    if (failed === 0) {
        resultDiv.innerHTML = `<p style="color: var(--success-color); margin-top: 1rem;">Backfill complete — ${status.days_completed} days synced successfully.</p>`;
    } else {
        resultDiv.innerHTML = `<p style="color: var(--warning-color); margin-top: 1rem;">Backfill complete — ${status.days_completed} succeeded, ${failed} failed. You can re-run to retry failed days.</p>`;
    }
}

async function checkBackfillOnLoad() {
    try {
        const resp = await fetch('/api/sync/backfill/status');
        const status = await resp.json();
        if (status.is_running) {
            showBackfillProgress();
            pollBackfillStatus();
        }
    } catch (error) {
        // Ignore - endpoint may not exist on older versions
    }
}

// Load on page load
document.addEventListener('DOMContentLoaded', () => {
    loadOverview();
    document.getElementById('backfill-btn').addEventListener('click', startBackfill);
    checkBackfillOnLoad();
});
