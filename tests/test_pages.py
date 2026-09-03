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
    assert 'href="/api/export/full"' in html
    assert "Export all data" in html
    assert 'id="habit-import-file"' in html
    assert 'id="habit-import-btn"' in html
    assert 'id="habit-import-file-name"' in html


def test_insights_page_links_to_full_data_export():
    with TestClient(app) as client:
        resp = client.get("/insights")

    assert resp.status_code == 200
    assert 'href="/api/export/full"' in resp.text
    assert "Export All Data (ZIP)" in resp.text


def test_habit_settings_editor_prioritizes_display_label_cards():
    with TestClient(app) as client:
        html_resp = client.get("/settings")
        css_resp = client.get("/static/css/style.css")

    assert html_resp.status_code == 200
    assert css_resp.status_code == 200
    html = html_resp.text
    css = css_resp.text
    assert 'id="habits-list"' in html
    assert 'class="habit-card-list"' in html
    assert 'card.className = `habit-card${archivedClass}`' in html
    assert 'name="display_name"' in html
    assert 'Internal name' in html
    assert 'class="settings-table"' not in html
    assert '.habit-card-list' in css
    assert '.habit-card-main' in css
    assert '.habit-internal-name' in css


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
    assert html.index('id="gym-template-activities"') < html.index('id="gym-add-activity"')
    assert "/static/js/gym-settings.js" in html


def test_gym_settings_activity_editor_avoids_horizontal_scroller():
    with TestClient(app) as client:
        css_resp = client.get("/static/css/style.css")
        js_resp = client.get("/static/js/gym-settings.js")

    assert css_resp.status_code == 200
    assert js_resp.status_code == 200
    layout_block = re.search(r"\.gym-settings-layout\s*\{(?P<body>[^}]+)\}", css_resp.text)
    assert layout_block is not None
    assert "grid-template-columns: 1fr;" in layout_block.group("body")
    activity_block = re.search(r"\.gym-settings-activity\s*\{(?P<body>[^}]+)\}", css_resp.text)
    assert activity_block is not None
    assert "overflow-x" not in activity_block.group("body")
    assert "display: flex;" in activity_block.group("body")
    assert "flex-direction: column;" in activity_block.group("body")
    assert "width: 100%;" in activity_block.group("body")
    header_block = re.search(r"\.gym-settings-activity-header\s*\{(?P<body>[^}]+)\}", css_resp.text)
    assert header_block is not None
    assert "justify-content: space-between;" in header_block.group("body")
    fields_block = re.search(r"\.gym-settings-activity-fields\s*\{(?P<body>[^}]+)\}", css_resp.text)
    assert fields_block is not None
    assert "grid-template-columns: minmax(16rem, 2fr) repeat(4, minmax(6rem, 1fr));" in fields_block.group("body")
    assert "width: 100%;" in fields_block.group("body")
    actions_block = re.search(r"\.gym-settings-activity-actions\s*\{(?P<body>[^}]+)\}", css_resp.text)
    assert actions_block is not None
    assert "justify-content: flex-end;" in actions_block.group("body")
    details_block = re.search(r"\.gym-settings-activity-details\s*\{(?P<body>[^}]+)\}", css_resp.text)
    assert details_block is not None
    assert "display: contents;" in details_block.group("body")
    assert "gym-settings-activity-details" in js_resp.text


def test_habit_add_form_wraps_inside_settings_card():
    with TestClient(app) as client:
        resp = client.get("/static/css/style.css")

    assert resp.status_code == 200
    css = resp.text
    details_block = re.search(r"\.add-habit-details\s*\{(?P<body>[^}]+)\}", css)
    assert details_block is not None
    assert "container-type: inline-size;" in details_block.group("body")

    form_block = re.search(r"\.add-habit-form\s*\{(?P<body>[^}]+)\}", css)
    assert form_block is not None
    assert "grid-template-columns: repeat(auto-fit, minmax(min(100%, 10rem), 1fr));" in form_block.group("body")
    assert "align-items: end;" in form_block.group("body")

    name_block = re.search(r"\.add-habit-form > input\[name=\"name\"\]\s*\{(?P<body>[^}]+)\}", css)
    assert name_block is not None
    assert "grid-column: span 2;" in name_block.group("body")


def test_gym_settings_activity_editor_supports_reordering():
    with TestClient(app) as client:
        resp = client.get("/static/js/gym-settings.js")

    assert resp.status_code == 200
    script = resp.text
    assert 'data-action="move-activity-up"' in script
    assert 'data-action="move-activity-down"' in script
    assert 'data-action="remove-activity" aria-label="Remove activity">×</button>' in script
    assert "gym-settings-icon-btn" in script
    assert "insertBefore(row, previous)" in script
    assert "insertBefore(next, row)" in script


def test_gym_settings_activity_editor_filters_fields_by_type():
    with TestClient(app) as client:
        resp = client.get("/static/js/gym-settings.js")

    assert resp.status_code == 200
    script = resp.text
    assert "data-activity-type=\"mobility\"" in script
    assert "data-activity-type=\"reps\"" not in script
    assert "data-field=\"activity_type\"" not in script
    assert "data-activity-type=\"freeform\"" not in script
    assert "unitSelectHtml('target_weight_unit', 'Unit', activity.target_weight_unit, ['kg', 'lbs'])" in script
    assert "unitSelectHtml('target_weight_unit', 'Unit', activity.target_weight_unit, ['kph', 'mph', 'rpm'])" in script
    assert "fieldHtml('target_reps', 'Reps', 'number', activity.target_reps, {step: '1'})" in script
    assert "normalizeActivityForType(data)" in script
    assert "target_duration_minutes = null" in script
    assert "target_sets: ['strength', 'mobility'].includes(type) ? 3 : null" in script
    assert "target_reps: ['strength', 'mobility'].includes(type) ? 12 : null" in script


def test_gym_settings_add_activity_asks_for_type():
    with TestClient(app) as client:
        resp = client.get("/static/js/gym-settings.js")

    assert resp.status_code == 200
    script = resp.text
    assert "showActivityTypeChooser()" in script
    assert "gym-activity-type-choice" in script
    assert "Add strength" in script
    assert "Add cardio" in script
    assert "Add mobility" in script
    assert "Add reps" not in script


def test_gym_session_editor_supports_mobility_sets_and_reps():
    with TestClient(app) as client:
        resp = client.get("/static/js/gym.js")

    assert resp.status_code == 200
    script = resp.text
    assert "activity.activity_type === 'reps'" not in script
    assert "actual_reps', 'Reps'" in script
    assert "actual_sets', 'Sets'" in script
    assert "planned_reps" in script


def test_gym_session_summary_uses_current_actual_values():
    with TestClient(app) as client:
        resp = client.get("/static/js/gym.js")

    assert resp.status_code == 200
    script = resp.text
    assert "function activitySummary(activity)" in script
    assert "activity.actual_weight ?? activity.planned_weight" in script
    assert "activity.actual_duration_minutes ?? activity.planned_duration_minutes" in script
    assert "activity.actual_sets ?? activity.planned_sets" in script


def test_gym_session_completion_can_update_template():
    with TestClient(app) as client:
        resp = client.get("/static/js/gym.js")

    assert resp.status_code == 200
    script = resp.text
    assert "promptTemplateUpdate: event.target.checked" in script
    assert "promptTemplateUpdate: true" in script
    assert "Update the template with these completed values?" in script
    assert "function maybeUpdateTemplateFromActivity(activity)" in script
    assert "`/api/gym/templates/${template.id}`" in script


def test_gym_page_cache_busts_session_script():
    with TestClient(app) as client:
        resp = client.get("/gym")

    assert resp.status_code == 200
    assert "/static/js/gym.js?v=20260903-previous-session" in resp.text


def test_gym_settings_template_list_supports_unarchive():
    with TestClient(app) as client:
        resp = client.get("/static/js/gym-settings.js")

    assert resp.status_code == 200
    script = resp.text
    assert "data-action=\"unarchive-template\"" in script
    assert "Unarchive" in script
    assert "/unarchive" in script


def test_overview_page_no_longer_renders_manual_sync_controls():
    with TestClient(app) as client:
        resp = client.get("/overview")

    assert resp.status_code == 200
    html = resp.text
    assert "Sync Status" not in html
    assert "Backfill Historical Data" not in html
    assert 'id="sync-btn"' not in html


def test_overview_page_renders_loading_spinners():
    with TestClient(app) as client:
        resp = client.get("/overview")

    assert resp.status_code == 200
    html = resp.text
    assert 'class="value loading loading--inline loading--with-spinner" id="total-days"' in html
    assert 'class="loading loading--with-spinner"' in html


def test_daily_page_renders_loading_spinners():
    with TestClient(app) as client:
        resp = client.get("/daily")

    assert resp.status_code == 200
    html = resp.text
    assert html.count('class="loading loading--with-spinner"') >= 3
    assert 'id="metrics-grid"' in html
    assert 'id="habits-list"' in html


def test_correlations_page_renders_loading_spinner_shells():
    with TestClient(app) as client:
        resp = client.get("/correlations")

    assert resp.status_code == 200
    html = resp.text
    assert 'Loading targets' in html
    assert 'class="loading loading--with-spinner"' in html


def test_trends_page_renders_loading_spinners():
    with TestClient(app) as client:
        resp = client.get("/trends")

    assert resp.status_code == 200
    html = resp.text
    assert html.count('class="loading loading--with-spinner"') >= 2
    assert 'id="trends-chart-loading"' in html


def test_insights_page_renders_loading_spinners():
    with TestClient(app) as client:
        resp = client.get("/insights")

    assert resp.status_code == 200
    html = resp.text
    assert html.count('class="loading loading--with-spinner"') >= 2


def test_log_page_renders_loading_spinner():
    with TestClient(app) as client:
        resp = client.get("/log")

    assert resp.status_code == 200
    html = resp.text
    assert 'id="log-loading" class="loading loading--with-spinner"' in html


def test_gym_page_renders_loading_spinner():
    with TestClient(app) as client:
        resp = client.get("/gym")

    assert resp.status_code == 200
    html = resp.text
    assert 'id="gym-status" class="gym-status loading loading--with-spinner"' in html


def test_settings_page_renders_loading_spinners():
    with TestClient(app) as client:
        resp = client.get("/settings")

    assert resp.status_code == 200
    html = resp.text
    assert html.count('class="loading loading--with-spinner"') >= 3


def test_garmin_setup_page_renders_loading_spinner():
    with TestClient(app) as client:
        resp = client.get("/setup/garmin")

    assert resp.status_code == 200
    html = resp.text
    assert 'class="loading loading--with-spinner"' in html


def test_loading_css_renders_spinner():
    with TestClient(app) as client:
        resp = client.get("/static/css/style.css")

    assert resp.status_code == 200
    css = resp.text
    assert ".loading--with-spinner::before" in css
    assert "@keyframes loading-spin" in css


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


def test_signal_field_daily_detail_has_panel_inset():
    with TestClient(app) as client:
        resp = client.get("/static/css/style.css")

    assert resp.status_code == 200
    css = resp.text
    assert "padding: clamp(1rem, 2vw, 1.5rem);" in css
    assert "grid-template-columns: minmax(0, 1fr) minmax(220px, 280px);" in css


def test_signal_field_settings_habit_cards_use_light_surface():
    with TestClient(app) as client:
        resp = client.get("/static/css/style.css")

    assert resp.status_code == 200
    css = resp.text
    assert "background: rgba(26, 26, 36, 0.68);" not in css
    assert "background: color-mix(in srgb, var(--surface) 92%, var(--surface-warm));" in css
    assert "color: var(--fg);" in css
    assert "color: var(--accent-on);" in css


def test_signal_field_mobile_nav_wraps_and_daily_stacks():
    with TestClient(app) as client:
        resp = client.get("/static/css/style.css")

    assert resp.status_code == 200
    css = resp.text
    assert "overflow-x: visible;" in css
    assert "flex-wrap: wrap;" in css
    assert "grid-template-columns: minmax(0, 1fr);" in css
