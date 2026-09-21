from tests.test_daily_light_card import render_daily_card


def test_home_assistant_card_renders_arbitrary_daily_metrics():
    html = render_daily_card(
        "renderHomeAssistantCard",
        {"home_assistant_metrics": [
            {
                "selector": "home_assistant:sensor.greenhouse_soil",
                "entity_id": "sensor.greenhouse_soil",
                "display_name": "Greenhouse soil",
                "value": 42.25,
                "unit": "%",
                "device_class": "moisture",
                "min": 38.0,
                "max": 47.0,
                "coverage_pct": 87.5,
            },
            {
                "selector": "home_assistant:binary_sensor.window",
                "entity_id": "binary_sensor.window",
                "display_name": "Window",
                "value": 0.5,
                "unit": None,
                "device_class": "window",
                "min": 0.0,
                "max": 1.0,
                "coverage_pct": 100.0,
            },
        ]},
    )

    assert "Home Assistant" in html
    assert "Greenhouse soil" in html
    assert "42.3%" in html
    assert "38" in html and "47" in html
    assert "88% coverage" in html
    assert "Window" in html
