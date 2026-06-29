import asyncio
import io
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

try:
    from astrbot.api import logger
except Exception:  # pragma: no cover - AstrBot supplies this at plugin runtime.
    class _FallbackLogger:
        def warning(self, *args: Any, **kwargs: Any) -> None:
            return None

    logger = _FallbackLogger()


@dataclass(frozen=True)
class GeneratorParams:
    min_images: int = 0
    max_images: int = 0
    min_texts: int = 0
    max_texts: int = 0
    default_texts: List[str] = field(default_factory=list)


class GeneratorEngine:
    def __init__(self, importer: Optional[Callable[[], Iterable[Any]]] = None):
        self._importer = importer or self._load_from_meme_generator
        self._memes: List[Any] = []
        self._load_error: Optional[str] = None
        self._loaded = False

    @property
    def available(self) -> bool:
        self._ensure_loaded()
        return bool(self._memes)

    @property
    def load_error(self) -> Optional[str]:
        self._ensure_loaded()
        return self._load_error

    def _load_from_meme_generator(self) -> Iterable[Any]:
        from meme_generator import get_memes

        return get_memes()

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return

        self._loaded = True
        try:
            self._memes = list(self._importer())
        except Exception as exc:
            self._load_error = str(exc)
            self._memes = []
            logger.warning("meme-generator unavailable: %s", exc)

    def _keywords(self, meme: Any) -> List[str]:
        info = getattr(meme, "info", None)
        if info is not None and hasattr(info, "keywords"):
            return list(getattr(info, "keywords") or [])
        return list(getattr(meme, "keywords", []) or [])

    def _params(self, meme: Any) -> GeneratorParams:
        info = getattr(meme, "info", None)
        raw = getattr(info, "params", None) if info is not None else None
        if raw is None:
            raw = getattr(meme, "params", None)
        if raw is None:
            raw = getattr(meme, "params_type", None)
        if raw is None:
            return GeneratorParams()

        return GeneratorParams(
            min_images=int(getattr(raw, "min_images", 0) or 0),
            max_images=int(getattr(raw, "max_images", 0) or 0),
            min_texts=int(getattr(raw, "min_texts", 0) or 0),
            max_texts=int(getattr(raw, "max_texts", 0) or 0),
            default_texts=list(getattr(raw, "default_texts", []) or []),
        )

    def _tags(self, meme: Any) -> List[str]:
        info = getattr(meme, "info", None)
        if info is not None and hasattr(info, "tags"):
            return list(getattr(info, "tags") or [])
        return list(getattr(meme, "tags", []) or [])

    def _candidate_keywords(self, disabled: Iterable[str]) -> List[Tuple[str, Any]]:
        disabled_set = {keyword for keyword in disabled if keyword}
        candidates: List[Tuple[str, Any]] = []
        for meme in self._memes:
            meme_key = getattr(meme, "key", "")
            if meme_key in disabled_set:
                continue
            for keyword in self._keywords(meme):
                if keyword and keyword not in disabled_set:
                    candidates.append((keyword, meme))
        return candidates

    def find_meme(self, keyword: str) -> Optional[Any]:
        self._ensure_loaded()
        for meme in self._memes:
            if keyword == getattr(meme, "key", "") or keyword in self._keywords(meme):
                return meme
        return None

    def match_keyword(
        self,
        text: str,
        fuzzy: bool,
        disabled: Iterable[str],
    ) -> Optional[str]:
        self._ensure_loaded()
        text = (text or "").strip()
        if not text:
            return None

        candidates = self._candidate_keywords(disabled)
        if fuzzy:
            candidates = sorted(candidates, key=lambda item: len(item[0]), reverse=True)
            for keyword, _meme in candidates:
                if keyword in text:
                    return keyword
            return None

        first_word = text.split(maxsplit=1)[0]
        for keyword, _meme in candidates:
            if keyword == first_word:
                return keyword
        return None

    @staticmethod
    def unwrap_bytes(result: Any, action: str) -> bytes:
        if isinstance(result, io.BytesIO):
            return result.getvalue()
        if isinstance(result, (bytes, bytearray, memoryview)):
            return bytes(result)

        detail = getattr(result, "feedback", None) or getattr(result, "error", None)
        if detail is None:
            detail = repr(result)
        raise RuntimeError("{} failed: {}".format(action, detail))

    def get_meme_info(self, keyword: str) -> Optional[Tuple[str, bytes]]:
        meme = self.find_meme(keyword)
        if meme is None:
            return None

        params = self._params(meme)
        keywords = self._keywords(meme)
        tags = self._tags(meme)
        lines = [
            "Name: {}".format(getattr(meme, "key", keyword)),
            "Keywords: {}".format(", ".join(keywords)),
        ]
        if params.max_images:
            lines.append("Images: {}-{}".format(params.min_images, params.max_images))
        if params.max_texts:
            lines.append("Texts: {}-{}".format(params.min_texts, params.max_texts))
        if tags:
            lines.append("Tags: {}".format(", ".join(tags)))

        preview = self.unwrap_bytes(meme.generate_preview(), "generate preview for {}".format(keyword))
        return "\n".join(lines), preview

    async def generate(
        self,
        keyword: str,
        images: List[Tuple[str, bytes]],
        texts: List[str],
        options: Dict[str, object],
    ) -> Optional[bytes]:
        meme = self.find_meme(keyword)
        if meme is None:
            return None

        result = await asyncio.to_thread(
            meme.generate,
            [data for _name, data in images],
            texts,
            options,
        )
        return self.unwrap_bytes(result, "generate meme {}".format(keyword))
