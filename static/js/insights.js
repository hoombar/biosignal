// Insights page JavaScript

async function loadInsights() {
    try {
        const resp = await fetch('/api/insights');
        const insights = await resp.json();

        const container = document.getElementById('insights-list');

        if (insights.length === 0) {
            container.innerHTML = '<p>No insights yet. Need at least 7 days of data with PM slump tracking.</p>';
            return;
        }

        container.innerHTML = insights.map(insight => {
            const icon = insight.confidence === 'high' ? '✓' :
                        insight.confidence === 'medium' ? '!' : '?';
            const color = insight.confidence === 'high' ? 'var(--success-color)' :
                         insight.confidence === 'medium' ? 'var(--warning-color)' :
                         'var(--text-secondary)';

            return `
                <div style="margin-bottom: 1.5rem; padding: 1rem; border: 1px solid var(--border-color); border-radius: 6px;">
                    <div style="display: flex; align-items: start; gap: 1rem;">
                        <div style="font-size: 1.5rem; color: ${color};">${icon}</div>
                        <div style="flex: 1;">
                            <p style="margin: 0; font-size: 1.1rem;">${insight.text}</p>
                            <p style="margin: 0.5rem 0 0; font-size: 0.875rem; color: var(--text-secondary);">
                                Confidence: ${insight.confidence}
                                ${insight.effect_size ? ` • Effect size: ${insight.effect_size.toFixed(2)}` : ''}
                            </p>
                        </div>
                    </div>
                </div>
            `;
        }).join('');

    } catch (error) {
        console.error('Error loading insights:', error);
        document.getElementById('insights-list').innerHTML = '<p class="error">Failed to load insights</p>';
    }
}

async function loadPatterns() {
    try {
        const resp = await fetch('/api/patterns');
        const patterns = await resp.json();

        const container = document.getElementById('patterns-list');

        if (patterns.length === 0) {
            container.innerHTML = '<p>No patterns detected yet.</p>';
            return;
        }

        container.innerHTML = '<table style="width: 100%; border-collapse: collapse;">' +
            '<thead><tr>' +
            '<th style="text-align: left; padding: 0.5rem;">Condition</th>' +
            '<th style="text-align: right; padding: 0.5rem;">Fog Probability</th>' +
            '<th style="text-align: right; padding: 0.5rem;">Baseline</th>' +
            '<th style="text-align: right; padding: 0.5rem;">Relative Risk</th>' +
            '<th style="text-align: right; padding: 0.5rem;">Sample Size</th>' +
            '</tr></thead><tbody>' +
            patterns.map(p => `
                <tr style="border-top: 1px solid var(--border-color);">
                    <td style="padding: 0.5rem;">${p.description}</td>
                    <td style="text-align: right; padding: 0.5rem;">${(p.probability * 100).toFixed(0)}%</td>
                    <td style="text-align: right; padding: 0.5rem;">${(p.baseline_probability * 100).toFixed(0)}%</td>
                    <td style="text-align: right; padding: 0.5rem; font-weight: bold; color: ${p.relative_risk > 1 ? 'var(--danger-color)' : 'var(--success-color)'};">
                        ${p.relative_risk.toFixed(2)}x
                    </td>
                    <td style="text-align: right; padding: 0.5rem;">${p.sample_size}</td>
                </tr>
            `).join('') +
            '</tbody></table>';

    } catch (error) {
        console.error('Error loading patterns:', error);
        document.getElementById('patterns-list').innerHTML = '<p class="error">Failed to load patterns</p>';
    }
}

function exportData(format, days) {
    window.location.href = `/api/export?format=${format}&days=${days}`;
}

// Load on page load
document.addEventListener('DOMContentLoaded', () => {
    loadInsights();
    loadPatterns();
});
