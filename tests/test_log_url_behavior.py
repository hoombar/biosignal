import json
import subprocess
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_log_js_scenario(
    initial_hash: str,
    action: str | None = None,
    supplement_config: dict | None = None,
    daily_response: list[dict] | None = None,
) -> dict:
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        const source = fs.readFileSync('static/js/log.js', 'utf8');
        const initialHash = process.argv[1];
        const action = process.argv[2] || '';
        const supplementConfig = JSON.parse(process.argv[3] || '{"slots":[]}');
        const dailyResponse = JSON.parse(process.argv[4] || 'null');
        const elements = {};
        let habitBindOptions = null;
        const scrollCalls = [];
        const dailyUrls = [];
        const fetchCalls = [];

        function makeElement(id) {
            return {
                id,
                textContent: '',
                innerHTML: '',
                disabled: false,
                style: { display: '' },
                listeners: {},
                addEventListener(type, handler) {
                    this.listeners[type] = handler;
                },
                click() {
                    if (this.listeners.click) this.listeners.click();
                },
            };
        }

        const replaceCalls = [];
        const fixedNow = new Date('2026-05-04T12:00:00');
        class FixedDate extends Date {
            constructor(...args) {
                if (args.length === 0) {
                    super(fixedNow.getTime());
                } else {
                    super(...args);
                }
            }
            static now() {
                return fixedNow.getTime();
            }
        }

        const context = {
            Date: FixedDate,
            Promise,
            RegExp,
            console: { warn() {} },
            setTimeout,
            FormData: class FormData {
                constructor(form) {
                    this.fields = form.fields || {};
                }
                get(name) {
                    return this.fields[name] ?? null;
                }
            },
            window: {
                location: { hash: initialHash },
                _activeHabits: [],
                scrollX: 0,
                scrollY: 480,
                scrollTo(x, y) {
                    scrollCalls.push([x, y]);
                    this.scrollX = x;
                    this.scrollY = y;
                },
            },
            history: {
                replaceState(_state, _title, url) {
                    replaceCalls.push(url);
                    context.window.location.hash = url.startsWith('#') ? url : '';
                },
            },
            document: {
                getElementById(id) {
                    if (!elements[id]) elements[id] = makeElement(id);
                    return elements[id];
                },
                addEventListener(type, handler) {
                    this[type] = handler;
                },
            },
            fetch: async (url, options) => {
                fetchCalls.push({
                    url: String(url),
                    method: options?.method || 'GET',
                    body: options?.body || null,
                });
                if (String(url).startsWith('/api/daily')) dailyUrls.push(url);
                return {
                    ok: true,
                    text: async () => '',
                    json: async () => {
                        if (url === '/api/habits/list') return [];
                        if (url === '/api/supplements/config') return supplementConfig;
                        return dailyResponse || [{ date: '2026-05-04', habits: [], supplements: [], contexts: [] }];
                    },
                };
            },
            loadHabitConfig: async () => {},
            loadHabitsList: async () => [],
            HabitPanel: {
                renderHabitsPanel: () => '<div></div>',
                bindHabitsPanel: (_container, opts) => { habitBindOptions = opts; },
            },
        };
        context.window.Date = FixedDate;
        context.window.history = context.history;
        context.window.document = context.document;

        vm.createContext(context);
        vm.runInContext(source, context);

        async function flushAsyncWork() {
            for (let i = 0; i < 6; i += 1) {
                await Promise.resolve();
                await new Promise(resolve => setTimeout(resolve, 0));
            }
        }

        (async () => {
            await flushAsyncWork();
            if (action === 'prev') {
                elements['log-prev'].click();
                await flushAsyncWork();
            } else if (action === 'habitChange') {
                await habitBindOptions.onValueChange('2026-05-04', 'coffee', 'counter', 2);
                await flushAsyncWork();
            } else if (action === 'contextSubmit') {
                await elements['log-context'].listeners.submit({
                    preventDefault() {},
                    target: {
                        id: 'context-form',
                        fields: {
                            title: 'Conference in Germany',
                            start_date: '2026-05-19',
                            end_date: '2026-05-23',
                            category: 'conference',
                            exclude_from_baseline: 'on',
                        },
                        querySelector() { return { disabled: false }; },
                    },
                });
                await flushAsyncWork();
            } else if (action === 'contextEdit' || action === 'contextEditSubmit') {
                await elements['log-context'].listeners.click({
                    target: {
                        closest(selector) {
                            if (selector === 'button[data-context-edit]') {
                                return { dataset: { contextEdit: '1' } };
                            }
                            return null;
                        },
                    },
                });
                if (action === 'contextEditSubmit') {
                    await elements['log-context'].listeners.submit({
                        preventDefault() {},
                        target: {
                            id: 'context-form',
                            dataset: { contextId: '1' },
                            fields: {
                                title: 'Conference extended',
                                start_date: '2026-05-01',
                                end_date: '2026-05-09',
                                category: 'conference',
                                exclude_from_baseline: 'on',
                                notes: 'Updated range',
                            },
                            querySelector() { return { disabled: false }; },
                        },
                    });
                    await flushAsyncWork();
                }
            }
            console.log(JSON.stringify({
                hash: context.window.location.hash,
                replaceCalls,
                dateText: elements['log-date'].textContent,
                contextHtml: elements['log-context'].innerHTML,
                dailyUrls,
                fetchCalls,
                scrollCalls,
                supplementsHtml: elements['log-supplements'].innerHTML,
            }));
        })().catch(err => {
            console.error(err);
            process.exit(1);
        });
        """
    )
    result = subprocess.run(
        [
            "node",
            "-e",
            script,
            initial_hash,
            action or "",
            json.dumps(supplement_config or {"slots": []}),
            json.dumps(daily_response) if daily_response is not None else "null",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_log_defaults_to_today_without_adding_hash_to_url():
    result = run_log_js_scenario("")

    assert result["hash"] == ""
    assert result["replaceCalls"] == []


def test_log_navigation_adds_selected_date_to_url():
    result = run_log_js_scenario("", "prev")

    assert result["hash"] == "#2026-05-03"
    assert result["replaceCalls"] == ["#2026-05-03"]


def test_log_only_renders_configured_supplement_slots():
    result = run_log_js_scenario(
        "",
        supplement_config={
            "slots": [
                {"slot": "morning", "version": 1, "items": [{"name": "Vitamin D"}]},
                {"slot": "midday", "version": None, "items": []},
                {"slot": "evening", "version": None, "items": []},
            ]
        },
    )

    html = result["supplementsHtml"]
    assert 'data-slot="morning"' in html
    assert 'data-slot="midday"' not in html
    assert 'data-slot="evening"' not in html


def test_log_context_panel_defaults_collapsed_with_saved_context():
    result = run_log_js_scenario(
        "#2026-05-04",
        daily_response=[{
            "date": "2026-05-04",
            "habits": [],
            "supplements": [],
            "baseline_excluded": True,
            "contexts": [{
                "id": 1,
                "title": "Conference abroad",
                "start_date": "2026-05-01",
                "end_date": "2026-05-07",
                "category": "conference",
                "tags": ["hotel"],
                "intensity": "high",
                "exclude_from_baseline": True,
                "notes": "Saved range",
            }],
        }],
    )

    html = result["contextHtml"]
    assert '<details class="context-panel">' in html
    assert '<details class="context-panel" open' not in html
    assert '1 context: Conference abroad' in html
    assert 'Saved for this date range' in html
    assert 'Excluded from baseline' in html


def test_log_context_edit_uses_saved_date_range_instead_of_selected_day():
    result = run_log_js_scenario(
        "#2026-05-04",
        "contextEdit",
        daily_response=[{
            "date": "2026-05-04",
            "habits": [],
            "supplements": [],
            "contexts": [{
                "id": 1,
                "title": "Conference abroad",
                "start_date": "2026-05-01",
                "end_date": "2026-05-07",
                "category": "conference",
                "tags": ["hotel"],
                "intensity": "high",
                "exclude_from_baseline": True,
                "notes": "Saved range",
            }],
        }],
    )

    html = result["contextHtml"]
    assert '<details class="context-panel" open>' in html
    assert 'name="start_date" value="2026-05-01"' in html
    assert 'name="end_date" value="2026-05-07"' in html
    assert 'data-context-id="1"' in html
    assert "Update context" in html


def test_log_context_edit_patches_fields_without_erasing_hidden_metadata():
    result = run_log_js_scenario(
        "#2026-05-04",
        "contextEditSubmit",
        daily_response=[{
            "date": "2026-05-04",
            "habits": [],
            "supplements": [],
            "contexts": [{
                "id": 1,
                "title": "Conference abroad",
                "start_date": "2026-05-01",
                "end_date": "2026-05-07",
                "category": "conference",
                "tags": ["hotel"],
                "intensity": "high",
                "exclude_from_baseline": True,
                "notes": "Saved range",
            }],
        }],
    )

    request = next(call for call in result["fetchCalls"] if call["method"] == "PATCH")
    assert request["url"] == "/api/context-events/1"
    body = json.loads(request["body"])
    assert body["start_date"] == "2026-05-01"
    assert body["end_date"] == "2026-05-09"
    assert "tags" not in body
    assert "intensity" not in body


def test_log_preserves_scroll_after_habit_counter_update():
    result = run_log_js_scenario("#2026-05-04", "habitChange")

    assert result["scrollCalls"] == [[0, 480]]


def test_log_refetches_current_day_after_context_submit():
    result = run_log_js_scenario("#2026-05-04", "contextSubmit")

    request = next(call for call in result["fetchCalls"] if call["method"] == "POST")
    assert request["url"] == "/api/context-events"
    assert result["dailyUrls"].count("/api/daily?start=2026-05-04&end=2026-05-04") == 2
