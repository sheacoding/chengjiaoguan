"""
/* ========================================================================== */
/* GEB L3: 生产检查脚本测试                                                   */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 subprocess、sys、json 与 scripts/production_check.py
 * [OUTPUT]: 验证 production_check dry-run 输出部署检查步骤、保护 token 且默认不触发 scheduler
 * [POS]: tests 的生产彩排脚本证明文件，锁住部署检查只走公开 API 并避免默认副作用
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

import json
import importlib.util
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "production_check.py"


def test_production_check_dry_run_lists_read_only_steps_without_scheduler():
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dry-run",
            "--json",
            "--base-url",
            "https://closer.example",
            "--seller-id",
            "7",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)

    assert payload["dry_run"] is True
    assert payload["seller_id"] == 7
    assert payload["auth"] == {"mode": "seller_shortcut", "token_configured": False, "header": "Authorization"}
    assert [step["name"] for step in payload["steps"]] == ["health", "readiness", "alerts"]
    assert payload["steps"][0]["url"] == "https://closer.example/api/v1/health"


def test_production_check_dry_run_masks_token_and_requires_explicit_scheduler():
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dry-run",
            "--json",
            "--base-url",
            "https://closer.example",
            "--token",
            "cak_secret_value",
            "--run-scheduler",
            "--no-monitoring",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)

    assert "cak_secret_value" not in result.stdout
    assert payload["auth"] == {"mode": "api_key", "token_configured": True, "header": "Authorization"}
    assert [step["name"] for step in payload["steps"]] == ["health", "readiness", "alerts", "scheduler"]
    assert payload["steps"][-1]["method"] == "POST"
    assert payload["steps"][-1]["url"].endswith("/api/v1/ops/scheduler/run?emit_monitoring=false")


def test_production_check_deployment_status_maps_runtime_risk():
    module = _load_script()
    payload = {
        "checks": {
            "health": {"status": "ok"},
            "readiness": {"status": "ready"},
            "alerts": {"status": "ok"},
            "scheduler": {"status": "ok"},
        }
    }

    assert module.deployment_status(payload) == "passed"
    payload["checks"]["readiness"]["status"] = "degraded"
    assert module.deployment_status(payload) == "warning"
    payload["checks"]["readiness"]["status"] = "ready"
    payload["checks"]["alerts"]["status"] = "critical"
    assert module.deployment_status(payload) == "failed"
    payload["checks"]["health"]["status"] = "down"
    assert module.deployment_status(payload) == "failed"


def _load_script():
    spec = importlib.util.spec_from_file_location("production_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["production_check"] = module
    spec.loader.exec_module(module)
    return module
