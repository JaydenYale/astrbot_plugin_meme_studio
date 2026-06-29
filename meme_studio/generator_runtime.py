import asyncio
import io
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from astrbot.api import logger
from astrbot.api.message_components import Image
from PIL import Image as PILImage

try:
    from .generator_engine import GeneratorEngine, GeneratorParams
    from .generator_params import collect_generator_params
except ImportError:  # pragma: no cover - supports direct package execution in tests.
    from meme_studio.generator_engine import GeneratorEngine, GeneratorParams
    from meme_studio.generator_params import collect_generator_params


QQ_AVATAR_URL = "http://q1.qlogo.cn/g?b=qq&nk={qq}&s=640"
HELP_COMMANDS = {"meme帮助", "表情帮助", "meme菜单", "meme列表"}
DETAIL_COMMANDS = {"meme详情", "表情详情", "meme信息"}
BLACKLIST_COMMANDS = {"meme黑名单"}
DISABLE_COMMANDS = {"禁用meme"}
ENABLE_COMMANDS = {"启用meme"}


@dataclass
class GeneratorRuntimeConfig:
    generator_enabled: bool = True
    generator_need_prefix: bool = True
    generator_extra_prefix: str = ""
    generator_fuzzy_match: bool = False
    generator_timeout_seconds: int = 15
    generator_disabled_list: List[str] = field(default_factory=list)
    generator_compress_static: bool = True

    @classmethod
    def from_mapping(cls, config: Optional[Dict[str, object]]) -> "GeneratorRuntimeConfig":
        mapping = config or {}
        return cls(
            generator_enabled=_bool_value(mapping.get("generator_enabled"), True),
            generator_need_prefix=_bool_value(mapping.get("generator_need_prefix"), True),
            generator_extra_prefix=str(mapping.get("generator_extra_prefix") or ""),
            generator_fuzzy_match=_bool_value(mapping.get("generator_fuzzy_match"), False),
            generator_timeout_seconds=_positive_int(
                mapping.get("generator_timeout_seconds"),
                15,
            ),
            generator_disabled_list=_string_list(mapping.get("generator_disabled_list")),
            generator_compress_static=_bool_value(mapping.get("generator_compress_static"), True),
        )


class MemeGeneratorRuntime:
    def __init__(
        self,
        engine: GeneratorEngine,
        config: GeneratorRuntimeConfig,
        qq_avatar_source: Optional[Callable[[object], str]] = None,
    ):
        self.engine = engine
        self.config = config
        self._qq_avatar_source = qq_avatar_source or (lambda qq: QQ_AVATAR_URL.format(qq=qq))

    def extract_command_text(self, message: str, is_wake: bool = False) -> Optional[str]:
        if not self.config.generator_enabled:
            return None

        text = str(message or "").strip()
        if not text:
            return None

        extra_prefix = self.config.generator_extra_prefix
        if extra_prefix:
            if not text.startswith(extra_prefix):
                return None
            text = text[len(extra_prefix) :].lstrip()
            if not text:
                return None

        if self.config.generator_need_prefix:
            if text[0] in {"/", "\uff0f"}:
                text = text[1:].lstrip()
            elif not is_wake:
                return None
        elif text[0] in {"/", "\uff0f"}:
            text = text[1:].lstrip()

        return text or None

    async def handle(self, event: Any, image_loader: Callable[[str], Any]):
        command_text = self.extract_command_text(
            _event_message_text(event),
            is_wake=_event_is_wake(event),
        )
        if command_text is None:
            return

        if not self._engine_available():
            return

        special_result = await self._handle_special_command(event, command_text)
        if special_result is not None:
            yield special_result
            return

        keyword = self.engine.match_keyword(
            command_text,
            fuzzy=self.config.generator_fuzzy_match,
            disabled=self.config.generator_disabled_list,
        )
        if not keyword:
            return

        params = self._params_for_keyword(keyword)

        async def avatar_loader(qq: str) -> Any:
            source = self._qq_avatar_source(qq)
            return await _maybe_await(image_loader(source))

        try:
            images, texts, options = await collect_generator_params(
                event,
                params,
                command_text=command_text,
                avatar_loader=avatar_loader,
                image_loader=image_loader,
            )
        except Exception:
            logger.exception("meme-generator image load failed")
            yield event.plain_result("图片读取失败，请换一张图再试。")
            return

        try:
            image_bytes = await asyncio.wait_for(
                self.engine.generate(keyword, images, texts, options),
                timeout=self.config.generator_timeout_seconds,
            )
        except asyncio.TimeoutError:
            yield event.plain_result("meme-generator 生成超时，请稍后重试。")
            return
        except Exception:
            logger.exception("meme-generator runtime failed")
            yield event.plain_result("meme-generator 处理失败，请稍后重试。")
            return

        if not image_bytes:
            return

        if self.config.generator_compress_static:
            image_bytes = _compress_static_image(image_bytes)

        yield _image_result(event, image_bytes)

    async def _handle_special_command(self, event: Any, command_text: str) -> Optional[Any]:
        command, argument = _split_command(command_text)
        if command in HELP_COMMANDS:
            return await self._help_result(event)
        if command in DETAIL_COMMANDS:
            return self._detail_result(event, argument)
        if command in BLACKLIST_COMMANDS:
            return event.plain_result(self._blacklist_text())
        if command in DISABLE_COMMANDS or command in ENABLE_COMMANDS:
            return event.plain_result("请在插件配置中调整 generator_disabled_list。")
        return None

    async def _help_result(self, event: Any) -> Any:
        help_payload = _call_optional(self.engine, "get_meme_help")
        if inspect.isawaitable(help_payload):
            help_payload = await help_payload

        if isinstance(help_payload, str) and help_payload:
            return event.plain_result(help_payload)
        if isinstance(help_payload, (bytes, bytearray, memoryview)):
            return _image_result(event, bytes(help_payload))

        lines = [
            "meme-generator 帮助",
            "发送 /<关键词> [@用户] [文字] 生成表情。",
            "发送 /meme详情 <关键词> 查看表情详情。",
        ]
        return event.plain_result("\n".join(lines))

    def _detail_result(self, event: Any, keyword: str) -> Any:
        keyword = keyword.strip()
        if not keyword:
            return event.plain_result("用法：/meme详情 <关键词>")

        info = self.engine.get_meme_info(keyword)
        if info is None:
            return event.plain_result("没有找到这个 meme。")

        info_text, preview = info
        result = event.plain_result(info_text)
        if preview:
            chain = list(getattr(result, "chain", []) or [])
            chain.append(Image.fromBytes(preview))
            result.chain = chain
        return result

    def _blacklist_text(self) -> str:
        if not self.config.generator_disabled_list:
            return "当前没有禁用的 meme-generator 关键词。"
        return "已禁用：{}".format(", ".join(self.config.generator_disabled_list))

    def _engine_available(self) -> bool:
        try:
            return bool(getattr(self.engine, "available", True))
        except Exception as exc:
            logger.warning("meme-generator catalog unavailable: %s", exc)
            return False

    def _params_for_keyword(self, keyword: str) -> GeneratorParams:
        get_params = getattr(self.engine, "get_params", None)
        if callable(get_params):
            params = get_params(keyword)
            if params is not None:
                return params

        find_meme = getattr(self.engine, "find_meme", None)
        raw_params = getattr(self.engine, "_params", None)
        if callable(find_meme) and callable(raw_params):
            meme = find_meme(keyword)
            if meme is not None:
                return raw_params(meme)

        return GeneratorParams()


def _event_message_text(event: Any) -> str:
    text = getattr(event, "message_str", None)
    if text is not None:
        return str(text)

    message_obj = getattr(event, "message_obj", None)
    text = getattr(message_obj, "message_str", None)
    if text is not None:
        return str(text)

    return ""


def _event_is_wake(event: Any) -> bool:
    for name in ("is_wake", "is_wake_up", "is_at", "is_to_me"):
        value = getattr(event, name, None)
        try:
            if callable(value):
                value = value()
        except Exception:
            value = None
        if isinstance(value, bool) and value:
            return True
    return False


def _split_command(command_text: str) -> Tuple[str, str]:
    parts = str(command_text or "").strip().split(maxsplit=1)
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def _image_result(event: Any, image_bytes: bytes) -> Any:
    result = event.make_result()
    result.chain = [Image.fromBytes(image_bytes)]
    return result


def _compress_static_image(image_bytes: bytes, max_side: int = 512) -> bytes:
    try:
        with PILImage.open(io.BytesIO(image_bytes)) as image:
            if getattr(image, "is_animated", False):
                return image_bytes
            if max(image.size) <= max_side:
                return image_bytes

            image = image.copy()
            image.thumbnail((max_side, max_side), _pil_lanczos())
            output = io.BytesIO()
            image.save(output, format="PNG", optimize=True)
            return output.getvalue()
    except Exception:
        return image_bytes


def _pil_lanczos() -> int:
    resampling = getattr(PILImage, "Resampling", PILImage)
    return getattr(resampling, "LANCZOS")


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _call_optional(owner: Any, name: str) -> Any:
    method = getattr(owner, name, None)
    if not callable(method):
        return None
    try:
        return method()
    except Exception as exc:
        logger.warning("meme-generator helper failed: %s error=%s", name, exc)
        return None


def _bool_value(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "enable", "enabled", "开启"}:
            return True
        if normalized in {"0", "false", "no", "off", "disable", "disabled", "关闭"}:
            return False
    return bool(value)


def _positive_int(value: object, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _string_list(value: object) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, Iterable):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []
