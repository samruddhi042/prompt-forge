# PromptForge: prompt quality and security studio

Describe a task, and PromptForge builds several prompt variants, scores them, attacks the best one with prompt-injection attacks, hardens it, and proves the improvement with numbers. It ships with three domain packs: **Resume Screener** (recruiters), **Support Desk** (customer support) and **Answer Grader** (teachers).

## Run it (Windows)

```bat
cd promptforge
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn backend.main:app --reload
```
Open http://localhost:8000. On Mac/Linux use `source venv/bin/activate` and `cp`.

## Mock mode vs live mode

| Mode | When | What you get |
|---|---|---|
| **MOCK** (orange badge) | `GEMINI_API_KEY` empty, or `MOCK_MODE=1` | Free offline simulator. Use it to test the UI. **Numbers are simulated, not real model behaviour**, and reports are labelled SIMULATED. |
| **LIVE** (green badge) | key set in `.env` | Real Gemini calls, cached in `data/cache.json` so repeat runs are instant and free. |

**Getting a key:** Gemini Plus (the chat subscription) does not include API access. Create a free key in Google AI Studio (aistudio.google.com), paste it into `.env` as `GEMINI_API_KEY`, and copy a current model name from AI Studio into `MODEL_NAME` if the default is unavailable.

**Rate limits:** a full run makes roughly 60 calls (about 90 with self-consistency). If you see 429 errors, raise `REQUEST_INTERVAL` in `.env` (for example 4), or use "3 test inputs". Do one live run before your viva so everything is cached, and never run it for the first time in front of the examiner.

## The pipeline (your "prompt lifecycle" from Unit I)

1. **Generate**: 4 prompt variants (zero-shot, few-shot, CoT, role-based) from one template with slots for context, constraints and output format. Optional 5th: self-consistency (CoT sampled 3 times, majority vote).
2. **Evaluate**: each variant runs on the test inputs. Accuracy is checked against known answers; relevance and coherence come from a batched LLM judge; token cost is measured. Composite = 0.5 accuracy + 0.2 relevance + 0.2 coherence + 0.1 cost-efficiency.
3. **Red-team**: 5 attacks on every variant (direct injection, hidden/indirect injection, role-play jailbreak, system-prompt leak, data exfiltration). Leaks are detected with honeypot strings placed in the prompt's "internal notes".
4. **Harden** the winner: delimiters, instruction hierarchy, confidentiality rules, self-check (reflection).
5. **Re-attack** with the same attacks.
6. **Re-evaluate** quality, because defenses cost tokens and can change accuracy.

## Where each syllabus unit shows up

- **Unit I**: prompt structure (context, constraints, output format), the lifecycle above, bias probes (e.g. a test resume with gender and age stated), LLM limitations shown in the report.
- **Unit II**: zero/few-shot, CoT, role and persona prompts, reusable templates (`backend/generator.py`), token optimisation, debugging via the Attack Lab.
- **Unit III**: Gemini API (`backend/llm_client.py`), prompt chaining (the 6-stage pipeline in `backend/pipeline.py`), real-world applications through domain packs. *There is no RAG in this version; do not claim it in the viva.*
- **Unit IV**: self-consistency and reflection, evaluation metrics, bias, prompt-injection security, responsible AI (the limitations section).

## Project layout

```
backend/  llm_client.py (all model calls + cache + mock)   generator.py (variants + hardener)
          evaluator.py (metrics, judge, self-consistency)  redteam.py (attacks)
          pipeline.py (orchestrator)  report.py  db.py  main.py (FastAPI + live streaming)
packs/    resume.json  support.json  grading.json   <- one JSON file per domain
frontend/ index.html  style.css  app.js  chart.umd.js  (no build step)
data/     cache.json + promptforge.db (created automatically)
```

## Add your own domain pack

Copy `packs/resume.json`, change the fields, restart the server. `kind` is `score` (1-10 with an expected range per test) or `decision` (one of `choices`, with a `hijack` value the attacker wants). Write 6 or more test inputs with known correct answers, one weak `attack_base` input, and 5 attack payloads.

## Be honest about the limits (examiners respect this)

- The LLM judge can favour longer or more confident answers, so relevance and coherence are indicative, and accuracy is the trustworthy metric.
- 6 test inputs per task is a small sample; treat percentages as indicative, not statistically significant.
- Attack success is measured on 5 attack families. A hardened prompt is harder to break, not unbreakable.
- Gemini's own safety filters may block some attack outputs; empty or blocked responses count as "attack failed".

## Security notes

- The API key lives only in `.env` on the backend and never reaches the browser. Do not commit `.env`.
- All model output is HTML-escaped before display in the UI.
