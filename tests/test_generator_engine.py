import io
import sys
import types
import unittest


class FakeLogger:
    def __init__(self):
        self.warnings = []

    def warning(self, *args, **kwargs):
        self.warnings.append((args, kwargs))


fake_logger = FakeLogger()
astrbot = types.ModuleType("astrbot")
api = types.ModuleType("astrbot.api")
api.logger = fake_logger
sys.modules.setdefault("astrbot", astrbot)
sys.modules.setdefault("astrbot.api", api)

from meme_studio.generator_engine import GeneratorEngine, GeneratorParams


class FakeInfo:
    keywords = ["pet", "petpet"]
    tags = ["action"]
    params = GeneratorParams(
        min_images=1,
        max_images=1,
        min_texts=0,
        max_texts=1,
        default_texts=[],
    )


class FakeMeme:
    key = "petpet"
    info = FakeInfo()

    def __init__(self):
        self.generated = []

    def generate_preview(self):
        return io.BytesIO(b"preview")

    def generate(self, images, texts, options):
        self.generated.append((images, texts, options))
        return b"generated"


class GeneratorEngineTest(unittest.TestCase):
    def test_missing_dependency_is_not_available_and_loads_once(self):
        calls = []

        def importer():
            calls.append("called")
            raise ImportError("missing meme_generator")

        engine = GeneratorEngine(importer=importer)

        self.assertFalse(engine.available)
        self.assertFalse(engine.available)
        self.assertIsNone(engine.match_keyword("pet @someone", fuzzy=False, disabled=[]))
        self.assertEqual(calls, ["called"])

    def test_match_keyword_exact_and_fuzzy(self):
        engine = GeneratorEngine(importer=lambda: [FakeMeme()])

        self.assertEqual(engine.match_keyword("pet @someone", fuzzy=False, disabled=[]), "pet")
        self.assertIsNone(engine.match_keyword("please pet this", fuzzy=False, disabled=[]))
        self.assertEqual(engine.match_keyword("please pet this", fuzzy=True, disabled=[]), "pet")

    def test_disabled_keyword_is_ignored(self):
        engine = GeneratorEngine(importer=lambda: [FakeMeme()])

        self.assertIsNone(engine.match_keyword("pet", fuzzy=False, disabled=["pet"]))

    def test_info_and_preview_unwrap_bytesio(self):
        engine = GeneratorEngine(importer=lambda: [FakeMeme()])

        info_text, preview = engine.get_meme_info("pet")

        self.assertIn("petpet", info_text)
        self.assertIn("pet", info_text)
        self.assertIn("action", info_text)
        self.assertEqual(preview, b"preview")

    def test_generate_runs_in_thread_and_unwraps_bytes(self):
        meme = FakeMeme()
        engine = GeneratorEngine(importer=lambda: [meme])

        result = self._run(engine.generate("pet", [("target", b"image")], ["hello"], {"speed": 2}))

        self.assertEqual(result, b"generated")
        self.assertEqual(meme.generated, [([b"image"], ["hello"], {"speed": 2})])

    @staticmethod
    def _run(awaitable):
        return __import__("asyncio").run(awaitable)


if __name__ == "__main__":
    unittest.main()
