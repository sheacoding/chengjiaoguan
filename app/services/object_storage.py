"""
/* ========================================================================== */
/* GEB L3: 对象存储边界                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 os、json、pathlib、urllib、dataclass 与二进制对象内容
 * [OUTPUT]: 对外提供 StoredObject、ObjectStorage、ObjectStorageConfig、LocalObjectStorage、HttpObjectStorage、document_storage、get_document_storage_config、store_document_object
 * [POS]: services 的文件产物存储边界，把业务服务从本地文件系统与远端对象存储细节中解耦
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol
from urllib.request import Request, urlopen


DEFAULT_DOCUMENT_DIR = "tmp/pi_documents"
DOCUMENT_STORAGE_BACKEND_ENV = "CLOSER_DOCUMENT_STORAGE_BACKEND"
DOCUMENT_STORAGE_ENDPOINT_ENV = "CLOSER_DOCUMENT_STORAGE_ENDPOINT"
DOCUMENT_STORAGE_AUTH_TOKEN_ENV = "CLOSER_DOCUMENT_STORAGE_AUTH_TOKEN"
DOCUMENT_STORAGE_TIMEOUT_ENV = "CLOSER_DOCUMENT_STORAGE_TIMEOUT_SECONDS"
LOCAL_BACKEND = "local"
HTTP_BACKEND_ALIASES = {"http", "remote", "remote_http", "s3", "r2", "oss"}


@dataclass(frozen=True)
class StoredObject:
    storage_key: str
    filename: str
    mime_type: str
    size: int
    backend: str
    path: str | None = None
    url: str | None = None

    def metadata(self) -> dict[str, str | int | None]:
        data: dict[str, str | int | None] = {
            "filename": self.filename,
            "storage_key": self.storage_key,
            "mime_type": self.mime_type,
            "size": self.size,
            "backend": self.backend,
        }
        if self.path is not None:
            data["path"] = self.path
        if self.url is not None:
            data["url"] = self.url
        return data


@dataclass(frozen=True)
class ObjectStorageConfig:
    backend: str
    root: str | None
    endpoint: str | None
    auth_token_configured: bool
    timeout_seconds: float | None
    status: str
    message: str

    def details(self) -> dict[str, str | float | bool | None]:
        return {
            "backend": self.backend,
            "root": self.root,
            "endpoint": self.endpoint,
            "auth_token_configured": self.auth_token_configured,
            "timeout_seconds": self.timeout_seconds,
        }


class ObjectStorage(Protocol):
    backend: str

    def put_bytes(self, key: str, content: bytes, mime_type: str) -> StoredObject:
        raise NotImplementedError


@dataclass(frozen=True)
class LocalObjectStorage:
    root: Path
    backend: str = "local"

    def put_bytes(self, key: str, content: bytes, mime_type: str) -> StoredObject:
        safe_key = _safe_key(key)
        path = self.root / Path(*PurePosixPath(safe_key).parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return StoredObject(
            storage_key=safe_key,
            filename=path.name,
            mime_type=mime_type,
            size=path.stat().st_size,
            backend=self.backend,
            path=str(path),
        )


@dataclass(frozen=True)
class HttpObjectStorage:
    endpoint: str
    auth_token: str | None = None
    timeout_seconds: float = 10.0
    backend: str = "http"

    def put_bytes(self, key: str, content: bytes, mime_type: str) -> StoredObject:
        safe_key = _safe_key(key)
        url = _render_endpoint(self.endpoint, safe_key)
        headers = {"Content-Type": mime_type}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        request = Request(url, data=content, headers=headers, method="PUT")
        with urlopen(request, timeout=self.timeout_seconds) as response:
            response_url = _response_url(response, url)
            response.read()
        return StoredObject(
            storage_key=safe_key,
            filename=Path(safe_key).name,
            mime_type=mime_type,
            size=len(content),
            backend=self.backend,
            url=response_url,
        )


def document_storage(env: dict[str, str] | None = None) -> ObjectStorage:
    env = env or os.environ
    backend = _backend(env)
    if backend == LOCAL_BACKEND:
        return LocalObjectStorage(Path(_local_root(env)))
    if backend == "http":
        endpoint = _clean(env.get(DOCUMENT_STORAGE_ENDPOINT_ENV))
        if endpoint is None:
            raise ValueError("CLOSER_DOCUMENT_STORAGE_ENDPOINT is required for remote object storage")
        return HttpObjectStorage(
            endpoint=endpoint,
            auth_token=_clean(env.get(DOCUMENT_STORAGE_AUTH_TOKEN_ENV)),
            timeout_seconds=_timeout_seconds(env),
        )
    raise ValueError(f"Unsupported document storage backend: {backend}")


def get_document_storage_config(env: dict[str, str] | None = None) -> ObjectStorageConfig:
    env = env or os.environ
    backend = _backend(env)
    if backend == LOCAL_BACKEND:
        root = _local_root(env)
        if root == DEFAULT_DOCUMENT_DIR:
            return ObjectStorageConfig(
                backend=LOCAL_BACKEND,
                root=root,
                endpoint=None,
                auth_token_configured=False,
                timeout_seconds=None,
                status="warning",
                message="Document storage uses the default tmp path",
            )
        return ObjectStorageConfig(
            backend=LOCAL_BACKEND,
            root=root,
            endpoint=None,
            auth_token_configured=False,
            timeout_seconds=None,
            status="ok",
            message="Document storage path is configured",
        )
    if backend == "http":
        endpoint = _clean(env.get(DOCUMENT_STORAGE_ENDPOINT_ENV))
        timeout_seconds = _timeout_seconds(env)
        if endpoint is None:
            return ObjectStorageConfig(
                backend="http",
                root=None,
                endpoint=None,
                auth_token_configured=bool(_clean(env.get(DOCUMENT_STORAGE_AUTH_TOKEN_ENV))),
                timeout_seconds=timeout_seconds,
                status="failed",
                message="CLOSER_DOCUMENT_STORAGE_ENDPOINT is required for remote object storage",
            )
        return ObjectStorageConfig(
            backend="http",
            root=None,
            endpoint=endpoint,
            auth_token_configured=bool(_clean(env.get(DOCUMENT_STORAGE_AUTH_TOKEN_ENV))),
            timeout_seconds=timeout_seconds,
            status="ok",
            message="Remote document storage backend is configured",
        )
    return ObjectStorageConfig(
        backend=backend,
        root=None,
        endpoint=None,
        auth_token_configured=bool(_clean(env.get(DOCUMENT_STORAGE_AUTH_TOKEN_ENV))),
        timeout_seconds=None,
        status="failed",
        message=f"Unsupported document storage backend: {backend}",
    )


def store_document_object(key: str, content: bytes, mime_type: str) -> dict[str, str | int | None]:
    return document_storage().put_bytes(key, content, mime_type).metadata()


def _safe_key(key: str) -> str:
    path = PurePosixPath(key)
    if path.is_absolute():
        raise ValueError("storage key must be relative")
    parts = path.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("storage key contains an unsafe path segment")
    return str(path)


def _backend(env: dict[str, str]) -> str:
    value = _clean(env.get(DOCUMENT_STORAGE_BACKEND_ENV)) or LOCAL_BACKEND
    backend = value.lower()
    if backend in HTTP_BACKEND_ALIASES:
        return "http"
    return backend


def _local_root(env: dict[str, str]) -> str:
    return _clean(env.get("CLOSER_DOCUMENT_STORAGE_DIR")) or DEFAULT_DOCUMENT_DIR


def _timeout_seconds(env: dict[str, str]) -> float:
    value = _clean(env.get(DOCUMENT_STORAGE_TIMEOUT_ENV))
    if value is None:
        return 10.0
    timeout = float(value)
    if timeout <= 0:
        raise ValueError("Document storage timeout must be positive")
    return timeout


def _render_endpoint(endpoint: str, key: str) -> str:
    if "{key}" in endpoint:
        return endpoint.format(key=key)
    if endpoint.endswith("/"):
        return f"{endpoint}{key}"
    return f"{endpoint}/{key}"


def _response_url(response, fallback: str) -> str:
    if hasattr(response, "geturl"):
        response_url = response.geturl()
        if response_url:
            return str(response_url)
    headers = getattr(response, "headers", None)
    if headers is not None:
        location = headers.get("Location")
        if location:
            return str(location)
    body = getattr(response, "read", None)
    if callable(body):
        try:
            payload = json.loads(body().decode("utf-8"))
        except Exception:
            return fallback
        if isinstance(payload, dict):
            url = payload.get("url") or payload.get("location")
            if url:
                return str(url)
    return fallback


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None
