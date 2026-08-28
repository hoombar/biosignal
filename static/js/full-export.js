(() => {
    document.querySelectorAll('[data-full-export]').forEach((button) => {
        const status = button.parentElement.querySelector('[data-full-export-status]')
            || document.getElementById('full-export-status');
        const originalText = button.textContent;
        let busy = false;

        button.addEventListener('click', async (event) => {
            event.preventDefault();
            if (busy) return;
            busy = true;
            button.setAttribute('aria-disabled', 'true');
            button.classList.add('disabled');
            button.textContent = 'Preparing ZIP...';
            if (status) {
                status.textContent = 'This may take a minute for larger datasets.';
                status.className = 'save-status';
            }

            try {
                const response = await fetch(button.href);
                if (!response.ok) {
                    throw new Error(`Export failed (HTTP ${response.status})`);
                }
                const blob = await response.blob();
                const download = document.createElement('a');
                download.href = URL.createObjectURL(blob);
                download.download = response.headers.get('content-disposition')?.match(/filename="?([^";]+)"?/)?.[1]
                    || 'biosignal_full_export.zip';
                download.click();
                setTimeout(() => URL.revokeObjectURL(download.href), 1000);
                if (status) {
                    status.textContent = 'Download ready.';
                    status.className = 'save-status save-status--ok';
                }
            } catch (error) {
                if (status) {
                    status.textContent = error.message;
                    status.className = 'save-status save-status--err';
                }
            } finally {
                button.removeAttribute('aria-disabled');
                button.classList.remove('disabled');
                button.textContent = originalText;
                busy = false;
            }
        });
    });
})();
