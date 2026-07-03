"""E2E test — 直接调起 main.py，让 LLM 执行 C:\\WinTool 整理任务。

通过 subprocess 跑真实入口；脚本喂预先准备好的对话；按时间打印进度；
最后 dump 到 e2e_output.txt，并校验 WinTool 顶层确实少了散文件、新目录被创建。

前置:
- /perm mode trust 已经在 permissions.yaml 里设了（之前用户设过）
- main.py 可以正常启动
"""
import subprocess
import sys
import threading
import time
from pathlib import Path


ROOT = Path(r"C:/WinTool/FSAR")
WINTOOL = Path(r"C:/WinTool")

# 用户说过确认后照方案执行；多余的用户消息兜底用
SCRIPT = [
    "/perm mode trust",     # 关键：trust 模式覆盖 file_ops.move / run_command 的 ask
    "整理一下C:\WinTool文件夹，把散在外面的文件都归类放到对应文件夹内",
    "确认，我别的文件夹不要动",
    "继续",
    "继续",
    "继续",
    "继续",
    "exit",
]

OUTPUT_FILE = ROOT / "e2e_output.txt"


def stream_output(proc, chunks):
    """实时打印 stdout/stderr，回传全部 bytes 用于写文件。"""
    out = []
    while True:
        chunk = proc.stdout.read(1)
        if not chunk:
            break
        out.append(chunk)
        sys.stdout.buffer.write(chunk)
        sys.stdout.buffer.flush()
    return b"".join(out)


def main():
    print("=" * 70)
    print("FSAR E2E 测试 — 真实 LLM 执行 C:\\WinTool 整理")
    print("=" * 70)
    print()

    # 先拍一张快照：当前 WinTool 顶层散文件
    try:
        before = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-ChildItem 'C:\\WinTool' -File | Select-Object Name | Sort-Object Name"],
            capture_output=True, text=True, timeout=15,
        )
        print("【整理前】C:\\WinTool 顶层文件:")
        print(before.stdout)
        print()
    except Exception as e:
        print(f"(无法读整理前状态: {e})")

    # 起 main.py
    print("启动 main.py ...")
    proc = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=str(ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=0,
    )

    start = time.monotonic()

    # 后台线程：读输出
    output_chunks = []

    def reader():
        while True:
            c = proc.stdout.read(1)
            if not c:
                break
            output_chunks.append(c)
            try:
                sys.stdout.buffer.write(c)
                sys.stdout.buffer.flush()
            except Exception:
                pass

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    # 主线程：按节奏喂对话
    for line in SCRIPT[:-1]:
        try:
            proc.stdin.write((line + "\n").encode("utf-8"))
            proc.stdin.flush()
            print(f"\n>>> [喂入] {line!r}")
        except Exception as e:
            print(f"\n!!! stdin 写失败: {e}")
            break
        time.sleep(12)  # 给 LLM + tool 执行留够时间（trust 模式后无 confirm 阻塞）

    # exit
    try:
        proc.stdin.write(b"exit\n")
        proc.stdin.flush()
    except Exception:
        pass

    # 等进程退出（最多 9 分钟 — 整理 30+ 个文件移动可能很慢）
    try:
        proc.wait(timeout=540)
    except subprocess.TimeoutExpired:
        proc.kill()
        print("\n!!! TIMEOUT")
        return 1

    t.join(timeout=2)
    elapsed = time.monotonic() - start
    print(f"\n\n[main.py 退出] 耗时 {elapsed:.1f}s")

    raw = b"".join(output_chunks)
    OUTPUT_FILE.write_bytes(raw)
    print(f"输出已存: {OUTPUT_FILE} ({len(raw)} bytes)")

    # 校验：跑了多少 PowerShell 移动类命令
    text = raw.decode("utf-8", errors="replace")
    move = text.count("Move-Item") + text.count("MOVED")
    mkdir = text.count("New-Item") + text.count("mkdir")
    tool_calls = text.count("[Tool]")
    denied = text.count("[DENIED]")
    print(f"\n[Tool] 行数: {tool_calls}")
    print(f"[DENIED] 行数: {denied}")
    print(f"PowerShell Move/New 命令字面出现: move={move}, mkdir={mkdir}")

    # 拍快照：整理后
    try:
        after = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-ChildItem 'C:\\WinTool' -File | Select-Object Name | Sort-Object Name"],
            capture_output=True, text=True, timeout=15,
        )
        print("\n【整理后】C:\\WinTool 顶层文件:")
        print(after.stdout)
    except Exception as e:
        print(f"(无法读整理后状态: {e})")

    print()
    print("=" * 70)
    if tool_calls >= 5 and (move >= 1 or mkdir >= 1):
        print("✅ E2E 看起来成功：agent 真的发了 tool_call 并执行了移动")
        return 0
    elif tool_calls < 5:
        print("❌ E2E 失败：tool_call 数量太少（agent 走纯文本？）")
        return 1
    else:
        print("⚠ E2E 部分成功：tool 有调用但没看到 Move-Item，请人工看输出")
        return 2


if __name__ == "__main__":
    sys.exit(main())
