def build_markdown(r):
    m, hm = r["metrics"], r["hardened"]["metrics"]
    w = r["winner"]
    mode = "SIMULATED (mock mode - numbers are not real model behaviour)" if r["mock"] else f"LIVE ({r['model']})"
    L = []
    L.append(f"# PromptForge Report - {r['pack_name']}")
    L.append(f"*Run {r['run_id']} - {r['created']} - Mode: {mode}*\n")
    L.append(f"**Task:** {r['task']}\n")
    L.append("## 1. Prompt leaderboard (quality)")
    L.append("| Rank | Variant | Accuracy | Relevance /5 | Coherence /5 | Avg tokens | Format valid | Composite |")
    L.append("|---|---|---|---|---|---|---|---|")
    labels = {v["id"]: v["label"] for v in r["variants"]}
    for i, (vid, x) in enumerate(sorted(m.items(), key=lambda kv: -kv[1]["composite"]), 1):
        L.append(f"| {i} | {labels[vid]}{' (winner)' if vid == w else ''} | {x['accuracy']:.0%} | {x['relevance']:.1f} | "
                 f"{x['coherence']:.1f} | {x['avg_tokens']:.0f} | {x['format_valid']:.0%} | {x['composite']:.2f} |")
    L.append("\nComposite = 0.5 accuracy + 0.2 relevance + 0.2 coherence + 0.1 cost-efficiency.\n")
    L.append("## 2. Security (attack success rate, lower is better)")
    L.append("| Attack | " + " | ".join(labels[v["id"]] for v in r["variants"]) + " | Hardened winner |")
    L.append("|---|" + "---|" * (len(r["variants"]) + 1))
    for t in r["attack_types"]:
        row = []
        for v in r["variants"]:
            a = next((a for a in r["attacks"] if a["phase"] == "before" and a["variant"] == v["id"] and a["atype"] == t), None)
            row.append("BREACHED" if a and a["success"] else "blocked")
        a = next((a for a in r["attacks"] if a["phase"] == "after" and a["atype"] == t), None)
        row.append("BREACHED" if a and a["success"] else "blocked")
        L.append(f"| {t} | " + " | ".join(row) + " |")
    L.append(f"\n**Winner ({labels[w]}) attack success rate: {r['asr_before']:.0%} before hardening -> {r['asr_after']:.0%} after.**\n")
    L.append("## 3. Defenses added")
    for d in r["hardened"]["defenses"]:
        L.append(f"- {d}")
    L.append("\n## 4. Cost of security (trade-off)")
    L.append("| Metric | Before | After |\n|---|---|---|")
    L.append(f"| Accuracy | {m[w]['accuracy']:.0%} | {hm['accuracy']:.0%} |")
    L.append(f"| Avg tokens per call | {m[w]['avg_tokens']:.0f} | {hm['avg_tokens']:.0f} |")
    L.append(f"| Composite quality | {m[w]['composite']:.2f} | {hm['composite']:.2f} |")
    L.append("\n## 5. Final hardened template\n```text\n" + r["hardened"]["template"] + "\n```\n")
    L.append("## 6. Limitations (be honest in the viva)")
    L.append("- Relevance and coherence come from an LLM judge, which can favour longer or more confident answers.")
    L.append("- Small test sets (a handful of inputs) give noisy accuracy; attack results are a sample, not a proof of safety.")
    L.append("- Only 5 attack families were tested; a hardened prompt is harder to break, not unbreakable.")
    L.append(f"- Total tokens used in this run: {r['tokens_total']}.\n")
    L.append("## 7. Syllabus coverage")
    L.append("- Unit I: prompt structure (context, constraints, output format), prompt lifecycle, hallucination/bias probes.")
    L.append("- Unit II: zero-shot, few-shot, CoT, role-based prompts, reusable templates, debugging and token optimisation.")
    L.append("- Unit III: LLM API, prompt chaining as the 6-stage pipeline, domain packs as real-world applications.")
    L.append("- Unit IV: self-consistency, reflection (self-check), evaluation metrics, prompt-injection security, responsible AI.")
    return "\n".join(L)
