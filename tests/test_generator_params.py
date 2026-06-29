import types
import unittest

from meme_studio.generator_engine import GeneratorParams
from meme_studio.generator_params import collect_generator_params


class FakeEvent:
    def __init__(self, message=None, sender_id="10001", self_id="20002", sender_name="sender"):
        self.message_obj = types.SimpleNamespace(message=message or [])
        self._sender_id = sender_id
        self._self_id = self_id
        self._sender_name = sender_name

    def get_sender_id(self):
        return self._sender_id

    def get_self_id(self):
        return self._self_id

    def get_sender_name(self):
        return self._sender_name


class FakeImage:
    def __init__(self, source):
        self.url = source


class GeneratorParamsCollectorTest(unittest.IsolatedAsyncioTestCase):
    async def test_collects_text_options_and_sender_avatar_fallback(self):
        calls = []

        async def avatar_loader(qq):
            calls.append(qq)
            return "avatar-{}".format(qq).encode("ascii")

        images, texts, options = await collect_generator_params(
            FakeEvent(),
            GeneratorParams(min_images=1, max_images=1, min_texts=1, max_texts=2, default_texts=[]),
            command_text="pet hello mood=happy",
            avatar_loader=avatar_loader,
        )

        self.assertEqual(images, [("sender", b"avatar-10001")])
        self.assertEqual(texts, ["hello"])
        self.assertEqual(options, {"mood": "happy"})
        self.assertEqual(calls, ["10001"])

    async def test_at_token_loads_avatar_image(self):
        calls = []

        async def avatar_loader(qq):
            calls.append(qq)
            return "avatar-{}".format(qq).encode("ascii")

        images, texts, options = await collect_generator_params(
            FakeEvent(),
            GeneratorParams(min_images=1, max_images=2, min_texts=0, max_texts=1, default_texts=[]),
            command_text="pet @123456",
            avatar_loader=avatar_loader,
        )

        self.assertEqual(images, [("123456", b"avatar-123456")])
        self.assertEqual(texts, [])
        self.assertEqual(options, {})
        self.assertEqual(calls, ["123456"])

    async def test_image_component_uses_injected_image_loader(self):
        image_calls = []
        avatar_calls = []

        async def image_loader(source):
            image_calls.append(source)
            return b"loaded-image"

        async def avatar_loader(qq):
            avatar_calls.append(qq)
            return b"avatar"

        images, texts, options = await collect_generator_params(
            FakeEvent(message=[FakeImage("image://one")]),
            GeneratorParams(min_images=1, max_images=1, min_texts=0, max_texts=0, default_texts=[]),
            command_text="pet",
            avatar_loader=avatar_loader,
            image_loader=image_loader,
        )

        self.assertEqual(images, [("image://one", b"loaded-image")])
        self.assertEqual(texts, [])
        self.assertEqual(options, {})
        self.assertEqual(image_calls, ["image://one"])
        self.assertEqual(avatar_calls, [])

    async def test_default_texts_fill_shortage_and_clip_to_max_texts(self):
        async def avatar_loader(qq):
            return None

        images, texts, options = await collect_generator_params(
            FakeEvent(),
            GeneratorParams(
                min_images=0,
                max_images=0,
                min_texts=3,
                max_texts=2,
                default_texts=["fallback-one", "fallback-two"],
            ),
            command_text="pet hello",
            avatar_loader=avatar_loader,
        )

        self.assertEqual(images, [])
        self.assertEqual(texts, ["hello", "fallback-one"])
        self.assertEqual(options, {})


if __name__ == "__main__":
    unittest.main()
