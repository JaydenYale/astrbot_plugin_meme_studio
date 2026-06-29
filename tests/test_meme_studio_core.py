import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageSequence

from meme_studio_core import (
    decompose_gif_to_frames,
    image_to_frame,
    render_manifest,
    validate_command_name,
)


ROOT = Path(__file__).resolve().parents[1]


class MemeStudioCoreTest(unittest.TestCase):
    def test_legacy_core_module_reexports_renderer_api(self):
        import meme_studio_core
        from meme_studio import renderer

        self.assertIs(meme_studio_core.validate_manifest, renderer.validate_manifest)
        self.assertIs(meme_studio_core.render_manifest, renderer.render_manifest)

    def test_validate_command_name_rejects_unsafe_path_text(self):
        for value in ("../坏", "坏/名", "坏\\名", "", "   "):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_command_name(value)

    def test_validate_command_name_accepts_chinese_command_name(self):
        self.assertEqual(validate_command_name("摸摸头Pro"), "摸摸头Pro")

    def test_decompose_gif_to_frames_preserves_frame_count_and_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gif_path = root / "source.gif"
            frames_dir = root / "frames"
            self._make_test_gif(gif_path)

            frames = decompose_gif_to_frames(gif_path, frames_dir)

            self.assertEqual(len(frames), 2)
            self.assertEqual([frame["duration_ms"] for frame in frames], [90, 130])
            self.assertTrue((frames_dir / "0.png").is_file())
            self.assertTrue((frames_dir / "1.png").is_file())

    def test_image_to_frame_converts_static_image_to_png_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image_path = root / "source.jpg"
            output_path = root / "frames" / "0.png"
            Image.new("RGB", (80, 60), "blue").save(image_path)

            frame = image_to_frame(image_path, output_path)

            self.assertEqual(frame["file"], "frames/0.png")
            self.assertEqual(frame["duration_ms"], 80)
            self.assertTrue(output_path.is_file())

    def test_render_manifest_writes_static_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = self._make_manifest(root, output="png", frame_count=1)
            avatar_path = self._make_avatar(root)
            output_path = root / "result.png"

            render_manifest(avatar_path, manifest_path, output_path)

            self.assertTrue(output_path.is_file())
            with Image.open(output_path) as output:
                self.assertEqual(output.size, (120, 100))

    def test_render_manifest_writes_animated_gif(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = self._make_manifest(root, output="gif", frame_count=2)
            avatar_path = self._make_avatar(root)
            output_path = root / "result.gif"

            render_manifest(avatar_path, manifest_path, output_path)

            self.assertTrue(output_path.is_file())
            with Image.open(output_path) as output:
                self.assertTrue(getattr(output, "is_animated", False))
                self.assertEqual(sum(1 for _ in ImageSequence.Iterator(output)), 2)

    def test_render_manifest_template_script_writes_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = self._make_manifest(root, output="gif", frame_count=2)
            avatar_path = self._make_avatar(root)
            output_path = root / "script-result.gif"

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "render_manifest_template.py"),
                    str(avatar_path),
                    str(output_path),
                    str(manifest_path),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output_path.is_file())

    def _make_test_gif(self, gif_path: Path) -> None:
        frames = [
            Image.new("RGBA", (32, 32), "red"),
            Image.new("RGBA", (32, 32), "green"),
        ]
        frames[0].save(
            gif_path,
            save_all=True,
            append_images=frames[1:],
            duration=[90, 130],
            loop=0,
        )

    def _make_avatar(self, root: Path) -> Path:
        avatar_path = root / "avatar.png"
        Image.new("RGBA", (64, 64), "red").save(avatar_path)
        return avatar_path

    def _make_manifest(self, root: Path, output: str, frame_count: int) -> Path:
        frames_dir = root / "frames"
        frames_dir.mkdir()
        frames = []
        for index in range(frame_count):
            frame_path = frames_dir / f"{index}.png"
            Image.new("RGBA", (120, 100), (30 + index * 40, 90, 160, 255)).save(frame_path)
            frames.append(
                {
                    "file": f"frames/{index}.png",
                    "duration_ms": 80 + index * 10,
                    "slot": {
                        "x": 36,
                        "y": 22,
                        "width": 44,
                        "height": 44,
                        "rotation": 0,
                    },
                }
            )

        manifest_path = root / "manifest.json"
        manifest = {
            "version": 1,
            "command": "测试模板",
            "output": output,
            "message": "正在生成...",
            "duration_ms": 80,
            "avatar": {"shape": "circle", "fit": "cover"},
            "frames": frames,
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        return manifest_path


if __name__ == "__main__":
    unittest.main()
