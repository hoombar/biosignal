import re
from pathlib import Path

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


def test_settings_page_renders_sync_controls():
    with TestClient(app) as client:
        resp = client.get("/settings")

    assert resp.status_code == 200
    html = resp.text
    assert "Service Sync" in html
    assert 'data-sync-service="garmin"' in html
    assert 'data-sync-service="environment"' in html
    assert 'id="backfill-date"' in html
    assert 'id="sync-status"' in html


def test_settings_page_groups_sections_in_tabs():
    with TestClient(app) as client:
        resp = client.get("/settings")

    assert resp.status_code == 200
    html = resp.text
    assert 'class="settings-tabs"' in html
    assert 'role="tablist"' in html
    assert 'for="settings-tab-sync"' in html
    assert 'for="settings-tab-supplements"' in html
    assert 'for="settings-tab-preferences"' in html
    assert 'for="settings-tab-gym"' in html
    assert 'for="settings-tab-habits"' in html
    assert 'id="settings-panel-sync"' in html
    assert 'id="settings-panel-supplements"' in html
    assert 'id="settings-panel-preferences"' in html
    assert 'id="settings-panel-gym"' in html
    assert 'id="settings-panel-habits"' in html


def test_settings_page_renders_weather_unit_preferences():
    with TestClient(app) as client:
        resp = client.get("/settings")

    assert resp.status_code == 200
    html = resp.text
    assert 'id="weather-temperature-unit"' in html
    assert 'id="weather-wind-speed-unit"' in html
    assert "Fahrenheit" in html
    assert "mph" in html


def test_settings_page_renders_gym_template_editor():
    with TestClient(app) as client:
        resp = client.get("/settings")

    assert resp.status_code == 200
    html = resp.text
    assert 'id="gym-template-form"' in html
    assert 'id="gym-template-list"' in html
    assert 'id="gym-add-activity"' in html
    assert "/static/js/gym-settings.js" in html


def test_gym_settings_activity_editor_avoids_horizontal_scroller():
    with TestClient(app) as client:
        css_resp = client.get("/static/css/style.css")
        js_resp = client.get("/static/js/gym-settings.js")

    assert css_resp.status_code == 200
    assert js_resp.status_code == 200
    activity_block = re.search(r"\.gym-settings-activity\s*\{(?P<body>[^}]+)\}", css_resp.text)
    assert activity_block is not None
    assert "flex-direction: column;" in activity_block.group("body")
    assert "overflow-x" not in activity_block.group("body")
    assert "gym-settings-activity-details" in js_resp.text


def test_gym_settings_activity_editor_supports_reordering():
    with TestClient(app) as client:
        resp = client.get("/static/js/gym-settings.js")

    assert resp.status_code == 200
    script = resp.text
    assert 'data-action="move-activity-up"' in script
    assert 'data-action="move-activity-down"' in script
    assert "insertBefore(row, previous)" in script
    assert "insertBefore(next, row)" in script


def test_overview_page_no_longer_renders_manual_sync_controls():
    with TestClient(app) as client:
        resp = client.get("/")

    assert resp.status_code == 200
    html = resp.text
    assert "Sync Status" not in html
    assert "Backfill Historical Data" not in html
    assert 'id="sync-btn"' not in html


def test_log_page_renders_brand_logo_and_favicon():
    with TestClient(app) as client:
        resp = client.get("/log")

    assert resp.status_code == 200
    html = resp.text
    assert 'rel="icon"' in html
    assert "/static/images/favicon.png" in html
    assert 'class="site-header"' in html
    assert 'class="site-logo"' in html
    assert "/static/images/logo.jpeg" in html


def test_log_page_renders_context_panel_shell():
    with TestClient(app) as client:
        resp = client.get("/log")

    assert resp.status_code == 200
    html = resp.text
    assert 'id="log-context"' in html
    assert 'class="log-context"' in html


def test_gym_page_renders_lean_session_shell():
    with TestClient(app) as client:
        resp = client.get("/gym")

    assert resp.status_code == 200
    html = resp.text
    assert 'class="gym-page"' in html
    assert 'id="gym-date"' in html
    assert 'id="gym-session"' in html
    assert 'id="gym-template-list"' in html
    assert "/static/js/gym.js" in html


def test_navigation_includes_gym_page():
    with TestClient(app) as client:
        resp = client.get("/gym")

    assert resp.status_code == 200
    html = resp.text
    assert 'href="/gym"' in html
    assert '>Gym<' in html
    assert 'active_page == \'gym\'' in Path("app/templates/base.html").read_text()


def test_log_page_renders_responsive_navigation_shell():
    with TestClient(app) as client:
        resp = client.get("/log")

    assert resp.status_code == 200
    html = resp.text
    assert 'class="nav-toggle"' in html
    assert 'aria-controls="site-nav"' in html
    assert 'aria-expanded="false"' in html
    assert 'class="site-nav"' in html
    assert 'id="site-nav"' in html
    assert "/static/js/site-nav.js" in html


def test_brand_assets_use_dark_background_logo():
    from PIL import Image

    assets = {
        Path("static/images/logo.jpeg"): (320, 239),
        Path("static/images/favicon.png"): (256, 256),
        Path("static/images/apple-touch-icon.png"): (180, 180),
    }

    for path, expected_size in assets.items():
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            assert rgb.size == expected_size

            corners = (
                rgb.getpixel((0, 0)),
                rgb.getpixel((rgb.width - 1, 0)),
                rgb.getpixel((0, rgb.height - 1)),
                rgb.getpixel((rgb.width - 1, rgb.height - 1)),
            )
            assert all(max(corner) <= 20 for corner in corners)


def test_brand_wrapper_has_no_visible_frame():
    with TestClient(app) as client:
        resp = client.get("/static/css/style.css")

    assert resp.status_code == 200
    match = re.search(r"\.site-brand\s*\{(?P<body>[^}]+)\}", resp.text)
    assert match is not None

    block = match.group("body")
    assert "padding: 0;" in block
    assert "background: transparent;" in block
    assert "border: 0;" in block
    assert "box-shadow: none;" in block


def test_log_habit_text_uses_high_contrast_colors():
    with TestClient(app) as client:
        resp = client.get("/static/css/style.css")

    assert resp.status_code == 200
    css = resp.text

    label_block = re.search(r"\.log-habits\s+\.habit-sidebar-label\s*\{(?P<body>[^}]+)\}", css)
    assert label_block is not None
    assert "color: var(--text-primary);" in label_block.group("body")

    toggle_block = re.search(r"\.log-habits\s+\.habit-toggle\s*\{(?P<body>[^}]+)\}", css)
    assert toggle_block is not None
    assert "color: var(--text-primary);" in toggle_block.group("body")

    counter_block = re.search(r"\.log-habits\s+\.habit-counter-btn\s*\{(?P<body>[^}]+)\}", css)
    assert counter_block is not None
    assert "color: var(--text-primary);" in counter_block.group("body")


def test_responsive_header_css_supports_inline_and_mobile_nav():
    with TestClient(app) as client:
        resp = client.get("/static/css/style.css")

    assert resp.status_code == 200
    css = resp.text

    header_block = re.search(r"\.site-header\s*\{(?P<body>[^}]+)\}", css)
    assert header_block is not None
    assert "align-items: center;" in header_block.group("body")
    assert "flex-wrap: wrap;" in header_block.group("body")

    logo_block = re.search(r"\.site-logo\s*\{(?P<body>[^}]+)\}", css)
    assert logo_block is not None
    assert "height: clamp(3.5rem, 8vw, 5rem);" in logo_block.group("body")

    nav_block = re.search(r"\.site-nav\s*\{(?P<body>[^}]+)\}", css)
    assert nav_block is not None
    assert "margin-left: auto;" in nav_block.group("body")

    toggle_block = re.search(r"\.nav-toggle\s*\{(?P<body>[^}]+)\}", css)
    assert toggle_block is not None
    assert "display: none;" in toggle_block.group("body")

    mobile_nav_block = re.search(
        r"\.site-header\[data-nav-open=\"true\"\]\s+\.site-nav\s*\{(?P<body>[^}]+)\}",
        css,
    )
    assert mobile_nav_block is not None
    assert "display: flex;" in mobile_nav_block.group("body")


def test_mobile_nav_script_toggles_menu_state():
    with TestClient(app) as client:
        resp = client.get("/static/js/site-nav.js")

    assert resp.status_code == 200
    script = resp.text
    assert "data-nav-open" in script
    assert "aria-expanded" in script
    assert "matchMedia" in script
