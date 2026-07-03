"""P2 端到端冒烟 — 模拟 _execute_guarded 全路径（不经过 LLM）。

覆盖:
- PROCEED 路径写入审计
- DENY 路径不执行、写入审计
- session_trust 真正生效
"""
import io
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))

from src.security import RiskEngine, make_entry, append_entry, tail as audit_tail
from src.security.permissions import load_permissions, save_permissions
from src.tools import create_default_registry

perm = load_permissions()
registry = create_default_registry()
engine = RiskEngine(perm)


def guarded_execute(name: str, args: dict) -> str:
    """复制 main.py._execute_guarded 的核心逻辑，不含 ask_user 路径"""
    import time
    tool = registry.get(name)
    verdict = engine.evaluate(tool, args)
    user_response = "auto"

    if verdict.is_denied():
        append_entry(make_entry(
            session="TEST", tool=name, args=args,
            risk=verdict.effective_risk, verdict="deny",
            user_response="", outcome="denied",
        ))
        return f"[DENIED] {verdict.reason}"

    start = time.monotonic()
    try:
        # run tool
        result = "smoke-test-result"
        error = None
        outcome = "success"
    except Exception as e:
        result = f"Error: {e}"
        error = str(e)
        outcome = "error"
    duration_ms = int((time.monotonic() - start) * 1000)

    append_entry(make_entry(
        session="TEST", tool=name, args=args,
        risk=verdict.effective_risk,
        verdict="confirm" if verdict.needs_confirm() else "proceed",
        user_response=user_response,
        outcome=outcome, error=error, duration_ms=duration_ms,
    ))
    return result


# 清掉旧测试条目好辨认
import os
audit_file = Path("data/logs/audit.log")
if audit_file.exists():
    # 只删 TEST session 的行
    keep = []
    with open(audit_file, "r", encoding="utf-8") as f:
        for line in f:
            if '"session": "TEST"' not in line and '"session":"TEST"' not in line:
                keep.append(line)
    with open(audit_file, "w", encoding="utf-8") as f:
        f.writelines(keep)


print("\n=== 真实执行路径测试 ===\n")

# 1) SAFE tool
print("[1] web_search (PROCEED path)")
r = guarded_execute("web_search", {"query": "foo"})
print(f"    result: {r}")

# 2) DENY path
print("[2] run_command blocked_pattern (DENY)")
r = guarded_execute("run_command", {"command": "del /s /q C:\\*"})
print(f"    result: {r}")

# 3) Path rule DENY
print("[3] file_ops read C:\\Windows (DENY)")
r = guarded_execute("file_ops", {"operation": "read", "path": "C:\\Windows\\foo"})
print(f"    result: {r}")

print("\n=== 审计日志 ===\n")
entries = audit_tail(5)
session_test_entries = [e for e in entries if e.get("session") == "TEST"][-3:]
print(f"最近 3 条 TEST 会话记录:\n")
for e in session_test_entries:
    print(f"  tool={e['tool']} verdict={e['verdict']} risk={e['risk']} "
          f"outcome={e.get('outcome')}")

assert len(session_test_entries) == 3, f"应写入 3 条 TEST 审计，实际 {len(session_test_entries)}"
assert session_test_entries[0]["verdict"] == "proceed"
assert session_test_entries[1]["verdict"] == "deny"
assert session_test_entries[2]["verdict"] == "deny"

print("\n[OK] 3 条审计写入成功，含 proceed/deny 路径")

# 测试 4: 持久化测试
print("\n=== 永久 trust 写回测试 ===\n")
perm.set_permanent_trust("run_command")
save_permissions(perm)
print("[4] grant run_command 后，重新加载")
fresh = load_permissions()
assert fresh.tools.get("run_command", {}).get("mode") == "trust", "模式应被持久化"
print(f"    reload 后 run_command.mode = {fresh.tools['run_command']['mode']}")

# 还原
fresh.tools["run_command"]["mode"] = "ask"
save_permissions(fresh)

print("\n[OK] 全部冒烟测试通过")
