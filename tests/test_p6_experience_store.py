"""Phase 6 tests — ExperienceStore + tools + lifecycle + auto-promote.

Run:
    python -m unittest tests.test_p6_experience_store -v
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path


class TestExperienceStore(unittest.TestCase):
    """p6.1 — schema, CRUD, lifecycle, auto-promote bridge."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="fsar_p6_")
        self.db_path = os.path.join(self.tmpdir, "memory.db")
        from src.memory.experience_store import (
            ExperienceStore, Experience, ExperienceTemplate, ExperienceScript,
            ExperienceReference, MemoryChunk,
        )
        self.ExperienceStore = ExperienceStore
        self.Experience = Experience
        self.ET = ExperienceTemplate
        self.ES = ExperienceScript
        self.ER = ExperienceReference
        self.MemoryChunk = MemoryChunk
        self.store = ExperienceStore(db_path=self.db_path)

    def _make_experience(self, name="test-exp", category="coding", **kw):
        defaults = dict(
            name=name, category=category,
            description="A test experience for the P6 suite.",
            body="## Procedure\n1. Step one\n2. Step two\n3. Done.",
            trigger_patterns=["test pattern"],
            pitfalls=["never overwrite"],
            prerequisites=["python 3.11"],
        )
        defaults.update(kw)
        return self.Experience(**defaults)

    def test_a_upsert_and_get_by_name(self):
        e = self._make_experience()
        eid = self.store.upsert_experience(e)
        self.assertIsInstance(eid, int)
        got = self.store.get_by_name("test-exp")
        self.assertIsNotNone(got)
        self.assertEqual(got.id, eid)
        self.assertEqual(got.name, "test-exp")
        self.assertEqual(got.category, "coding")
        self.assertEqual(got.pitfalls, ["never overwrite"])
        self.assertEqual(got.state, "active")
        self.assertFalse(got.pinned)

    def test_b_upsert_updates_existing_row(self):
        self.store.upsert_experience(
            self._make_experience(description="first")
        )
        self.store.upsert_experience(
            self._make_experience(description="second")
        )
        rows = self.store.list_for_index()
        matching = [r for r in rows if r.name == "test-exp"]
        self.assertEqual(len(matching), 1, "upsert must update in place, not duplicate")
        self.assertEqual(matching[0].description, "second")

    def test_c_get_by_name_returns_none_for_missing(self):
        self.assertIsNone(self.store.get_by_name("does-not-exist"))

    def test_d_validation(self):
        with self.assertRaises(ValueError):
            self.store.upsert_experience(self.Experience(name="", category="x", description="y", body="z"))
        with self.assertRaises(ValueError):
            self.store.upsert_experience(
                self._make_experience(state="bogus")
            )

    # ---------- children ----------

    def test_e_save_full_with_templates_scripts_refs(self):
        e = self._make_experience()
        eid = self.store.save_experience_full(
            e,
            templates=[self.ET(name="weekly", content="# plan"),
                       self.ET(name="monthly", content="# plan v2")],
            scripts=[self.ES(name="run", language="bash", content="echo hi")],
            references=[self.ER(title="ref1", body="see link", source="paste",
                                source_url="https://example.com")],
        )
        self.assertIsInstance(eid, int)
        self.assertEqual(len(self.store.get_templates(eid)), 2)
        self.assertEqual(len(self.store.get_scripts(eid)), 1)
        self.assertEqual(len(self.store.get_references(eid)), 1)

        second = self.store.save_experience_full(
            self._make_experience(),
            templates=[self.ET(name="only-one", content="x")],
        )
        # templates should be replaced, not appended
        self.assertEqual(len(self.store.get_templates(second)), 1)

    # ---------- usage + lifecycle ----------

    def test_f_bump_use_increments_and_promotes_stale(self):
        self.store.upsert_experience(self._make_experience())
        self.store.set_state("test-exp", "stale")
        self.store.bump_use("test-exp")
        after = self.store.get_by_name("test-exp")
        self.assertEqual(after.use_count, 1)
        self.assertEqual(after.state, "active", "use on stale row should auto-promote")
        self.assertIsNotNone(after.last_used_at)

    def test_g_mark_stale_skips_pinned(self):
        self.store.upsert_experience(self._make_experience())
        self.store.upsert_experience(self._make_experience(name="pinned", category="coding",
                                                           description="",
                                                           pinned=True))
        # Backdate both rows so the relative `days` cutoff actually catches them
        with self.store._connect() as conn:
            conn.execute(
                "UPDATE experiences SET created_at = ? WHERE name IN (?, ?)",
                ("2020-01-01T00:00:00", "test-exp", "pinned"),
            )
            conn.commit()
        n = self.store.mark_stale(days=30)
        self.assertEqual(n, 1, "only the non-pinned row should transition")
        states = {e.name: e.state for e in self.store.list_for_index(include_states=["active", "stale"])}
        self.assertEqual(states["pinned"], "active")
        self.assertEqual(states["test-exp"], "stale")

    def test_h_mark_archived_skips_active_and_pinned(self):
        self.store.upsert_experience(self._make_experience())
        self.store.upsert_experience(self._make_experience(name="also-pinned", description="", pinned=True))
        self.store.set_state("test-exp", "stale")
        self.store.set_state("also-pinned", "stale")
        n = self.store.mark_archived(days=0)
        self.assertEqual(n, 1)
        states = {e.name: e.state for e in self.store.list_for_index(include_states=["active", "stale", "archived"])}
        self.assertEqual(states["also-pinned"], "stale", "pinned rows should never archive")
        self.assertEqual(states["test-exp"], "archived")

    # ---------- rendering ----------

    def test_i_render_index_groups_by_category(self):
        self.store.upsert_experience(self._make_experience(name="a", category="coding"))
        self.store.upsert_experience(self._make_experience(name="b", category="file-management"))
        block = self.store.render_index()
        self.assertIn("a:", block)
        self.assertIn("b:", block)
        self.assertIn("coding", block)
        self.assertIn("file-management", block)
        # both descriptions should appear (truncated to 60 chars by default)
        self.assertIn("A test experience", block)
        self.assertIn("Only call experience_view", block)

    def test_j_render_index_truncates_long_descriptions(self):
        long_desc = "x" * 100
        self.store.upsert_experience(self._make_experience(description=long_desc))
        block = self.store.render_index(max_desc_chars=20)
        self.assertIn("…", block)
        # the truncated run of 'x' should NOT be 100 chars
        self.assertNotIn("x" * 80, block)

    # ---------- memory chunks ----------

    def test_k_add_and_search_chunks(self):
        cid = self.store.add_chunk(source="memory", title="lang pref",
                                   body="Chinese in chat, English in code",
                                   chunk_index=2)
        self.assertIsInstance(cid, int)
        chunks = self.store.list_chunks(source="memory")
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].chunk_index, 2)
        hits = self.store.search_chunks("Chinese")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].id, cid)

    # ---------- auto-promote bridge ----------

    def test_l_propose_from_reflections_returns_empty_when_table_missing(self):
        # fresh DB has no task_reflections table → graceful empty
        self.assertEqual(self.store.propose_from_reflections(), [])

    def test_m_propose_returns_clusters_above_threshold(self):
        # Need to fabricate task_reflections with the same DB to satisfy GROUP BY
        with self.store._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_reflections (
                    id INTEGER PRIMARY KEY,
                    task_id TEXT, session_id TEXT, outcome TEXT,
                    failure_modes TEXT, success_patterns TEXT,
                    suggested_strategy TEXT,
                    step_count INT, tools_used TEXT,
                    error_count INT, created_at TEXT
                )
            """)
            for i in range(5):
                conn.execute(
                    "INSERT INTO task_reflections "
                    "(task_id, session_id, outcome, failure_modes, success_patterns, "
                    " suggested_strategy, step_count, tools_used, error_count, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (f"t{i}", "s", "success", "[]", "[]",
                     "Prefer app_control over computer_use for chat apps",
                     1, "[]", 0, "2026-01-01"),
                )
            conn.execute(
                "INSERT INTO task_reflections "
                "(task_id, session_id, outcome, failure_modes, success_patterns, "
                " suggested_strategy, step_count, tools_used, error_count, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("tLow", "s", "success", "[]", "[]",
                 "Some single-occurrence strategy",
                 1, "[]", 0, "2026-01-01"),
            )
            conn.commit()

        out = self.store.propose_from_reflections(threshold=3)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].occurrence_count, 5)
        self.assertIn("task_strategy::", out[0].name)

    def test_n_auto_promote_creates_rows(self):
        with self.store._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_reflections (
                    id INTEGER PRIMARY KEY,
                    task_id TEXT, session_id TEXT, outcome TEXT,
                    failure_modes TEXT, success_patterns TEXT,
                    suggested_strategy TEXT,
                    step_count INT, tools_used TEXT,
                    error_count INT, created_at TEXT
                )
            """)
            for i in range(3):
                conn.execute(
                    "INSERT INTO task_reflections "
                    "(task_id, session_id, outcome, failure_modes, success_patterns, "
                    " suggested_strategy, step_count, tools_used, error_count, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (f"t{i}", "s", "success", "[]", "[]",
                     "Batch shell commands whenever possible",
                     1, "[]", 0, "2026-01-01"),
                )
            conn.commit()
        n = self.store.auto_promote(threshold=3)
        self.assertEqual(n, 1)
        exp = self.store.list_for_index()
        promoted = [e for e in exp if e.created_by == "task_reflection"]
        self.assertEqual(len(promoted), 1)

        # Second run: no new rows (already promoted)
        n2 = self.store.auto_promote(threshold=3)
        self.assertEqual(n2, 0)


class TestExperienceTools(unittest.TestCase):
    """p6.2 — experience_view / learn_experience / list_experiences tools."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="fsar_p6_tools_")
        self.db_path = os.path.join(self.tmpdir, "memory.db")
        from src.memory.experience_store import ExperienceStore, Experience
        store = ExperienceStore(db_path=self.db_path)
        store.upsert_experience(Experience(
            name="smoke-skill", category="coding",
            description="Roundtrip fixture", body="step 1\nstep 2",
        ))

    def test_o_tool_registration(self):
        from src.tools import create_default_registry
        reg = create_default_registry()
        for n in ("experience_view", "learn_experience", "list_experiences"):
            with self.subTest(tool=n):
                self.assertIsNotNone(reg.get(n), f"missing tool: {n}")

    def test_p_view_bumps_use_count(self):
        # patch _store() factory inside the tool module to use the temp DB.
        from src.tools.builtin import experience_tools as et
        from src.memory.experience_store import ExperienceStore
        et._store = lambda: ExperienceStore(db_path=self.db_path)
        from src.tools import create_default_registry
        reg = create_default_registry()
        view = reg.get("experience_view")
        # round 1
        asyncio.run(view.execute(name="smoke-skill"))
        store = ExperienceStore(db_path=self.db_path)
        use1 = store.get_by_name("smoke-skill").use_count
        # round 2
        asyncio.run(view.execute(name="smoke-skill"))
        use2 = store.get_by_name("smoke-skill").use_count
        self.assertEqual(use1, 1)
        self.assertEqual(use2, 2)

    def test_q_view_unknown_returns_not_found(self):
        from src.tools.builtin import experience_tools as et
        from src.memory.experience_store import ExperienceStore
        et._store = lambda: ExperienceStore(db_path=self.db_path)
        from src.tools import create_default_registry
        reg = create_default_registry()
        view = reg.get("experience_view")
        result = asyncio.run(view.execute(name="nope"))
        self.assertIn("NOT_FOUND", result)

    def test_r_learn_then_list(self):
        from src.tools.builtin import experience_tools as et
        from src.memory.experience_store import ExperienceStore
        et._store = lambda: ExperienceStore(db_path=self.db_path)
        from src.tools import create_default_registry
        reg = create_default_registry()
        learn = reg.get("learn_experience")
        result = asyncio.run(learn.execute(
            name="learned-via-tool", category="coding",
            description="born from test",
            body="step 1\nstep 2",
        ))
        self.assertIn("[OK]", result)
        listing = asyncio.run(reg.get("list_experiences").execute(category="coding"))
        self.assertIn("learned-via-tool", listing)

    def test_s_view_external_skill_attaches_skill_md(self):
        import os
        from pathlib import Path
        from unittest.mock import patch

        from src.memory.experience_store import ExperienceStore, Experience
        from src.tools.builtin import experience_tools as et
        from src.tools import create_default_registry

        root = Path(tempfile.mkdtemp(prefix="fsar_p6_skill_"))
        skill_md = root / "skills" / "my-skill" / "SKILL.md"
        skill_md.parent.mkdir(parents=True)
        skill_md.write_text("# My Skill\n\nRule: always use the seed template.\n", encoding="utf-8")

        et._store = lambda: ExperienceStore(db_path=self.db_path)
        store = ExperienceStore(db_path=self.db_path)
        store.upsert_experience(Experience(
            name="my-skill", category="external-skill",
            description="external", body="summary only",
        ))
        reg = create_default_registry()
        view = reg.get("experience_view")

        with patch("src.utils.fsar_home.get_fsar_home", return_value=root):
            result = asyncio.run(view.execute(name="my-skill"))

        self.assertIn("summary only", result)
        self.assertIn("always use the seed template", result)
        self.assertIn("冲突规则", result)

    def test_t_view_graceful_when_skill_md_missing(self):
        from src.memory.experience_store import ExperienceStore, Experience
        from src.tools.builtin import experience_tools as et
        from src.tools import create_default_registry

        et._store = lambda: ExperienceStore(db_path=self.db_path)
        store = ExperienceStore(db_path=self.db_path)
        store.upsert_experience(Experience(
            name="ghost-skill", category="external-skill",
            description="external", body="summary only",
        ))
        reg = create_default_registry()
        view = reg.get("experience_view")

        result = asyncio.run(view.execute(name="ghost-skill"))
        self.assertIn("summary only", result)
        self.assertNotIn("SKILL.md", result)

    def test_u_sync_skills_from_disk_registers_new_skill(self):
        from pathlib import Path
        from src.memory.experience_store import ExperienceStore
        from src.memory.skill_sync import sync_skills_from_disk

        root = Path(tempfile.mkdtemp(prefix="fsar_p6_sync_"))
        skill_md = root / "skills" / "demo-skill" / "SKILL.md"
        skill_md.parent.mkdir(parents=True)
        skill_md.write_text(
            "---\nname: demo-skill\ndescription: A demo skill\n---\n\n# Demo\nSteps.\n",
            encoding="utf-8",
        )
        # a non-skill dir without SKILL.md must be skipped
        (root / "skills" / "no-skill").mkdir()

        store = ExperienceStore(db_path=self.db_path)
        n = sync_skills_from_disk(store, skills_root=root / "skills")
        self.assertEqual(n, 1)
        got = store.get_by_name("demo-skill")
        self.assertIsNotNone(got)
        self.assertEqual(got.category, "external-skill")
        self.assertEqual(got.description, "A demo skill")

    def test_v_sync_skills_from_disk_idempotent(self):
        from pathlib import Path
        from src.memory.experience_store import ExperienceStore
        from src.memory.skill_sync import sync_skills_from_disk

        root = Path(tempfile.mkdtemp(prefix="fsar_p6_sync_"))
        skill_md = root / "skills" / "demo-skill" / "SKILL.md"
        skill_md.parent.mkdir(parents=True)
        skill_md.write_text(
            "---\nname: demo-skill\ndescription: A demo skill\n---\n\n# Demo\nSteps.\n",
            encoding="utf-8",
        )
        store = ExperienceStore(db_path=self.db_path)
        self.assertEqual(sync_skills_from_disk(store, skills_root=root / "skills"), 1)
        # second pass must not duplicate
        self.assertEqual(sync_skills_from_disk(store, skills_root=root / "skills"), 0)
        names = [e.name for e in store.list_for_index()]
        self.assertEqual(names.count("demo-skill"), 1)

    def test_w_list_linked_files_surfaces_support_files(self):
        from pathlib import Path
        from src.tools.builtin.experience_tools import _list_linked_files

        root = Path(tempfile.mkdtemp(prefix="fsar_p6_links_"))
        (root / "references").mkdir()
        (root / "assets").mkdir()
        (root / "scripts").mkdir()
        (root / "references" / "layout-recipes.md").write_text("x")
        (root / "references" / "components.md").write_text("x")
        (root / "assets" / "template-swiss-card.html").write_text("x")
        (root / "assets" / "bg.png").write_text("x")  # asset image: excluded
        (root / "scripts" / "render.mjs").write_text("x")
        (root / "validate-social-deck.mjs").write_text("x")

        links = _list_linked_files(root)
        joined = "\n".join(links)
        self.assertIn("layout-recipes.md", joined)
        self.assertIn("template-swiss-card.html", joined)
        self.assertIn("render.mjs", joined)
        self.assertIn("validate-social-deck.mjs", joined)
        self.assertNotIn("bg.png", joined)

    def test_x_skill_gate_flags_custom_html(self):
        from pathlib import Path
        from src.memory import skill_gate as gate

        root = Path(tempfile.mkdtemp(prefix="fsar_p6_gate_"))
        template = root / "template-editorial-card.html"
        template.write_text(
            "<!-- POSTERS_HERE -->\n<html data-theme=\"ink-classic\">\n"
            "<div class=\"pipeline-v\"><div class=\"marginalia\"></div></div>\n"
            "<span class=\"ledger-row\"></span>\n",
            encoding="utf-8",
        )
        custom = root / "custom.html"
        custom.write_text(
            "<html><div class=\"cover-grid\"><div class=\"bar\"></div></div>\n",
            encoding="utf-8",
        )
        copied = root / "copied.html"
        copied.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")

        self.assertTrue(gate.template_compliance(custom, template))
        self.assertFalse(gate.template_compliance(copied, template))

    def test_y_skill_gate_finds_newest_task_index(self):
        import os
        from pathlib import Path
        from src.memory import skill_gate as gate

        root = Path(tempfile.mkdtemp(prefix="fsar_p6_gate_"))
        old = root / "task-old"
        new = root / "task-new"
        old.mkdir()
        new.mkdir()
        (old / "index.html").write_text("old", encoding="utf-8")
        (new / "index.html").write_text("new", encoding="utf-8")
        # backdate the old one so the newest is unambiguous
        os.utime(old / "index.html", (1000, 1000))

        found = gate.find_task_index_html(root)
        self.assertEqual(found, new / "index.html")


class TestExperienceImport(unittest.TestCase):
    """p6.3.5 — markdown → DB row."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="fsar_p6_imp_")
        self.db_path = os.path.join(self.tmpdir, "memory.db")
        self.src = Path(self.tmpdir) / "skill.md"
        self.src.write_text(self._fixture(), encoding="utf-8")

    def _fixture(self) -> str:
        return (
            "---\n"
            "name: import-fixture\n"
            "category: file-management\n"
            "description: Markdown import fixture for the P6 test suite.\n"
            "trigger_patterns:\n"
            "  - import\n"
            "pitfalls:\n"
            "  - do not import twice\n"
            "---\n\n"
            "# Import Fixture\n\n"
            "## Procedure\n"
            "1. Drop the file.\n"
            "2. Run /import.\n\n"
            "## Template: report\n"
            "```\n"
            "# {{TITLE}}\nGenerated: {{DATE}}\n"
            "```\n\n"
            "## Script: bash classify\n"
            "```bash\n"
            "echo classify $*  # stub\n"
            "```\n\n"
            "## Reference: spec link\n"
            "https://example.com/skill-spec\n"
            "Full spec lives at the URL above.\n"
        )

    def test_s_parse_markdown(self):
        from src.tools.builtin.experience_import import parse_skill_markdown
        text = self.src.read_text(encoding="utf-8")
        parsed = parse_skill_markdown(text, source_path=str(self.src))
        self.assertEqual(parsed.name, "import-fixture")
        self.assertEqual(parsed.category, "file-management")
        self.assertEqual(len(parsed.templates), 1)
        self.assertEqual(parsed.templates[0].name, "report")
        self.assertEqual(len(parsed.scripts), 1)
        self.assertEqual(parsed.scripts[0].language, "bash")
        self.assertEqual(parsed.scripts[0].name, "classify")
        self.assertEqual(len(parsed.references), 1)
        self.assertIn("https://example.com", parsed.references[0].source_url)

    def test_t_import_to_db(self):
        from src.tools.builtin.experience_import import import_markdown_file
        from src.memory.experience_store import ExperienceStore
        # point store singleton to temp DB by monkey-patching its __init__
        from src.tools.builtin import experience_import as ei
        ei.ExperienceStore = lambda db_path=None: ExperienceStore(db_path=self.db_path) if db_path else ExperienceStore(db_path=self.db_path)
        name, action, summary = import_markdown_file(self.src)
        self.assertEqual(name, "import-fixture")
        self.assertEqual(action, "created")
        store = ExperienceStore(db_path=self.db_path)
        exp = store.get_by_name("import-fixture")
        self.assertIsNotNone(exp)
        self.assertEqual(exp.created_by, "import")
        self.assertEqual(len(store.get_templates(exp.id)), 1)
        self.assertEqual(len(store.get_scripts(exp.id)), 1)
        self.assertEqual(len(store.get_references(exp.id)), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
