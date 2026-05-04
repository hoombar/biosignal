import json
import subprocess
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_habit_panel_row_tap_scenario(habit_type: str = "binary") -> dict:
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        const source = fs.readFileSync('static/js/habit-panel.js', 'utf8');
        const habitType = process.argv[1];
        const fetchCalls = [];

        const toggleButton = {
            getAttribute(name) {
                return name === 'aria-pressed' ? 'false' : null;
            },
        };

        const item = {
            dataset: {
                date: '2026-05-04',
                habitId: '42',
                habitName: 'pm_slump',
                habitType,
            },
            classList: {
                add() {},
                remove() {},
            },
            closest(selector) {
                return selector === '.habit-sidebar-item' ? this : null;
            },
            querySelector(selector) {
                return selector === '.habit-toggle' ? toggleButton : null;
            },
        };

        const target = {
            closest(selector) {
                if (selector === 'button[data-action]') return null;
                if (selector === '.habit-sidebar-item') return item;
                return null;
            },
        };

        const container = {
            addEventListener(type, handler) {
                this[type] = handler;
            },
        };

        const context = {
            console: { error() {} },
            window: {},
            fetch: async (url, opts) => {
                fetchCalls.push({ url, opts });
                return { ok: true, text: async () => '' };
            },
        };

        vm.createContext(context);
        vm.runInContext(source, context);

        let changed = null;
        context.window.HabitPanel.bindHabitsPanel(container, {
            onValueChange(date, habitName, type, newValue) {
                changed = { date, habitName, type, newValue };
            },
        });

        (async () => {
            container.click({ target });
            for (let i = 0; i < 4; i += 1) {
                await Promise.resolve();
                await new Promise(resolve => setTimeout(resolve, 0));
            }
            console.log(JSON.stringify({ fetchCalls, changed }));
        })().catch(err => {
            console.error(err);
            process.exit(1);
        });
        """
    )
    result = subprocess.run(
        ["node", "-e", script, habit_type],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_binary_habit_row_tap_logs_habit():
    result = run_habit_panel_row_tap_scenario("binary")

    assert result["fetchCalls"][0]["url"] == "/api/habits/log/2026-05-04/42"
    assert json.loads(result["fetchCalls"][0]["opts"]["body"]) == {"value": 1}
    assert result["changed"] == {
        "date": "2026-05-04",
        "habitName": "pm_slump",
        "type": "binary",
        "newValue": 1,
    }


def test_counter_habit_row_tap_does_not_log_without_button():
    result = run_habit_panel_row_tap_scenario("counter")

    assert result["fetchCalls"] == []
    assert result["changed"] is None
