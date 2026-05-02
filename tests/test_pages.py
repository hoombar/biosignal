from pathlib import Path

from PIL import Image
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


def test_brand_assets_use_dark_background_logo():
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
