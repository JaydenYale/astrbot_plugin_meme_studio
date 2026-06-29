import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image, ImageDraw, ImageSequence


DEFAULT_FRAME_DURATION_MS = 80
INVALID_COMMAND_CHARS = re.compile(r'[\\/<>:"|?*\x00-\x1f]')


def validate_command_name(command: str) -> str:
    normalized = command.strip()
    if not normalized:
        raise ValueError("指令名不能为空")
    if normalized in {".", ".."} or INVALID_COMMAND_CHARS.search(normalized):
        raise ValueError("指令名包含非法路径字符")
    return normalized


def image_to_frame(image_path: Path, output_path: Path) -> Dict[str, object]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(image_path) as image:
        frame = image.convert("RGBA")
        frame.save(output_path, format="PNG")

    return {
        "file": _relative_frame_file(output_path),
        "duration_ms": DEFAULT_FRAME_DURATION_MS,
        "width": frame.width,
        "height": frame.height,
    }


def decompose_gif_to_frames(gif_path: Path, frames_dir: Path) -> List[Dict[str, object]]:
    frames_dir.mkdir(parents=True, exist_ok=True)
    frame_infos = []

    with Image.open(gif_path) as image:
        for index, frame in enumerate(ImageSequence.Iterator(image)):
            output_path = frames_dir / f"{index}.png"
            duration = int(frame.info.get("duration", DEFAULT_FRAME_DURATION_MS))
            rgba_frame = frame.convert("RGBA")
            rgba_frame.save(output_path, format="PNG")
            frame_infos.append(
                {
                    "file": _relative_frame_file(output_path),
                    "duration_ms": duration,
                    "width": rgba_frame.width,
                    "height": rgba_frame.height,
                }
            )

    if not frame_infos:
        raise ValueError("GIF 没有可用帧")
    return frame_infos


def validate_manifest(manifest: Dict[str, object]) -> Dict[str, object]:
    if manifest.get("version") != 1:
        raise ValueError("不支持的 manifest 版本")

    command = validate_command_name(str(manifest.get("command", "")))
    output = str(manifest.get("output", "")).lower()
    if output not in {"png", "gif"}:
        raise ValueError("输出类型必须是 png 或 gif")

    frames = manifest.get("frames")
    if not isinstance(frames, list) or not frames:
        raise ValueError("manifest 至少需要一帧")

    for frame in frames:
        if not isinstance(frame, dict):
            raise ValueError("帧配置必须是对象")
        if not frame.get("file"):
            raise ValueError("帧缺少文件路径")
        _validate_slot(frame.get("slot"))

    avatar = manifest.get("avatar")
    if not isinstance(avatar, dict):
        avatar = {}
        manifest["avatar"] = avatar

    shape = str(avatar.get("shape", "circle"))
    if shape not in {"circle", "rectangle", "rounded"}:
        raise ValueError("头像形状必须是 circle、rectangle 或 rounded")

    manifest["command"] = command
    manifest["output"] = output
    avatar["shape"] = shape
    avatar["fit"] = str(avatar.get("fit", "cover"))
    return manifest


def render_manifest(avatar_path: Path, manifest_path: Path, output_path: Path) -> Path:
    manifest = validate_manifest(json.loads(manifest_path.read_text(encoding="utf-8")))
    manifest_root = manifest_path.parent
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(avatar_path) as avatar_image:
        avatar = avatar_image.convert("RGBA")

    rendered_frames = []
    durations = []
    avatar_config = manifest["avatar"]

    for frame_config in manifest["frames"]:
        frame_path = _safe_join(manifest_root, str(frame_config["file"]))
        with Image.open(frame_path) as frame_image:
            frame = frame_image.convert("RGBA")

        slot = frame_config["slot"]
        composed_avatar = _prepare_avatar_for_slot(avatar, slot, str(avatar_config["shape"]))
        paste_xy = _paste_position(slot, composed_avatar.size)
        frame.alpha_composite(composed_avatar, paste_xy)
        rendered_frames.append(frame)
        durations.append(int(frame_config.get("duration_ms", manifest.get("duration_ms", DEFAULT_FRAME_DURATION_MS))))

    if manifest["output"] == "png":
        rendered_frames[0].save(output_path, format="PNG")
    else:
        rendered_frames[0].save(
            output_path,
            format="GIF",
            save_all=True,
            append_images=rendered_frames[1:],
            duration=durations,
            loop=0,
            disposal=2,
        )

    return output_path


def _relative_frame_file(output_path: Path) -> str:
    return f"{output_path.parent.name}/{output_path.name}"


def _validate_slot(slot: object) -> None:
    if not isinstance(slot, dict):
        raise ValueError("帧缺少头像区域")
    for key in ("x", "y", "width", "height"):
        value = slot.get(key)
        if not isinstance(value, (int, float)):
            raise ValueError(f"头像区域缺少 {key}")
    if slot["width"] <= 0 or slot["height"] <= 0:
        raise ValueError("头像区域宽高必须大于 0")
    rotation = slot.get("rotation", 0)
    if not isinstance(rotation, (int, float)):
        raise ValueError("头像区域 rotation 必须是数字")


def _safe_join(root: Path, relative_path: str) -> Path:
    path = (root / relative_path).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        raise ValueError("manifest 引用了非法帧路径")
    if not path.is_file():
        raise FileNotFoundError(f"缺少模板帧：{relative_path}")
    return path


def _prepare_avatar_for_slot(avatar: Image.Image, slot: Dict[str, object], shape: str) -> Image.Image:
    size = (int(round(slot["width"])), int(round(slot["height"])))
    fitted = _cover_resize(avatar, size)

    if shape == "circle":
        fitted = _apply_circle_mask(fitted)
    elif shape == "rounded":
        fitted = _apply_rounded_mask(fitted)

    rotation = float(slot.get("rotation", 0))
    if rotation:
        fitted = fitted.rotate(rotation, expand=True, resample=Image.Resampling.BICUBIC)
    return fitted


def _cover_resize(image: Image.Image, size: Tuple[int, int]) -> Image.Image:
    target_width, target_height = size
    source_width, source_height = image.size
    scale = max(target_width / source_width, target_height / source_height)
    resized = image.resize(
        (max(1, int(round(source_width * scale))), max(1, int(round(source_height * scale)))),
        Image.Resampling.LANCZOS,
    )
    left = max(0, (resized.width - target_width) // 2)
    top = max(0, (resized.height - target_height) // 2)
    return resized.crop((left, top, left + target_width, top + target_height))


def _apply_circle_mask(image: Image.Image) -> Image.Image:
    masked = image.copy()
    mask = Image.new("L", image.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, image.width - 1, image.height - 1), fill=255)
    masked.putalpha(mask)
    return masked


def _apply_rounded_mask(image: Image.Image) -> Image.Image:
    masked = image.copy()
    mask = Image.new("L", image.size, 0)
    draw = ImageDraw.Draw(mask)
    radius = max(1, min(image.size) // 5)
    draw.rounded_rectangle((0, 0, image.width - 1, image.height - 1), radius=radius, fill=255)
    masked.putalpha(mask)
    return masked


def _paste_position(slot: Dict[str, object], avatar_size: Tuple[int, int]) -> Tuple[int, int]:
    center_x = float(slot["x"]) + float(slot["width"]) / 2
    center_y = float(slot["y"]) + float(slot["height"]) / 2
    return (
        int(round(center_x - avatar_size[0] / 2)),
        int(round(center_y - avatar_size[1] / 2)),
    )
