# updates — 版本检查与受限更新流程

> 语言：中文 | [English](updates.en.md) · 返回[模块介绍](README.md)

版本发现与应用。`github.py`（`GitHubClient`）访问 GitHub Releases API；`releases.py`（`select_releases`、`sync_release_notifications`）把更新的版本转成 `release` 通知，并负责稳定/beta 频道划分。`announcements.py` 从本仓库 `main` 上的 `announcements/` 目录拉取 markdown，按内容哈希与本地 manifest 比对，走与其它已存内容相同的筛查管线，只保留筛查后的结果。`apply.py` 就是更新本身：`build_plan` / `apply_plan`（`UpdatePlan`、`target_branch_for`）运行受限的本地 git 流程，一旦检出有未提交改动、或已有 git 操作正在进行，就直接拒绝。GUI 经 `handlers/notifications.py` 到达。
