import json
import subprocess
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def render_daily_card(function_name: str, day: dict, preferences: dict | None = None) -> str:
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        const source = fs.readFileSync('static/js/daily.js', 'utf8');
        const functionName = process.argv[1];
        const day = JSON.parse(process.argv[2]);
        const preferences = JSON.parse(process.argv[3] || '{}');

        const context = {
            console,
            window: {
                location: { hash: '' },
                addEventListener() {},
            },
            document: {
                addEventListener() {},
                getElementById() { return null; },
                querySelectorAll() { return []; },
            },
            history: { pushState() {} },
            fetch: async () => ({ json: async () => [] }),
            requestAnimationFrame(callback) { callback(); },
            loadHabitConfig: async () => {},
            loadHabitsList: async () => [],
            getHabitDisplay: () => ({ label: '', color: '', sort_order: 0 }),
            getHabitColor: () => '#000',
            HabitPanel: {
                renderHabitsPanel: () => '',
                bindHabitsPanel: () => {},
            },
            __weatherPreferences: preferences,
        };

        vm.createContext(context);
        vm.runInContext(source, context);

        if (typeof context[functionName] !== 'function') {
            throw new Error(`${functionName} is not defined`);
        }

        console.log(JSON.stringify({ html: context[functionName](day) }));
        """
    )
    result = subprocess.run(
        ["node", "-e", script, function_name, json.dumps(day), json.dumps(preferences or {})],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)["html"]


def render_light_card(day: dict) -> str:
    return render_daily_card("renderLightCard", day)


def render_pollen_card(day: dict) -> str:
    return render_daily_card("renderPollenCard", day)


def render_weather_card(day: dict) -> str:
    return render_daily_card("renderWeatherCard", day)


def render_weather_card_with_preferences(day: dict, preferences: dict) -> str:
    return render_daily_card("renderWeatherCard", day, preferences)


def render_activity_card(day: dict) -> str:
    return render_daily_card("renderActivityCard", day)


def render_sleep_card(day: dict) -> str:
    return render_daily_card("renderSleepCard", day)


def render_context_summary(day: dict) -> str:
    return render_daily_card("renderContextSummary", day)


def test_daily_context_summary_renders_baseline_exclusion():
    html = render_context_summary({
        "baseline_excluded": True,
        "contexts": [{
            "id": 1,
            "title": "Conference abroad",
            "start_date": "2026-05-19",
            "end_date": "2026-05-24",
            "category": "conference",
            "tags": ["flight", "hotel"],
            "intensity": "high",
            "exclude_from_baseline": True,
            "notes": "Long travel day.",
        }],
    })

    assert "Context" in html
    assert "Conference Abroad" in html
    assert "Conference" in html
    assert "Excluded from baseline" in html
    assert "flight" in html
    assert "hotel" in html
    assert '/log?context=1#' in html


def test_daily_context_summary_empty_without_contexts():
    assert render_context_summary({"contexts": []}) == ""


def test_daily_light_card_renders_daylight_and_sun_times():
    html = render_light_card({
        "daylight_minutes": 984,
        "sunrise_minutes_after_midnight": 282,
        "sunset_minutes_after_midnight": 1266,
        "solar_noon_minutes_after_midnight": 774,
    })

    assert "Light" in html
    assert "16h 24m" in html
    assert "Sunrise" in html
    assert "04:42" in html
    assert "Sunset" in html
    assert "21:06" in html
    assert "Solar Noon" in html
    assert "12:54" in html


def test_daily_activity_card_renders_likely_walk_metrics():
    html = render_activity_card({
        "steps_total": 8400,
        "steps_morning": 3200,
        "steps_peak_45min": 3000,
        "steps_walking_30min_blocks": 2,
        "walk_hr_elevated_45min_windows": 1,
        "walk_peak_45min_hr_delta": 33,
        "had_likely_walk": True,
        "had_likely_brisk_walk": True,
        "had_training": False,
    })

    assert "Likely brisk walk" in html
    assert "Peak 45 min" in html
    assert "3,000" in html
    assert "Brisk walk windows" in html
    assert "1 x 45m" in html
    assert "Step-only 30m blocks" in html
    assert "Walk HR lift" in html
    assert "+33 bpm" in html


def test_daily_activity_card_renders_training_activity_as_own_card():
    html = render_activity_card({
        "steps_total": 5200,
        "steps_morning": 1200,
        "steps_peak_45min": 900,
        "steps_walking_30min_blocks": 0,
        "had_training": True,
        "training_type": "lap_swimming",
        "activity_sessions": [{
            "activity_type": "lap_swimming",
            "start_time": "7:00 AM",
            "duration_min": 45,
            "distance_meters": 2000,
            "laps": 80,
            "pool_length_meters": 25,
            "avg_hr": 132,
            "max_hr": 168,
            "calories": 420,
            "training_effect_aerobic": None,
            "training_effect_anaerobic": None,
        }],
    })

    assert "Steps" in html
    assert '<span class="card-title">Lap Swimming</span>' in html
    assert '<span class="metric-value">2.0</span>' in html
    assert '<span class="metric-unit">km · 80 laps</span>' in html
    assert "Lap Swimming" in html
    assert "45 min" in html
    assert "80 laps" in html
    assert "Max HR" in html
    assert "168 bpm" in html
    assert "Training Sessions" not in html


def test_daily_activity_card_renders_multiple_training_activity_cards():
    html = render_activity_card({
        "steps_total": 5200,
        "had_training": True,
        "activity_sessions": [
            {
                "activity_type": "lap_swimming",
                "start_time": "7:00 AM",
                "duration_min": 45,
                "distance_meters": 2000,
                "laps": 80,
                "pool_length_meters": 25,
                "avg_hr": 132,
                "max_hr": 168,
                "calories": 420,
                "training_effect_aerobic": None,
                "training_effect_anaerobic": None,
            },
            {
                "activity_type": "mixed_martial_arts",
                "start_time": "6:30 PM",
                "duration_min": 60,
                "distance_meters": None,
                "laps": None,
                "pool_length_meters": None,
                "avg_hr": 142,
                "max_hr": 172,
                "calories": 485,
                "training_effect_aerobic": 3.2,
                "training_effect_anaerobic": 2.8,
            },
        ],
    })

    assert '<span class="card-title">Lap Swimming</span>' in html
    assert '<span class="card-title">Mixed Martial Arts</span>' in html
    assert '<span class="metric-value">172</span>' in html
    assert '<span class="metric-unit">bpm max</span>' in html
    assert "Training Sessions" not in html


def test_daily_activity_card_uses_hr_for_zero_distance_combat_and_strength():
    html = render_activity_card({
        "steps_total": 5200,
        "had_training": True,
        "activity_sessions": [
            {
                "activity_type": "mixed_martial_arts",
                "start_time": "12:05 PM",
                "duration_min": 60,
                "distance_meters": 0,
                "laps": None,
                "pool_length_meters": None,
                "avg_hr": 126,
                "max_hr": 172,
                "calories": 509,
                "training_effect_aerobic": None,
                "training_effect_anaerobic": None,
            },
            {
                "activity_type": "strength_training",
                "start_time": "12:17 PM",
                "duration_min": 57,
                "distance_meters": 0,
                "laps": None,
                "pool_length_meters": None,
                "avg_hr": 124,
                "max_hr": 154,
                "calories": 467,
                "training_effect_aerobic": None,
                "training_effect_anaerobic": None,
            },
        ],
    })

    assert "&#129355;" in html
    assert "&#127947;" in html
    assert '<span class="metric-value">172</span>' in html
    assert '<span class="metric-value">154</span>' in html
    assert '<span class="metric-unit">bpm max</span>' in html
    assert "0.0" not in html
    assert "Distance" not in html


def test_daily_metric_details_are_collapsed_by_default():
    html = render_sleep_card({
        "sleep_score": 81,
        "sleep_hours": 7.5,
        "deep_sleep_pct": 18,
        "rem_sleep_pct": 22,
        "sleep_efficiency": 91,
    })

    assert '<details class="metric-details" data-details-key="sleep">' in html
    assert '<summary class="metric-details-summary">Details</summary>' in html
    assert '<details class="metric-details" open' not in html
    assert "Duration" in html


def test_daily_light_card_renders_empty_values_when_location_unset():
    html = render_light_card({
        "daylight_minutes": None,
        "sunrise_minutes_after_midnight": None,
        "sunset_minutes_after_midnight": None,
        "solar_noon_minutes_after_midnight": None,
    })

    assert "Light" in html
    assert "NaN" not in html
    assert ">0h<" not in html
    assert '<span class="metric-value">-</span>' in html


def test_daily_pollen_card_renders_peak_and_available_types():
    html = render_pollen_card({
        "grass_pollen_avg": 12.5,
        "grass_pollen_max": 22,
        "birch_pollen_avg": 4,
        "birch_pollen_max": 8,
        "alder_pollen_avg": None,
        "alder_pollen_max": None,
    })

    assert "Pollen" in html
    assert "22" in html
    assert "Grass peak" in html
    assert "Avg / Max" in html
    assert "Grass" in html
    assert "12.5 / 22" in html
    assert "Birch" in html
    assert "4 / 8" in html
    assert "Alder" not in html


def test_daily_pollen_card_renders_empty_state_without_synced_data():
    html = render_pollen_card({
        "grass_pollen_avg": None,
        "grass_pollen_max": None,
        "birch_pollen_avg": None,
        "birch_pollen_max": None,
    })

    assert "Pollen" in html
    assert "No data" in html
    assert "NaN" not in html
    assert '<span class="metric-value">-</span>' in html


def test_daily_weather_card_renders_temperature_humidity_and_rain():
    html = render_weather_card({
        "temperature_2m_min": 12.2,
        "temperature_2m_max": 24.8,
        "apparent_temperature_max": 28.1,
        "relative_humidity_2m_avg": 72,
        "relative_humidity_2m_max": 91,
        "precipitation_sum": 3.4,
        "precipitation_hours": 2,
        "wind_speed_10m_max": 31,
        "cloud_cover_avg": 65,
    })

    assert "Weather" in html
    assert "12-25°C" in html
    assert "home weather" not in html
    assert "Feels max" in html
    assert "28°C" in html
    assert "Humidity" in html
    assert "72% / 91%" in html
    assert "Precipitation" in html
    assert "3.4 mm" in html
    assert "Wind max" in html
    assert "31 km/h" in html


def test_daily_weather_card_uses_unit_preferences():
    html = render_weather_card_with_preferences({
        "temperature_2m_min": 12.2,
        "temperature_2m_max": 24.8,
        "apparent_temperature_max": 28.1,
        "relative_humidity_2m_avg": 72,
        "relative_humidity_2m_max": 91,
        "precipitation_sum": 3.4,
        "precipitation_hours": 2,
        "wind_speed_10m_max": 31,
        "cloud_cover_avg": 65,
    }, {
        "weather_temperature_unit": "fahrenheit",
        "weather_wind_speed_unit": "mph",
    })

    assert "54-77°F" in html
    assert "83°F" in html
    assert "19 mph" in html
    assert "31 km/h" not in html


def test_daily_weather_card_renders_pressure_and_condition_rows():
    html = render_weather_card({
        "temperature_2m_min": 12.2,
        "temperature_2m_max": 24.8,
        "surface_pressure_avg": 1012.3,
        "weather_code_mode": 61.0,
    })

    assert "Pressure" in html
    assert "1012 hPa" in html
    assert "Conditions" in html
    assert "Slight rain" in html


def test_daily_weather_card_condition_only_day_is_not_empty_state():
    html = render_weather_card({
        "temperature_2m_avg": None,
        "weather_code_mode": 0.0,
    })

    assert "No data" not in html
    assert "Conditions" in html
    assert "Clear sky" in html


def test_daily_weather_card_unknown_condition_code_falls_back_to_code():
    html = render_weather_card({"weather_code_mode": 42.0})

    assert "Conditions" in html
    assert "Code 42" in html


def test_daily_weather_card_renders_empty_state_without_synced_data():
    html = render_weather_card({
        "temperature_2m_min": None,
        "temperature_2m_max": None,
        "apparent_temperature_max": None,
        "relative_humidity_2m_avg": None,
        "precipitation_sum": None,
    })

    assert "Weather" in html
    assert "No data" in html
    assert "NaN" not in html
    assert '<span class="metric-value">-</span>' in html
