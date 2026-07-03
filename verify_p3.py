"""FSAR P3 验证脚本 — Memory System.

覆盖:
1. LongTermMemory 返回 msg_id（评分系统依赖）
2. UserModel: preferences / patterns / profile CRUD
3. FeedbackStore: 评分 CRUD + 统计 + 高/低分查询
4. SemanticMemory: 添加 + 搜索（chroma 不可用时降级）
5. MemoryRecall: 拼 context 文本
6. IdleReflector: 规则版复盘（不依赖 LLM）
7. main.FSAR: 集成（实例化不报错 + rating_prompt_enabled 可控）
"""

from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

# 强制 UTF-8 输出 (Windows GBK 默认编码)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).parent))

# 用临时 DB 避免污染 data/memory.db
TMP_DIR = Path(tempfile.mkdtemp(prefix="fsar_p3_"))
DB_PATH = TMP_DIR / "memory.db"


def banner(title: str):
    print(f"\n=== {title} ===")


def assert_eq(actual, expected, msg=""):
    if actual != expected:
        raise AssertionError(f"{msg}: expected {expected!r}, got {actual!r}")
    print(f"  [OK] {msg}: {actual!r}")


def assert_true(cond, msg=""):
    if not cond:
        raise AssertionError(f"{msg}: condition false")
    print(f"  [OK] {msg}")


# -------- 1. LongTermMemory 返回 id --------
banner("1. LongTermMemory 返回 msg_id")
from src.memory.long_term import LongTermMemory

ltm = LongTermMemory(db_path=DB_PATH)
id1 = ltm.save_message("s1", "user", "你好")
id2 = ltm.save_message("s1", "assistant", "你好，有什么可以帮你的？")
assert_true(id1 > 0 and id2 > id1, "msg_id 应为递增正整数")
stats = ltm.get_stats()
assert_eq(stats["total_messages"], 2, "保存后 total_messages")


# -------- 2. UserModel --------
banner("2. UserModel")
from src.memory.user_model import UserModel

um = UserModel(db_path=DB_PATH)
um.set_preference("editor", "VSCode")
um.set_preference("language", "中文", source="explicit")
um.set_preference("autosave", "true", source="inferred", confidence=0.6)

v = um.get_preference("editor")
assert_eq(v, "VSCode", "preference 读写")

all_p = um.get_all_preferences()
assert_eq(len(all_p), 3, "3 条偏好")

# patterns
um.record_pattern("常用 file_ops 整理下载目录", "在 2026-06-30 观察到")
um.record_pattern("常用 file_ops 整理下载目录", "在 2026-06-30 观察到")
um.record_pattern("晚上 8 点后开始编程", "近期多次")
top = um.get_top_patterns(limit=10)
assert_eq(top[0]["count"], 2, "首次 pattern 计数为 2")

# profile
um.set_profile("comm_style", "喜欢简短回复", source="reflection")
um.set_profile("active_hours", "晚上 8 点后", source="reflection")
prof = um.get_profile()
assert_eq(len(prof), 2, "profile 2 条")
assert_true("喜欢简短回复" in prof["comm_style"], "profile 内容")


# -------- 3. FeedbackStore (RLHF 风格) --------
banner("3. FeedbackStore — RLHF 风格评分")
from src.memory.feedback import FeedbackStore

fb = FeedbackStore(db_path=DB_PATH)
fb.add_or_update_rating(id1, "s1", 5, "完美")
fb.add_or_update_rating(id2, "s1", 2, "太啰嗦")

f = fb.get_rating(id1)
assert_eq(f.rating, 5, "msg1 评分")
assert_eq(f.reason, "完美", "msg1 原因")

# 重复打分应覆盖
fb.add_or_update_rating(id1, "s1", 4, "改分")
f = fb.get_rating(id1)
assert_eq(f.rating, 4, "msg1 评分被覆盖为 4")
assert_eq(f.reason, "改分", "msg1 原因被覆盖")

stats = fb.get_stats()
assert_eq(stats["total"], 2, "评分总数 2")
assert_eq(stats["high_count"], 1, "高分 1 条")
assert_eq(stats["low_count"], 1, "低分 1 条")

high = fb.get_high_rated(limit=5)
assert_eq(len(high), 1, "高分样本 1")
low = fb.get_low_rated(limit=5)
assert_eq(len(low), 1, "低分样本 1")
assert_true("太啰嗦" in low[0]["reason"], "低分原因")

# 非法评分
try:
    fb.add_or_update_rating(id1, "s1", 6)
    raise AssertionError("应拒绝 rating > 5")
except ValueError:
    print("  ✓ 拒绝非法评分 6")

try:
    fb.add_or_update_rating(id1, "s1", 0)
    raise AssertionError("应拒绝 rating < 1")
except ValueError:
    print("  ✓ 拒绝非法评分 0")


# -------- 4. SemanticMemory (ChromaDB 降级) --------
banner("4. SemanticMemory — ChromaDB + embedder factory")
from src.memory.semantic import SemanticMemory
from src.memory.embedder import build_embedder, probe

# 4a. Factory: 默认 (从 .env / settings.yaml 读)
ef_default = build_embedder()
print(f"  默认 embedder: {ef_default.__class__.__name__} "
      f"@ {ef_default.base_url} / {ef_default.model}")

# 4b. Factory: 显式选 LM Studio
ef_lms = build_embedder(provider="lmstudio")
assert_true(ef_lms.__class__.__name__ == "LMStudioEmbeddingFunction",
            "factory → LMStudioEmbeddingFunction")

# 4c. Factory: 显式选 Ollama (本地没装也能构造)
ef_ollama = build_embedder(provider="ollama",
                           base_url="http://localhost:11434",
                           model="nomic-embed-text")
assert_true(ef_ollama.__class__.__name__ == "OllamaEmbeddingFunction",
            "factory → OllamaEmbeddingFunction")
print(f"  Ollama embedder: {ef_ollama.base_url} / {ef_ollama.model}")

# 4d. Factory: 未知 provider 应抛错
try:
    build_embedder(provider="bogus")
    raise AssertionError("应拒绝未知 provider")
except ValueError as e:
    print(f"  [OK] 拒绝未知 provider: {e}")

# 4e. probe 当前 embedder
info = probe()
print(f"  probe: ok={info['ok']}, dim={info.get('dim')}, "
      f"provider={info.get('provider')}")
assert_true(info["ok"], "probe 默认 embedder 可用")

CHROMA_PATH = TMP_DIR / "chroma"
sm = SemanticMemory(path=CHROMA_PATH)
print(f"  chroma available: {sm.available}")

if sm.available:
    # 添加 5 条不同主题的"对话"
    docs = [
        ("用户喜欢用 VSCode 写 Python", "s1", "user"),
        ("今天天气不错，适合出门散步", "s1", "user"),
        ("Python 的 list comprehension 怎么用？", "s1", "user"),
        ("晚饭吃什么？", "s1", "user"),
        ("帮我用 git 提交一下代码", "s1", "user"),
    ]
    for text, sid, role in docs:
        did = sm.add(text, session_id=sid, role=role)
        print(f"  + {text[:30]:30s} → {did[:20] if did else 'FAIL'}")

    n = sm.count()
    assert_eq(n, 5, "semantic count after 5 adds")

    # 语义搜索：查 "编辑器相关" 应找到 VSCode
    hits = sm.search("编辑器", n=3)
    assert_true(len(hits) > 0, f"搜索 '编辑器' 返回 {len(hits)} 条")
    if hits:
        top = hits[0]
        print(f"  top hit: distance={top.distance:.3f}, text={top.text[:40]!r}")
        assert_true("VSCode" in top.text or "代码" in top.text or "git" in top.text,
                    "top hit 应该是编辑器/代码相关")

    # 语义搜索：查 "吃什么" 应找到晚饭
    hits = sm.search("推荐晚餐", n=2)
    assert_true(len(hits) > 0, "搜索 '推荐晚餐' 返回结果")
    if hits:
        print(f"  '推荐晚餐' top: {hits[0].text[:30]!r}")

    # clear
    sm.clear()
    n2 = sm.count()
    assert_eq(n2, 0, "clear 后 count=0")
    print("  [OK] clear 不抛错")
else:
    print("  chroma 不可用，跳过 semantic 测试")
    sm.clear()
    print("  [OK] clear 不抛错")


# -------- 5. MemoryRecall --------
banner("5. MemoryRecall — 统一召回接口")
from src.memory.recall import MemoryRecall, RecallResult

mr = MemoryRecall(
    long_term=ltm, semantic=sm, user_model=um, feedback=fb,
)
result = mr.recall_for_context("用户用 VSCode", semantic_top_k=3)
ctx = result.to_context(max_len=2000)
print(f"  recall context 长度: {len(ctx)}")
assert_true("VSCode" in ctx, "context 含偏好")
assert_true("常用 file_ops" in ctx, "context 含模式")
assert_true("comm_style" in ctx or "喜欢简短回复" in ctx, "context 含画像")

empty = mr.recall_for_context("无关查询", include_semantic=False)
# 没记忆时不报错
assert_true(isinstance(empty, RecallResult), "空召回返回对象")

stats = mr.stats()
print(f"  recall stats: long_term={stats['long_term']['total_messages']}, "
      f"semantic={stats['semantic_count']}, prefs={stats['preferences_count']}, "
      f"patterns={stats['patterns_count']}, profile={stats['profile_count']}, "
      f"feedback={stats['feedback']['total']}")


# -------- 6. IdleReflector — 规则版 --------
banner("6. IdleReflector — 规则版（不依赖 LLM）")
from src.memory.reflection import IdleReflector, ReflectionReport

ref = IdleReflector(long_term=ltm, user_model=um, feedback=fb,
                    interval_hours=12.0)
# 没 LLM → 走规则版
report = ref.reflect(force=True)
assert_true(isinstance(report, ReflectionReport), "返回 ReflectionReport")
print(f"  profile: {list(report.profile.keys())}")
print(f"  preferences: {list(report.preferences.keys())}")
# 规则版应该看到 1 高 + 1 低 → mixed 信号
assert_true(any("混合" in v or "反馈" in v for v in report.profile.values()),
            "规则版识别出混合评分")

# should_reflect 默认 True (上次已 mark done 但消息不够)
last = ref.last_reflection_at()
assert_true(last is not None, "复盘后 last_reflection_at 已记录")

# 写回应当增加 profile 数（之前 2 条 + 至少 1 条新）
new_prof = um.get_profile()
assert_true(len(new_prof) >= 3, f"profile 应新增，目前 {len(new_prof)} 条")


# -------- 7. main.FSAR 集成 --------
banner("7. main.FSAR 集成 — 实例化不报错")
import os
os.environ.setdefault("LLM_BASE_URL", "http://localhost:0")
os.environ.setdefault("LLM_API_KEY", "sk-test")
os.environ.setdefault("LLM_MODEL", "test-model")
os.environ.setdefault("LLM_PROVIDER", "test")

import main as fsar_main
fsar = fsar_main.FSAR()
assert_true(hasattr(fsar, "semantic"), "FSAR.semantic")
assert_true(hasattr(fsar, "user_model"), "FSAR.user_model")
assert_true(hasattr(fsar, "feedback"), "FSAR.feedback")
assert_true(hasattr(fsar, "recall"), "FSAR.recall")
assert_true(hasattr(fsar, "reflector"), "FSAR.reflector")
assert_true(fsar._rating_prompt_enabled, "默认开启评分提示")

# 模拟 _save_assistant_reply
async def fake_save():
    # 直接调 short_memory + long_memory 模拟
    fsar.short_memory.add("assistant", "测试回复")
    msg_id = fsar.long_memory.save_message(fsar.session_id, "assistant", "测试回复")
    fsar._last_assistant_msg_id = msg_id
    return msg_id

import asyncio
mid = asyncio.run(fake_save())
assert_true(mid > 0, "save 返回 id")

# _build_memory_context 不报错
ctx = fsar._build_memory_context("测试查询")
print(f"  build_memory_context 长度: {len(ctx)}")


print("\n✅ 所有 P3 验证通过")
print(f"   临时数据: {TMP_DIR}")