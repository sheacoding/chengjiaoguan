# Closer Backend Collaboration Guide

## Project

Closer is a cross-border B2B AI inquiry closing agent for small exporters. The MVP backend must support this demo path:

1. Inbound inquiry enters through a channel adapter.
2. The system creates or links a customer, inquiry, conversation, and first message.
3. The inquiry is scored as grade A/B/C with explainable signals.
4. Product and knowledge matches ground the reply.
5. The quote engine creates a structured quotation from pricing rules.
6. Floor-price and sensitive-action guardrails create an approval instead of sending unsafe content.
7. A human can review, edit, approve, reject, take over, release, and send.
8. Follow-up tasks keep unreplied inquiries moving.

## Ownership

Role A owns the backend-heavy vertical from the schedule:

- Channel gateway and adapters: site form, email IMAP/SMTP, WhatsApp Cloud API.
- Inquiry scoring and CRM creation.
- Inquiry, conversation, message, takeover, and release APIs.
- Quote engine, quote tools, and PI generation.
- Knowledge ingestion, lightweight RAG search, and product matching.
- `send_message` tool with approval handoff when guardrails trigger.
- Approvals, quotations, and follow-up APIs/tools assigned to A in the balanced plan.

Role B owns the separate Agent orchestration skeleton and global guardrail policy. Keep A-owned tool signatures stable so B can call them from PydanticAI.

## Engineering Rules

- Backend stack: Python, FastAPI, SQLAlchemy, Pydantic, PostgreSQL/pgvector in production, SQLite for local tests.
- Keep API responses aligned with the Backend API Contract under `/api/v1`.
- Enforce tenant isolation by `seller_id`; tests may use `X-Seller-Id: 1`.
- Store money as `Decimal` in services and database models.
- Use deterministic services in tests; do not call real LLMs, IMAP, SMTP, or WhatsApp APIs in unit tests.
- Every completed schedule task must include focused tests and a commit after tests pass.
- Do not commit generated caches, local databases, secrets, or `tmp/`.

## Verification

Use the bundled Python runtime or any Python 3.12 environment:

```powershell
python -m pip install -e .[dev]
python -m pytest
```

For demo development, start the API with:

```powershell
uvicorn app.main:app --reload
```

## API Contract Defaults

- Base path: `/api/v1`
- Auth shortcut for MVP/tests: `X-Seller-Id` header, defaulting to seller `1`.
- Error shape: `{ "error": { "code": "...", "message": "..." } }`
- Pagination shape: `{ "items": [...], "total": n, "page": n, "page_size": n }`

