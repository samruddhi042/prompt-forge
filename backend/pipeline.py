"""Orchestrator: the 6-stage prompt lifecycle (design -> test -> attack -> harden -> re-attack -> re-test)."""
import datetime
from . import llm_client, generator, evaluator, redteam

STAGES = ["Generate variants", "Evaluate", "Red-team", "Harden", "Re-attack", "Re-evaluate"]


def _asr(attacks, phase, variant):
    rows = [a for a in attacks if a["phase"] == phase and a["variant"] == variant]
    return (sum(1 for a in rows if a["success"]) / len(rows)) if rows else 0.0


def run(run_id, pack, opts, emit):
    ctx = {"tokens": 0}
    task = (opts.get("task") or "").strip() or pack["task"]
    n_tests = max(1, min(int(opts.get("n_tests") or len(pack["tests"])), len(pack["tests"])))
    tests = pack["tests"][:n_tests]
    mock = llm_client.is_mock()
    emit("start", mock=mock, model=llm_client.model_name(), pack=pack["name"], n_tests=n_tests)

    # 1. generate variants -------------------------------------------------------------
    emit("stage", n=1, label=STAGES[0])
    variants = generator.build_variants(pack, task, bool(opts.get("self_consistency")))
    emit("log", msg=f"Built {len(variants)} prompt variants from one template (context + constraints + output format).")
    emit("variants", variants=variants)

    # 2. evaluate -----------------------------------------------------------------------
    emit("stage", n=2, label=STAGES[1])
    metrics = {}
    for v in variants:
        emit("log", msg=f"Evaluating {v['label']} on {n_tests} test inputs...")
        metrics[v["id"]] = evaluator.evaluate_variant(pack, v, task, tests, ctx)
        emit("eval", variant=v["id"], metrics=metrics[v["id"]])
    evaluator.finalize(metrics)
    winner_id = max(metrics, key=lambda k: metrics[k]["composite"])
    winner = next(v for v in variants if v["id"] == winner_id)
    emit("leaderboard", metrics=metrics, winner=winner_id)
    emit("log", msg=f"Winner on quality: {winner['label']} (composite {metrics[winner_id]['composite']:.2f}).")

    # 3. red-team every variant ----------------------------------------------------------
    emit("stage", n=3, label=STAGES[2])
    attacks = []
    for v in variants:
        emit("log", msg=f"Attacking {v['label']} with {len(pack['attacks'])} attack types...")
        for atk in pack["attacks"]:
            rec = redteam.attack(pack, v["template"], v["style"], atk, ctx)
            rec.update(phase="before", variant=v["id"])
            attacks.append(rec)
            emit("attack", **rec)
    asr_before = _asr(attacks, "before", winner_id)
    emit("log", msg=f"Winner's attack success rate BEFORE hardening: {asr_before:.0%}.")

    # 4. harden the winner ---------------------------------------------------------------
    emit("stage", n=4, label=STAGES[3])
    hard_template = generator.harden(pack, winner, task)
    diff = generator.diff_lines(winner["template"], hard_template)
    emit("hardened", template=hard_template, diff=diff, defenses=generator.DEFENSES)
    emit("log", msg="Added 4 defense layers: delimiters, instruction hierarchy, confidentiality, self-check.")

    # 5. re-attack -----------------------------------------------------------------------
    emit("stage", n=5, label=STAGES[4])
    for atk in pack["attacks"]:
        rec = redteam.attack(pack, hard_template, winner["style"], atk, ctx)
        rec.update(phase="after", variant="hardened")
        attacks.append(rec)
        emit("attack", **rec)
    asr_after = _asr(attacks, "after", "hardened")
    emit("log", msg=f"Attack success rate AFTER hardening: {asr_after:.0%}.")

    # 6. re-evaluate the hardened prompt (defenses can hurt quality) ------------------------
    emit("stage", n=6, label=STAGES[5])
    hv = {"id": "hardened", "style": winner["style"], "label": "Hardened " + winner["label"], "template": hard_template}
    hm = evaluator.evaluate_variant(pack, hv, task, tests, ctx)
    evaluator.composite(hm, min(metrics[winner_id]["avg_tokens"], hm["avg_tokens"]))
    emit("reeval", metrics=hm)

    result = {
        "run_id": run_id, "domain": pack["id"], "pack_name": pack["name"], "task": task,
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "mock": mock, "model": llm_client.model_name(), "n_tests": n_tests,
        "variants": variants, "metrics": metrics, "winner": winner_id, "attacks": attacks,
        "attack_types": [a["type"] for a in pack["attacks"]],
        "asr_before": asr_before, "asr_after": asr_after,
        "hardened": {"template": hard_template, "diff": diff, "defenses": generator.DEFENSES, "metrics": hm},
        "tokens_total": ctx["tokens"],
    }
    return result
