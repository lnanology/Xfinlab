import os
from dotenv import load_dotenv

load_dotenv()

AI_PROVIDER = os.getenv("AI_PROVIDER", "groq")

# Best-effort token-usage capture for the monthly AI-token quota
# (services/token_quota_service.py). FastAPI/Starlette runs each request
# in its own async task on a single event loop thread and every call site
# here awaits the provider call synchronously before reading this value
# back out (see api/*.py: get_ai_response(...) followed immediately by
# record_ai_token_usage()) -- there's no `await` in between that could
# let another request's call interleave and overwrite it first. This is
# NOT safe if these functions were ever called from multiple OS threads
# concurrently for the same slot, so it's approximate metering, not
# billing-grade precision.
_LAST_USAGE_TOKENS = {"value": 0}


def get_last_usage_tokens() -> int:
    """Token count (prompt+completion) from the most recent
    get_ai_response()/get_vision_response() call. 0 if the provider's
    response didn't include usage data (e.g. DeepSeek error responses)."""
    return _LAST_USAGE_TOKENS["value"]


def set_last_usage_tokens(total: int) -> None:
    """2026-07-20 addition: lets a caller that makes SEVERAL sequential
    get_ai_response() calls for one logical "feature run" (e.g.
    services/agent_debate_service.py's run_debate(), which makes 4 calls
    -- 3 personas + 1 arbiter) overwrite this shared slot with the real
    summed total across all of them, right before returning. Without
    this, the site's usual pattern of "call get_ai_response(), then once
    record_ai_token_usage()" would only ever bill the LAST of the 4
    calls, silently dropping the other 3's real cost. Same shared-slot
    concurrency caveat as get_last_usage_tokens() applies here."""
    _LAST_USAGE_TOKENS["value"] = total


def get_ai_response(prompt: str, max_tokens: int = 1000, provider: str = None) -> str:
    """
    Universal AI router - switch provider via AI_PROVIDER env var, or pass
    `provider` explicitly to override it for one call (added 2026-07-18
    for features like services/agent_debate_service.py that deliberately
    always want DeepSeek regardless of the site's global default -- a
    multi-call feature like a debate should stay on the specifically
    confirmed-cheap provider, not silently ride whatever AI_PROVIDER
    happens to be set to).

    Supported:
        groq     → Groq (free, fast)
        deepseek → DeepSeek V4 Flash, served via DeepInfra (cheap) --
                   needs DEEPINFRA_API_KEY, not a DeepSeek-issued key;
                   see _deepseek()'s docstring for why
        claude   → Anthropic Claude (best quality)

    Args:
        prompt: The prompt to send
        max_tokens: Max response tokens
        provider: optional override ("groq"/"deepseek"/"claude"); defaults
            to the AI_PROVIDER env var when omitted

    Returns:
        str: AI response text
    """
    provider = (provider or AI_PROVIDER).lower()
    _LAST_USAGE_TOKENS["value"] = 0

    if provider == "groq":
        return _groq(prompt, max_tokens)
    elif provider == "deepseek":
        return _deepseek(prompt, max_tokens)
    elif provider == "claude":
        return _claude(prompt, max_tokens)
    else:
        raise ValueError(f"Unknown AI provider: {provider}. Use groq / deepseek / claude")


VISION_PROVIDER = os.getenv("VISION_PROVIDER", "gemini")


def get_vision_response(prompt: str, image_base64: str, mime_type: str = "image/jpeg", max_tokens: int = 1000) -> str:
    """
    Analyze an image with a vision-capable model.

    Switch provider via VISION_PROVIDER env var:
        gemini → Google Gemini (recommended — much better at reading exact
                 numbers/axis labels off charts than Groq's preview models)
        groq   → Groq (fast/cheap, but weaker at precise number-reading)

    Args:
        prompt: The text instructions/question about the image
        image_base64: Base64-encoded image data (no data: prefix)
        mime_type: Image MIME type (image/jpeg, image/png, image/webp)
        max_tokens: Max response tokens

    Returns:
        str: AI response text
    """
    provider = VISION_PROVIDER.lower()
    _LAST_USAGE_TOKENS["value"] = 0

    if provider == "gemini":
        return _gemini_vision(prompt, image_base64, mime_type, max_tokens)
    elif provider == "groq":
        return _groq_vision(prompt, image_base64, mime_type, max_tokens)
    else:
        raise ValueError(f"Unknown VISION_PROVIDER: {provider}. Use gemini / groq")


def _gemini_vision(prompt: str, image_base64: str, mime_type: str, max_tokens: int) -> str:
    import requests

    api_key = os.getenv("GEMINI_API_KEY")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={api_key}"
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": mime_type, "data": image_base64}},
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": max_tokens,
            # Gemini 2.5 Flash uses hidden "thinking" tokens by default, which
            # count against maxOutputTokens and were eating the whole budget
            # before any visible JSON got written — hence truncated output.
            # Disable thinking so all tokens go to the actual answer.
            "thinkingConfig": {"thinkingBudget": 0},
            # Force strict JSON output — the API guarantees a syntactically
            # valid, complete JSON object instead of markdown-wrapped or
            # truncated free-form text.
            "responseMimeType": "application/json",
        },
    }
    res = requests.post(url, json=payload, timeout=60)
    res.raise_for_status()
    data = res.json()
    usage = data.get("usageMetadata", {}).get("totalTokenCount")
    if usage:
        _LAST_USAGE_TOKENS["value"] = usage
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def _groq_vision(prompt: str, image_base64: str, mime_type: str, max_tokens: int) -> str:
    from groq import Groq
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    response = client.chat.completions.create(
        # Groq deprecated llama-4-scout/llama-3.2-vision in June 2026.
        # qwen/qwen3.6-27b is the current vision-capable model (preview tier).
        model="qwen/qwen3.6-27b",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{image_base64}"},
                    },
                ],
            }
        ],
        temperature=0.3,
        max_tokens=max_tokens,
    )
    if getattr(response, "usage", None) and response.usage.total_tokens:
        _LAST_USAGE_TOKENS["value"] = response.usage.total_tokens
    return response.choices[0].message.content.strip()


def _groq(prompt: str, max_tokens: int) -> str:
    """
    2026-07-20 fix: "AI文字解讀" (chart-analysis.html's commentary feature,
    which calls this via the AI_PROVIDER default) was silently returning
    empty text. Root cause: openai/gpt-oss-120b is a REASONING model --
    per Groq's own docs (console.groq.com/docs/reasoning), its internal
    chain-of-thought tokens count against the same max_completion_tokens
    budget as the visible answer, and Groq's community forum documents
    this model returning a fully empty message.content when that budget
    is too low (worse the lower it is) -- the model spends the whole
    budget "thinking" and never gets to write a visible answer. This
    codebase's chart-analysis.html commentary call used max_tokens=400,
    well under Groq's own recommended 1024+ default for this model.

    Fix: (1) reasoning_effort="low" -- per Groq's docs this specifically
    reduces how many tokens gpt-oss-120b spends on hidden reasoning,
    leaving more of the budget for the actual visible answer; (2) a
    700-token floor on top of whatever the caller asked for, since even
    "low" reasoning effort still needs headroom beyond a short answer's
    own length; (3) max_completion_tokens is the parameter name Groq's
    current docs use for reasoning-aware models (max_tokens still
    appeared to be accepted before, but wasn't reliably budgeting
    reasoning tokens against the callers' request).
    """
    from groq import Groq
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    response = client.chat.completions.create(
        # llama-3.1-8b-instant was deprecated by Groq on 2026-06-17.
        # openai/gpt-oss-120b is Groq's recommended replacement.
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_completion_tokens=max(max_tokens, 700),
        reasoning_effort="low",
    )
    if getattr(response, "usage", None) and response.usage.total_tokens:
        _LAST_USAGE_TOKENS["value"] = response.usage.total_tokens
    content = (response.choices[0].message.content or "").strip()
    if not content:
        # Defensive fallback: if the model still burned the whole budget
        # on reasoning (shouldn't happen with the above, but Groq's own
        # bug reports show it can still occur), fail loudly instead of
        # silently returning "" -- the caller's except-block then shows
        # a real error message instead of a blank result.
        raise ValueError("Groq gpt-oss-120b returned empty content (reasoning likely consumed the token budget)")
    return content


def _deepseek(prompt: str, max_tokens: int, _retry: int = 1) -> str:
    """
    2026-07-20: switched this provider's backing host from DeepSeek's own
    API (api.deepseek.com) to DeepInfra (api.deepinfra.com) -- the account
    only has a DeepInfra API key, not an official DeepSeek one, and
    DeepInfra hosts the same deepseek-ai/DeepSeek-V4-Flash model behind an
    OpenAI-compatible chat-completions endpoint, so this is a same-model
    swap of the transport, not a quality/capability downgrade. Auth is now
    DEEPINFRA_API_KEY (a DeepSeek-issued DEEPSEEK_API_KEY will NOT work
    against DeepInfra's endpoint -- the two are separate accounts/keys).

    DeepInfra also publishes no hard rate-limit/SLA guarantee for this
    model tier, so the same retry-once-after-backoff behavior as the
    previous direct-DeepSeek integration is kept (matches the "good
    citizen + graceful degradation" convention services/outbound_http.py
    uses for scraped sources).
    """
    import time
    import requests
    headers = {
        "Authorization": f"Bearer {os.getenv('DEEPINFRA_API_KEY')}",
        "Content-Type": "application/json"
    }
    payload = {
        # DeepInfra's model catalog id for this model (NOT the same string
        # DeepSeek's own API used -- see https://deepinfra.com/deepseek-ai/
        # DeepSeek-V4-Flash/api for the current reference). Same underlying
        # model as the previous "deepseek-v4-flash" on api.deepseek.com.
        "model": "deepseek-ai/DeepSeek-V4-Flash",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.3
    }
    res = requests.post("https://api.deepinfra.com/v1/openai/chat/completions",
                        json=payload, headers=headers, timeout=30)
    if res.status_code in (429, 503) and _retry > 0:
        time.sleep(3)
        return _deepseek(prompt, max_tokens, _retry=_retry - 1)
    data = res.json()
    usage = data.get("usage", {}).get("total_tokens")
    if usage:
        _LAST_USAGE_TOKENS["value"] = usage
    return data["choices"][0]["message"]["content"].strip()


def _claude(prompt: str, max_tokens: int) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )
    if getattr(message, "usage", None):
        _LAST_USAGE_TOKENS["value"] = (message.usage.input_tokens or 0) + (message.usage.output_tokens or 0)
    return message.content[0].text.strip()
