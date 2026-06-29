import base64
import json
import mimetypes
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import unquote, urlparse

from .renderer import validate_command_name
from .studio_security import StudioAuthConfig, extract_request_token, token_matches
from .studio_service import MemeStudioService


MAX_JSON_BYTES = 80 * 1024 * 1024
WEB_ROOT = Path(__file__).resolve().parent / "web"


def create_server(
    project_root: Path,
    host: str = "127.0.0.1",
    port: int = 8765,
    auth_config: Optional[StudioAuthConfig] = None,
) -> ThreadingHTTPServer:
    service = MemeStudioService(
        project_root=project_root,
        session_root=project_root / ".meme_studio_sessions",
        export_root=project_root / "exports",
    )

    class MemeStudioHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send_file(WEB_ROOT / "index.html")
                return
            if parsed.path in {"/app.js", "/styles.css"}:
                self._send_file(WEB_ROOT / parsed.path.lstrip("/"))
                return
            if parsed.path.startswith("/api/") and not self._is_authorized(parsed):
                self._send_json({"error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            if parsed.path == "/api/templates":
                self._send_json({"templates": service.list_applied_templates()})
                return
            if parsed.path.startswith("/api/templates/"):
                self._send_template_preview(parsed.path)
                return
            if parsed.path.startswith("/api/projects/"):
                self._send_project_frame(parsed.path)
                return
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/") and not self._is_authorized(parsed):
                self._send_json({"error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                payload = self._read_json()
                if parsed.path == "/api/upload":
                    self._send_json(service.upload_files(_decode_uploads(payload.get("files", []))))
                    return
                if parsed.path == "/api/decompose-gif":
                    self._send_json(service.upload_files(_decode_uploads([payload["file"]])))
                    return
                if parsed.path == "/api/export":
                    export_dir = service.export_template(str(payload["project_id"]), payload["manifest"])
                    self._send_json({"path": str(export_dir)})
                    return
                if parsed.path == "/api/preview-current":
                    preview_path = service.preview_current_template(str(payload["project_id"]), payload["manifest"])
                    project_id = str(payload["project_id"])
                    self._send_json(
                        {"preview_url": f"/api/projects/{project_id}/{preview_path.name}?v={uuid.uuid4().hex}"}
                    )
                    return
                if parsed.path == "/api/apply":
                    data_dir = service.apply_template(str(payload["project_id"]), payload["manifest"])
                    self._send_json({"path": str(data_dir), "templates": service.list_applied_templates()})
                    return
                if parsed.path == "/api/delete-template":
                    command = validate_command_name(str(payload.get("command", "")))
                    data_dir = service.delete_template(command)
                    self._send_json(
                        {
                            "deleted": command,
                            "path": str(data_dir),
                            "templates": service.list_applied_templates(),
                        }
                    )
                    return
                self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            except Exception as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _is_authorized(self, parsed) -> bool:
            if auth_config is None:
                return True
            token = extract_request_token(self.headers.get("Authorization", ""), parsed.query)
            return token_matches(auth_config, token)

        def _read_json(self) -> Dict[str, object]:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length > MAX_JSON_BYTES:
                raise ValueError("璇锋眰鍐呭杩囧ぇ")
            body = self.rfile.read(content_length)
            return json.loads(body.decode("utf-8"))

        def _send_file(self, path: Path) -> None:
            if not path.is_file():
                self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return

            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            data = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_project_frame(self, request_path: str) -> None:
            parts = [unquote(part) for part in request_path.split("/") if part]
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] in {"preview.png", "preview.gif"}:
                preview_path = service.project_dir(parts[2]) / parts[3]
                self._send_file(preview_path)
                return
            if len(parts) != 5 or parts[:2] != ["api", "projects"] or parts[3] != "frames":
                self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return

            project_id = parts[2]
            frame_name = parts[4]
            frame_path = service.project_dir(project_id) / "frames" / frame_name
            self._send_file(frame_path)

        def _send_template_preview(self, request_path: str) -> None:
            parts = [unquote(part) for part in request_path.split("/") if part]
            if len(parts) != 4 or parts[:2] != ["api", "templates"] or parts[3] not in {"preview.png", "preview.gif"}:
                self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return

            try:
                preview_path = service.template_preview(parts[2])
            except FileNotFoundError:
                self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return
            self._send_file(preview_path)

        def _send_json(self, payload: Dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return ThreadingHTTPServer((host, port), MemeStudioHandler)


def _decode_uploads(files: List[Dict[str, object]]) -> List[Dict[str, object]]:
    decoded = []
    for file_info in files:
        data = str(file_info["data"])
        if "," in data:
            data = data.split(",", 1)[1]
        decoded.append({"name": str(file_info["name"]), "data": base64.b64decode(data)})
    return decoded


def _clip_preview_reason(reason: str, limit: int = 42) -> str:
    normalized = " ".join(reason.split())
    normalized = normalized.encode("ascii", errors="ignore").decode("ascii").strip() or "Open details for info"
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit]}..."


def _normalize_preview_ext(output_ext: str) -> str:
    return "png" if output_ext.lower() == "png" else "gif"
