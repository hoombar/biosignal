import json
import subprocess
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_overview_snapshot(snapshot: list[dict]) -> dict:
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        const source = fs.readFileSync('static/js/overview.js', 'utf8');
        const snapshot = JSON.parse(process.argv[1]);
        const fetchCalls = [];
        const elements = {};

        function makeElement(id) {
            return {
                id,
                value: '',
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
                    json: async () => snapshot,
                };
            },
        };

        vm.createContext(context);
        vm.runInContext(source, context);

        (async () => {
            await context.loadCorrelationSnapshot();
            console.log(JSON.stringify({
                html: elements['top-correlates'].innerHTML,
                fetchCalls,
            }));
        })().catch(err => {
            console.error(err);
            process.exit(1);
        });
        """
    )
    result = subprocess.run(
        ["node", "-e", script, json.dumps(snapshot)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_overview_snapshot_renders_strong_signal_without_selected_habit():
    result = run_overview_snapshot([
        {
            "target": "habit:pm_slump",
            "target_label": "pm slump",
            "target_kind": "habit",
            "metric": "sleep_hours",
            "coefficient": -0.4567,
            "strength": "moderate",
            "n": 12,
        },
    ])

    assert "sleep hours" in result["html"]
    assert "pm slump" in result["html"]
    assert "r=-0.457" in result["html"]
    assert "n=12" in result["html"]
    assert result["fetchCalls"] == ["/api/correlation-snapshot?limit=6&min_abs=0.6&min_days=14"]
