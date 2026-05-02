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


def test_log_page_renders_brand_logo_and_favicon():
    with TestClient(app) as client:
        resp = client.get("/log")

    assert resp.status_code == 200
    html = resp.text
    assert 'rel="icon"' in html
    assert "/static/images/favicon.png" in html
    assert 'class="site-logo"' in html
    assert "/static/images/logo.jpeg" in html
