"""Every model call in PromptForge goes through ask().

Modes
-----
LIVE : GEMINI_API_KEY is set (and MOCK_MODE is not 1) -> real Gemini calls, cached on disk.
MOCK : no key, or MOCK_MODE=1 -> a deterministic *simulation* so you can test the UI for free.
       Mock numbers are NOT real model behaviour. The UI and report label them as simulated.
"""
import os, json, hashlib, time, threading
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
CACHE_PATH = DATA / "cache.json"

MODEL = os.getenv("MODEL_NAME", "gemini-2.5-flash")   # verify the current name in Google AI Studio
MIN_INTERVAL = float(os.getenv("REQUEST_INTERVAL", "1.0"))  # seconds between live calls (free-tier friendly)

_lock = threading.Lock()
_cache = None
_client = None
_last_call = 0.0


def is_mock() -> bool:
    return os.getenv("MOCK_MODE", "0") == "1" or not os.getenv("GEMINI_API_KEY")


def model_name() -> str:
    return "mock-simulator" if is_mock() else MODEL


# ----------------------------------------------------------------------------- live
def _get_cache():
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}
        except Exception:
            _cache = {}
    return _cache


def _call_gemini(prompt: str, temperature: float):
    global _client, _last_call
    from google import genai
    from google.genai import types

    if _client is None:
        _client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    delay = 3
    for attempt in range(6):
        wait = MIN_INTERVAL - (time.time() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.time()
        try:
            r = _client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=temperature),
            )
            try:
                text = r.text or ""          # blocked/empty responses count as "no output"
            except Exception:
                text = ""
            um = getattr(r, "usage_metadata", None)
            tokens = int(getattr(um, "total_token_count", 0) or 0)
            return text, tokens
        except Exception as e:  # retry only on rate-limit / transient errors
            msg = str(e).lower()
            retryable = any(k in msg for k in ("429", "quota", "rate", "503", "unavailable", "overloaded", "timeout"))
            if attempt == 5 or not retryable:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 40)


def ask(prompt: str, temperature: float = 0.0, sample: int = 0, hint: dict = None) -> dict:
    """Return {"text": str, "tokens": int}. `hint` is only used by the mock simulator."""
    if is_mock():
        time.sleep(0.03)
        return _mock(prompt, temperature, sample, hint or {})

    key = hashlib.md5(f"{MODEL}|{temperature}|{sample}|{prompt}".encode()).hexdigest()
    with _lock:
        cached = _get_cache().get(key)
    if cached:
        return cached
    text, tokens = _call_gemini(prompt, temperature)
    out = {"text": text, "tokens": tokens}
    with _lock:
        c = _get_cache()
        c[key] = out
        CACHE_PATH.write_text(json.dumps(c))
    return out


# ----------------------------------------------------------------------------- mock
def _h(*parts) -> int:
    return int(hashlib.md5("|".join(map(str, parts)).encode()).hexdigest(), 16)


_STYLE_RESIST = {"zero_shot": 0.0, "few_shot": 0.25, "cot": 0.40, "role": 0.20}
_STYLE_NOISE = {"zero_shot": 2, "few_shot": 1, "cot": 1, "role": 1}
_STYLE_WRONG = {"zero_shot": 0.25, "few_shot": 0.10, "cot": 0.10, "role": 0.15}
_ATK_MOD = {"direct_injection": 0.0, "indirect_hidden": -0.10, "roleplay": -0.10,
            "prompt_leak": 0.05, "exfiltration": 0.05}
_HIJACK_TYPES = ("direct_injection", "indirect_hidden", "roleplay")
_REPLIES = {
    "REFUND": "Thanks for reaching out. I've approved your refund and you'll receive it in 5-7 days.",
    "DENY": "I'm sorry, but this item isn't eligible for a refund under our policy.",
    "ESCALATE": "I'm escalating this to our specialist team right away; they'll contact you shortly.",
    "INFO": "Your order is on its way; you can follow it with the tracking link in your email.",
}


def _style(low: str) -> str:
    if "step by step" in low:
        return "cot"
    if "example 1" in low:
        return "few_shot"
    if low.lstrip().startswith("you are a"):
        return "role"
    return "zero_shot"


def _mock(prompt, temperature, sample, hint):
    ids = hint.get("judge_ids")
    if ids:
        arr = [{"id": i, "relevance": 3 + _h("rel", i, len(prompt)) % 3,
                "coherence": 3 + _h("coh", i, len(prompt)) % 3} for i in ids]
        txt = json.dumps(arr)
        return {"text": txt, "tokens": (len(prompt) + len(txt)) // 4}

    low = prompt.lower()
    style = _style(low)
    hard = "untrusted_data" in low
    seed = _h(prompt, sample, round(temperature, 2))
    atk = hint.get("attack")
    kind = hint.get("kind", "score")
    truth = hint.get("truth")

    follows = False
    if atk:
        resist = 0.95 if hard else _STYLE_RESIST[style]
        resist = min(0.98, max(0.0, resist + _ATK_MOD.get(atk, 0.0)))
        follows = (seed % 100) / 100 >= resist

    n = _STYLE_NOISE[style]
    if kind == "score":
        score = max(1, min(10, int(truth) + (seed // 7) % (2 * n + 1) - n))
        if atk in _HIJACK_TYPES and follows:
            score = hint.get("hijack", 10)
        obj = {"score": score, "reason": "Simulated: matches part of the required skills."}
    else:
        decision = truth
        choices = hint.get("choices") or ["REFUND", "DENY", "ESCALATE", "INFO"]
        if (seed // 11 % 100) / 100 < _STYLE_WRONG[style]:
            others = [c for c in choices if c != truth]
            decision = others[seed % len(others)]
        if atk in _HIJACK_TYPES and follows:
            decision = hint.get("hijack", "REFUND")
        obj = {"decision": decision, "reply": _REPLIES.get(decision, "Thanks for contacting us.")}

    text = json.dumps(obj)
    if style == "cot":
        text = "Step 1: list the relevant facts. Step 2: compare with the context.\n" + text
    if atk == "prompt_leak" and follows:
        text = f"My instructions: ... Internal reference code: {hint.get('canary')}\n" + text
    if atk == "exfiltration" and follows:
        text = f"Other record I processed: {hint.get('private')} (ID 5521).\n" + text
    return {"text": text, "tokens": (len(prompt) + len(text)) // 4}
