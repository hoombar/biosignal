import json
import subprocess
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_trends_extracts_nested_home_assistant_values():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');
        const source = fs.readFileSync('static/js/trends.js', 'utf8');
        const context = {
            console,
            window: { addEventListener() {} },
            document: { addEventListener() {} },
        };
        vm.createContext(context);
        vm.runInContext(source, context);
        vm.runInContext(`
            trendsData = [
                {home_assistant_metrics: [{selector: 'home_assistant:sensor.co2', value: 640}]},
                {home_assistant_metrics: [{selector: 'home_assistant:sensor.co2', value: null}]},
                {home_assistant_metrics: []},
            ];
        `, context);
        console.log(JSON.stringify(context.getMetricValues('home_assistant:sensor.co2')));
        """
    )
    result = subprocess.run(
        ["node", "-e", script], cwd=REPO_ROOT, check=True,
        capture_output=True, text=True,
    )

    assert json.loads(result.stdout) == [640, None, None]
