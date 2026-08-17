# SPDX-License-Identifier: MIT
import json
from pathlib import Path

from src.memory.skin_store import list_skins


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_lists_valid_skins_sorted(tmp_path: Path):
    _write(tmp_path / "warm" / "skin.json", {"id": "warm", "name": "暖阳", "base": "light", "palette": {"bg": "#faf8f5", "accent": "#d4a04a"}})
    _write(tmp_path / "night" / "skin.json", {"id": "night", "name": "暗紫", "base": "dark", "palette": {}})
    skins = list_skins(tmp_path)
    assert [s["id"] for s in skins] == ["night", "warm"]
    assert skins[1]["name"] == "暖阳"
    assert skins[0]["base"] == "dark"
    assert skins[1]["palette"]["accent"] == "#d4a04a"


def test_skips_bad_json(tmp_path: Path):
    (tmp_path / "broken").mkdir(parents=True)
    (tmp_path / "broken" / "skin.json").write_text("{not json", encoding="utf-8")
    _write(tmp_path / "ok" / "skin.json", {"id": "ok", "name": "OK", "palette": {}})
    assert [s["id"] for s in list_skins(tmp_path)] == ["ok"]


def test_skips_id_mismatch(tmp_path: Path):
    _write(tmp_path / "mismatch" / "skin.json", {"id": "other", "name": "X"})
    assert list_skins(tmp_path) == []


def test_skips_bad_base_and_filters_unknown_palette(tmp_path: Path):
    _write(tmp_path / "weird" / "skin.json", {
        "id": "weird", "name": "W", "base": "neon",
        "palette": {"bg": "#000", "accent": 123, "nope": "#fff", "surface2": "rgba(0,0,0,0.03)"},
    })
    skins = list_skins(tmp_path)
    assert skins[0]["base"] == "light"
    assert skins[0]["palette"] == {"bg": "#000", "surface2": "rgba(0,0,0,0.03)"}


def test_missing_dir_returns_empty(tmp_path: Path):
    assert list_skins(tmp_path / "nope") == []


def test_parses_background_and_clamps_overlay(tmp_path: Path):
    _write(tmp_path / "s" / "skin.json", {
        "id": "s", "name": "S", "base": "light", "palette": {},
        "background": {"chatImage": "/skin-assets/s/bg.png", "chatOverlay": 2.5},
    })
    assert list_skins(tmp_path)[0]["background"] == {"chatImage": "/skin-assets/s/bg.png", "chatOverlay": 1.0}


def test_background_invalid_fields_dropped(tmp_path: Path):
    _write(tmp_path / "s" / "skin.json", {
        "id": "s", "name": "S",
        "background": {"chatImage": 5, "chatOverlay": "x"},
    })
    assert list_skins(tmp_path)[0]["background"] == {}

def test_parses_elements_and_pattern(tmp_path: Path):
    _write(tmp_path / "s" / "skin.json", {
        "id": "s", "name": "S", "base": "light", "palette": {},
        "elements": {
            "button": {"bg": "#d4a04a", "image": "/skin-assets/s/tex.png", "imageOpacity": 2.5, "nope": "x"},
            "input": {"bg": "#fff"},
        },
        "pattern": {"image": "/skin-assets/s/pat.png", "opacity": 0.5},
    })
    s = list_skins(tmp_path)[0]
    assert s["elements"]["button"] == {"bg": "#d4a04a", "image": "/skin-assets/s/tex.png", "imageOpacity": 1.0}
    assert s["elements"]["input"] == {"bg": "#fff"}
    assert s["pattern"] == {"image": "/skin-assets/s/pat.png", "opacity": 0.5}


def test_elements_pattern_invalid_dropped(tmp_path: Path):
    _write(tmp_path / "s" / "skin.json", {
        "id": "s", "name": "S",
        "elements": {"bogus": {"bg": "#fff"}, "button": {"hover": 5}},
        "pattern": {"image": 5, "opacity": "x"},
    })
    s = list_skins(tmp_path)[0]
    assert s["elements"] == {}
    assert s["pattern"] == {}
