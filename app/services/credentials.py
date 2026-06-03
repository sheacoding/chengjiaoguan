"""
/* ========================================================================== */
/* GEB L3: 渠道凭据封装                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 base64、dataclass、hashlib、hmac、json、os、secrets 与 typing.Mapping
 * [OUTPUT]: 对外提供 seal_credentials、reveal_credentials、rotate_credentials_seal、credentials_key_status、is_credentials_configured、CredentialsError
 * [POS]: services 的敏感配置边界，负责把 channel_account.credentials 从明文 JSON 变为可校验、可轮换的封存结构
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from typing import Any, Mapping


SEAL_VERSION = "closer.credentials.v1"
PREVIOUS_SECRETS_ENV = "CLOSER_CREDENTIALS_PREVIOUS_SECRETS"
DEV_CREDENTIALS_ENV = "CLOSER_ALLOW_DEV_CREDENTIALS"
_DEV_SECRET = "closer-local-dev-credentials-secret"


class CredentialsError(ValueError):
    pass


@dataclass(frozen=True)
class KeyMaterial:
    secret: str
    key: bytes
    key_id: str


def seal_credentials(credentials: Mapping[str, Any] | None) -> dict[str, str]:
    if not credentials:
        return {}
    if is_sealed_credentials(credentials):
        return dict(credentials)

    plaintext = json.dumps(credentials, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    material = _current_key_material()
    nonce = secrets.token_bytes(16)
    ciphertext = _xor(plaintext, _keystream(material.key, nonce, len(plaintext)))
    mac = _mac(material.key, nonce, ciphertext)
    return {
        "_sealed": SEAL_VERSION,
        "key_id": material.key_id,
        "nonce": _b64(nonce),
        "ciphertext": _b64(ciphertext),
        "mac": _b64(mac),
    }


def reveal_credentials(credentials: Mapping[str, Any] | None) -> dict[str, Any]:
    if not credentials:
        return {}
    if not is_sealed_credentials(credentials):
        return dict(credentials)

    nonce = _unb64(str(credentials.get("nonce", "")))
    ciphertext = _unb64(str(credentials.get("ciphertext", "")))
    expected_mac = _unb64(str(credentials.get("mac", "")))
    material = _verified_key_material(credentials, nonce, ciphertext, expected_mac)
    plaintext = _xor(ciphertext, _keystream(material.key, nonce, len(ciphertext)))
    try:
        decoded = json.loads(plaintext.decode())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CredentialsError("Credentials payload is invalid") from exc
    if not isinstance(decoded, dict):
        raise CredentialsError("Credentials payload must be an object")
    return decoded


def rotate_credentials_seal(credentials: Mapping[str, Any] | None) -> tuple[dict[str, str], bool]:
    if not credentials:
        return {}, False
    plaintext = reveal_credentials(credentials)
    if credentials_key_status(credentials) == "current":
        return dict(credentials), False
    return seal_credentials(plaintext), True


def credentials_key_status(credentials: Mapping[str, Any] | None) -> str:
    if not credentials:
        return "empty"
    if not is_sealed_credentials(credentials):
        return "plaintext"
    key_id = credentials.get("key_id")
    if key_id == _current_key_material().key_id:
        return "current"
    return "legacy"


def is_credentials_configured(credentials: Mapping[str, Any] | None) -> bool:
    if not credentials:
        return False
    if is_sealed_credentials(credentials):
        return bool(credentials.get("ciphertext"))
    return True


def is_sealed_credentials(credentials: Mapping[str, Any] | None) -> bool:
    return bool(credentials and credentials.get("_sealed") == SEAL_VERSION)


def _verified_key_material(
    credentials: Mapping[str, Any],
    nonce: bytes,
    ciphertext: bytes,
    expected_mac: bytes,
) -> KeyMaterial:
    key_id = credentials.get("key_id")
    for material in _key_candidates():
        if key_id and key_id != material.key_id:
            continue
        actual_mac = _mac(material.key, nonce, ciphertext)
        if hmac.compare_digest(actual_mac, expected_mac):
            return material
    if key_id:
        raise CredentialsError("Credentials seal key is not configured")
    for material in _key_candidates():
        actual_mac = _mac(material.key, nonce, ciphertext)
        if hmac.compare_digest(actual_mac, expected_mac):
            return material
    raise CredentialsError("Credentials seal verification failed")


def _current_key_material() -> KeyMaterial:
    secret = os.getenv("CLOSER_CREDENTIALS_SECRET")
    if not secret:
        if not _dev_credentials_enabled():
            raise CredentialsError("CLOSER_CREDENTIALS_SECRET is required")
        secret = _DEV_SECRET
    return _material(secret)


def _key_candidates() -> list[KeyMaterial]:
    secrets = [_current_key_material().secret]
    secrets.extend(_previous_secrets())
    unique = []
    for secret in secrets:
        if secret and secret not in unique:
            unique.append(secret)
    return [_material(secret) for secret in unique]


def _previous_secrets() -> list[str]:
    raw = os.getenv(PREVIOUS_SECRETS_ENV) or ""
    return [part.strip() for part in raw.split(",") if part.strip()]


def _material(secret: str) -> KeyMaterial:
    key = hashlib.sha256(secret.encode()).digest()
    key_id = hashlib.sha256((SEAL_VERSION + ":" + secret).encode()).hexdigest()[:16]
    return KeyMaterial(secret=secret, key=key, key_id=key_id)


def _dev_credentials_enabled() -> bool:
    return (os.getenv(DEV_CREDENTIALS_ENV) or "").strip().lower() in {"1", "true", "yes", "on"}


def _keystream(key: bytes, nonce: bytes, size: int) -> bytes:
    blocks = []
    counter = 0
    while sum(len(block) for block in blocks) < size:
        counter_bytes = counter.to_bytes(8, "big")
        blocks.append(hmac.new(key, nonce + counter_bytes, hashlib.sha256).digest())
        counter += 1
    return b"".join(blocks)[:size]


def _mac(key: bytes, nonce: bytes, ciphertext: bytes) -> bytes:
    return hmac.new(key, SEAL_VERSION.encode() + nonce + ciphertext, hashlib.sha256).digest()


def _xor(left: bytes, right: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right, strict=True))


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
