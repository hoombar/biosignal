import json
import subprocess
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_overview_correlations(correlations: list[dict]) -> dict:
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        const source = fs.readFileSync('static/js/overview.js', 'utf8');
        const correlations = JSON.parse(process.argv[1]);
        const fetchCalls = [];
        const elements = {};

        function makeElement(id) {
            return {
                id,
                value: id === 'target-habit' ? 'pm_slump' : '',
                innerHTML: '',
                textContent: '',
            };
        }

        const context = {
            console: { error() {} },
            localStorage: {
                values: {},
                getItem(key) { return this.values[key] || null; },
                setItem(key, value) { this.values[key] = String(value); },
            },
            document: {
                addEventListener() {},
                getElementById(id) {
                    if (!elements[id]) elements[id] = makeElement(id);
                    return elements[id];
                },
            },
            fetch: async (url) => {
                fetchCalls.push(url);
                return {
                    ok: true,
                    json: async () => correlations,
                };
            },
        };

        vm.createContext(context);
        vm.runInContext(source, context);

        (async () => {
            await context.loadCorrelations();
            console.log(JSON.stringify({
                html: elements['top-correlates'].innerHTML,
                fetchCalls,
                storedHabit: context.localStorage.values['biosignal_target_habit'],
            }));
        })().catch(err => {
            console.error(err);
            process.exit(1);
        });
        """
    )
    result = subprocess.run(
        ["node", "-e", script, json.dumps(correlations)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_overview_correlations_render_without_optional_mean_fields():
    result = run_overview_correlations([
        {
            "metric": "sleep_hours",
            "coefficient": -0.4567,
            "strength": "moderate",
        },
    ])

    assert "sleep hours" in result["html"]
    assert "Correlation: -0.457 (moderate)" in result["html"]
    assert "Positive days" not in result["html"]
    assert result["storedHabit"] == "pm_slump"
    assert result["fetchCalls"] == ["/api/correlations?target_habit=pm_slump"]
