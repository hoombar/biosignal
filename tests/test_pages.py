from fastapi.testclient import TestClient

from app.main import app


def test_settings_page_renders_backup_controls():
    with TestClient(app) as client:
        resp = client.get("/settings")

    assert resp.status_code == 200
    html = resp.text
    assert "Export habits" in html
    assert 'id="habit-import-file"' in html
    assert 'id="habit-import-btn"' in html
    assert 'id="habit-import-file-name"' in html
