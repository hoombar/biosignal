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


def test_correlations_rows_render_threshold_summary():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        const source = fs.readFileSync('static/js/correlations.js', 'utf8');
        const elements = {};

        function makeElement(id) {
            return {
                id,
                innerHTML: '',
                textContent: '',
                style: { display: 'none' },
                dataset: {},
                classList: { add() {}, remove() {}, toggle() {} },
                addEventListener() {},
                hasAttribute() { return false; },
                removeAttribute() {},
                setAttribute() {},
                focus() {},
            };
        }

        const context = {
            console: { error() {}, warn() {} },
            localStorage: {
                values: {},
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
        };

        vm.createContext(context);
        vm.runInContext(source, context);
        vm.runInContext(`
            metricMetadata = {
                coffee: { description: 'Tracked habit: Coffee', unit: 'count', category: 'Habits' },
            };
            lastCorrelations = [{
                metric: 'habit_coffee',
                coefficient: 0.8,
                p_value: 0.01,
                n: 10,
                strength: 'strong',
                threshold_value: 3,
                threshold_operator: '>',
                above_threshold_n: 5,
                below_threshold_n: 5,
                above_threshold_target_rate: 0.8,
                below_threshold_target_rate: 0.2,
                relative_risk: 4,
            }];
            renderRows();
        `, context);

        console.log(JSON.stringify({ html: elements['correlation-rows'].innerHTML }));
        """
    )
    result = subprocess.run(
        ["node", "-e", script],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    html = json.loads(result.stdout)["html"]
    assert "coffee &gt; 3" in html
    assert "80%" in html
    assert "20%" in html
