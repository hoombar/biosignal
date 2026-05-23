import json
import subprocess
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def render_daily_card(function_name: str, day: dict) -> str:
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        const source = fs.readFileSync('static/js/daily.js', 'utf8');
        const functionName = process.argv[1];
        const day = JSON.parse(process.argv[2]);

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
        ["node", "-e", script, function_name, json.dumps(day)],
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


def test_daily_activity_card_renders_training_metrics_separately_from_steps():
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
    assert "Training Sessions" in html
    assert "Lap Swimming" in html
    assert "45 min" in html
    assert "2.0 km" in html
    assert "80 laps" in html
    assert "Max HR" in html
    assert "168 bpm" in html


def test_daily_activity_card_collapsed_training_summary_shows_session_type():
    html = render_activity_card({
        "steps_total": 5200,
        "had_training": True,
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

    assert '<span class="card-title">Training Sessions</span>' in html
    assert '<span class="metric-value">Lap Swimming</span>' in html
    assert '<span class="metric-unit">1 session</span>' in html


def test_daily_metric_details_are_collapsed_by_default():
    html = render_sleep_card({
        "sleep_score": 81,
        "sleep_hours": 7.5,
        "deep_sleep_pct": 18,
        "rem_sleep_pct": 22,
        "sleep_efficiency": 91,
    })

    assert '<details class="metric-details">' in html
    assert '<summary class="metric-details-summary">Details</summary>' in html
    assert '<details class="metric-details" open>' not in html
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
