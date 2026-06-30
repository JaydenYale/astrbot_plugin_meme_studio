import argparse
import socket
import sys
import webbrowser
from pathlib import Path
from urllib.parse import urlencode


ROOT_MARKERS = ("metadata.yaml", "meme_commands.py")


def find_project_root(start: Path) -> Path:
    current = start.resolve()
    if current.is_file():
        current = current.parent

    for candidate in (current, *current.parents):
        if all((candidate / marker).is_file() for marker in ROOT_MARKERS):
            return candidate
    raise RuntimeError("找不到 AstrBot 表情包插件项目根目录")


def resolve_auth_config(host: str, token: str):
    """Return token auth for all bind hosts; host is reserved for policy changes."""
    from meme_studio.studio_security import StudioAuthConfig, generate_access_token

    value = token.strip() if token else ""
    return StudioAuthConfig(token=value or generate_access_token())


def build_server_url(host: str, port: int, token: str) -> str:
    url = f"http://{_format_url_host(host)}:{port}/"
    if not token:
        return url
    return f"{url}?{urlencode({'token': token})}"


def _format_url_host(host: str) -> str:
    value = host.strip()
    if ":" in value and not (value.startswith("[") and value.endswith("]")):
        return f"[{value}]"
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="启动表情包模板制造器")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8765, help="首选监听端口")
    parser.add_argument("--token", default="", help="访问 Studio 管理 API 的令牌；留空时自动生成")
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    start = Path(sys.executable if getattr(sys, "frozen", False) else __file__)
    project_root = find_project_root(start)
    sys.path.insert(0, str(project_root))

    from tools.meme_studio.server import create_server

    port = _find_free_port(args.host, args.port)
    auth_config = resolve_auth_config(args.host, args.token)
    server = create_server(project_root, args.host, port, auth_config=auth_config)
    url = build_server_url(args.host, port, auth_config.token)
    print(f"Meme Studio running at {url}", flush=True)
    if not args.no_open:
        webbrowser.open(url)
    server.serve_forever()


def _find_free_port(host: str, preferred_port: int) -> int:
    for port in range(preferred_port, preferred_port + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError("找不到可用端口")


if __name__ == "__main__":
    main()
