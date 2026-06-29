import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
from typing import Dict, Iterable, Optional, Tuple


@dataclass(frozen=True)
class MemeCommand:
    name: str
    script: str
    output_ext: str = "gif"
    message: str = "正在生成..."
    is_double: bool = False
    extra_args: Tuple[str, ...] = ()


ROOT = Path(__file__).resolve().parents[1]
GENERATED_COMMANDS_PATH = ROOT / "generated_meme_commands.json"
INVALID_COMMAND_CHARS = re.compile(r'[\\/<>:"|?*\x00-\x1f]')


BUILTIN_MEME_COMMANDS = (
    MemeCommand("泉此方看", "泉此方看.py", "png", "此方正在看..."),
    MemeCommand("吸", "吸.py", "gif", "正在发动黑洞..."),
    MemeCommand("敲", "敲.py", "gif", "当当当！"),
    MemeCommand("墙纸", "墙纸.py", "gif", "正在粉刷墙壁..."),
    MemeCommand("抛", "抛.py", "gif", "用力一扔！"),
    MemeCommand("拍", "拍.py", "gif", "无影手准备中..."),
    MemeCommand("拿捏", "拿捏.py", "gif", "尽在掌控..."),
    MemeCommand("膜拜", "膜拜.py", "gif", "大佬受我一拜！"),
    MemeCommand("卖掉了", "卖掉了.py", "png", "成交！"),
    MemeCommand("啾啾", "啾啾.py", "gif", "Mua~"),
    MemeCommand("紧贴", "紧贴.py", "gif", "贴住了，贴得死死的！"),
    MemeCommand("胡桃啃", "胡桃啃.py", "gif", "胡桃牙痒痒了..."),
    MemeCommand("搓", "搓.py", "gif", "正在疯狂揉搓..."),
    MemeCommand("锤", "锤.py", "gif", "吃我一锤！"),
    MemeCommand("舔屏", "舔屏.py", "gif", "嘿嘿嘿..."),
    MemeCommand("贴贴", "贴贴.py", "gif", "飞扑贴贴！", is_double=True),
    MemeCommand("伽波贴", "伽波贴.py", "gif", "伽波！"),
    MemeCommand("催眠", "催眠.py", "gif", "注入暗示中..."),
    MemeCommand("打拳", "打拳.py", "gif", "欧拉欧拉欧拉！"),
    MemeCommand("可莉吃", "可莉吃.py", "gif", "可莉开饭啦！"),
    MemeCommand("跳", "跳.py", "gif", "跳一跳！"),
    MemeCommand("撸", "撸.py", "gif", "正在加速...", extra_args=("1",)),
    MemeCommand("双手撸", "撸.py", "gif", "双手加速...", extra_args=("1",)),
    MemeCommand("单手撸", "撸.py", "gif", "单手加速...", extra_args=("2",)),
    MemeCommand("射", "射.py", "gif", "准备击中..."),
    MemeCommand("垃圾桶", "垃圾桶.py", "gif", "回收废品中..."),
    MemeCommand("顶", "顶.py", "gif", "顶上去！"),
    MemeCommand("科目三", "科目三.py", "gif", "社会摇准备..."),
    MemeCommand("砸", "砸.py", "gif", "大锤搞定！"),
    MemeCommand("摸头", "摸头.py", "gif", "乖乖，摸摸头..."),
    MemeCommand("吃", "吃.py", "gif", "阿姆阿姆..."),
    MemeCommand("草神啃", "草神啃.py", "gif", "纳西妲也想啃..."),
    MemeCommand("抱大腿", "抱大腿.py", "gif", "求带飞！"),
    MemeCommand("飞机杯", "飞机杯.py", "gif", "正在起飞！"),
    MemeCommand("汤姆嘲笑", "汤姆嘲笑.py", "gif", "汤姆正在大笑..."),
    MemeCommand("字符画", "字符画.py", "png", "正在转码..."),
    MemeCommand("抱抱", "抱抱.py", "gif", "抱一个~", is_double=True),
    MemeCommand("白子舔", "白子舔.py", "gif", "白子忍不住了..."),
    MemeCommand("撅", "撅.py", "gif", "小心后面！", is_double=True),
)

def load_generated_commands(path: Optional[Path] = None) -> Tuple[MemeCommand, ...]:
    config_path = path or GENERATED_COMMANDS_PATH
    if not config_path.is_file():
        return ()

    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()

    commands = []
    entries = payload.get("commands", [])
    if not isinstance(entries, list):
        return ()

    for entry in entries:
        command = _build_generated_command(entry)
        if command is not None:
            commands.append(command)

    return tuple(commands)


def _build_generated_command(entry: object) -> Optional[MemeCommand]:
    if not isinstance(entry, dict):
        return None

    try:
        name = _validate_generated_command_name(str(entry.get("name", "")))
        manifest = _normalize_generated_manifest(str(entry.get("manifest", "")))
        output = _normalize_generated_output(str(entry.get("output", "gif")))
    except ValueError:
        return None

    message = str(entry.get("message", "正在生成..."))
    return MemeCommand(
        name,
        "render_manifest_template.py",
        output,
        message,
        extra_args=(manifest,),
    )


def _validate_generated_command_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        raise ValueError("generated command name is empty")
    if normalized in {".", ".."} or INVALID_COMMAND_CHARS.search(normalized):
        raise ValueError("generated command name contains unsafe characters")
    return normalized


def _normalize_generated_manifest(manifest: str) -> str:
    normalized = manifest.strip().replace("\\", "/")
    if not normalized:
        raise ValueError("generated manifest is empty")
    if ":" in normalized or normalized.startswith(("/", "~")):
        raise ValueError("generated manifest must be relative")

    path = PurePosixPath(normalized)
    parts = path.parts
    if len(parts) < 3 or parts[0] != "data" or parts[-1] != "manifest.json":
        raise ValueError("generated manifest must be under data/*/manifest.json")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("generated manifest contains unsafe path parts")

    return path.as_posix()


def _normalize_generated_output(output: str) -> str:
    normalized = output.strip().lower()
    if normalized not in {"png", "gif"}:
        raise ValueError("generated output must be png or gif")
    return normalized


def all_meme_commands(generated_path: Optional[Path] = None) -> Tuple[MemeCommand, ...]:
    return BUILTIN_MEME_COMMANDS + load_generated_commands(generated_path)


MEME_COMMANDS = all_meme_commands()
MEME_COMMANDS_BY_NAME = {command.name: command for command in MEME_COMMANDS}

GENERATOR_CONF_SCHEMA: Dict[str, Dict[str, object]] = {
    "generator_enabled": {
        "type": "bool",
        "description": "启用 meme-generator 大表情库引擎",
        "hint": "关闭后仅保留本地和 Meme Studio 模板。无法安装 generator 依赖或资源时可设为 false。",
        "default": True,
    },
    "generator_need_prefix": {
        "type": "bool",
        "description": "meme-generator 需要触发前缀",
        "hint": "启用后需要 /、全角 ／，或通过唤醒/提及机器人触发 generator 表情。",
        "default": True,
    },
    "generator_extra_prefix": {
        "type": "string",
        "description": "meme-generator 额外触发前缀",
        "hint": "留空则不要求额外前缀；填写后消息必须先以该前缀开头，例如 !/关键词。",
        "default": "",
    },
    "generator_fuzzy_match": {
        "type": "bool",
        "description": "启用 meme-generator 模糊匹配",
        "hint": "开启后消息中包含关键词即可触发 generator 表情，容易误触，建议谨慎开启。",
        "default": False,
    },
    "generator_timeout_seconds": {
        "type": "int",
        "description": "meme-generator 生成超时时长",
        "hint": "单次 generator 表情生成的超时时间，单位秒。",
        "slider": {
            "min": 5,
            "max": 120,
            "step": 5,
        },
        "default": 15,
    },
    "generator_compress_static": {
        "type": "bool",
        "description": "压缩 meme-generator 静态输出",
        "hint": "开启后会将过大的静态 generator 输出缩放到较安全的尺寸；GIF 动图保持原样。",
        "default": True,
    },
    "generator_disabled_list": {
        "type": "list",
        "description": "meme-generator 禁用关键词",
        "hint": "列表里的关键词不会触发 generator 引擎；本地和 Meme Studio 模板开关不受影响。",
        "default": [],
    },
}


def build_conf_schema(
    commands: Optional[Iterable[MemeCommand]] = None,
    generated_path: Optional[Path] = None,
) -> Dict[str, Dict[str, object]]:
    schema_commands = tuple(commands) if commands is not None else all_meme_commands(generated_path)
    command_schema = {
        command.name: {
            "type": "bool",
            "description": "开启{}".format(command.name),
            "default": True,
        }
        for command in schema_commands
    }
    return dict(GENERATOR_CONF_SCHEMA, **command_schema)
