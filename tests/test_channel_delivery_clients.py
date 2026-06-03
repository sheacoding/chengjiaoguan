"""
/* ========================================================================== */
/* GEB L3: 出站渠道客户端测试                                                 */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 pytest、json 与 app.services.channel_delivery_clients 的 payload-only、SMTP、WhatsApp 客户端
 * [OUTPUT]: 验证默认 payload-only 不触网、SMTP 客户端组合邮件、WhatsApp Cloud 客户端组合 HTTP 请求
 * [POS]: tests 的外部发送客户端边界证明文件，锁住真实渠道实发能力与确定性测试隔离
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

import json

from app.services import channel_delivery_clients as clients


def test_payload_only_delivery_client_queues_without_network():
    result = clients.PayloadOnlyDeliveryClient().send({"body": "hello"}, {})

    assert result == {"status": "queued", "client": "payload_only", "provider_message_id": None}


def test_smtp_delivery_client_sends_email_with_credentials(monkeypatch):
    sent_messages = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            self.host = host
            self.port = port
            self.timeout = timeout
            self.logged_in = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def login(self, username, password):
            self.logged_in = (username, password)

        def send_message(self, message):
            sent_messages.append((self, message))

    monkeypatch.setattr(clients.smtplib, "SMTP_SSL", FakeSMTP)

    result = clients.SmtpDeliveryClient().send(
        {
            "from": "sales@example.com",
            "to": "buyer@example.com",
            "subject": "Quote",
            "message_id": "closer:email:out:1",
            "body": "Thanks for your inquiry.",
        },
        {"host": "smtp.example.com", "port": 465, "username": "sales", "password": "secret"},
    )

    smtp, message = sent_messages[0]
    assert result == {"status": "sent", "client": "smtp", "provider_message_id": "closer:email:out:1"}
    assert smtp.host == "smtp.example.com"
    assert smtp.logged_in == ("sales", "secret")
    assert message["To"] == "buyer@example.com"
    assert "Thanks for your inquiry" in message.get_content()


def test_whatsapp_cloud_delivery_client_sends_http_request(monkeypatch):
    requests = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return json.dumps({"messages": [{"id": "wamid.out.1"}]}).encode()

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr(clients, "urlopen", fake_urlopen)

    payload = {"messaging_product": "whatsapp", "to": "15551234567", "type": "text", "text": {"body": "Hello"}}
    result = clients.WhatsAppCloudDeliveryClient().send(
        payload,
        {"access_token": "token-123", "phone_number_id": "phone-1", "api_version": "v20.0"},
    )

    request, timeout = requests[0]
    assert result["status"] == "sent"
    assert result["client"] == "whatsapp_cloud"
    assert result["provider_message_id"] == "wamid.out.1"
    assert timeout == 10.0
    assert request.full_url == "https://graph.facebook.com/v20.0/phone-1/messages"
    assert request.get_header("Authorization") == "Bearer token-123"
    assert json.loads(request.data.decode()) == payload
