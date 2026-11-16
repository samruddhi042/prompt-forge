import asyncio, json, threading, time, traceback, uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, llm_client, packs as packs_mod, pipeline, report

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"

app = FastAPI(title="PromptForge")
db.init()
PACKS = packs_mod.load_all()
RUNS = {}   # run_id -> {"events": [...], "done": bool}


class RunRequest(BaseModel):
    domain: str
    task: Optional[str] = None
    self_consistency: bool = False
    n_tests: int = 6


@app.get("/api/health")
def health():
    return {"mode": "mock" if llm_client.is_mock() else "live", "model": llm_client.model_name()}


@app.get("/api/packs")
def list_packs():
    return [packs_mod.public(p) for p in PACKS.values()]


@app.post("/api/run")
def start_run(req: RunRequest):
    pack = PACKS.get(req.domain)
    if not pack:
        raise HTTPException(404, "Unknown domain pack")
    run_id = uuid.uuid4().hex[:10]
    state = {"events": [], "done": False}
    RUNS[run_id] = state
    mock = llm_client.is_mock()

    def emit(type_, **data):
        state["events"].append({"type": type_, **data})
        if mock and type_ in ("eval", "attack"):
            time.sleep(0.12)   # makes the simulated live feed visible

    def worker():
        try:
            result = pipeline.run(run_id, pack, req.model_dump(), emit)
            db.save_run(run_id, pack["id"], result["created"], "done", result)
            emit("done", result=result)
        except Exception as e:
            traceback.print_exc()
            emit("error", msg=f"{type(e).__name__}: {e}")
        finally:
            state["done"] = True

    threading.Thread(target=worker, daemon=True).start()
    return {"run_id": run_id}


@app.get("/api/stream/{run_id}")
async def stream(run_id: str):
    state = RUNS.get(run_id)
    if not state:
        raise HTTPException(404, "Unknown run")

    async def gen():
        i = 0
        while True:
            while i < len(state["events"]):
                yield f"data: {json.dumps(state['events'][i])}\n\n"
                i += 1
            if state["done"] and i >= len(state["events"]):
                break
            await asyncio.sleep(0.15)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/runs")
def runs():
    return db.list_runs()


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    r = db.get_run(run_id)
    if not r:
        raise HTTPException(404, "Run not found")
    return r


@app.get("/api/runs/{run_id}/report.md")
def get_report(run_id: str):
    r = db.get_run(run_id)
    if not r:
        raise HTTPException(404, "Run not found")
    return PlainTextResponse(report.build_markdown(r), headers={
        "Content-Disposition": f'attachment; filename="promptforge-{r["domain"]}-{run_id}.md"'})


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
