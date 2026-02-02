// Overview page JavaScript

async function loadOverview() {
    try {
        // Load daily summaries
        const dailyResp = await fetch('/api/daily?days=365');
        const dailyData = await dailyResp.json();

        // Filter to days with pm_slump data
        const daysWithData = dailyData.filter(d => d.pm_slump !== null);
        const fogDays = daysWithData.filter(d => d.pm_slump === true);

        // Calculate stats
        document.getElementById('total-days').textContent = daysWithData.length;
        document.getElementById('fog-days').textContent = fogDays.length;

        const fogPct = daysWithData.length > 0 ? (fogDays.length / daysWithData.length * 100).toFixed(1) : 0;
        document.getElementById('fog-pct').textContent = fogPct + '%';

        // Calculate current clear streak
        let streak = 0;
        for (let i = daysWithData.length - 1; i >= 0; i--) {
            if (daysWithData[i].pm_slump === false) {
                streak++;
            } else {
                break;
            }
        }
        document.getElementById('clear-streak').textContent = streak + ' days';

    } catch (error) {
        console.error('Error loading overview:', error);
    }

    // Load top correlates
    try {
        const corrResp = await fetch('/api/correlations');
        const correlations = await corrResp.json();

        const top3 = correlations.slice(0, 3);
        const container = document.getElementById('top-correlates');

        if (top3.length === 0) {
            container.innerHTML = '<p>Insufficient data for correlations (need at least 7 days)</p>';
        } else {
            container.innerHTML = top3.map(c => `
                <div style="margin-bottom: 1rem; padding: 1rem; border-left: 3px solid var(--primary-color);">
                    <strong>${c.metric.replace(/_/g, ' ')}</strong><br>
                    Correlation: ${c.coefficient.toFixed(3)} (${c.strength})<br>
                    ${c.fog_day_avg !== null ? `Fog days: ${c.fog_day_avg.toFixed(1)}, Clear days: ${c.clear_day_avg.toFixed(1)}` : ''}
                </div>
            `).join('');
        }
    } catch (error) {
        console.error('Error loading correlations:', error);
        document.getElementById('top-correlates').innerHTML = '<p class="error">Failed to load correlations</p>';
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

// Load on page load
document.addEventListener('DOMContentLoaded', loadOverview);
