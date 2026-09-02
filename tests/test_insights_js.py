"""Browser-behavior tests for the insights page."""

import json
import subprocess
import textwrap


def test_changing_habit_aborts_and_ignores_stale_analysis():
    script = textwrap.dedent(
        r"""
        const fs = require('fs');
        const vm = require('vm');

        const elements = {
            'target-habit': {
                value: 'bath',
                innerHTML: '',
                options: [{ text: 'Bath' }, { text: 'Coffee' }],
                selectedIndex: 0,
            },
            'insights-list': { innerHTML: '' },
            'patterns-list': { innerHTML: '' },
        };
        const pending = [];
        let domReady;

        class FakeAbortController {
            constructor() { this.signal = { aborted: false }; }
            abort() { this.signal.aborted = true; }
        }

        const context = vm.createContext({
            AbortController: FakeAbortController,
            console,
            document: {
                getElementById: id => elements[id],
                addEventListener: (event, callback) => {
                    if (event === 'DOMContentLoaded') domReady = callback;
                },
            },
            fetch: (url, options = {}) => {
                if (url === '/api/settings/habits') {
                    return Promise.resolve({
                        ok: true,
                        json: async () => [
                            { habit_name: 'bath', display_name: 'Bath' },
                            { habit_name: 'coffee', display_name: 'Coffee' },
                        ],
                    });
                }
                return new Promise(resolve => pending.push({ url, options, resolve }));
            },
            window: { location: {} },
        });

        const source = fs.readFileSync('static/js/insights.js', 'utf8');
        vm.runInContext(source, context);

        (async () => {
            const firstLoad = domReady();
            await new Promise(resolve => setImmediate(resolve));

            elements['target-habit'].value = 'coffee';
            elements['target-habit'].selectedIndex = 1;
            const secondLoad = vm.runInContext('loadAll()', context);
            await new Promise(resolve => setImmediate(resolve));

            const coffee = pending.filter(request => request.url.includes('coffee'));
            const bath = pending.filter(request => request.url.includes('bath'));

            for (const request of coffee) {
                const isInsights = request.url.startsWith('/api/insights');
                request.resolve({
                    ok: true,
                    json: async () => isInsights
                        ? [{ text: 'Coffee result', confidence: 'high', effect_size: 2 }]
                        : [{ description: 'Coffee pattern', probability: 0.8,
                             baseline_probability: 0.4, relative_risk: 2, sample_size: 10 }],
                });
            }
            await secondLoad;

            for (const request of bath) {
                const isInsights = request.url.startsWith('/api/insights');
                request.resolve({
                    ok: true,
                    json: async () => isInsights
                        ? [{ text: 'Stale Bath result', confidence: 'high', effect_size: 2 }]
                        : [{ description: 'Stale Bath pattern', probability: 0.8,
                             baseline_probability: 0.4, relative_risk: 2, sample_size: 10 }],
                });
            }
            await firstLoad;

            console.log(JSON.stringify({
                urls: pending.map(request => request.url),
                bathAborted: bath.every(request => request.options.signal?.aborted === true),
                insightsHtml: elements['insights-list'].innerHTML,
                patternsHtml: elements['patterns-list'].innerHTML,
            }));
        })().catch(error => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert result["bathAborted"] is True
    assert "Coffee result" in result["insightsHtml"]
    assert "Stale Bath result" not in result["insightsHtml"]
    assert "Coffee pattern" in result["patternsHtml"]
    assert "Stale Bath pattern" not in result["patternsHtml"]
