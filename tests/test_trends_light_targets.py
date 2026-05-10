import json
import subprocess
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_trends_target_scenario(target: str) -> dict:
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        const source = fs.readFileSync('static/js/trends.js', 'utf8');
        const selectedTarget = process.argv[1];
        const elements = {};
        const fetchCalls = [];

        function makeElement(id) {
            return {
                id,
                value: '',
                innerHTML: '',
                className: '',
                checked: false,
                style: {
                    setProperty() {},
                },
                classList: {
                    contains() { return false; },
                    add() {},
                    remove() {},
                    toggle() {},
                },
                appendChild() {},
                querySelector() { return null; },
            };
        }

        const responses = {
            '/api/export/metadata': {
                features: {
                    daylight_minutes: {
                        description: 'Minutes between local sunrise and sunset',
                        unit: 'minutes',
                        category: 'Light',
                    },
                    sleep_score: {
                        description: 'Garmin sleep score',
                        unit: '0-100',
                        category: 'Sleep',
                    },
                    'supplement:vitamin_d': {
                        description: 'Supplement: Vitamin D',
                        unit: 'boolean',
                        category: 'Supplements',
                    },
                },
            },
            '/api/settings/habits': [
                { habit_name: 'pm_slump', display_name: 'PM Slump', color: '#ff4466' },
            ],
            '/api/correlation-targets': [
                { target: 'daylight_minutes', label: 'daylight minutes', kind: 'metric', category: 'Light' },
                { target: 'sleep_score', label: 'sleep score', kind: 'metric', category: 'Sleep' },
                { target: 'habit:pm_slump', label: 'PM Slump', kind: 'habit', category: 'Habits' },
                { target: 'supplement:vitamin_d', label: 'Vitamin D', kind: 'supplement', category: 'Supplements' },
            ],
            '/api/daily?start=2026-04-23&end=2026-05-06': [],
        };

        const context = {
            console,
            Set,
            Date: class extends Date {
                constructor(...args) {
                    if (args.length === 0) super('2026-05-06T12:00:00');
                    else super(...args);
                }
                static now() {
                    return new Date('2026-05-06T12:00:00').getTime();
                }
            },
            localStorage: {
                values: {},
                getItem(key) { return this.values[key] || null; },
                setItem(key, value) { this.values[key] = String(value); },
            },
            document: {
                addEventListener() {},
                createElement() { return makeElement('created'); },
                querySelectorAll() { return []; },
                getElementById(id) {
                    if (!elements[id]) elements[id] = makeElement(id);
                    return elements[id];
                },
            },
            window: {
                addEventListener() {},
            },
            Chart: function() {},
            fetch: async (url) => {
                fetchCalls.push(url);
                if (url.startsWith('/api/correlations?')) {
                    return {
                        ok: true,
                        json: async () => [
                            { metric: 'habit_pm_slump', coefficient: 0.42, n: 12, strength: 'moderate' },
                        ],
                    };
                }
                return {
                    ok: true,
                    json: async () => responses[url],
                };
            },
            alert() {},
        };
        context.window.document = context.document;
        context.window.localStorage = context.localStorage;

        vm.createContext(context);
        vm.runInContext(source, context);

        (async () => {
            await context.init();
            const select = elements['correlate-target'];
            select.value = selectedTarget;
            await context.onCorrelateTargetChange();

            console.log(JSON.stringify({
                optionsHtml: select.innerHTML,
                suggestionsHtml: elements['suggestions-content'].innerHTML,
                fetchCalls,
                storedTarget: context.localStorage.values['biosignal_correlation_target'],
            }));
        })().catch(err => {
            console.error(err);
            process.exit(1);
        });
        """
    )
    result = subprocess.run(
        ["node", "-e", script, target],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_trends_selector_includes_light_metric_targets():
    result = run_trends_target_scenario("daylight_minutes")

    assert "Metric: daylight minutes" in result["optionsHtml"]
    assert "Habit: PM Slump" in result["optionsHtml"]
    assert result["storedTarget"] == "daylight_minutes"
    assert any(
        call == "/api/correlations?target=daylight_minutes&min_days=5"
        for call in result["fetchCalls"]
    )
    assert "PM Slump" in result["suggestionsHtml"]


def test_trends_selector_includes_supplement_targets():
    result = run_trends_target_scenario("supplement:vitamin_d")

    assert "Supplements" in result["optionsHtml"]
    assert "Supplement: Vitamin D" in result["optionsHtml"]
    assert any(
        call == "/api/correlations?target=supplement%3Avitamin_d&min_days=5"
        for call in result["fetchCalls"]
    )
    assert result["storedTarget"] == "supplement:vitamin_d"
