import inspect
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

try:
    from .generator_engine import GeneratorParams
except ImportError:  # pragma: no cover - supports direct package execution in tests.
    from meme_studio.generator_engine import GeneratorParams


ImageItem = Tuple[str, bytes]
Loader = Callable[[str], Any]


async def collect_generator_params(
    event: Any,
    params: GeneratorParams,
    command_text: str,
    avatar_loader: Optional[Loader],
    image_loader: Optional[Loader] = None,
) -> Tuple[List[ImageItem], List[str], Dict[str, object]]:
    images: List[ImageItem] = []
    texts: List[str] = []
    options: Dict[str, object] = {}
    seen_avatar_ids: Set[str] = set()
    seen_image_sources: Set[str] = set()

    max_images = _non_negative_int(getattr(params, "max_images", 0))
    max_texts = _non_negative_int(getattr(params, "max_texts", 0))
    min_images = _bounded_required(getattr(params, "min_images", 0), max_images)
    min_texts = _bounded_required(getattr(params, "min_texts", 0), max_texts)

    async def add_image(name: str, data: Any) -> bool:
        if max_images <= 0 or len(images) >= max_images:
            return False
        image_bytes = _coerce_bytes(data)
        if image_bytes is None:
            return False
        images.append((name, image_bytes))
        return True

    async def add_avatar(qq: Any, name: Optional[str] = None, skip_self: bool = False) -> bool:
        qq_text = _string_or_none(qq)
        if not qq_text or avatar_loader is None:
            return False
        if skip_self and qq_text == _self_id(event):
            return False
        if qq_text in seen_avatar_ids:
            return False
        if max_images <= 0 or len(images) >= max_images:
            return False

        seen_avatar_ids.add(qq_text)
        data = await _call_loader(avatar_loader, qq_text)
        return await add_image(name or qq_text, data)

    async def add_source(source: Any) -> bool:
        source_text = _string_or_none(source)
        if not source_text or image_loader is None:
            return False
        if source_text in seen_image_sources:
            return False
        if max_images <= 0 or len(images) >= max_images:
            return False

        seen_image_sources.add(source_text)
        data = await _call_loader(image_loader, source_text)
        return await add_image(source_text, data)

    async def collect_token(token: str) -> None:
        key, value = _split_option(token)
        if key is not None:
            options[key] = value
            return

        qq = _at_token_target(token)
        if qq is not None:
            await add_avatar(qq)
            return

        texts.append(token)

    tokens = _split_words(command_text)
    for token in tokens[1:]:
        await collect_token(token)

    command_body = _normalize_command_text(command_text)
    for component in _message_components(event):
        await _collect_component(
            component,
            collect_token=collect_token,
            add_avatar=add_avatar,
            add_source=add_source,
            command_body=command_body,
        )

    if len(images) < min_images:
        sender_id = _call_event_method(event, "get_sender_id")
        sender_name = _string_or_none(_call_event_method(event, "get_sender_name")) or "sender"
        await add_avatar(sender_id, sender_name)

    if len(images) < min_images:
        self_id = _call_event_method(event, "get_self_id")
        await add_avatar(self_id, "bot")

    default_texts = list(getattr(params, "default_texts", []) or [])
    for default_text in default_texts:
        if len(texts) >= min_texts:
            break
        text = _string_or_none(default_text)
        if text:
            texts.append(text)

    return images[:max_images], texts[:max_texts], options


async def _collect_component(
    component: Any,
    collect_token: Callable[[str], Any],
    add_avatar: Callable[..., Any],
    add_source: Callable[[Any], Any],
    command_body: str,
) -> None:
    if component is None:
        return

    if _is_reply_component(component):
        for nested in _nested_components(component):
            await _collect_component(
                nested,
                collect_token=collect_token,
                add_avatar=add_avatar,
                add_source=add_source,
                command_body=command_body,
            )
        sender_id = _first_attr(component, ("sender_id", "sender", "user_id", "qq"))
        if sender_id is not None:
            await add_avatar(sender_id, skip_self=True)
        return

    source = _image_source(component)
    if source is not None:
        await add_source(source)
        return

    qq = _at_target(component)
    if qq is not None:
        await add_avatar(qq, skip_self=True)
        return

    plain_text = _plain_text(component)
    if plain_text is not None and _normalize_command_text(plain_text) != command_body:
        for token in _split_words(plain_text):
            await collect_token(token)


async def _call_loader(loader: Loader, value: str) -> Any:
    try:
        result = loader(value)
        if inspect.isawaitable(result):
            return await result
        return result
    except Exception:
        return None


def _coerce_bytes(data: Any) -> Optional[bytes]:
    if data is None:
        return None
    if isinstance(data, bytes):
        return data
    if isinstance(data, (bytearray, memoryview)):
        return bytes(data)
    return None


def _message_components(event: Any) -> List[Any]:
    candidates: List[Any] = []
    message_obj = getattr(event, "message_obj", None)
    for owner in (message_obj, event):
        if owner is None:
            continue
        for attr in ("message", "messages", "message_chain", "chain"):
            value = getattr(owner, attr, None)
            if value is not None:
                candidates.extend(_as_components(value))

    if not candidates:
        getter = getattr(event, "get_messages", None)
        if callable(getter):
            try:
                candidates.extend(_as_components(getter()))
            except Exception:
                pass

    return candidates


def _as_components(value: Any) -> List[Any]:
    if value is None or isinstance(value, (str, bytes, bytearray)):
        return []
    if isinstance(value, Iterable):
        return list(value)
    return [value]


def _nested_components(component: Any) -> List[Any]:
    nested: List[Any] = []
    for attr in ("message", "messages", "message_chain", "chain"):
        value = getattr(component, attr, None)
        if value is not None:
            nested.extend(_as_components(value))
    message_obj = getattr(component, "message_obj", None)
    if message_obj is not None:
        nested.extend(_message_components(message_obj))
    return nested


def _image_source(component: Any) -> Optional[str]:
    if not _looks_like(component, "image") and not any(
        getattr(component, attr, None) for attr in ("url", "file", "path", "src", "source")
    ):
        return None
    return _string_or_none(_first_attr(component, ("url", "file", "path", "src", "source")))


def _at_target(component: Any) -> Optional[str]:
    if not _looks_like(component, "at") and not hasattr(component, "qq"):
        return None
    return _string_or_none(_first_attr(component, ("qq", "target", "user_id", "id")))


def _plain_text(component: Any) -> Optional[str]:
    if isinstance(component, str):
        return component
    if _looks_like(component, "plain") or hasattr(component, "text"):
        return _string_or_none(_first_attr(component, ("text", "content", "message")))
    return None


def _is_reply_component(component: Any) -> bool:
    return _looks_like(component, "reply")


def _looks_like(component: Any, marker: str) -> bool:
    marker = marker.lower()
    class_name = component.__class__.__name__.lower()
    type_name = str(getattr(component, "type", "") or getattr(component, "kind", "")).lower()
    return marker in class_name or marker == type_name


def _first_attr(obj: Any, attrs: Iterable[str]) -> Any:
    for attr in attrs:
        value = getattr(obj, attr, None)
        if value is not None:
            return value
    return None


def _call_event_method(event: Any, name: str) -> Any:
    method = getattr(event, name, None)
    if not callable(method):
        return None
    try:
        return method()
    except Exception:
        return None


def _self_id(event: Any) -> Optional[str]:
    return _string_or_none(_call_event_method(event, "get_self_id"))


def _split_words(text: str) -> List[str]:
    return str(text or "").split()


def _split_option(token: str) -> Tuple[Optional[str], Optional[str]]:
    if "=" not in token:
        return None, None
    key, value = token.split("=", 1)
    key = key.strip()
    if not key:
        return None, None
    return key, value


def _at_token_target(token: str) -> Optional[str]:
    if len(token) <= 1 or not token.startswith("@"):
        return None
    target = token[1:].strip()
    return target or None


def _string_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_command_text(text: str) -> str:
    text = str(text or "").strip()
    while text.startswith(("/", "\uff0f")):
        text = text[1:].lstrip()
    return text


def _non_negative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _bounded_required(value: Any, limit: int) -> int:
    required = _non_negative_int(value)
    if limit <= 0:
        return 0
    return min(required, limit)
