import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

from PIL import Image, ImageDraw, ImageSequence

from .commands import BUILTIN_MEME_COMMANDS, MemeCommand, build_conf_schema
from .renderer import (
    decompose_gif_to_frames,
    image_to_frame,
    render_manifest,
    validate_command_name,
    validate_manifest,
)


PREVIEW_SIZE = (360, 240)
PREVIEW_TIMEOUT_SECONDS = 30


class MemeStudioService:
    def __init__(
        self,
        project_root: Path,
        session_root: Path,
        export_root: Path,
        preview_root: Optional[Path] = None,
    ):
        self.project_root = project_root
        self.session_root = session_root
        self.export_root = export_root
        self.preview_root = preview_root or project_root / ".meme_studio_previews"
        self.session_root.mkdir(parents=True, exist_ok=True)
        self.export_root.mkdir(parents=True, exist_ok=True)
        self.preview_root.mkdir(parents=True, exist_ok=True)

    def project_dir(self, project_id: str) -> Path:
        path = (self.session_root / project_id).resolve()
        try:
            path.relative_to(self.session_root.resolve())
        except ValueError:
            raise ValueError("非法项目 ID")
        return path

    def upload_files(self, files: List[Dict[str, object]]) -> Dict[str, object]:
        if not files:
            raise ValueError("至少需要上传一个素材文件")

        project_id = uuid.uuid4().hex
        project_dir = self.project_dir(project_id)
        upload_dir = project_dir / "uploads"
        frames_dir = project_dir / "frames"
        upload_dir.mkdir(parents=True, exist_ok=True)
        frames_dir.mkdir(parents=True, exist_ok=True)

        if len(files) == 1 and str(files[0]["name"]).lower().endswith(".gif"):
            source_path = upload_dir / "source.gif"
            source_path.write_bytes(_file_bytes(files[0]))
            frames = decompose_gif_to_frames(source_path, frames_dir)
        else:
            frames = []
            for index, file_info in enumerate(files):
                source_path = upload_dir / str(file_info["name"])
                source_path.write_bytes(_file_bytes(file_info))
                frames.append(image_to_frame(source_path, frames_dir / f"{index}.png"))

        return {"project_id": project_id, "frames": frames}

    def export_template(self, project_id: str, manifest: Dict[str, object]) -> Path:
        manifest = validate_manifest(dict(manifest))
        command = validate_command_name(str(manifest["command"]))
        export_dir = self.export_root / command
        self._write_template(project_id, manifest, export_dir)
        return export_dir

    def apply_template(self, project_id: str, manifest: Dict[str, object]) -> Path:
        manifest = validate_manifest(dict(manifest))
        command = validate_command_name(str(manifest["command"]))
        data_dir = self._template_data_dir(command)
        self._write_template(project_id, manifest, data_dir)
        self._upsert_generated_command(command, manifest)
        self._clear_preview_cache(command)
        self._write_conf_schema()
        return data_dir

    def list_applied_templates(self) -> List[Dict[str, object]]:
        payload = self._read_generated_payload()
        generated_templates = [self._generated_template_entry(entry) for entry in payload.get("commands", [])]
        generated_names = {template["name"] for template in generated_templates}
        builtin_templates = [
            self._builtin_template_entry(command)
            for command in BUILTIN_MEME_COMMANDS
            if command.name not in generated_names
        ]
        return generated_templates + builtin_templates

    def delete_template(self, command: str) -> Path:
        command = validate_command_name(command)
        data_dir = self._template_data_dir(command)
        payload = self._read_generated_payload()
        commands = payload.get("commands", [])
        kept_commands = [item for item in commands if item.get("name") != command]
        if len(kept_commands) == len(commands) and not data_dir.exists():
            raise FileNotFoundError(f"未找到表情：{command}")
        if data_dir.exists():
            if not data_dir.is_dir():
                raise ValueError(f"表情路径不是目录：{data_dir}")
            shutil.rmtree(data_dir)
        payload["commands"] = kept_commands
        self._write_generated_payload(payload)
        self._clear_preview_cache(command)
        self._write_conf_schema()
        return data_dir

    def template_preview(self, command: str) -> Path:
        command = validate_command_name(command)
        preview_ext = self._preview_ext(command)
        preview_path = self._preview_cache_path(command, preview_ext)
        if preview_path.is_file():
            return preview_path

        with tempfile.TemporaryDirectory(prefix="preview_", dir=str(self.preview_root)) as tmp:
            tmp_dir = Path(tmp)
            temp_preview = tmp_dir / f"preview.{preview_ext}"
            try:
                self._render_preview(command, tmp_dir, temp_preview)
            except Exception as exc:
                if not self._known_template_name(command):
                    raise
                self._write_placeholder_preview(temp_preview, str(exc), preview_ext)
            shutil.copyfile(str(temp_preview), str(preview_path))
        return preview_path

    def preview_current_template(self, project_id: str, manifest: Dict[str, object]) -> Path:
        manifest = validate_manifest(dict(manifest))
        project_dir = self.project_dir(project_id)
        manifest_path = project_dir / "preview_manifest.json"
        raw_output = project_dir / f"preview_raw.{manifest['output']}"
        preview_path = project_dir / f"preview.{manifest['output']}"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        render_manifest(self._preview_avatar_path(), manifest_path, raw_output)
        self._write_preview_media(raw_output, preview_path)
        return preview_path

    def _write_template(self, project_id: str, manifest: Dict[str, object], target_dir: Path) -> None:
        project_dir = self.project_dir(project_id)
        source_frames_dir = project_dir / "frames"
        if not source_frames_dir.is_dir():
            raise FileNotFoundError("项目没有可导出的帧")

        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_frames_dir, target_dir / "frames")
        (target_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _upsert_generated_command(self, command: str, manifest: Dict[str, object]) -> None:
        payload = self._read_generated_payload()
        entry = {
            "name": command,
            "manifest": f"data/{command}/manifest.json",
            "output": manifest["output"],
            "message": manifest.get("message", "正在生成..."),
        }
        commands = [item for item in payload.get("commands", []) if item.get("name") != command]
        commands.append(entry)
        payload["commands"] = commands
        self._write_generated_payload(payload)

    def _generated_path(self) -> Path:
        return self.project_root / "generated_meme_commands.json"

    def _read_generated_payload(self) -> Dict[str, object]:
        generated_path = self._generated_path()
        if not generated_path.is_file():
            return {"commands": []}
        payload = json.loads(generated_path.read_text(encoding="utf-8"))
        if not isinstance(payload.get("commands"), list):
            payload["commands"] = []
        return payload

    def _write_generated_payload(self, payload: Dict[str, object]) -> None:
        self._generated_path().write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _generated_template_entry(self, entry: Dict[str, object]) -> Dict[str, object]:
        command = validate_command_name(str(entry.get("name", "")))
        data_dir = self._template_data_dir(command)
        manifest_path = data_dir / "manifest.json"
        manifest = self._read_template_manifest(manifest_path)
        frames = manifest.get("frames", []) if isinstance(manifest, dict) else []
        avatar = manifest.get("avatar", {}) if isinstance(manifest, dict) else {}
        output = str(entry.get("output", manifest.get("output", "")))
        return {
            "name": command,
            "source": "generated",
            "deletable": True,
            "script": "render_manifest_template.py",
            "manifest": f"data/{command}/manifest.json",
            "data_path": str(data_dir),
            "output": output,
            "message": str(entry.get("message", manifest.get("message", ""))),
            "frame_count": len(frames) if isinstance(frames, list) else 0,
            "avatar_shape": str(avatar.get("shape", "")) if isinstance(avatar, dict) else "",
            "is_double": False,
            "exists": manifest_path.is_file(),
            "preview_url": self._preview_url(command, output),
        }

    def _builtin_template_entry(self, command: MemeCommand) -> Dict[str, object]:
        script_path = self.project_root / "scripts" / command.script
        return {
            "name": command.name,
            "source": "builtin",
            "deletable": False,
            "script": command.script,
            "manifest": "",
            "data_path": str(script_path),
            "output": command.output_ext,
            "message": command.message,
            "frame_count": 0,
            "avatar_shape": "",
            "is_double": command.is_double,
            "exists": script_path.is_file(),
            "preview_url": self._preview_url(command.name, command.output_ext),
        }

    def _render_preview(self, command: str, tmp_dir: Path, preview_path: Path) -> None:
        generated_entry = self._generated_payload_entry(command)
        if generated_entry is not None:
            self._render_generated_preview(generated_entry, tmp_dir, preview_path)
            return

        builtin_command = self._builtin_command(command)
        if builtin_command is None:
            raise FileNotFoundError(f"未找到表情：{command}")
        self._render_builtin_preview(builtin_command, tmp_dir, preview_path)

    def _render_generated_preview(self, entry: Dict[str, object], tmp_dir: Path, preview_path: Path) -> None:
        command = validate_command_name(str(entry.get("name", "")))
        manifest_path = self._template_data_dir(command) / "manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(f"缺少模板文件：{manifest_path}")

        output = str(entry.get("output", "gif")).lower()
        if output not in {"png", "gif"}:
            output = "gif"
        raw_path = tmp_dir / f"raw.{output}"
        render_manifest(self._preview_avatar_path(), manifest_path, raw_path)
        self._write_preview_media(raw_path, preview_path)

    def _render_builtin_preview(self, command: MemeCommand, tmp_dir: Path, preview_path: Path) -> None:
        script_path = self.project_root / "scripts" / command.script
        if not script_path.is_file():
            raise FileNotFoundError(f"缺少脚本：{script_path}")

        raw_path = tmp_dir / f"raw.{command.output_ext}"
        avatar_path = self._preview_avatar_path()
        args = [self._python_executable(), str(script_path)]
        if command.is_double:
            args.extend([str(avatar_path), str(avatar_path), str(raw_path)])
        else:
            args.extend([str(avatar_path), str(raw_path)])
        args.extend(command.extra_args)

        result = subprocess.run(
            args,
            cwd=str(self.project_root),
            capture_output=True,
            text=True,
            timeout=PREVIEW_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "脚本预览失败").strip()
            raise RuntimeError(message)
        if not raw_path.is_file():
            raise FileNotFoundError("脚本没有输出预览图")
        self._write_preview_media(raw_path, preview_path)

    def _write_preview_media(self, source_path: Path, preview_path: Path) -> None:
        if preview_path.suffix.lower() == ".gif":
            self._write_animated_preview(source_path, preview_path)
            return
        self._write_static_preview(source_path, preview_path)

    def _write_static_preview(self, source_path: Path, preview_path: Path) -> None:
        with Image.open(source_path) as source:
            frame = next(ImageSequence.Iterator(source)).convert("RGBA")
            frame.thumbnail(PREVIEW_SIZE, Image.Resampling.LANCZOS)

        canvas = self._checkerboard(PREVIEW_SIZE)
        left = (PREVIEW_SIZE[0] - frame.width) // 2
        top = (PREVIEW_SIZE[1] - frame.height) // 2
        canvas.alpha_composite(frame, (left, top))
        canvas.convert("RGB").save(preview_path, format="PNG", optimize=True)

    def _write_animated_preview(self, source_path: Path, preview_path: Path) -> None:
        frames = []
        durations = []
        with Image.open(source_path) as source:
            for source_frame in ImageSequence.Iterator(source):
                frame = source_frame.convert("RGBA")
                frame.thumbnail(PREVIEW_SIZE, Image.Resampling.LANCZOS)
                canvas = self._checkerboard(PREVIEW_SIZE)
                left = (PREVIEW_SIZE[0] - frame.width) // 2
                top = (PREVIEW_SIZE[1] - frame.height) // 2
                canvas.alpha_composite(frame, (left, top))
                frames.append(canvas.convert("P", palette=Image.Palette.ADAPTIVE))
                durations.append(int(source_frame.info.get("duration", 80)))

        if not frames:
            raise ValueError("预览 GIF 没有可用帧")
        frames[0].save(
            preview_path,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            duration=durations,
            loop=0,
            disposal=2,
            optimize=False,
        )

    def _write_placeholder_preview(self, preview_path: Path, reason: str, preview_ext: str) -> None:
        canvas = self._checkerboard(PREVIEW_SIZE)
        try:
            with Image.open(self._preview_avatar_path()) as avatar:
                logo = avatar.convert("RGBA")
                logo.thumbnail((96, 96), Image.Resampling.LANCZOS)
                canvas.alpha_composite(logo, ((PREVIEW_SIZE[0] - logo.width) // 2, 36))
        except Exception:
            pass

        draw = ImageDraw.Draw(canvas)
        draw.rectangle((0, PREVIEW_SIZE[1] - 54, PREVIEW_SIZE[0], PREVIEW_SIZE[1]), fill=(255, 255, 255, 220))
        draw.text((14, PREVIEW_SIZE[1] - 44), "Preview unavailable", fill=(32, 36, 44))
        draw.text((14, PREVIEW_SIZE[1] - 24), _preview_placeholder_reason(reason), fill=(102, 112, 133))
        if preview_ext == "gif":
            canvas.convert("P", palette=Image.Palette.ADAPTIVE).save(preview_path, format="GIF", loop=0)
            return
        canvas.convert("RGB").save(preview_path, format="PNG", optimize=True)

    def _checkerboard(self, size: Tuple[int, int]) -> Image.Image:
        canvas = Image.new("RGBA", size, (255, 255, 255, 255))
        draw = ImageDraw.Draw(canvas)
        square = 12
        for y in range(0, size[1], square):
            for x in range(0, size[0], square):
                color = (239, 243, 248, 255) if (x // square + y // square) % 2 else (248, 250, 252, 255)
                draw.rectangle((x, y, x + square - 1, y + square - 1), fill=color)
        return canvas

    def _preview_avatar_path(self) -> Path:
        logo_path = self.project_root / "logo.png"
        if logo_path.is_file():
            return logo_path

        fallback_path = self.preview_root / "preview_avatar.png"
        if not fallback_path.is_file():
            image = Image.new("RGBA", (128, 128), (23, 107, 135, 255))
            draw = ImageDraw.Draw(image)
            draw.ellipse((24, 20, 104, 100), fill=(255, 255, 255, 255))
            draw.rectangle((38, 78, 90, 112), fill=(255, 255, 255, 255))
            image.save(fallback_path, format="PNG")
        return fallback_path

    def _python_executable(self) -> str:
        executable = Path(sys.executable)
        if getattr(sys, "frozen", False) or executable.name.lower() == "memestudio.exe":
            python_executable = shutil.which("python") or shutil.which("py")
            if python_executable:
                return python_executable
            raise RuntimeError("找不到 Python，无法生成内置脚本预览")
        return sys.executable

    def _generated_payload_entry(self, command: str) -> Optional[Dict[str, object]]:
        for entry in self._read_generated_payload().get("commands", []):
            if entry.get("name") == command:
                return entry
        return None

    def _builtin_command(self, command: str) -> Optional[MemeCommand]:
        for builtin_command in BUILTIN_MEME_COMMANDS:
            if builtin_command.name == command:
                return builtin_command
        return None

    def _known_template_name(self, command: str) -> bool:
        return self._generated_payload_entry(command) is not None or self._builtin_command(command) is not None

    def _preview_ext(self, command: str) -> str:
        generated_entry = self._generated_payload_entry(command)
        if generated_entry is not None:
            return _preview_ext_for_output(str(generated_entry.get("output", "gif")))
        builtin_command = self._builtin_command(command)
        if builtin_command is not None:
            return _preview_ext_for_output(builtin_command.output_ext)
        raise FileNotFoundError(f"未找到表情：{command}")

    def _preview_url(self, command: str, output_ext: str) -> str:
        preview_ext = _preview_ext_for_output(output_ext)
        return f"/api/templates/{quote(command, safe='')}/preview.{preview_ext}"

    def _preview_cache_path(self, command: str, preview_ext: str) -> Path:
        digest = hashlib.sha256(command.encode("utf-8")).hexdigest()[:16]
        return self.preview_root / f"{digest}.{preview_ext}"

    def _clear_preview_cache(self, command: str) -> None:
        for preview_ext in ("png", "gif"):
            try:
                self._preview_cache_path(command, preview_ext).unlink()
            except FileNotFoundError:
                continue

    def _template_data_dir(self, command: str) -> Path:
        command = validate_command_name(command)
        data_root = (self.project_root / "data").resolve()
        data_dir = (data_root / command).resolve()
        try:
            data_dir.relative_to(data_root)
        except ValueError:
            raise ValueError("表情路径越界")
        return data_dir

    def _read_template_manifest(self, manifest_path: Path) -> Dict[str, object]:
        if not manifest_path.is_file():
            return {}
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return manifest if isinstance(manifest, dict) else {}

    def _write_conf_schema(self) -> None:
        schema = build_conf_schema(generated_path=self.project_root / "generated_meme_commands.json")
        (self.project_root / "_conf_schema.json").write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def _file_bytes(file_info: Dict[str, object]) -> bytes:
    data = file_info["data"]
    if isinstance(data, bytes):
        return data
    raise TypeError("上传文件 data 必须是 bytes")


def _preview_placeholder_reason(reason: str, limit: int = 42) -> str:
    normalized = " ".join(reason.split())
    normalized = normalized.encode("ascii", errors="ignore").decode("ascii").strip() or "Open details for info"
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit]}..."


def _preview_ext_for_output(output_ext: str) -> str:
    return "png" if output_ext.lower() == "png" else "gif"
