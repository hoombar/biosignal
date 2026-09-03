import json
import subprocess
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_gym_activity_cards_render_substitution_controls():
    source = (REPO_ROOT / "static/js/gym.js").read_text()

    assert "renderSubstitutePanel()" in source
    assert 'data-action="substitute-activity"' in source


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
    routes: list[dict] | None = None,
) -> dict:
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        let source = fs.readFileSync('static/js/gym.js', 'utf8');
        source = source.replace(
            "document.addEventListener('DOMContentLoaded', init);",
            "globalThis.__gymTest = {deleteSession, refresh, state, goToPreviousSession}; document.addEventListener('DOMContentLoaded', init);",
        );
        const sessionPayload = JSON.parse(process.argv[1]);
        const action = process.argv[2] || '';
        const addTypeChange = process.argv[3] || '';
        const routes = JSON.parse(process.argv[4] || '[]');
        const elements = {};
        const confirmCalls = [];
        const fetchCalls = [];
        const pendingTimers = [];
        const routeCallCounts = {};
        const errorLog = [];

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
            console: {
                error(...args) {
                    errorLog.push(args.map(a => (a && a.message) ? a.message : String(a)).join(' '));
                },
            },
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
                listeners: {},
                addEventListener(type, handler) {
                    this.listeners[type] = handler;
                },
            },
            setTimeout(callback) {
                pendingTimers.push(callback);
            },
            fetch: async (url, options) => {
                const method = (options && options.method) || 'GET';
                const call = {url: String(url), method};
                if (options && options.body) call.body = String(options.body);
                fetchCalls.push(call);
                if (method === 'DELETE') {
                    return {ok: true, status: 204, text: async () => '', json: async () => null};
                }
                const routeIndex = routes.findIndex(r => String(url).startsWith(r.match));
                if (routeIndex !== -1) {
                    const route = routes[routeIndex];
                    const key = `${method} ${route.match}`;
                    routeCallCounts[key] = (routeCallCounts[key] || 0) + 1;
                    if (route.failCount && routeCallCounts[key] <= route.failCount) {
                        throw new TypeError('Failed to fetch');
                    }
                    return {ok: true, status: 200, text: async () => 'route', json: async () => route.payload};
                }
                if (String(url).startsWith('/api/gym/session')) {
                    return {ok: true, status: 200, text: async () => 'session', json: async () => sessionPayload};
                }
                return {ok: true, status: 200, text: async () => 'ok', json: async () => []};
            },
        };
        vm.createContext(context);
        vm.runInContext(source, context);

        const drainTimers = async () => {
            for (let guard = 0; guard < 50 && pendingTimers.length; guard += 1) {
                pendingTimers.shift()();
                for (let micro = 0; micro < 5; micro++) await Promise.resolve();
            }
        };

        (async () => {
            await context.document.domReady();
            context.__gymTest.state.date = '2026-07-16';
            await context.__gymTest.refresh();
            if (action === 'delete') await context.__gymTest.deleteSession();
            if (action === 'previous') await context.__gymTest.goToPreviousSession();
            if (action.startsWith('save-activity') || action === 'rate-activity') {
                const effectiveAction = action === 'rate-activity' ? 'rate-activity' : 'save-activity';
                const weightInput = {dataset: {field: 'actual_weight'}, type: 'number', value: '55'};
                const card = {
                    dataset: {activityId: '3'},
                    querySelectorAll: (sel) => sel === '[data-field]' ? [weightInput] : [],
                    querySelector: () => null,
                };
                elements['gym-session'].listeners.click({
                    target: {
                        closest: (sel) => sel === '[data-action]'
                            ? {
                                dataset: {action: effectiveAction, rating: 'hard'},
                                closest: (inner) => inner === '[data-activity-id]' ? card : null,
                            }
                            : (sel === '[data-activity-id]' ? card : null),
                    },
                });
                for (let i = 0; i < 25; i++) await Promise.resolve();
            }
            if (action === 'save-activity-fail' || action === 'save-activity-recover') await drainTimers();
            if (action === 'substitute-activity') {
                const activityIdInput = {dataset: {substituteField: 'activity_id'}, value: '5'};
                const panel = {querySelectorAll: (sel) => sel === '[data-substitute-field]' ? [activityIdInput] : []};
                const card = {
                    dataset: {activityId: '3'},
                    querySelectorAll: () => [],
                    querySelector: () => null,
                };
                elements['gym-session'].listeners.click({
                    target: {
                        closest: (sel) => sel === '[data-action]'
                            ? {
                                dataset: {action},
                                closest: (inner) => inner === '[data-activity-id]'
                                    ? card
                                    : (inner === '.gym-substitute-panel' ? panel : null),
                            }
                            : (sel === '[data-activity-id]' ? card : null),
                    },
                });
                for (let i = 0; i < 25; i++) await Promise.resolve();
            }
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
                dateValue: elements['gym-date'].value,
                statusText: elements['gym-status'].textContent,
                sessionGetCount: fetchCalls.filter(c => c.url.startsWith('/api/gym/session?')).length,
                hasBeforeunload: Boolean(context.window.listeners.beforeunload),
                errorLog,
            }));
        })();
        """
    )
    result = subprocess.run(
        ["node", "-e", script, json.dumps(session_payload), action or "", fire_add_type_change or "", json.dumps(routes or [])],
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


def make_strength_session_activity() -> dict:
    return {
        "id": 3,
        "sort_order": 0,
        "activity_type": "strength",
        "name_snapshot": "Low row",
        "planned_sets": 3,
        "planned_reps": 12,
        "planned_weight": 50,
        "planned_weight_unit": "kg",
        "actual_sets": 3,
        "actual_reps": 12,
        "actual_weight": 50,
        "actual_weight_unit": "kg",
        "completed": False,
        "rating": None,
        "notes": None,
    }


def make_matching_template_payload(weight: int) -> dict:
    return {
        "id": 1,
        "name": "Standard upper/back and arms",
        "description": None,
        "activities": [{
            "id": 11,
            "sort_order": 0,
            "activity_type": "strength",
            "name": "Low row",
            "target_sets": 3,
            "target_reps": 12,
            "target_weight": weight,
            "target_weight_unit": "kg",
        }],
    }


def test_gym_weight_edit_offers_template_update_without_completion():
    activity = make_strength_session_activity()
    updated_activity = {**activity, "actual_weight": 55}
    routes = [
        {"match": "/api/gym/session-activities/3", "payload": updated_activity},
        {"match": "/api/gym/templates/1", "payload": make_matching_template_payload(weight=55)},
        {"match": "/api/gym/templates", "payload": [make_matching_template_payload(weight=50)]},
    ]

    result = run_gym_scenario(make_session_payload(None, activities=[activity]), action="save-activity", routes=routes)

    assert result["errorLog"] == []
    assert "Update the template with these completed values?" in result["confirmCalls"]
    template_puts = [c for c in result["fetchCalls"] if c["url"] == "/api/gym/templates/1" and c["method"] == "PUT"]
    assert template_puts and '"target_weight":55' in template_puts[0]["body"]


def test_gym_weight_edit_summary_reflects_change_immediately():
    activity = make_strength_session_activity()
    updated_activity = {**activity, "actual_weight": 55}
    routes = [
        {"match": "/api/gym/session-activities/3", "payload": updated_activity},
        {"match": "/api/gym/templates/1", "payload": make_matching_template_payload(weight=55)},
        {"match": "/api/gym/templates", "payload": [make_matching_template_payload(weight=50)]},
    ]

    result = run_gym_scenario(make_session_payload(None, activities=[activity]), action="save-activity", routes=routes)

    assert "55 kg · 3 x 12" in result["html"]


def test_gym_rating_save_does_not_offer_template_update():
    activity = make_strength_session_activity()
    updated_activity = {**activity, "rating": "hard"}
    routes = [
        {"match": "/api/gym/session-activities/3", "payload": updated_activity},
        {"match": "/api/gym/templates", "payload": [make_matching_template_payload(weight=50)]},
    ]

    result = run_gym_scenario(make_session_payload(None, activities=[activity]), action="rate-activity", routes=routes)

    assert result["confirmCalls"] == []
    assert not [c for c in result["fetchCalls"] if c["url"].startswith("/api/gym/templates/")]


def test_gym_previous_session_button_loads_earlier_session():
    routes = [{"match": "/api/gym/sessions/previous", "payload": {"date": "2026-07-14"}}]

    result = run_gym_scenario(make_session_payload(None), action="previous", routes=routes)

    previous_calls = [c for c in result["fetchCalls"] if c["url"].startswith("/api/gym/sessions/previous")]
    assert previous_calls and "before=2026-07-16" in previous_calls[0]["url"]
    assert "date=2026-07-14" in result["fetchCalls"][-1]["url"]
    assert result["dateValue"] == "2026-07-14"


def test_gym_previous_session_without_history_shows_message():
    routes = [{"match": "/api/gym/sessions/previous", "payload": None}]

    result = run_gym_scenario(make_session_payload(None), action="previous", routes=routes)

    assert result["statusText"] == "No previous session."
    assert result["dateValue"] != "2026-07-14"


def make_activity_with_previous_performance(completed: bool) -> dict:
    return {
        **make_strength_session_activity(),
        "id": 4,
        "completed": completed,
        "previous_performance": {
            "date": "2026-06-01",
            "sets": 3,
            "reps": 12,
            "weight": 52.5,
            "weight_unit": "kg",
            "duration_minutes": None,
            "intensity": None,
            "speed": None,
            "rating": "normal",
        },
    }


def test_gym_completed_activity_shows_previous_performance():
    result = run_gym_scenario(make_session_payload(None, activities=[make_activity_with_previous_performance(True)]))

    assert "Last time (2026-06-01)" in result["html"]
    assert "52.5 kg · 3 x 12" in result["html"]
    assert "felt normal" in result["html"]


def test_gym_incomplete_activity_hides_previous_performance():
    result = run_gym_scenario(make_session_payload(None, activities=[make_activity_with_previous_performance(False)]))

    assert "Last time (2026-06-01)" not in result["html"]


def test_gym_failed_save_keeps_edit_and_shows_durable_unsaved_warning():
    activity = make_strength_session_activity()
    updated_activity = {**activity, "actual_weight": 55}
    routes = [
        {"match": "/api/gym/session-activities/3", "payload": updated_activity, "failCount": 99},
        {"match": "/api/gym/templates", "payload": [make_matching_template_payload(weight=50)]},
    ]

    result = run_gym_scenario(make_session_payload(None, activities=[activity]), action="save-activity-fail", routes=routes)

    assert result["sessionGetCount"] == 2
    assert "55 kg · 3 x 12" in result["html"]
    assert "gym-activity--unsaved" in result["html"]
    assert "Retrying in the background" in result["html"]


def test_gym_pending_save_retries_in_background_and_clears_warning():
    activity = make_strength_session_activity()
    updated_activity = {**activity, "actual_weight": 55}
    routes = [
        {"match": "/api/gym/session-activities/3", "payload": updated_activity, "failCount": 2},
        {"match": "/api/gym/templates", "payload": [make_matching_template_payload(weight=50)]},
    ]

    result = run_gym_scenario(make_session_payload(None, activities=[activity]), action="save-activity-recover", routes=routes)

    put_calls = [c for c in result["fetchCalls"] if c["url"] == "/api/gym/session-activities/3" and c["method"] == "PUT"]
    assert len(put_calls) == 3
    assert "gym-activity--unsaved" not in result["html"]
    assert "55 kg · 3 x 12" in result["html"]


def test_gym_page_warns_before_leaving_with_pending_saves():
    result = run_gym_scenario(make_session_payload(None))

    assert result["hasBeforeunload"] is True


def test_gym_activity_card_offers_substitution_form():
    result = run_gym_scenario(make_session_payload(None, activities=[make_strength_session_activity()]))

    assert 'data-action="substitute-activity"' in result["html"]
    assert 'data-substitute-field="activity_id"' in result["html"]


def test_gym_finished_session_hides_substitution_form():
    payload = make_session_payload("2026-07-16T10:30:00+00:00", activities=[make_strength_session_activity()])
    result = run_gym_scenario(payload)

    assert 'data-action="substitute-activity"' not in result["html"]


def test_gym_substitute_submit_keeps_planned_context():
    activity = make_strength_session_activity()
    substituted = {
        **activity,
        "substitution_activity_id": 5,
        "substitution_name_snapshot": "Laid-back leg press",
        "actual_weight": 80,
        "completed": False,
    }
    routes = [
        {"match": "/api/gym/session-activities/3/substitution", "payload": substituted},
        {"match": "/api/gym/templates", "payload": [make_matching_template_payload(weight=50)]},
    ]

    result = run_gym_scenario(make_session_payload(None, activities=[activity]), action="substitute-activity", routes=routes)

    assert result["errorLog"] == []
    substitution_puts = [c for c in result["fetchCalls"] if c["url"].endswith("/substitution") and c["method"] == "PUT"]
    assert substitution_puts and '"activity_id":5' in substitution_puts[0]["body"]
    assert "Instead of Low row" in result["html"]
    assert "Laid-back leg press" in result["html"]
