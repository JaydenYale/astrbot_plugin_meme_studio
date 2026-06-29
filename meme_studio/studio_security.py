import hmac
import secrets
from dataclasses import dataclass
from urllib.parse import parse_qs


@dataclass(frozen=True)
class StudioAuthConfig:
    token: str


def generate_access_token() -> str:
    return secrets.token_urlsafe(32)


def is_public_bind_host(host: str) -> bool:
    normalized = host.strip().lower()
    return normalized in {"0.0.0.0", "::"} or normalized not in {"", "127.0.0.1", "::1", "localhost"}


def extract_request_token(authorization: str, query: str) -> str:
    value = authorization.strip()
    if value.lower().startswith("bearer "):
        return value.split(" ", 1)[1].strip()
    values = parse_qs(query).get("token", [])
    return values[0] if values else ""


def token_matches(config: StudioAuthConfig, provided: str) -> bool:
    return bool(provided) and hmac.compare_digest(config.token, provided)
