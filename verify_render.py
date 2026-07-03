"""P2.5 Markdown 渲染验证 — 直接调用 render 模块看输出。"""

import io
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))

from src.utils import render


SAMPLE = """# FSAR 测试

这是一个**Markdown**渲染测试。

## 功能列表

- ✅ 加粗、`行内代码`、多行代码块
- ✅ 列表、表格、链接
- ✅ 语法高亮（python）

## 代码示例

```python
def hello(name: str) -> str:
    return f"hello, {name}"

print(hello("FSAR"))
```

## 表格

| 工具 | 风险 | 模式 |
|------|------|------|
| web_search | SAFE | trust |
| run_command | HIGH | ask |
| file_ops | MEDIUM | mixed |

> 引用块也算。

[GitHub](https://github.com)
"""


def main():
    print("\n=== 1. md() 直接渲染 ===\n")
    render.md(SAMPLE)

    print("\n=== 2. say() FSAR 发言 ===\n")
    render.say(SAMPLE)

    print("\n=== 3. status + status_md ===\n")
    render.status("Tool", "run_command: {\"command\": \"dir\"}")
    render.status_md("Result", " Directory of C:\\\\Users\n\n```\nfoo.txt\nbar.txt\n```")

    print("\n=== 4. header / panel / code / warn ===\n")
    render.header("P2.5 渲染验证")
    render.code("def f(): return 42", "python")
    render.panel("这是一个面板", title="信息")
    render.warn("这是一个警告")
    render.ok("全部成功")

    print("\n=== 完成 ===")


if __name__ == "__main__":
    main()
