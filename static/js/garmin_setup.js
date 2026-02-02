// Garmin Setup page JavaScript

let currentSessionId = null;

async function checkStatus() {
    try {
        const resp = await fetch('/api/garmin/auth/status');
        const data = await resp.json();

        const container = document.getElementById('auth-status');

        if (data.status === 'valid') {
            container.innerHTML = `
                <p><span class="status-badge valid">Connected</span></p>
                <p style="margin-top: 0.5rem;">${data.message}</p>
                <p style="margin-top: 1rem;">
                    <button onclick="showLoginSection()" style="padding: 0.5rem 1rem; font-size: 0.875rem;">
                        Re-authenticate
                    </button>
                </p>
            `;
        } else {
            const badge = data.status === 'expired' ? 'expired' : 'not-configured';
            const label = data.status === 'expired' ? 'Expired' : 'Not Configured';
            container.innerHTML = `
                <p><span class="status-badge ${badge}">${label}</span></p>
                <p style="margin-top: 0.5rem;">${data.message}</p>
            `;
            showLoginSection();
        }
    } catch (error) {
        console.error('Status check failed:', error);
        document.getElementById('auth-status').innerHTML =
            '<p class="error">Failed to check authentication status.</p>';
        showLoginSection();
    }
}

function showLoginSection() {
    document.getElementById('login-section').style.display = '';
}

async function initiateLogin() {
    const btn = document.getElementById('login-btn');
    const status = document.getElementById('login-status');

    btn.disabled = true;
    btn.textContent = 'Connecting...';
    status.innerHTML = '<p class="loading" style="padding: 1rem;">Logging in to Garmin...</p>';

    try {
        const resp = await fetch('/api/garmin/auth/login', { method: 'POST' });

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || 'Login failed');
        }

        const data = await resp.json();

        if (data.status === 'mfa_required') {
            currentSessionId = data.session_id;
            status.innerHTML = '';
            document.getElementById('login-section').style.display = 'none';
            document.getElementById('mfa-section').style.display = '';
            document.getElementById('mfa-code').focus();
        } else if (data.status === 'success') {
            showSuccess();
        }
    } catch (error) {
        status.innerHTML = `<p class="error">${error.message}</p>`;
    } finally {
        btn.disabled = false;
        btn.textContent = 'Connect to Garmin';
    }
}

async function submitMfa() {
    const code = document.getElementById('mfa-code').value.trim();
    if (!code || code.length < 6) {
        document.getElementById('mfa-status').innerHTML =
            '<p class="error">Please enter a 6-digit code.</p>';
        return;
    }

    const btn = document.getElementById('mfa-btn');
    const status = document.getElementById('mfa-status');

    btn.disabled = true;
    btn.textContent = 'Verifying...';
    status.innerHTML = '';

    try {
        const resp = await fetch('/api/garmin/auth/mfa', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: currentSessionId,
                mfa_code: code,
            }),
        });

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || 'MFA verification failed');
        }

        const data = await resp.json();
        if (data.status === 'success') {
            showSuccess();
        }
    } catch (error) {
        status.innerHTML = `<p class="error">${error.message}</p>`;
        document.getElementById('mfa-code').value = '';
        document.getElementById('mfa-code').focus();
    } finally {
        btn.disabled = false;
        btn.textContent = 'Verify Code';
    }
}

function showSuccess() {
    document.getElementById('status-section').style.display = 'none';
    document.getElementById('login-section').style.display = 'none';
    document.getElementById('mfa-section').style.display = 'none';
    document.getElementById('success-section').style.display = '';
}

document.addEventListener('DOMContentLoaded', () => {
    checkStatus();

    document.getElementById('mfa-code').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') submitMfa();
    });
});
