import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from meme_studio_launcher import build_server_url, find_project_root, main, resolve_auth_config


class MemeStudioLauncherTest(unittest.TestCase):
    def test_find_project_root_walks_up_from_dist_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "metadata.yaml").write_text('name: "表情包制造厂"\n', encoding="utf-8")
            (root / "meme_commands.py").write_text("# marker\n", encoding="utf-8")
            dist = root / "dist"
            dist.mkdir()

            self.assertEqual(find_project_root(dist), root)

    def test_build_server_url_includes_token_when_present(self):
        self.assertEqual(build_server_url("127.0.0.1", 8765, "secret"), "http://127.0.0.1:8765/?token=secret")

    def test_build_server_url_omits_token_when_empty(self):
        self.assertEqual(build_server_url("127.0.0.1", 8765, ""), "http://127.0.0.1:8765/")

    def test_build_server_url_brackets_ipv6_hosts(self):
        self.assertEqual(build_server_url("::1", 8765, "secret"), "http://[::1]:8765/?token=secret")

    def test_resolve_auth_config_generates_token_for_public_bind_host(self):
        config = resolve_auth_config("0.0.0.0", "")

        self.assertTrue(config.token)

    def test_resolve_auth_config_generates_token_for_loopback_bind_host(self):
        config = resolve_auth_config("127.0.0.1", "")

        self.assertTrue(config.token)

    def test_resolve_auth_config_uses_provided_token(self):
        config = resolve_auth_config("127.0.0.1", " secret ")

        self.assertEqual(config.token, "secret")

    def test_main_passes_auth_config_and_opens_tokenized_url(self):
        created = {}

        class FakeServer:
            def serve_forever(self):
                created["served"] = True

        def fake_create_server(project_root, host, port, auth_config=None):
            created["project_root"] = project_root
            created["host"] = host
            created["port"] = port
            created["auth_config"] = auth_config
            return FakeServer()

        with mock.patch.object(
            sys,
            "argv",
            ["meme_studio_launcher.py", "--host", "127.0.0.1", "--port", "8765", "--token", "secret"],
        ), mock.patch("meme_studio_launcher.find_project_root", return_value=Path.cwd()), mock.patch(
            "meme_studio_launcher._find_free_port", return_value=8766
        ), mock.patch("tools.meme_studio.server.create_server", side_effect=fake_create_server), mock.patch(
            "webbrowser.open"
        ) as open_browser, mock.patch("builtins.print") as print_output:
            main()

        self.assertEqual(created["host"], "127.0.0.1")
        self.assertEqual(created["port"], 8766)
        self.assertEqual(created["auth_config"].token, "secret")
        self.assertTrue(created["served"])
        print_output.assert_called_once_with(
            "Meme Studio running at http://127.0.0.1:8766/?token=secret", flush=True
        )
        open_browser.assert_called_once_with("http://127.0.0.1:8766/?token=secret")


if __name__ == "__main__":
    unittest.main()
