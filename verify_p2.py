"""P2 安全层手动验证 — 不依赖 LLM，直接调用 RiskEngine。

覆盖:
1. SAFE 工具静默 PROCEED
2. HIGH 工具 → CONFIRM
3. blocked_patterns → DENY
4. path_rules → DENY
5. mode=trust → CONFIRM 变 PROCEED
6. session_trust → CONFIRM 变 PROCEED
7. session_deny → DENY
8. file_ops.read (yaml 配 trust) → PROCEED
9. file_ops.delete (yaml 配 ask) → CONFIRM
"""
import io
import sys
from pathlib import Path

# Force UTF-8 on Windows console (default GBK fails on unicode symbols)
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))

from src.security import load_permissions, RiskEngine
from src.tools import create_default_registry


def make_args(**kw):
    return kw


def banner(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print('='*60)


def show(label, verdict):
    print(f"  {label:40s} → {verdict.action:8s} ({verdict.rule_matched})  [{verdict.effective_risk}]")
    return verdict


def main():
    print("FSAR P2 安全层验证")
    print()

    perm = load_permissions()
    registry = create_default_registry()
    engine = RiskEngine(perm)

    results = []

    banner("场景 1: SAFE 工具 (web_search)")
    t = registry.get("web_search")
    v = engine.evaluate(t, {"query": "今天天气"})
    r = show("查询天气 → 应 PROCEED", v)
    results.append(("web_search PROCEED", r.action == "proceed"))

    banner("场景 2: HIGH 工具 (run_command, 安全命令)")
    t = registry.get("run_command")
    v = engine.evaluate(t, {"command": "dir", "shell": "powershell"})
    r = show("dir 命令 → 应 CONFIRM (ask mode)", v)
    results.append(("run_command dir CONFIRM", r.action == "confirm"))

    banner("场景 3: blocked_pattern 命中")
    t = registry.get("run_command")
    v = engine.evaluate(t, {"command": "rm -rf /tmp", "shell": "bash"})
    r = show("rm -rf / → 应 DENY", v)
    results.append(("rm -rf DENY", r.action == "deny"))

    banner("场景 4: path_rule 命中 (C:\\Windows)")
    t = registry.get("file_ops")
    v = engine.evaluate(t, {"operation": "read", "path": "C:\\Windows\\System32\\drivers\\etc\\hosts"})
    r = show("读 Windows 路径 → 应 DENY", v)
    results.append(("Windows path DENY", r.action == "deny"))

    banner("场景 5: path_rule 删除 C:\\ 根目录")
    t = registry.get("file_ops")
    v = engine.evaluate(t, {"operation": "delete", "path": "C:\\"})
    r = show("删 C:\\ → 应 DENY (path_rule)", v)
    results.append(("delete C:\\ DENY", r.action == "deny"))

    banner("场景 6: file_ops.read (yaml 配 trust) → PROCEED")
    t = registry.get("file_ops")
    v = engine.evaluate(t, {"operation": "read", "path": "C:\\Users\\test\\file.txt"})
    r = show("读普通文件 → 应 PROCEED", v)
    results.append(("file_ops.read PROCEED", r.action == "proceed"))

    banner("场景 7: file_ops.delete (yaml 配 ask) → CONFIRM")
    t = registry.get("file_ops")
    v = engine.evaluate(t, {"operation": "delete", "path": "C:\\Users\\test\\junk.txt"})
    r = show("删除文件 → 应 CONFIRM", v)
    results.append(("file_ops.delete CONFIRM", r.action == "confirm"))

    banner("场景 8: session_trust 覆盖 CONFIRM → PROCEED")
    perm.set_session_trust("run_command")
    t = registry.get("run_command")
    v = engine.evaluate(t, {"command": "echo hello", "shell": "powershell"})
    r = show("session trust run_command → 应 PROCEED", v)
    results.append(("session_trust PROCEED", r.action == "proceed"))
    perm.clear_session()

    banner("场景 9: session_deny → 任何 run_command → DENY")
    perm.set_session_deny("run_command")
    t = registry.get("run_command")
    v = engine.evaluate(t, {"command": "echo hello", "shell": "powershell"})
    r = show("session deny run_command → 应 DENY", v)
    results.append(("session_deny DENY", r.action == "deny"))
    perm.clear_session()

    banner("场景 10: mode=trust → app_control 不再 CONFIRM")
    perm.mode = "trust"
    t = registry.get("app_control")
    v = engine.evaluate(t, {"target": "notepad"})
    r = show("mode=trust, 开 notepad → 应 PROCEED (LOW 工具)", v)
    # app_control risk=LOW, mode=ask; trust mode 下: risk<CRITICAL threshold → proceed
    results.append(("mode=trust LOW PROCEED", r.action == "proceed"))
    perm.mode = "normal"

    banner("场景 11: app_control 在 strict mode 下 → CONFIRM")
    perm.mode = "strict"
    t = registry.get("app_control")
    v = engine.evaluate(t, {"target": "notepad"})
    r = show("mode=strict, 开 notepad → 应 CONFIRM (LOW > threshold)", v)
    results.append(("mode=strict LOW CONFIRM", r.action == "confirm"))
    perm.mode = "normal"

    banner("场景 12: edit 工具 → CONFIRM")
    t = registry.get("edit")
    v = engine.evaluate(t, {"file_path": "C:\\foo.txt", "old_text": "a", "new_text": "b"})
    r = show("edit 任意文件 → 应 CONFIRM (ask mode)", v)
    results.append(("edit CONFIRM", r.action == "confirm"))

    # 汇总
    banner("汇总")
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"\n  {passed}/{total} 通过\n")
    for label, ok in results:
        print(f"  {'✓' if ok else '✗'} {label}")

    print()
    if passed == total:
        print("🎉 全部通过")
        return 0
    print(f"❌ {total - passed} 项失败")
    return 1


if __name__ == "__main__":
    sys.exit(main())
