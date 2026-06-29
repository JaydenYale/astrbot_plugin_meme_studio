import asyncio
import io
import sys
import types
import unittest

from PIL import Image as PILImage


class FakeLogger:
    def warning(self, *args, **kwargs):
        pass

    def exception(self, *args, **kwargs):
        pass


class FakeFilter:
    class EventMessageType:
        ALL = "all"

    @staticmethod
    def command(name):
        def decorate(func):
            func.__astrbot_command_name__ = name
            return func

        return decorate

    @staticmethod
    def event_message_type(message_type):
        def decorate(func):
            func.__astrbot_event_message_type__ = message_type
            return func

        return decorate


class FakeStar:
    def __init__(self, context):
        self.context = context


class FakeContext:
    pass


class FakeAstrMessageEvent:
    pass


class FakeAt:
    def __init__(self, qq):
        self.qq = qq


class FakeImage:
    def __init__(self, data=None, url=None, file=None):
        self.data = data
        self.url = url
        self.file = file

    @classmethod
    def fromBytes(cls, image_bytes):
        return cls(data=image_bytes)


def install_astrbot_stubs():
    astrbot = types.ModuleType("astrbot")
    api = types.ModuleType("astrbot.api")
    api.logger = FakeLogger()

    event = types.ModuleType("astrbot.api.event")
    event.AstrMessageEvent = FakeAstrMessageEvent
    event.filter = FakeFilter

    message_components = types.ModuleType("astrbot.api.message_components")
    message_components.At = FakeAt
    message_components.Image = FakeImage

    star = types.ModuleType("astrbot.api.star")
    star.Context = FakeContext
    star.Star = FakeStar

    sys.modules["astrbot"] = astrbot
    sys.modules["astrbot.api"] = api
    sys.modules["astrbot.api.event"] = event
    sys.modules["astrbot.api.message_components"] = message_components
    sys.modules["astrbot.api.star"] = star


install_astrbot_stubs()

from meme_studio.generator_engine import GeneratorParams
from meme_studio.generator_runtime import GeneratorRuntimeConfig, MemeGeneratorRuntime
from meme_studio.runtime import MemeStudioRuntime, QQ_AVATAR_URL


class FakeResult:
    def __init__(self, text=None):
        self.text = text
        self.chain = []


class FakeEvent:
    def __init__(self, message_str, sender_id="10001", self_id="20002", message=None):
        self.message_str = message_str
        self.message_obj = types.SimpleNamespace(message_str=message_str, message=message or [])
        self._sender_id = sender_id
        self._self_id = self_id

    def get_sender_id(self):
        return self._sender_id

    def get_self_id(self):
        return self._self_id

    def get_sender_name(self):
        return "sender"

    def plain_result(self, text):
        return FakeResult(text=text)

    def make_result(self):
        return FakeResult()


class FakeMeme:
    pass


class FakeEngine:
    available = True

    def __init__(self):
        self.generated = []
        self.detail_calls = []

    def match_keyword(self, text, fuzzy, disabled):
        return "pet" if text.startswith("pet") and "pet" not in disabled else None

    def find_meme(self, keyword):
        return FakeMeme() if keyword == "pet" else None

    def _params(self, meme):
        return GeneratorParams(min_images=1, max_images=1, min_texts=0, max_texts=2)

    def get_meme_info(self, keyword):
        self.detail_calls.append(keyword)
        if keyword != "pet":
            return None
        return "Name: pet", b"preview"

    async def generate(self, keyword, images, texts, options):
        self.generated.append((keyword, images, texts, options))
        return b"generated-image"


class StaticImageEngine(FakeEngine):
    def __init__(self, image_bytes):
        super().__init__()
        self.image_bytes = image_bytes

    def match_keyword(self, text, fuzzy, disabled):
        return "wide" if text.startswith("wide") else None

    def _params(self, meme):
        return GeneratorParams(min_images=0, max_images=0, min_texts=0, max_texts=0)

    async def generate(self, keyword, images, texts, options):
        self.generated.append((keyword, images, texts, options))
        return self.image_bytes


class UnavailableEngine:
    available = False

    def match_keyword(self, text, fuzzy, disabled):
        raise AssertionError("unavailable engine should not be matched")


class FakeGeneratorRuntime:
    def __init__(self):
        self.called = False

    async def handle(self, event, image_loader):
        self.called = True
        yield event.plain_result("generator called")


async def collect_async(async_iterable):
    return [item async for item in async_iterable]


class GeneratorRuntimeConfigTest(unittest.TestCase):
    def test_from_mapping_uses_defaults_and_normalizes_disabled_list(self):
        config = GeneratorRuntimeConfig.from_mapping({})

        self.assertTrue(config.generator_enabled)
        self.assertTrue(config.generator_need_prefix)
        self.assertEqual(config.generator_extra_prefix, "")
        self.assertFalse(config.generator_fuzzy_match)
        self.assertEqual(config.generator_timeout_seconds, 15)
        self.assertEqual(config.generator_disabled_list, [])
        self.assertTrue(config.generator_compress_static)

        config = GeneratorRuntimeConfig.from_mapping(
            {
                "generator_enabled": "off",
                "generator_need_prefix": "false",
                "generator_extra_prefix": "!",
                "generator_fuzzy_match": "yes",
                "generator_timeout_seconds": "3",
                "generator_disabled_list": "pet, hug",
                "generator_compress_static": "0",
            }
        )

        self.assertFalse(config.generator_enabled)
        self.assertFalse(config.generator_need_prefix)
        self.assertEqual(config.generator_extra_prefix, "!")
        self.assertTrue(config.generator_fuzzy_match)
        self.assertEqual(config.generator_timeout_seconds, 3)
        self.assertEqual(config.generator_disabled_list, ["pet", "hug"])
        self.assertFalse(config.generator_compress_static)


class GeneratorRuntimeExtractCommandTest(unittest.TestCase):
    def test_strips_slash_prefix_when_prefix_required(self):
        runtime = MemeGeneratorRuntime(FakeEngine(), GeneratorRuntimeConfig())

        self.assertEqual(runtime.extract_command_text("/pet @10001", is_wake=False), "pet @10001")
        self.assertEqual(runtime.extract_command_text("／pet @10001", is_wake=False), "pet @10001")

    def test_ignores_plain_message_when_prefix_required(self):
        runtime = MemeGeneratorRuntime(FakeEngine(), GeneratorRuntimeConfig(generator_need_prefix=True))

        self.assertIsNone(runtime.extract_command_text("pet @10001", is_wake=False))
        self.assertEqual(runtime.extract_command_text("pet @10001", is_wake=True), "pet @10001")

    def test_requires_extra_prefix_when_configured(self):
        runtime = MemeGeneratorRuntime(
            FakeEngine(),
            GeneratorRuntimeConfig(generator_extra_prefix="!"),
        )

        self.assertIsNone(runtime.extract_command_text("/pet", is_wake=False))
        self.assertEqual(runtime.extract_command_text("!/pet", is_wake=False), "pet")

    def test_disabled_runtime_returns_none(self):
        runtime = MemeGeneratorRuntime(
            FakeEngine(),
            GeneratorRuntimeConfig(generator_enabled=False),
        )

        self.assertIsNone(runtime.extract_command_text("/pet", is_wake=False))


class GeneratorRuntimeHandleTest(unittest.IsolatedAsyncioTestCase):
    async def test_unavailable_engine_does_not_yield(self):
        runtime = MemeGeneratorRuntime(UnavailableEngine(), GeneratorRuntimeConfig())

        results = await collect_async(runtime.handle(FakeEvent("/pet @123"), image_loader=lambda source: b""))

        self.assertEqual(results, [])

    async def test_no_keyword_match_does_not_yield(self):
        runtime = MemeGeneratorRuntime(FakeEngine(), GeneratorRuntimeConfig())

        results = await collect_async(runtime.handle(FakeEvent("/unknown"), image_loader=lambda source: b""))

        self.assertEqual(results, [])

    async def test_detail_command_yields_plain_text_and_preview_image(self):
        engine = FakeEngine()
        runtime = MemeGeneratorRuntime(engine, GeneratorRuntimeConfig())

        results = await collect_async(runtime.handle(FakeEvent("/meme详情 pet"), image_loader=lambda source: b""))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].text, "Name: pet")
        self.assertEqual(results[0].chain[0].data, b"preview")
        self.assertEqual(engine.detail_calls, ["pet"])

    async def test_successful_generate_yields_image_chain_result(self):
        engine = FakeEngine()
        runtime = MemeGeneratorRuntime(engine, GeneratorRuntimeConfig())
        loaded_sources = []

        async def image_loader(source):
            loaded_sources.append(source)
            return b"avatar-bytes"

        results = await collect_async(runtime.handle(FakeEvent("/pet @123 hello"), image_loader=image_loader))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].chain[0].data, b"generated-image")
        self.assertEqual(loaded_sources, [QQ_AVATAR_URL.format(qq="123")])
        self.assertEqual(
            engine.generated,
            [("pet", [("123", b"avatar-bytes")], ["hello"], {})],
        )

    async def test_explicit_image_loader_error_yields_read_failure_without_generate(self):
        engine = FakeEngine()
        runtime = MemeGeneratorRuntime(engine, GeneratorRuntimeConfig())

        async def image_loader(source):
            self.assertEqual(source, "bad-source")
            raise FileNotFoundError("bad image")

        results = await collect_async(
            runtime.handle(
                FakeEvent("/pet", message=[FakeImage(url="bad-source")]),
                image_loader=image_loader,
            )
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(engine.generated, [])
        self.assertTrue("图片" in results[0].text or "读取" in results[0].text)

    async def test_compress_static_image_resizes_large_generator_output(self):
        original = make_png(900, 300)
        engine = StaticImageEngine(original)
        runtime = MemeGeneratorRuntime(engine, GeneratorRuntimeConfig(generator_compress_static=True))

        results = await collect_async(runtime.handle(FakeEvent("/wide"), image_loader=lambda source: b""))

        output = results[0].chain[0].data
        with PILImage.open(io.BytesIO(output)) as image:
            self.assertLessEqual(max(image.size), 512)


class MemeStudioRuntimeDispatchTest(unittest.IsolatedAsyncioTestCase):
    async def test_local_command_priority_does_not_call_generator_runtime(self):
        plugin = MemeStudioRuntime(FakeContext(), {})
        fake_generator = FakeGeneratorRuntime()
        plugin.generator_runtime = fake_generator

        results = await collect_async(plugin.on_message(FakeEvent("/砸 @123")))

        self.assertFalse(fake_generator.called)
        self.assertEqual(len(results), 1)
        self.assertIn("指令需要带图发送", results[0].text)


def make_png(width, height):
    buffer = io.BytesIO()
    PILImage.new("RGB", (width, height), (40, 120, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
