"""
/* ========================================================================== */
/* GEB L3: 对象存储测试                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 pytest、tmp_path、monkeypatch、app.services.object_storage 的本地/远端对象存储边界
 * [OUTPUT]: 验证本地对象写入元数据、远端 HTTP PUT、storage config 与 unsafe storage key 拒绝
 * [POS]: tests 的文件产物存储证明文件，锁住业务服务与文件系统/远端对象存储之间的隔离边界
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

import pytest

from app.services.object_storage import HttpObjectStorage, LocalObjectStorage, get_document_storage_config


def test_local_object_storage_writes_bytes_and_metadata(tmp_path):
    storage = LocalObjectStorage(tmp_path)

    result = storage.put_bytes("seller_1/PI-000001.txt", b"PROFORMA INVOICE", "text/plain")

    assert result.backend == "local"
    assert result.filename == "PI-000001.txt"
    assert result.storage_key == "seller_1/PI-000001.txt"
    assert result.size == len(b"PROFORMA INVOICE")
    assert tmp_path.joinpath("seller_1", "PI-000001.txt").read_bytes() == b"PROFORMA INVOICE"
    assert result.metadata()["path"] == str(tmp_path.joinpath("seller_1", "PI-000001.txt"))


def test_local_object_storage_rejects_unsafe_keys(tmp_path):
    storage = LocalObjectStorage(tmp_path)

    for key in ["/seller_1/pi.txt", "../pi.txt", "seller_1/../pi.txt"]:
        with pytest.raises(ValueError, match="storage key"):
            storage.put_bytes(key, b"x", "text/plain")


def test_http_object_storage_puts_bytes_via_urlopen(monkeypatch):
    requests = []

    class FakeResponse:
        headers = {"Location": "https://storage.example/files/seller_1/PI-000001.txt"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return b"{}"

        def geturl(self):
            return "https://storage.example/files/seller_1/PI-000001.txt"

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr("app.services.object_storage.urlopen", fake_urlopen)

    storage = HttpObjectStorage(
        endpoint="https://storage.example/files/{key}",
        auth_token="token-123",
        timeout_seconds=3.5,
    )
    result = storage.put_bytes("seller_1/PI-000001.txt", b"PROFORMA INVOICE", "text/plain")

    request, timeout = requests[0]
    assert timeout == 3.5
    assert request.full_url == "https://storage.example/files/seller_1/PI-000001.txt"
    assert request.get_header("Authorization") == "Bearer token-123"
    assert request.get_header("Content-type") == "text/plain"
    assert result.backend == "http"
    assert result.url == "https://storage.example/files/seller_1/PI-000001.txt"
    assert result.metadata()["url"] == "https://storage.example/files/seller_1/PI-000001.txt"


def test_get_document_storage_config_reports_http_backend(monkeypatch):
    monkeypatch.setenv("CLOSER_DOCUMENT_STORAGE_BACKEND", "http")
    monkeypatch.setenv("CLOSER_DOCUMENT_STORAGE_ENDPOINT", "https://storage.example/files/{key}")
    monkeypatch.setenv("CLOSER_DOCUMENT_STORAGE_AUTH_TOKEN", "token-123")
    monkeypatch.setenv("CLOSER_DOCUMENT_STORAGE_TIMEOUT_SECONDS", "2.5")

    config = get_document_storage_config()

    assert config.status == "ok"
    assert config.details()["backend"] == "http"
    assert config.details()["endpoint"] == "https://storage.example/files/{key}"
    assert config.details()["auth_token_configured"] is True
