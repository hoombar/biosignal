import json
import subprocess
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_correlation_target_selector(target: str) -> dict:
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        const source = fs.readFileSync('static/js/correlations.js', 'utf8');
        const target = process.argv[1];
        const elements = {};
        const fetchCalls = [];

        function makeElement(id) {
            return {
                id,
                value: '',
                innerHTML: '',
                textContent: '',
                style: { display: 'none' },
                dataset: {},
                classList: {
                    add() {},
                    remove() {},
                    toggle() {},
                },
                addEventListener() {},
                hasAttribute() { return false; },
                removeAttribute() {},
                setAttribute() {},
                focus() {},
            };
        }

        const responses = {
            '/api/export/metadata': {
                features: {
                    sleep_score: { description: 'Garmin sleep score', unit: '0-100', category: 'Sleep' },
                    'supplement:vitamin_d3': { description: 'Supplement: Vitamin D3', unit: 'boolean', category: 'Supplements' },
                },
            },
            '/api/correlation-targets': [
                { target: 'sleep_score', label: 'sleep score', kind: 'metric', category: 'Sleep' },
                { target: 'habit:pm_slump', label: 'PM Slump', kind: 'habit', category: 'Habits' },
                { target: 'supplement:vitamin_d3', label: 'Vitamin D3', kind: 'supplement', category: 'Supplements' },
            ],
        };

        const context = {
            console: { error() {}, warn() {} },
            localStorage: {
                values: { biosignal_correlation_target: target },
                getItem(key) { return this.values[key] || null; },
                setItem(key, value) { this.values[key] = String(value); },
            },
            document: {
                addEventListener() {},
                querySelector() { return makeElement('query'); },
                querySelectorAll() { return []; },
                getElementById(id) {
                    if (!elements[id]) elements[id] = makeElement(id);
                    return elements[id];
                },
            },
            fetch: async (url) => {
                fetchCalls.push(url);
                if (url.startsWith('/api/correlations?')) {
                    return { ok: true, json: async () => [] };
                }
                return { ok: true, json: async () => responses[url] };
            },
        };

        vm.createContext(context);
        vm.runInContext(source, context);

        (async () => {
            await context.loadMetricMetadata();
            await context.loadTargetSelector();

            const select = elements['target-habit'];
            console.log(JSON.stringify({
                optionsHtml: select.innerHTML,
                selectedValue: select.value,
                targetLabel: elements['corr-target-label'].textContent,
                fetchCalls,
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


def test_correlations_selector_includes_supplement_targets():
    result = run_correlation_target_selector("supplement:vitamin_d3")

    assert "Supplements" in result["optionsHtml"]
    assert "Supplement: Vitamin D3" in result["optionsHtml"]
    assert result["selectedValue"] == "supplement:vitamin_d3"
    assert result["targetLabel"] == "Supplement: Vitamin D3"
    assert any(
        call == "/api/correlations?target=supplement%3Avitamin_d3"
        for call in result["fetchCalls"]
    )
