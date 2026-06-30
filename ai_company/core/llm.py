"""
統一LLMインターフェース
Gemini優先、429/クォータ超過時にOllamaへ自動フォールバック
"""
import asyncio
import json
import sys
import time as _time
import urllib.request
from pathlib import Path

from google import genai
from google.genai import types

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import GEMINI_API_KEY, MODELS, MAX_TOKENS, OLLAMA_URL, OLLAMA_MODEL

# ── グローバル状態 ──────────────────────────────────────────
_gemini_client: genai.Client | None = None
_ollama_until: float = 0.0   # この時刻まで Ollama 優先（10分後に Gemini 再試行）


def _get_gemini_client() -> genai.Client:
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    return _gemini_client


def is_using_ollama() -> bool:
    return _time.time() < _ollama_until or not GEMINI_API_KEY


def _switch_to_ollama(minutes: int = 3):
    global _ollama_until
    _ollama_until = _time.time() + minutes * 60
    print(f"[LLM] ⚡ Geminiクォータ超過 → Ollama ({OLLAMA_MODEL}) に{minutes}分フォールバック")


def _reset_ollama_fallback():
    global _ollama_until
    _ollama_until = 0.0


# ── Gemini 呼び出し ─────────────────────────────────────────

def _gemini_sync(prompt: str, system: str, model: str, max_tokens: int) -> str:
    # thinking_config は無効化（クォータを大量消費するため）
    response = _get_gemini_client().models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            temperature=0.35,
        ),
    )
    return response.text


# ── Ollama 呼び出し ─────────────────────────────────────────

def _ollama_sync(prompt: str, system: str) -> str:
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {"temperature": 0.35},
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as r:   # 5分
            return json.loads(r.read())["response"]
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Ollamaに接続できません ({OLLAMA_URL})。"
            f" `ollama serve` を起動し、`ollama pull {OLLAMA_MODEL}` でモデルをダウンロードしてください。"
            f" 詳細: {e}"
        )


# ── 統一インターフェース ────────────────────────────────────

async def call_llm(
    prompt: str,
    system: str = "あなたは優秀なAIアシスタントです。",
    tier: str = "worker",
) -> str:
    """
    LLMを呼び出す。Gemini優先、失敗時はOllamaへ自動切替（10分後に Gemini 再試行）。
    tier: "ceo" | "manager" | "worker"
    """
    loop = asyncio.get_event_loop()

    if is_using_ollama():
        return await loop.run_in_executor(None, lambda: _ollama_sync(prompt, system))

    model     = MODELS.get(tier, MODELS["worker"])
    max_tok   = MAX_TOKENS.get(tier, 2048)

    for attempt in range(4):
        try:
            return await loop.run_in_executor(
                None, lambda: _gemini_sync(prompt, system, model, max_tok)
            )
        except Exception as e:
            err = str(e)
            is_quota = "429" in err or "RESOURCE_EXHAUSTED" in err
            is_overloaded = "503" in err or ("UNAVAILABLE" in err and "503" not in err)
            # クォータ詳細をログに出力
            hint = ""
            if "PerDay" in err:
                hint = " [日次上限]"
            elif "PerMinute" in err or "retryDelay" in err:
                hint = " [分次上限]"
            elif is_overloaded:
                hint = " [503高需要]"

            if (is_quota or is_overloaded) and attempt < 2:
                wait = 60 * (2 ** attempt)   # 60s → 120s（503にも対応）
                print(f"[LLM] Gemini一時エラー{hint} → {wait}秒後リトライ ({attempt+1}/2)")
                await asyncio.sleep(wait)
            elif is_quota:
                _switch_to_ollama(minutes=3)
                try:
                    return await loop.run_in_executor(None, lambda: _ollama_sync(prompt, system))
                except RuntimeError:
                    # Ollama未起動: Gemini制限が解除されるまで待機して再試行
                    wait_sec = max(0.0, _ollama_until - _time.time())
                    if wait_sec > 1:
                        print(f"[LLM] Ollama未起動 → Gemini制限解除まで{int(wait_sec)}秒待機後に再試行")
                        await asyncio.sleep(wait_sec)
                        _reset_ollama_fallback()
                        return await loop.run_in_executor(
                            None, lambda: _gemini_sync(prompt, system, model, max_tok)
                        )
                    raise
            elif is_overloaded:
                # 503はOllama不要、3分待って最終リトライ
                print("[LLM] Gemini 503高需要 → 3分後に最終リトライ")
                await asyncio.sleep(180)
                return await loop.run_in_executor(
                    None, lambda: _gemini_sync(prompt, system, model, max_tok)
                )
            else:
                raise

    raise RuntimeError("LLM呼び出し失敗（リトライ超過）")
