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


def make_session_payload(completed_at: str | None, activities: list[dict] | None = None) -> dict:
    return {
        "id": 7,
        "date": "2026-07-16",
        "template_id": 1,
        "template_name_snapshot": "Standard upper/back and arms",
        "started_at": "2026-07-16T09:00:00+00:00",
        "completed_at": completed_at,
        "activities": activities or [],
    }


def run_gym_scenario(
    session_payload: dict,
    action: str | None = None,
    fire_add_type_change: str | None = None,
) -> dict:
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        let source = fs.readFileSync('static/js/gym.js', 'utf8');
        source = source.replace(
            "document.addEventListener('DOMContentLoaded', init);",
            "globalThis.__gymTest = {deleteSession, refresh}; document.addEventListener('DOMContentLoaded', init);",
        );
        const sessionPayload = JSON.parse(process.argv[1]);
        const action = process.argv[2] || '';
        const addTypeChange = process.argv[3] || '';
        const elements = {};
        const confirmCalls = [];
        const fetchCalls = [];

        function makeElement(id) {
            return {
                id,
                textContent: '',
                innerHTML: '',
                style: { display: '' },
                value: '',
                listeners: {},
                classList: { toggle() {}, add() {}, remove() {} },
                addEventListener(type, handler) {
                    this.listeners[type] = handler;
                },
            };
        }

        const context = {
            console: {error() {}},
            document: {
                addEventListener(type, handler) {
                    this.domReady = handler;
                },
                getElementById(id) {
                    if (!elements[id]) elements[id] = makeElement(id);
                    return elements[id];
                },
            },
            window: {
                confirm(message) {
                    confirmCalls.push(message);
                    return true;
                },
            },
            setTimeout(callback) { callback(); },
            fetch: async (url, options) => {
                const method = (options && options.method) || 'GET';
                fetchCalls.push({url: String(url), method});
                if (method === 'DELETE') {
                    return {ok: true, status: 204, text: async () => '', json: async () => null};
                }
                if (String(url).startsWith('/api/gym/session')) {
                    return {ok: true, status: 200, text: async () => 'session', json: async () => sessionPayload};
                }
                return {ok: true, status: 200, text: async () => 'ok', json: async () => []};
            },
        };
        vm.createContext(context);
        vm.runInContext(source, context);

        (async () => {
            await context.document.domReady();
            await context.__gymTest.refresh();
            if (action === 'delete') await context.__gymTest.deleteSession();
            if (addTypeChange) {
                const fieldsEl = makeElement('add-fields');
                elements['gym-session'].listeners.change({
                    target: {
                        dataset: {addField: 'activity_type'},
                        value: addTypeChange,
                        closest: () => ({querySelector: () => fieldsEl}),
                    },
                });
                await Promise.resolve();
                console.log(JSON.stringify({
                    html: elements['gym-session'].innerHTML,
                    addFieldsHtml: fieldsEl.innerHTML,
                    confirmCalls,
                    fetchCalls,
                }));
                return;
            }
            console.log(JSON.stringify({
                html: elements['gym-session'].innerHTML,
                confirmCalls,
                fetchCalls,
            }));
        })();
        """
    )
    result = subprocess.run(
        ["node", "-e", script, json.dumps(session_payload), action or "", fire_add_type_change or ""],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_gym_active_session_keeps_cancel_label():
    result = run_gym_scenario(make_session_payload(None))

    assert "Cancel session" in result["html"]
    assert "Discard session" not in result["html"]


def test_gym_finished_session_uses_discard_label():
    result = run_gym_scenario(make_session_payload("2026-07-16T10:30:00+00:00"))

    assert "Discard session" in result["html"]
    assert "Cancel session" not in result["html"]


def test_gym_discard_confirm_states_permanent_deletion():
    result = run_gym_scenario(make_session_payload("2026-07-16T10:30:00+00:00"), action="delete")

    assert len(result["confirmCalls"]) == 1
    message = result["confirmCalls"][0]
    assert "Discard" in message
    assert "permanently delete" in message
    assert {"url": "/api/gym/sessions/7", "method": "DELETE"} in result["fetchCalls"]


def test_gym_active_session_cancel_confirm_unchanged():
    result = run_gym_scenario(make_session_payload(None), action="delete")

    assert len(result["confirmCalls"]) == 1
    message = result["confirmCalls"][0]
    assert "Cancel this gym session?" in message
    assert {"url": "/api/gym/sessions/7", "method": "DELETE"} in result["fetchCalls"]


def make_mobility_session_payload() -> dict:
    return make_session_payload(None, activities=[{
        "id": 3,
        "activity_type": "mobility",
        "name_snapshot": "Kettlebell mason twist",
        "planned_sets": 3,
        "planned_reps": 10,
        "planned_weight": 12,
        "planned_weight_unit": "kg",
        "planned_notes": "very good",
        "actual_sets": None,
        "actual_reps": None,
        "actual_weight": None,
        "actual_weight_unit": None,
        "completed": False,
        "rating": None,
        "notes": None,
    }])


def test_gym_mobility_activity_card_offers_weight_and_note_fields():
    result = run_gym_scenario(make_mobility_session_payload())

    assert 'data-field="actual_weight"' in result["html"]
    assert 'data-field="notes"' in result["html"]
    assert "12 kg · 3 x 10" in result["html"]


def test_gym_add_activity_panel_has_notes_field():
    result = run_gym_scenario(make_session_payload(None))

    assert 'data-add-field="notes"' in result["html"]


def test_gym_add_activity_panel_mobility_type_offers_weight_and_unit():
    result = run_gym_scenario(make_session_payload(None), fire_add_type_change="mobility")

    assert 'data-add-field="target_weight"' in result["addFieldsHtml"]
    assert 'data-add-field="target_weight_unit"' in result["addFieldsHtml"]
    assert 'data-add-field="target_sets"' in result["addFieldsHtml"]
