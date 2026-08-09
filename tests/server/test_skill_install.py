import importlib

import pytest
from fastapi.testclient import TestClient

from src.memory.experience_store import ExperienceStore
from src.server.handlers.skill_install import install_skill_folder


def _write_skill(folder, *, with_children=True):
    folder.mkdir(exist_ok=True)
    (folder / "SKILL.md").write_text(
        "---\nname: install-demo\ncategory: tools\n---\n\nRun it.\n",
        encoding="utf-8",
    )
    if with_children:
        for directory in ("templates", "scripts", "references"):
            (folder / directory).mkdir(exist_ok=True)
        (folder / "templates" / "prompt.txt").write_text("Prompt\n", encoding="utf-8")
        (folder / "scripts" / "run.py").write_text("print('ok')\n", encoding="utf-8")
        (folder / "references" / "guide.md").write_text("Guide\n", encoding="utf-8")


def test_install_replaces_children_and_preserves_id(tmp_path):
    folder = tmp_path / "skill"
    db_path = tmp_path / "memory.db"
    _write_skill(folder)

    first = install_skill_folder(folder, db_path)

    assert first == {
        "id": first["id"],
        "name": "install-demo",
        "action": "created",
        "category": "tools",
        "templates": 1,
        "scripts": 1,
        "references": 1,
        "warnings": [],
    }

    for child in ("templates/prompt.txt", "scripts/run.py", "references/guide.md"):
        (folder / child).unlink()
    second = install_skill_folder(folder, db_path)

    assert second["id"] == first["id"]
    assert second["action"] == "updated"
    assert second["templates"] == second["scripts"] == second["references"] == 0

    store = ExperienceStore(db_path=db_path)
    experience = store.get_by_name("install-demo")
    assert experience is not None
    assert experience.id == first["id"]
    assert store.get_templates(experience.id) == []
    assert store.get_scripts(experience.id) == []
    assert store.get_references(experience.id) == []


@pytest.fixture
def api(tmp_path, monkeypatch):
    import src.server.ws_server as ws_mod

    importlib.reload(ws_mod)
    ws_mod._ctx = {**ws_mod._ctx, "db_path": str(tmp_path / "api.db")}
    return TestClient(ws_mod.app), ws_mod


def _headers(ws_mod, *, token=True, origin="http://127.0.0.1:8765"):
    headers = {"host": "127.0.0.1:8765", "origin": origin}
    if token:
        headers["authorization"] = f"Bearer {ws_mod._ws_auth.ensure_token()}"
    return headers


def test_install_route_rejects_bad_body(api):
    client, ws_mod = api

    assert client.post("/api/skill/install", headers=_headers(ws_mod), content="{").status_code == 400
    response = client.post("/api/skill/install", headers=_headers(ws_mod), json={})
    assert response.status_code == 400
    assert response.json() == {"detail": "bad_request"}


def test_install_route_requires_origin_and_token(api):
    client, ws_mod = api

    assert client.post("/api/skill/install", headers=_headers(ws_mod, token=False), json={}).status_code == 401
    response = client.post(
        "/api/skill/install",
        headers=_headers(ws_mod, origin="https://example.com"),
        json={"folder_path": "C:/skill"},
    )
    assert response.status_code == 403


def test_install_route_persists_children_and_broadcasts(api, tmp_path):
    client, ws_mod = api
    folder = tmp_path / "route-skill"
    _write_skill(folder)

    with client.websocket_connect("/ws") as websocket:
        websocket.receive_json()
        websocket.receive_json()
        response = client.post(
            "/api/skill/install",
            headers=_headers(ws_mod),
            json={"folder_path": str(folder)},
        )
        event = websocket.receive_json()

    assert response.status_code == 200
    assert response.json()["scripts"] == 1
    assert response.json()["templates"] == 1
    assert response.json()["references"] == 1
    assert event == {"type": "library.changed", "op": "install", "name": "install-demo"}

    store = ExperienceStore(db_path=ws_mod._ctx["db_path"])
    experience = store.get_by_name("install-demo")
    assert experience is not None
    assert len(store.get_scripts(experience.id)) == 1


def test_install_route_returns_stable_folder_error(api, tmp_path):
    client, ws_mod = api

    response = client.post(
        "/api/skill/install",
        headers=_headers(ws_mod),
        json={"folder_path": str(tmp_path)},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "skill_md_missing"}
