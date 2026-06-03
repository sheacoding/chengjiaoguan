#!/usr/bin/env python3
"""
/* ========================================================================== */
/* GEB L3: Demo 主链路脚本                                                    */
/* ========================================================================== */
/**
 * [INPUT]: 依赖标准库 argparse/json/urllib 与正在运行的 Closer HTTP API
 * [OUTPUT]: 对外提供 CLI，编排 /demo/seed、approval approve、messages 与 workers run-due
 * [POS]: scripts 的演示入口，只走公开 API，不绕过后端服务、护栏和租户鉴权
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any
from urllib import error, request


DEFAULT_BASE_URL = "http://127.0.0.1:8000"


@dataclass(frozen=True)
class DemoStep:
    name: str
    method: str
    path: str
    body: dict[str, Any] | None = None
    requires: str | None = None

    def preview(self, base_url: str) -> dict[str, Any]:
        item: dict[str, Any] = {
            "name": self.name,
            "method": self.method,
            "url": f"{base_url.rstrip('/')}{self.path}",
        }
        if self.body is not None:
            item["body"] = self.body
        if self.requires is not None:
            item["requires"] = self.requires
        return item


class ApiError(RuntimeError):
    def __init__(self, method: str, url: str, status: int | None, body: str):
        self.method = method
        self.url = url
        self.status = status
        self.body = body
        super().__init__(f"{method} {url} failed: {status or 'network_error'} {body}")


def demo_steps(*, approve: bool, run_workers: bool) -> list[DemoStep]:
    steps = [DemoStep("seed_demo", "POST", "/api/v1/demo/seed")]
    if approve:
        steps.extend(
            [
                DemoStep(
                    "approve_pending_message",
                    "POST",
                    "/api/v1/approvals/{approval_id}/approve",
                    requires="seed.approval.approval_id",
                ),
                DemoStep(
                    "list_conversation_messages",
                    "GET",
                    "/api/v1/conversations/{conversation_id}/messages",
                    requires="seed.conversation_id",
                ),
            ]
        )
    if run_workers:
        steps.append(DemoStep("run_due_workers", "POST", "/api/v1/workers/run-due"))
    return steps


def dry_run_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "dry_run": True,
        "base_url": args.base_url.rstrip("/"),
        "seller_id": args.seller_id,
        "headers": {"Authorization": f"Bearer seller:{args.seller_id}"},
        "steps": [step.preview(args.base_url) for step in demo_steps(approve=args.approve, run_workers=args.run_workers)],
    }


def api_request(
    *,
    base_url: str,
    seller_id: int,
    method: str,
    path: str,
    timeout: float,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer seller:{seller_id}",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise ApiError(method, url, exc.code, raw) from exc
    except error.URLError as exc:
        raise ApiError(method, url, None, str(exc.reason)) from exc


def run_live(args: argparse.Namespace) -> dict[str, Any]:
    result: dict[str, Any] = {"base_url": args.base_url.rstrip("/"), "seller_id": args.seller_id}
    seed = api_request(
        base_url=args.base_url,
        seller_id=args.seller_id,
        method="POST",
        path="/api/v1/demo/seed",
        timeout=args.timeout,
    )
    result["seed"] = seed
    if args.approve:
        approval_id = ((seed.get("approval") or {}).get("approval_id"))
        if approval_id is None:
            raise ApiError("POST", "/api/v1/approvals/{approval_id}/approve", None, "seed returned no approval_id")
        result["approval"] = api_request(
            base_url=args.base_url,
            seller_id=args.seller_id,
            method="POST",
            path=f"/api/v1/approvals/{approval_id}/approve",
            timeout=args.timeout,
        )
        conversation_id = seed.get("conversation_id")
        if conversation_id is not None:
            result["messages"] = api_request(
                base_url=args.base_url,
                seller_id=args.seller_id,
                method="GET",
                path=f"/api/v1/conversations/{conversation_id}/messages",
                timeout=args.timeout,
            )
    if args.run_workers:
        result["workers"] = api_request(
            base_url=args.base_url,
            seller_id=args.seller_id,
            method="POST",
            path="/api/v1/workers/run-due",
            timeout=args.timeout,
        )
    return result


def print_human_summary(payload: dict[str, Any], *, approve: bool, run_workers: bool) -> None:
    seed = payload.get("seed") or {}
    approval = seed.get("approval") or {}
    print(f"Demo seeded for seller {payload.get('seller_id')} at {payload.get('base_url')}")
    print(f"Inquiry #{seed.get('inquiry_id')} conversation #{seed.get('conversation_id')}")
    print(f"Score: {(seed.get('score') or {}).get('grade')} quotation #{(seed.get('quotation') or {}).get('quotation_id')}")
    print(f"Approval: {approval.get('status')} #{approval.get('approval_id')} reason={approval.get('reason')}")
    if not approve:
        print("Next: rerun with --approve to execute the pending message_send approval.")
    if approve:
        executed = payload.get("approval") or {}
        print(f"Approved: {executed.get('status')} executed={executed.get('executed')}")
        messages = payload.get("messages") or {}
        print(f"Messages: {messages.get('total', 0)}")
    if run_workers:
        workers = payload.get("workers") or {}
        print(f"Workers: {workers.get('status', 'ok')}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed and optionally execute the Closer demo main flow.")
    parser.add_argument("--base-url", default=os.environ.get("CLOSER_DEMO_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--seller-id", type=int, default=1)
    parser.add_argument("--approve", action="store_true", help="Approve the pending demo message_send approval.")
    parser.add_argument("--run-workers", action="store_true", help="Run due workers after the demo steps.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned HTTP calls without contacting the API.")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Print JSON output.")
    parser.add_argument("--timeout", type=float, default=10.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = dry_run_payload(args) if args.dry_run else run_live(args)
    except ApiError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.json_output or args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_human_summary(payload, approve=args.approve, run_workers=args.run_workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
