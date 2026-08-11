from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any

from mcp_ops_auth.rbac import Role
from mcp_ops_common.config import Settings

from mcp_ops_mcp_gateway.errors import AuthenticationFailed
from mcp_ops_mcp_gateway.models import Principal, PrincipalType


class HmacJwtAuthenticator:
    """Validate enterprise JWTs signed with HS256.

    This is intentionally small and strict. It supports the local enterprise pilot path without
    introducing arbitrary token parsing behavior or accepting unsigned tokens.
    """

    def __init__(self, settings: Settings) -> None:
        self.issuer = settings.jwt_issuer
        self.audience = settings.jwt_audience
        self.secret = settings.jwt_secret_key.encode("utf-8")

    def authenticate(self, token: str) -> Principal:
        header, payload, signature = _split_token(token)
        if header.get("alg") != "HS256" or header.get("typ") != "JWT":
            raise AuthenticationFailed("JWT header is not supported.")
        _verify_signature(token, self.secret, signature)
        _verify_registered_claims(payload, issuer=self.issuer, audience=self.audience)
        try:
            role = Role(str(payload["role"]))
            principal_type = PrincipalType(str(payload.get("principal_type", PrincipalType.HUMAN)))
            principal_id = str(payload["sub"])
        except (KeyError, ValueError) as exc:
            raise AuthenticationFailed("JWT principal claims are invalid.") from exc
        return Principal(
            principal_id=principal_id,
            role=role,
            principal_type=principal_type,
        )


def _split_token(token: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthenticationFailed("JWT must contain header, payload, and signature.")
    header = _decode_json(parts[0], "header")
    payload = _decode_json(parts[1], "payload")
    return header, payload, parts[2]


def _decode_json(encoded: str, section: str) -> dict[str, Any]:
    try:
        decoded = base64.urlsafe_b64decode(_pad_base64(encoded)).decode("utf-8")
        value = json.loads(decoded)
    except (ValueError, json.JSONDecodeError) as exc:
        raise AuthenticationFailed(f"JWT {section} is invalid.") from exc
    if not isinstance(value, dict):
        raise AuthenticationFailed(f"JWT {section} must be an object.")
    return value


def _verify_signature(token: str, secret: bytes, signature: str) -> None:
    signing_input = token.rsplit(".", maxsplit=1)[0].encode("utf-8")
    expected = hmac.new(secret, signing_input, hashlib.sha256).digest()
    expected_text = _base64url(expected)
    if not hmac.compare_digest(expected_text, signature):
        raise AuthenticationFailed("JWT signature is invalid.")


def _verify_registered_claims(
    payload: dict[str, Any],
    *,
    issuer: str,
    audience: str,
) -> None:
    now = int(datetime.now(UTC).timestamp())
    if payload.get("iss") != issuer:
        raise AuthenticationFailed("JWT issuer is invalid.")
    if not _audience_matches(payload.get("aud"), audience):
        raise AuthenticationFailed("JWT audience is invalid.")
    exp = payload.get("exp")
    if not isinstance(exp, int) or exp <= now:
        raise AuthenticationFailed("JWT is expired.")
    nbf = payload.get("nbf")
    if isinstance(nbf, int) and nbf > now:
        raise AuthenticationFailed("JWT is not valid yet.")


def _audience_matches(claim: object, expected: str) -> bool:
    if isinstance(claim, str):
        return claim == expected
    if isinstance(claim, list):
        return expected in claim
    return False


def _pad_base64(value: str) -> bytes:
    return (value + "=" * (-len(value) % 4)).encode("utf-8")


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")
