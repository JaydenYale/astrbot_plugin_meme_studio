import json
import subprocess
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MemeStudioWebTest(unittest.TestCase):
    def run_app_in_node(self, body, *, search="", storage=None):
        storage = storage or {}
        script = textwrap.dedent(
            f"""
            const fs = require("fs");
            const vm = require("vm");
            const appCode = fs.readFileSync({json.dumps(str(ROOT / "meme_studio" / "web" / "app.js"))}, "utf8");

            function makeElement(tagName = "div") {{
              return {{
                tagName: tagName.toUpperCase(),
                style: {{}},
                className: "",
                classList: {{contains: () => false}},
                children: [],
                files: [],
                value: "",
                disabled: false,
                textContent: "",
                innerHTML: "",
                loading: "",
                alt: "",
                src: "",
                addEventListener: () => {{}},
                setPointerCapture: () => {{}},
                removeAttribute: () => {{}},
                append: function(...children) {{ this.children.push(...children); }},
                appendChild: function(child) {{ this.children.push(child); return child; }},
                focus: () => {{}},
                getBoundingClientRect: () => ({{left: 0, top: 0, width: 100, height: 100}}),
              }};
            }}

            const elements = {{}};
            const storage = {json.dumps(storage)};
            const fetchCalls = [];
            const confirmCalls = [];
            const document = {{
              getElementById: (id) => elements[id] || (elements[id] = makeElement()),
              querySelector: (selector) => elements[selector] || (elements[selector] = makeElement()),
              createElement: (tagName) => makeElement(tagName),
            }};

            const context = {{
              console,
              document,
              window: {{
                addEventListener: () => {{}},
                location: {{search: {json.dumps(search)}}},
                confirm: (message) => {{
                  confirmCalls.push(message);
                  return false;
                }},
              }},
              localStorage: {{
                getItem: (key) => storage[key] || null,
                setItem: (key, value) => {{ storage[key] = String(value); }},
              }},
              URLSearchParams,
              fetch: async (url, options = {{}}) => {{
                fetchCalls.push({{url, options}});
                return {{ok: true, json: async () => ({{templates: []}})}};
              }},
              FileReader: function() {{}},
              Promise,
              Set,
              Error,
              JSON,
              Math,
              Number,
              String,
              encodeURIComponent,
            }};
            context.globalThis = context;

            vm.runInNewContext(appCode, context, {{filename: "app.js"}});

            (async () => {{
            {textwrap.indent(body, "              ")}
            }})().catch((error) => {{
              console.error(error && error.stack ? error.stack : error);
              process.exitCode = 1;
            }});
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
        return completed.stdout

    def test_web_client_sends_bearer_token(self):
        script = (ROOT / "meme_studio" / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("Authorization", script)
        self.assertIn("Bearer", script)
        self.assertIn("memeStudioToken", script)
        self.assertIn("withAuthToken", script)

    def test_template_list_uses_img_preview_with_auth_token(self):
        script = (ROOT / "meme_studio" / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn('const preview = document.createElement("img");', script)
        self.assertIn("preview.src = withAuthToken(template.preview_url);", script)
        self.assertNotIn('document.createElement("canvas")', script)
        self.assertNotIn(".getContext(", script)

    def test_with_auth_token_appends_to_existing_query_and_leaves_plain_url_without_token(self):
        with_token = self.run_app_in_node(
            """
            const helpers = context.window.__memeStudioTest;
            if (!helpers || !helpers.withAuthToken) {
              throw new Error("withAuthToken helper is not exposed");
            }
            console.log(helpers.withAuthToken("/api/preview.gif?frame=1"));
            """,
            storage={"memeStudioToken": "abc 123"},
        )
        self.assertEqual(with_token.strip().splitlines()[-1], "/api/preview.gif?frame=1&token=abc%20123")

        without_token = self.run_app_in_node(
            """
            const helpers = context.window.__memeStudioTest;
            if (!helpers || !helpers.withAuthToken) {
              throw new Error("withAuthToken helper is not exposed");
            }
            console.log(helpers.withAuthToken("/api/preview.gif?frame=1"));
            """
        )
        self.assertEqual(without_token.strip().splitlines()[-1], "/api/preview.gif?frame=1")

    def test_delete_template_confirms_and_cancel_skips_delete_request(self):
        self.run_app_in_node(
            """
            const helpers = context.window.__memeStudioTest;
            if (!helpers || !helpers.deleteTemplate) {
              throw new Error("deleteTemplate helper is not exposed");
            }

            await helpers.deleteTemplate({name: "wave", deletable: true});
            if (confirmCalls.length !== 1) {
              throw new Error(`expected one confirmation, got ${confirmCalls.length}`);
            }
            if (fetchCalls.some((call) => call.url === "/api/delete-template")) {
              throw new Error("delete-template request was sent after cancellation");
            }
            """
        )

    def test_avatar_slot_is_clamped_inside_frame_bounds(self):
        output = self.run_app_in_node(
            """
            const helpers = context.window.__memeStudioTest;
            if (!helpers || !helpers.clampSlotToFrame) {
              throw new Error("Meme Studio test helpers are not exposed");
            }

            const results = [
              helpers.clampSlotToFrame({x: 180, y: 170, width: 40, height: 50}, {width: 200, height: 200}),
              helpers.clampSlotToFrame({x: -30, y: -10, width: 40, height: 50}, {width: 200, height: 200}),
              helpers.clampSlotToFrame({x: 20, y: 30, width: 260, height: 250}, {width: 200, height: 180}),
            ];
            console.log(JSON.stringify(results));
            """
        )
        results = json.loads(output.strip().splitlines()[-1])
        self.assertEqual(results[0], {"x": 160, "y": 150, "width": 40, "height": 50, "rotation": 0})
        self.assertEqual(results[1], {"x": 0, "y": 0, "width": 40, "height": 50, "rotation": 0})
        self.assertEqual(results[2], {"x": 0, "y": 0, "width": 200, "height": 180, "rotation": 0})


if __name__ == "__main__":
    unittest.main()
