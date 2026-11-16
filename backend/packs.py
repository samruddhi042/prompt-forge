import json
from pathlib import Path

PACK_DIR = Path(__file__).resolve().parent.parent / "packs"


def load_all():
    packs = {}
    for f in sorted(PACK_DIR.glob("*.json")):
        p = json.loads(f.read_text(encoding="utf-8"))
        packs[p["id"]] = p
    return packs


def public(p):
    return {
        "id": p["id"], "name": p["name"], "icon": p["icon"], "audience": p["audience"],
        "task": p["task"], "context": p["context"], "kind": p["kind"],
        "attack_types": [a["type"] for a in p["attacks"]],
        "n_tests": len(p["tests"]),
        "sample_input": p["tests"][0]["input"],
    }
