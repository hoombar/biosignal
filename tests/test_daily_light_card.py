import json
import subprocess
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def render_light_card(day: dict) -> str:
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        const source = fs.readFileSync('static/js/daily.js', 'utf8');
        const day = JSON.parse(process.argv[1]);

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

        if (typeof context.renderLightCard !== 'function') {
            throw new Error('renderLightCard is not defined');
        }

        console.log(JSON.stringify({ html: context.renderLightCard(day) }));
        """
    )
    result = subprocess.run(
        ["node", "-e", script, json.dumps(day)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)["html"]


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
