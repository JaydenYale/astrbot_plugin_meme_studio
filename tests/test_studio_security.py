import unittest

from meme_studio.studio_security import (
    StudioAuthConfig,
    extract_request_token,
    generate_access_token,
    is_public_bind_host,
    token_matches,
)


class StudioSecurityTest(unittest.TestCase):
    def test_generate_access_token_is_urlsafe_and_long(self):
        token = generate_access_token()

        self.assertGreaterEqual(len(token), 32)
        self.assertNotIn("/", token)
        self.assertNotIn("+", token)

    def test_public_bind_host_detection(self):
        self.assertTrue(is_public_bind_host("0.0.0.0"))
        self.assertTrue(is_public_bind_host("::"))
        self.assertFalse(is_public_bind_host("127.0.0.1"))
        self.assertFalse(is_public_bind_host("localhost"))

    def test_token_matches_uses_configured_token(self):
        config = StudioAuthConfig(token="secret")

        self.assertTrue(token_matches(config, "secret"))
        self.assertFalse(token_matches(config, "wrong"))

    def test_extract_request_token_accepts_bearer_and_query(self):
        self.assertEqual(extract_request_token("Bearer abc", ""), "abc")
        self.assertEqual(extract_request_token("", "token=abc"), "abc")


if __name__ == "__main__":
    unittest.main()
