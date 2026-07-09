import os
from dotenv import load_dotenv

load_dotenv()

AI_PROVIDER = os.getenv("AI_PROVIDER", "groq")


def get_ai_response(prompt: str, max_tokens: int = 1000) -> str:
    """
    Universal AI router - switch provider via AI_PROVIDER env var

    Supported:
        groq     → Groq (free, fast)
        deepseek → DeepSeek (cheap)
        claude   → Anthropic Claude (best quality)

    Args:
        prompt: The prompt to send
        max_tokens: Max response tokens

    Returns:
        str: AI response text
    """
    provider = AI_PROVIDER.lower()

    if provider == "groq":
        return _groq(prompt, max_tokens)
    elif provider == "deepseek":
        return _deepseek(prompt, max_tokens)
    elif provider == "claude":
        return _claude(prompt, max_tokens)
    else:
        raise ValueError(f"Unknown AI provider: {provider}. Use groq / deepseek / claude")


def get_vision_response(prompt: str, image_base64: str, mime_type: str = "image/jpeg", max_tokens: int = 1000) -> str:
    """
    Analyze an image with a vision-capable model.

    Args:
        prompt: The text instructions/question about the image
        image_base64: Base64-encoded image data (no data: prefix)
        mime_type: Image MIME type (image/jpeg, image/png, image/webp)
        max_tokens: Max response tokens

    Returns:
        str: AI response text
    """
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
    return response.choices[0].message.content.strip()


def _groq(prompt: str, max_tokens: int) -> str:
    from groq import Groq
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    response = client.chat.completions.create(
        # llama-3.1-8b-instant was deprecated by Groq on 2026-06-17.
        # openai/gpt-oss-120b is Groq's recommended replacement.
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=max_tokens
    )
    return response.choices[0].message.content.strip()


def _deepseek(prompt: str, max_tokens: int) -> str:
    import requests
    headers = {
        "Authorization": f"Bearer {os.getenv('DEEPSEEK_API_KEY')}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.3
    }
    res = requests.post("https://api.deepseek.com/v1/chat/completions",
                        json=payload, headers=headers, timeout=30)
    return res.json()["choices"][0]["message"]["content"].strip()


def _claude(prompt: str, max_tokens: int) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text.strip()
