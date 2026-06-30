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


def _groq(prompt: str, max_tokens: int) -> str:
    from groq import Groq
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
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
