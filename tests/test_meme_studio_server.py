import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

from meme_commands import BUILTIN_MEME_COMMANDS
from meme_studio.studio_security import StudioAuthConfig
from meme_studio.studio_server import create_server
from meme_studio.studio_service import MemeStudioService


class MemeStudioServerTest(unittest.TestCase):
    def test_legacy_server_reexports_new_service(self):
        from meme_studio.studio_service import MemeStudioService
        from tools.meme_studio.server import MemeStudioService as LegacyMemeStudioService

        self.assertIs(LegacyMemeStudioService, MemeStudioService)

    def test_api_templates_requires_token_when_auth_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = create_server(Path(tmp), port=0, auth_config=StudioAuthConfig("secret"))
            thread = threading.Thread(target=server.serve_forever, daemon=True)

            try:
                thread.start()
                url = f"http://127.0.0.1:{server.server_address[1]}/api/templates"

                with self.assertRaises(urllib.error.HTTPError) as raised:
                    urllib.request.urlopen(url, timeout=5)
                self.assertEqual(raised.exception.code, 401)
                self.assertEqual(json.loads(raised.exception.read().decode("utf-8")), {"error": "unauthorized"})

                request = urllib.request.Request(url, headers={"Authorization": "Bearer secret"})
                with urllib.request.urlopen(request, timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    payload = json.loads(response.read().decode("utf-8"))
                self.assertIn("templates", payload)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_upload_decomposes_gif_into_project_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = self._make_service(root)
            gif_bytes = self._make_gif_bytes(root)

            project = service.upload_files([{"name": "source.gif", "data": gif_bytes}])

            self.assertEqual(len(project["frames"]), 2)
            self.assertTrue((service.project_dir(project["project_id"]) / "frames" / "0.png").is_file())
            self.assertTrue((service.project_dir(project["project_id"]) / "frames" / "1.png").is_file())

    def test_export_template_writes_manifest_and_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = self._make_service(root)
            project = service.upload_files([{"name": "source.png", "data": self._make_png_bytes(root)}])
            manifest = self._make_manifest(project)

            export_dir = service.export_template(project["project_id"], manifest)

            self.assertTrue((export_dir / "manifest.json").is_file())
            self.assertTrue((export_dir / "frames" / "0.png").is_file())

    def test_apply_template_writes_bot_data_and_generated_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = self._make_service(root)
            project = service.upload_files([{"name": "source.png", "data": self._make_png_bytes(root)}])
            manifest = self._make_manifest(project)

            data_dir = service.apply_template(project["project_id"], manifest)

            self.assertEqual(data_dir, root / "data" / "测试生成")
            self.assertTrue((data_dir / "manifest.json").is_file())
            generated = json.loads((root / "generated_meme_commands.json").read_text(encoding="utf-8"))
            self.assertEqual(generated["commands"][0]["name"], "测试生成")
            self.assertEqual(generated["commands"][0]["manifest"], "data/测试生成/manifest.json")
            schema = json.loads((root / "_conf_schema.json").read_text(encoding="utf-8"))
            self.assertIn("测试生成", schema)

    def test_list_applied_templates_reports_generated_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = self._make_service(root)
            project = service.upload_files([{"name": "source.png", "data": self._make_png_bytes(root)}])
            service.apply_template(project["project_id"], self._make_manifest(project, command="测试生成"))
            service.apply_template(project["project_id"], self._make_manifest(project, command="测试二号", output="png"))

            templates = service.list_applied_templates()
            generated_templates = [template for template in templates if template["source"] == "generated"]

            self.assertEqual([template["name"] for template in generated_templates], ["测试生成", "测试二号"])
            self.assertEqual(generated_templates[0]["manifest"], "data/测试生成/manifest.json")
            self.assertEqual(generated_templates[0]["output"], "gif")
            self.assertEqual(generated_templates[0]["message"], "测试生成中...")
            self.assertEqual(generated_templates[0]["frame_count"], 1)
            self.assertTrue(generated_templates[0]["exists"])
            self.assertEqual(generated_templates[0]["preview_url"], "/api/templates/%E6%B5%8B%E8%AF%95%E7%94%9F%E6%88%90/preview.gif")
            self.assertEqual(generated_templates[1]["output"], "png")
            self.assertEqual(generated_templates[1]["preview_url"], "/api/templates/%E6%B5%8B%E8%AF%95%E4%BA%8C%E5%8F%B7/preview.png")

    def test_list_applied_templates_includes_builtin_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first_builtin = BUILTIN_MEME_COMMANDS[0]
            script_path = root / "scripts" / first_builtin.script
            script_path.parent.mkdir(parents=True)
            script_path.write_text("print('ok')\n", encoding="utf-8")
            service = self._make_service(root)

            templates = service.list_applied_templates()

            self.assertGreaterEqual(len(templates), len(BUILTIN_MEME_COMMANDS))
            builtin = templates[0]
            self.assertEqual(builtin["name"], first_builtin.name)
            self.assertEqual(builtin["source"], "builtin")
            self.assertFalse(builtin["deletable"])
            self.assertEqual(builtin["script"], first_builtin.script)
            self.assertEqual(builtin["data_path"], str(script_path))
            self.assertTrue(builtin["preview_url"].endswith("/preview.png"))
            self.assertTrue(builtin["exists"])
            gif_builtin = next(template for template in templates if template["output"] == "gif")
            self.assertTrue(gif_builtin["preview_url"].endswith("/preview.gif"))

    def test_list_applied_templates_includes_builtin_and_generated_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = self._make_service(root)
            project = service.upload_files([{"name": "source.png", "data": self._make_png_bytes(root)}])
            service.apply_template(project["project_id"], self._make_manifest(project, command="测试生成"))

            templates = service.list_applied_templates()

            names = [template["name"] for template in templates]
            self.assertIn(BUILTIN_MEME_COMMANDS[0].name, names)
            self.assertIn("测试生成", names)
            generated = next(template for template in templates if template["name"] == "测试生成")
            self.assertEqual(generated["source"], "generated")
            self.assertTrue(generated["deletable"])

    def test_template_preview_renders_generated_manifest_with_logo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = self._make_service(root)
            self._write_logo(root)
            project = service.upload_files([{"name": "source.gif", "data": self._make_gif_bytes(root)}])
            service.apply_template(project["project_id"], self._make_manifest(project, command="测试生成"))

            preview_path = service.template_preview("测试生成")

            self.assertTrue(preview_path.is_file())
            with Image.open(preview_path) as preview:
                self.assertEqual(preview.format, "GIF")
                self.assertGreaterEqual(preview.n_frames, 2)
                self.assertLessEqual(preview.width, 360)
                self.assertLessEqual(preview.height, 240)

    def test_current_template_preview_renders_unsaved_project_with_logo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = self._make_service(root)
            self._write_logo(root)
            project = service.upload_files([{"name": "source.gif", "data": self._make_gif_bytes(root)}])

            preview_path = service.preview_current_template(project["project_id"], self._make_manifest(project))

            self.assertEqual(preview_path, service.project_dir(project["project_id"]) / "preview.gif")
            self.assertTrue(preview_path.is_file())
            with Image.open(preview_path) as preview:
                self.assertEqual(preview.format, "GIF")
                self.assertGreaterEqual(preview.n_frames, 2)
                self.assertLessEqual(preview.width, 360)
                self.assertLessEqual(preview.height, 240)

    def test_template_preview_uses_placeholder_when_builtin_preview_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = self._make_service(root)
            self._write_logo(root)

            preview_path = service.template_preview(BUILTIN_MEME_COMMANDS[0].name)

            self.assertTrue(preview_path.is_file())
            with Image.open(preview_path) as preview:
                self.assertEqual(preview.format, "PNG")

    def test_delete_template_removes_data_command_and_conf_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = self._make_service(root)
            project = service.upload_files([{"name": "source.png", "data": self._make_png_bytes(root)}])
            service.apply_template(project["project_id"], self._make_manifest(project, command="测试生成"))
            service.apply_template(project["project_id"], self._make_manifest(project, command="测试保留"))

            deleted_dir = service.delete_template("测试生成")

            self.assertEqual(deleted_dir, root / "data" / "测试生成")
            self.assertFalse((root / "data" / "测试生成").exists())
            self.assertTrue((root / "data" / "测试保留").is_dir())
            generated = json.loads((root / "generated_meme_commands.json").read_text(encoding="utf-8"))
            self.assertEqual([item["name"] for item in generated["commands"]], ["测试保留"])
            schema = json.loads((root / "_conf_schema.json").read_text(encoding="utf-8"))
            self.assertNotIn("测试生成", schema)
            self.assertIn("测试保留", schema)

    def test_delete_template_rejects_missing_generated_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = self._make_service(root)

            with self.assertRaises(FileNotFoundError):
                service.delete_template("不存在")

    def _make_service(self, root: Path) -> MemeStudioService:
        return MemeStudioService(
            project_root=root,
            session_root=root / ".meme_studio_sessions",
            export_root=root / "exports",
        )

    def _make_manifest(self, project: dict, command: str = "测试生成", output: str = "gif") -> dict:
        return {
            "version": 1,
            "command": command,
            "output": output,
            "message": f"{command}中...",
            "duration_ms": 80,
            "avatar": {"shape": "circle", "fit": "cover"},
            "frames": [
                {
                    "file": frame["file"],
                    "duration_ms": frame["duration_ms"],
                    "slot": {"x": 10, "y": 10, "width": 30, "height": 30, "rotation": 0},
                }
                for frame in project["frames"]
            ],
        }

    def _make_png_bytes(self, root: Path) -> bytes:
        path = root / "source.png"
        Image.new("RGBA", (64, 64), "blue").save(path)
        return path.read_bytes()

    def _make_gif_bytes(self, root: Path) -> bytes:
        path = root / "source.gif"
        frames = [Image.new("RGBA", (64, 64), "red"), Image.new("RGBA", (64, 64), "green")]
        frames[0].save(path, save_all=True, append_images=frames[1:], duration=[70, 120], loop=0)
        return path.read_bytes()

    def _write_logo(self, root: Path) -> None:
        Image.new("RGBA", (96, 96), "purple").save(root / "logo.png")


if __name__ == "__main__":
    unittest.main()
