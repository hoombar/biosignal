from tests.test_daily_light_card import render_daily_card


def test_bedroom_environment_card_renders_sleep_exposure_and_comparison():
    html = render_daily_card(
        "renderBedroomEnvironmentCard",
        {
            "bedroom_temperature_sleep_avg": 18.625,
            "bedroom_temperature_sleep_min": 18.0,
            "bedroom_temperature_sleep_max": 20.0,
            "bedroom_temperature_sleep_coverage_pct": 100.0,
            "bedroom_humidity_sleep_avg": 55.0,
            "bedroom_humidity_sleep_min": 50.0,
            "bedroom_humidity_sleep_max": 60.0,
            "bedroom_humidity_sleep_coverage_pct": 100.0,
            "bedroom_outdoor_sleep_temperature_delta": -5.0,
        },
    )

    assert "Bedroom environment" in html
    assert "18.6" in html
    assert "55%" in html
    assert "5.0" in html
    assert "cooler than outside" in html


def test_bedroom_environment_card_shows_low_coverage_without_exposure_value():
    html = render_daily_card(
        "renderBedroomEnvironmentCard",
        {"bedroom_temperature_sleep_coverage_pct": 62.5},
    )

    assert "No reliable sleep-window data" in html
    assert "63% coverage" in html


def test_bedroom_environment_card_does_not_hide_low_temperature_coverage():
    html = render_daily_card(
        "renderBedroomEnvironmentCard",
        {
            "bedroom_temperature_sleep_coverage_pct": 20,
            "bedroom_humidity_sleep_coverage_pct": 100,
        },
    )

    assert "Temperature coverage" in html
    assert "20%" in html
    assert "Humidity coverage" in html
    assert "100%" in html
