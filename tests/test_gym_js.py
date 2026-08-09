import json
import subprocess
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_gym_activity_cards_do_not_render_substitution_controls():
    source = (REPO_ROOT / "static/js/gym.js").read_text()

    assert "renderSubstitution(activity)" not in source
    assert 'data-action="substitute-activity"' not in source


def run_fetch_scenario(method: str, outcomes: list[str]) -> dict:
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        let source = fs.readFileSync('static/js/gym.js', 'utf8');
        source = source.replace(
            "document.addEventListener('DOMContentLoaded', init);",
            "globalThis.__gymTest = {fetchJson};",
        );
        const outcomes = JSON.parse(process.argv[1]);
        const method = process.argv[2];
        let calls = 0;
        const context = {
            console: {error() {}},
            document: {addEventListener() {}},
            setTimeout(callback) { callback(); },
            fetch: async () => {
                const outcome = outcomes[calls++];
                if (outcome === 'network-error') throw new TypeError('Failed to fetch');
                return {
                    ok: outcome === 'ok',
                    status: outcome === 'server-error' ? 503 : 200,
                    text: async () => outcome,
                    json: async () => ({saved: true}),
                };
            },
        };
        vm.createContext(context);
        vm.runInContext(source, context);

        (async () => {
            try {
                const result = await context.__gymTest.fetchJson('/save', {method});
                console.log(JSON.stringify({calls, result, error: null}));
            } catch (error) {
                console.log(JSON.stringify({calls, result: null, error: error.message}));
            }
        })();
        """
    )
    result = subprocess.run(
        ["node", "-e", script, json.dumps(outcomes), method],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_gym_save_retries_transient_network_failure():
    result = run_fetch_scenario("PUT", ["network-error", "ok"])

    assert result == {"calls": 2, "result": {"saved": True}, "error": None}


def test_gym_save_surfaces_error_after_retry_is_exhausted():
    result = run_fetch_scenario("PUT", ["server-error", "server-error"])

    assert result["calls"] == 2
    assert "server-error" in result["error"]


def test_gym_create_is_not_automatically_retried():
    result = run_fetch_scenario("POST", ["network-error", "ok"])

    assert result["calls"] == 1
    assert result["error"] == "Failed to fetch"
