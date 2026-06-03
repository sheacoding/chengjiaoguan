"""
/* ========================================================================== */
/* GEB L3: Demo 脚本测试                                                      */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 subprocess、sys、json 与 scripts/demo_flow.py
 * [OUTPUT]: 验证 demo_flow dry-run 可输出确定性演示步骤且不访问网络
 * [POS]: tests 的演示脚本证明文件，锁住演示脚本不会绕过 API 或默认触发副作用
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "demo_flow.py"


def test_demo_flow_dry_run_lists_api_steps_without_network():
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dry-run",
            "--approve",
            "--run-workers",
            "--json",
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
    assert payload["headers"] == {"Authorization": "Bearer seller:7"}
    assert [step["name"] for step in payload["steps"]] == [
        "seed_demo",
        "approve_pending_message",
        "list_conversation_messages",
        "run_due_workers",
    ]
    assert payload["steps"][0]["url"].endswith("/api/v1/demo/seed")
    assert payload["steps"][1]["requires"] == "seed.approval.approval_id"
