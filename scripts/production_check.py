#!/usr/bin/env python3
"""
/* ========================================================================== */
/* GEB L3: 生产部署检查脚本                                                   */
/* ========================================================================== */
/**
 * [INPUT]: 依赖标准库 argparse/json/urllib 与已部署的 Closer HTTP API
 * [OUTPUT]: 对外提供 CLI，检查 health、readiness、alerts，并可显式触发 scheduler/monitoring 入口
 * [POS]: scripts 的生产彩排入口，只走公开 API，把部署前检查、告警读取和外部调度接线收束成一条路径
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
from urllib import error, parse, request


DEFAULT_BASE_URL = "http://127.0.0.1:8000"


@dataclass(frozen=True)
class CheckStep:
    name: str
    method: str
    path: str
    query: dict[str, Any] | None = None

    def url(self, base_url: str) -> str:
        url = f"{base_url.rstrip('/')}{self.path}"
        if not self.query:
            return url
        return f"{url}?{parse.urlencode(self.query)}"

    def preview(self, base_url: str) -> dict[str, Any]:
        return {"name": self.name, "method": self.method, "url": self.url(base_url)}


class ApiError(RuntimeError):
    def __init__(self, method: str, url: str, status: int | None, body: str):
        self.method = method
        self.url = url
        self.status = status
        self.body = body
        super().__init__(f"{method} {url} failed: {status or 'network_error'} {body}")


def check_steps(*, run_scheduler: bool, emit_monitoring: bool) -> list[CheckStep]:
    steps = [
        CheckStep("health", "GET", "/api/v1/health"),
        CheckStep("readiness", "GET", "/api/v1/ops/readiness"),
        CheckStep("alerts", "GET", "/api/v1/ops/alerts"),
    ]
    if run_scheduler:
        steps.append(
            CheckStep(
                "scheduler",
                "POST",
                "/api/v1/ops/scheduler/run",
                {"emit_monitoring": str(emit_monitoring).lower()},
            )
        )
    return steps


def dry_run_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "dry_run": True,
        "base_url": args.base_url.rstrip("/"),
        "seller_id": args.seller_id,
        "auth": _auth_preview(args),
        "steps": [
            step.preview(args.base_url)
            for step in check_steps(run_scheduler=args.run_scheduler, emit_monitoring=args.emit_monitoring)
        ],
    }


def api_request(
    *,
    base_url: str,
    headers: dict[str, str],
    method: str,
    path: str,
    query: dict[str, Any] | None,
    timeout: float,
) -> dict[str, Any]:
    url = CheckStep("", method, path, query).url(base_url)
    req = request.Request(url, headers=headers, method=method)
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
    headers = _auth_headers(args)
    results: dict[str, Any] = {
        "dry_run": False,
        "base_url": args.base_url.rstrip("/"),
        "seller_id": args.seller_id,
        "auth": _auth_preview(args),
        "checks": {},
    }
    for step in check_steps(run_scheduler=args.run_scheduler, emit_monitoring=args.emit_monitoring):
        results["checks"][step.name] = api_request(
            base_url=args.base_url,
            headers=headers,
            method=step.method,
            path=step.path,
            query=step.query,
            timeout=args.timeout,
        )
    results["status"] = deployment_status(results)
    return results


def deployment_status(payload: dict[str, Any]) -> str:
    checks = payload.get("checks") or {}
    if (checks.get("health") or {}).get("status") != "ok":
        return "failed"
    readiness = (checks.get("readiness") or {}).get("status")
    alerts = (checks.get("alerts") or {}).get("status")
    scheduler = (checks.get("scheduler") or {}).get("status")
    if readiness == "unready" or alerts == "critical" or scheduler == "critical":
        return "failed"
    if readiness == "degraded" or alerts == "attention" or scheduler == "attention":
        return "warning"
    return "passed"


def print_human_summary(payload: dict[str, Any]) -> None:
    print(f"Production check for seller {payload.get('seller_id')} at {payload.get('base_url')}")
    print(f"Status: {payload.get('status', 'dry-run')}")
    checks = payload.get("checks") or {}
    for name in ["health", "readiness", "alerts", "scheduler"]:
        if name not in checks:
            continue
        item = checks[name]
        print(f"{name}: {item.get('status', 'ok')}")
        if name == "readiness":
            print(f"  summary: {json.dumps(item.get('summary') or {}, sort_keys=True)}")
        if name == "alerts":
            print(f"  total: {item.get('total', 0)} counts={json.dumps(item.get('counts') or {}, sort_keys=True)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check a Closer deployment through public HTTP APIs.")
    parser.add_argument("--base-url", default=os.environ.get("CLOSER_PRODUCTION_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--seller-id", type=int, default=int(os.environ.get("CLOSER_PRODUCTION_SELLER_ID", "1")))
    parser.add_argument("--token", default=os.environ.get("CLOSER_PRODUCTION_TOKEN"))
    parser.add_argument("--run-scheduler", action="store_true", help="Call /ops/scheduler/run; this may run due jobs.")
    parser.add_argument("--no-monitoring", action="store_false", dest="emit_monitoring", help="Skip scheduler monitoring emit.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned HTTP calls without contacting the API.")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Print JSON output.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on warnings as well as failures.")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.set_defaults(emit_monitoring=True)
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
        print_human_summary(payload)
    status = payload.get("status")
    if status == "failed" or (args.strict and status == "warning"):
        return 1
    return 0


def _auth_headers(args: argparse.Namespace) -> dict[str, str]:
    token = _clean(args.token)
    bearer = token if token and token.lower().startswith("bearer ") else f"Bearer {token}" if token else f"Bearer seller:{args.seller_id}"
    return {"Accept": "application/json", "Authorization": bearer}


def _auth_preview(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "mode": "api_key" if _clean(args.token) else "seller_shortcut",
        "token_configured": bool(_clean(args.token)),
        "header": "Authorization",
    }


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


if __name__ == "__main__":
    raise SystemExit(main())
