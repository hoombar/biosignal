from fastapi.testclient import TestClient

from app.main import app


def test_settings_exposes_home_assistant_connection_and_entity_controls():
    with TestClient(app) as client:
        response = client.get("/settings")

    assert response.status_code == 200
    html = response.text
    assert 'id="home-assistant-form"' in html
    assert 'id="home-assistant-url"' in html
    assert 'id="home-assistant-token"' in html
    assert 'id="home-assistant-discover"' in html
    assert 'id="home-assistant-entities"' in html
    assert "Bedroom sensors" not in html
    assert 'id="home-assistant-backfill-date"' in html
    assert '/static/js/home-assistant-settings.js' in html
