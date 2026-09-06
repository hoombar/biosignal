import json
import subprocess
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

METRIC_DETAILS_STORAGE_KEY = "biosignal.daily.metricDetails"


def run_daily_js(action: str, payload: dict) -> dict:
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        const source = fs.readFileSync('static/js/daily.js', 'utf8');
        const action = process.argv[1];
        const payload = JSON.parse(process.argv[2]);

        const storage = new Map(Object.entries(payload.storage || {}));
        const context = {
            console,
            localStorage: {
                getItem: (key) => (storage.has(key) ? storage.get(key) : null),
                setItem: (key, value) => storage.set(key, String(value)),
                removeItem: (key) => storage.delete(key),
            },
            window: { location: { hash: '' }, addEventListener() {} },
            document: {
                addEventListener() {},
                getElementById() { return null; },
                querySelectorAll() { return []; },
            },
            history: { pushState() {} },
            fetch: async () => ({ json: async () => ({}) }),
            requestAnimationFrame(callback) { callback(); },
            loadHabitConfig: async () => {},
            loadHabitsList: async () => [],
            getHabitDisplay: () => ({ label: '', color: '', sort_order: 0 }),
            getHabitColor: () => '#000',
            HabitPanel: {
                renderHabitsPanel: () => '',
                bindHabitsPanel: () => {},
            },
            __weatherPreferences: {},
        };

        vm.createContext(context);
        vm.runInContext(source, context);

        let result;
        if (action === 'render') {
            result = { html: context[payload.function](payload.day) };
        } else if (action === 'toggle') {
            const handlers = [];
            const target = {
                open: false,
                dataset: { detailsKey: payload.key },
                addEventListener(type, handler) {
                    if (type === 'toggle') handlers.push(handler);
                },
            };
            const container = { querySelectorAll: () => [target] };
            context._bindMetricDetailToggles(container);
            target.open = payload.open;
            handlers.forEach((handler) => handler());
            result = { storage: Object.fromEntries(storage) };
        } else {
            throw new Error(`Unknown action: ${action}`);
        }

        console.log(JSON.stringify(result));
        """
    )
    result = subprocess.run(
        ["node", "-e", script, action, json.dumps(payload)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def render_card(function_name: str, day: dict, state: dict | None = None) -> str:
    storage = {}
    if state is not None:
        storage[METRIC_DETAILS_STORAGE_KEY] = json.dumps(state)
    return run_daily_js("render", {"function": function_name, "day": day, "storage": storage})["html"]


def toggle_details(key: str, open_state: bool, state: dict | None = None) -> dict:
    storage = {}
    if state is not None:
        storage[METRIC_DETAILS_STORAGE_KEY] = json.dumps(state)
    return run_daily_js("toggle", {"key": key, "open": open_state, "storage": storage})["storage"]


def test_metric_details_render_collapsed_by_default_with_key():
    html = render_card("renderSleepCard", {"sleep_score": 72})

    assert '<details class="metric-details" data-details-key="sleep">' in html
    assert '<details class="metric-details" open' not in html


def test_metric_details_restore_open_state_from_storage():
    html = render_card("renderSleepCard", {"sleep_score": 72}, state={"sleep": True})

    assert '<details class="metric-details" open data-details-key="sleep">' in html


def test_metric_details_explicit_false_stays_collapsed():
    html = render_card("renderSleepCard", {"sleep_score": 72}, state={"sleep": False})

    assert '<details class="metric-details" data-details-key="sleep">' in html
    assert '<details class="metric-details" open' not in html


def test_each_card_has_its_own_details_key():
    sleep_html = render_card("renderSleepCard", {"sleep_score": 72})
    weather_html = render_card("renderWeatherCard", {"temperature_2m_avg": 15.0})
    activity_html = render_card("renderActivityCard", {
        "steps_total": 8000,
        "activity_sessions": [{
            "activity_type": "lap_swimming",
            "duration_min": 45,
        }],
    })

    assert 'data-details-key="weather"' in weather_html
    assert 'data-details-key="activity"' in activity_html
    assert 'data-details-key="session-lap_swimming"' in activity_html
    assert 'data-details-key="sleep"' in sleep_html


def test_toggle_open_persists_state():
    storage = toggle_details("weather", True)

    assert json.loads(storage[METRIC_DETAILS_STORAGE_KEY]) == {"weather": True}


def test_toggle_close_removes_state():
    storage = toggle_details("sleep", False, state={"sleep": True})

    assert json.loads(storage[METRIC_DETAILS_STORAGE_KEY]) == {}


def test_toggle_keeps_other_cards_state():
    storage = toggle_details("weather", True, state={"sleep": True})

    assert json.loads(storage[METRIC_DETAILS_STORAGE_KEY]) == {"sleep": True, "weather": True}


def test_corrupt_storage_falls_back_to_collapsed():
    result = run_daily_js("render", {
        "function": "renderSleepCard",
        "day": {"sleep_score": 72},
        "storage": {METRIC_DETAILS_STORAGE_KEY: "not-json{"},
    })

    assert '<details class="metric-details" data-details-key="sleep">' in result["html"]
    assert '<details class="metric-details" open' not in result["html"]
