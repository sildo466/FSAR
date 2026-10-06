# updates — release checks and the gated update flow

> Language: [中文](updates.md) | English · Back to [module index](README.en.md)

Update discovery and application. `github.py` (`GitHubClient`) talks to the GitHub Releases API; `releases.py` (`select_releases`, `sync_release_notifications`) turns newer releases into `release` notifications and owns the stable/beta channel split. `announcements.py` pulls markdown from this repository's `announcements/` folder on `main`, diffs it by content hash against a local manifest, screens it through the same pipeline as any other stored content, and keeps only the screened result. `apply.py` is the update itself: `build_plan` / `apply_plan` (`UpdatePlan`, `target_branch_for`) run the gated local git flow and refuse outright when the checkout has uncommitted modifications or a git operation already in progress. Reached from the GUI through `handlers/notifications.py`.
