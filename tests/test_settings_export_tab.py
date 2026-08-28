from fastapi.testclient import TestClient

from app.main import app


def test_settings_has_dedicated_import_export_tab():
    with TestClient(app) as client:
        response = client.get("/settings")

    assert response.status_code == 200
    html = response.text
    assert 'id="settings-tab-data"' in html
    assert 'for="settings-tab-data"' in html
    assert "Import / Export" in html
    assert 'id="settings-panel-data"' in html
    assert 'href="/api/export/full"' in html
    assert 'id="full-export-btn"' in html
    assert 'id="full-export-status"' in html
    assert 'href="/api/habits/export"' in html
    assert 'id="settings-panel-habits"' in html
