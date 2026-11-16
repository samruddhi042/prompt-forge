import sqlite3, json, threading
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "promptforge.db"
_lock = threading.Lock()


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init():
    DB_PATH.parent.mkdir(exist_ok=True)
    with _lock, _conn() as c:
        c.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, domain TEXT, created TEXT, "
                  "status TEXT, result TEXT)")


def save_run(run_id, domain, created, status, result):
    with _lock, _conn() as c:
        c.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?)",
                  (run_id, domain, created, status, json.dumps(result)))


def get_run(run_id):
    with _lock, _conn() as c:
        r = c.execute("SELECT result FROM runs WHERE id=?", (run_id,)).fetchone()
    return json.loads(r["result"]) if r else None


def list_runs():
    with _lock, _conn() as c:
        rows = c.execute("SELECT id, domain, created, result FROM runs WHERE status='done' "
                         "ORDER BY created DESC LIMIT 50").fetchall()
    out = []
    for r in rows:
        res = json.loads(r["result"])
        out.append({"id": r["id"], "domain": r["domain"], "pack_name": res.get("pack_name"),
                    "created": r["created"], "winner": res.get("winner"), "mock": res.get("mock"),
                    "asr_before": res.get("asr_before"), "asr_after": res.get("asr_after")})
    return out
