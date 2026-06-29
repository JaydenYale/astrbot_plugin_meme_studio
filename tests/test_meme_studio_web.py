import json
import subprocess
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MemeStudioWebTest(unittest.TestCase):
    def test_web_client_sends_bearer_token(self):
        script = (ROOT / "meme_studio" / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("Authorization", script)
        self.assertIn("Bearer", script)
        self.assertIn("memeStudioToken", script)

    def test_avatar_slot_is_clamped_inside_frame_bounds(self):
        script = textwrap.dedent(
            f"""
            const fs = require("fs");
            const vm = require("vm");
            const appCode = fs.readFileSync({json.dumps(str(ROOT / "meme_studio" / "web" / "app.js"))}, "utf8");

            function makeElement() {{
              return {{
                style: {{}},
                className: "",
                classList: {{contains: () => false}},
                files: [],
                value: "",
                disabled: false,
                textContent: "",
                innerHTML: "",
                addEventListener: () => {{}},
                setPointerCapture: () => {{}},
                removeAttribute: () => {{}},
                append: () => {{}},
                appendChild: () => {{}},
                focus: () => {{}},
                getBoundingClientRect: () => ({{left: 0, top: 0, width: 100, height: 100}}),
              }};
            }}

            const elements = {{}};
            const storage = {{}};
            const document = {{
              getElementById: (id) => elements[id] || (elements[id] = makeElement()),
              querySelector: (selector) => elements[selector] || (elements[selector] = makeElement()),
              createElement: () => makeElement(),
            }};

            const context = {{
              console,
              document,
              window: {{addEventListener: () => {{}}, location: {{search: ""}}}},
              localStorage: {{
                getItem: (key) => storage[key] || null,
                setItem: (key, value) => {{ storage[key] = String(value); }},
              }},
              URLSearchParams,
              fetch: async () => ({{ok: true, json: async () => ({{templates: []}})}}),
              FileReader: function() {{}},
              Promise,
              Set,
              Error,
              JSON,
              Math,
              Number,
              String,
            }};
            context.globalThis = context;

            vm.runInNewContext(appCode, context, {{filename: "app.js"}});
            const helpers = context.window.__memeStudioTest;
            if (!helpers || !helpers.clampSlotToFrame) {{
              throw new Error("Meme Studio test helpers are not exposed");
            }}

            const results = [
              helpers.clampSlotToFrame({{x: 180, y: 170, width: 40, height: 50}}, {{width: 200, height: 200}}),
              helpers.clampSlotToFrame({{x: -30, y: -10, width: 40, height: 50}}, {{width: 200, height: 200}}),
              helpers.clampSlotToFrame({{x: 20, y: 30, width: 260, height: 250}}, {{width: 200, height: 180}}),
            ];
            console.log(JSON.stringify(results));
            """
        )

        completed = subprocess.run(
            ["node", "-e", script],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        results = json.loads(completed.stdout.strip().splitlines()[-1])
        self.assertEqual(results[0], {"x": 160, "y": 150, "width": 40, "height": 50, "rotation": 0})
        self.assertEqual(results[1], {"x": 0, "y": 0, "width": 40, "height": 50, "rotation": 0})
        self.assertEqual(results[2], {"x": 0, "y": 0, "width": 200, "height": 180, "rotation": 0})


if __name__ == "__main__":
    unittest.main()
