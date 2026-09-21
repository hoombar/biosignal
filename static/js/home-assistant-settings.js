(function () {
    const form = document.getElementById('home-assistant-form');
    if (!form) return;

    const nameInput = document.getElementById('home-assistant-name');
    const urlInput = document.getElementById('home-assistant-url');
    const tokenInput = document.getElementById('home-assistant-token');
    const connectionStatus = document.getElementById('home-assistant-connection-status');
    const discoverButton = document.getElementById('home-assistant-discover');
    const discoveryStatus = document.getElementById('home-assistant-discovery-status');
    const temperatureSelect = document.getElementById('home-assistant-temperature');
    const humiditySelect = document.getElementById('home-assistant-humidity');
    const saveEntitiesButton = document.getElementById('home-assistant-save-entities');
    const entityStatus = document.getElementById('home-assistant-entity-status');
    const syncButton = document.getElementById('home-assistant-sync');
    const backfillDate = document.getElementById('home-assistant-backfill-date');
    const syncStatus = document.getElementById('home-assistant-sync-status');
    let discoveredEntities = [];
    let selectedEntities = [];

    function setStatus(element, message, error = false) {
        element.textContent = message;
        element.className = error ? 'save-status save-status--err' : 'save-status save-status--ok';
    }

    async function errorMessage(response) {
        const body = await response.json().catch(() => ({}));
        return body.detail || `HTTP ${response.status}`;
    }

    function renderOptions(select, entities, selectedId) {
        select.innerHTML = '<option value="">Not selected</option>';
        entities.forEach(entity => {
            const option = document.createElement('option');
            option.value = entity.entity_id;
            option.textContent = `${entity.display_name} (${entity.entity_id})`;
            option.selected = entity.entity_id === selectedId;
            select.appendChild(option);
        });
    }

    function renderEntitySelectors() {
        const selectedTemperature = selectedEntities.find(entity => entity.role === 'bedroom_temperature');
        const selectedHumidity = selectedEntities.find(entity => entity.role === 'bedroom_humidity');
        const combined = [...discoveredEntities];
        selectedEntities.forEach(entity => {
            if (!combined.some(item => item.entity_id === entity.entity_id)) combined.push(entity);
        });
        renderOptions(
            temperatureSelect,
            combined.filter(entity => entity.device_class === 'temperature'),
            selectedTemperature?.entity_id
        );
        renderOptions(
            humiditySelect,
            combined.filter(entity => entity.device_class === 'humidity'),
            selectedHumidity?.entity_id
        );
    }

    async function load() {
        const [connectionResponse, entitiesResponse] = await Promise.all([
            fetch('/api/home-assistant/connection'),
            fetch('/api/home-assistant/entities'),
        ]);
        if (connectionResponse.ok) {
            const connection = await connectionResponse.json();
            if (connection) {
                nameInput.value = connection.name;
                urlInput.value = connection.base_url;
                tokenInput.placeholder = 'Saved securely; leave blank to keep it';
                setStatus(connectionStatus, connection.last_successful_sync_at
                    ? `Connected; last sync ${new Date(connection.last_successful_sync_at + 'Z').toLocaleString()}`
                    : 'Connected; not synced yet');
            }
        }
        if (entitiesResponse.ok) selectedEntities = await entitiesResponse.json();
        renderEntitySelectors();
    }

    form.addEventListener('submit', async event => {
        event.preventDefault();
        setStatus(connectionStatus, 'Testing connection...');
        const payload = {
            name: nameInput.value.trim(),
            base_url: urlInput.value.trim(),
        };
        if (tokenInput.value) payload.token = tokenInput.value;
        const response = await fetch('/api/home-assistant/connection', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!response.ok) {
            setStatus(connectionStatus, await errorMessage(response), true);
            return;
        }
        tokenInput.value = '';
        tokenInput.placeholder = 'Saved securely; leave blank to keep it';
        setStatus(connectionStatus, 'Connected and saved');
    });

    discoverButton.addEventListener('click', async () => {
        setStatus(discoveryStatus, 'Discovering...');
        const response = await fetch('/api/home-assistant/entities/discover');
        if (!response.ok) {
            setStatus(discoveryStatus, await errorMessage(response), true);
            return;
        }
        discoveredEntities = await response.json();
        renderEntitySelectors();
        setStatus(discoveryStatus, `Found ${discoveredEntities.length} sensor entities`);
    });

    saveEntitiesButton.addEventListener('click', async () => {
        const entities = [];
        for (const [select, role] of [
            [temperatureSelect, 'bedroom_temperature'],
            [humiditySelect, 'bedroom_humidity'],
        ]) {
            if (!select.value) continue;
            const source = [...discoveredEntities, ...selectedEntities]
                .find(entity => entity.entity_id === select.value);
            entities.push({
                entity_id: source.entity_id,
                display_name: source.display_name,
                device_class: source.device_class,
                source_unit: source.unit ?? source.source_unit,
                role,
            });
        }
        const response = await fetch('/api/home-assistant/entities', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ entities }),
        });
        if (!response.ok) {
            setStatus(entityStatus, await errorMessage(response), true);
            return;
        }
        selectedEntities = await response.json();
        setStatus(entityStatus, 'Sensors saved');
    });

    syncButton.addEventListener('click', async () => {
        setStatus(syncStatus, 'Syncing...');
        const response = await fetch('/api/home-assistant/sync', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ start_date: backfillDate.value || null }),
        });
        if (!response.ok) {
            setStatus(syncStatus, await errorMessage(response), true);
            return;
        }
        const result = await response.json();
        setStatus(syncStatus, `Imported ${result.observations} observations from ${result.entities} sensors`);
    });

    load().catch(error => setStatus(connectionStatus, error.message, true));
})();
