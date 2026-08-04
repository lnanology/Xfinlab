"""Growth OS Phase 7 (2026-08-04): thin wrapper around Google Cloud
Text-to-Speech's REST API -- the TTS backbone for the new Video Engine
(services/video_engine_service.py).

Why Google Cloud TTS specifically: verified free-tier terms explicitly
permit commercial use (1,000,000 characters/month free for WaveNet/
Neural2 voices, https://cloud.google.com/text-to-speech/pricing), same
"verify commercial-use terms before integrating" discipline this
codebase already applies to every other external data/API source (see
services/license_registry.py). Rejected alternatives: ElevenLabs's free
tier is only 10k chars/month (too small for even light daily use);
unofficial wrappers around Microsoft Edge's read-aloud feature (e.g.
"edge-tts") have no real API key or commercial license at all -- using
them would repeat the exact anti-pattern this codebase already fixed
once before (see growth/reddit_bot.py's 2026-07 User-Agent-spoofing
cleanup).

Auth: a plain Google Cloud API key (NOT a service-account JSON key --
that would need the heavier google-cloud-texttospeech SDK and a
different auth flow). Enable "Cloud Text-to-Speech API" on a GCP
project, create an API key restricted to that one API, and set it as
GOOGLE_TTS_API_KEY. Calling code must always go through is_available()
first and treat a missing key as "feature unavailable", never crash --
same honesty-over-fabrication posture as services/finbert_sentiment_
service.py and services/agent_debate_service.py's own is_available()
gates.
"""
import base64
import os
from typing import Optional

import requests

_API_KEY_ENV = "GOOGLE_TTS_API_KEY"
_ENDPOINT = "https://texttospeech.googleapis.com/v1/text:synthesize"
_TIMEOUT_SECONDS = 30

# Maps this site's own lang codes (services/i18n.py) to a real Google
# Cloud TTS voice. Only the languages the Video Engine actually narrates
# in need an entry here -- not all 47 site languages, since video
# narration is a much narrower, deliberately-scoped feature (same
# "backend-only copy stays narrower than the 47-language site-wide
# convention" precedent as content_repurpose_service.py's EN/ES-only
# multilang fan-out).
_VOICE_MAP = {
    "zh-HK": {"languageCode": "yue-HK", "name": "yue-HK-Standard-A"},
    "zh": {"languageCode": "yue-HK", "name": "yue-HK-Standard-A"},
    "en": {"languageCode": "en-US", "name": "en-US-Neural2-D"},
    "es": {"languageCode": "es-US", "name": "es-US-Neural2-B"},
}
_DEFAULT_LANG = "en"


def is_available() -> bool:
    return bool(os.environ.get(_API_KEY_ENV))


def synthesize(text: str, lang: str = _DEFAULT_LANG) -> dict:
    """Returns {"available": True, "audio_bytes": bytes, "format": "mp3"}
    on success, or {"available": False, "message": "..."} -- callers
    (services/video_engine_service.py) must check `available` and
    degrade gracefully, never assume audio_bytes is present."""
    if not is_available():
        return {"available": False, "message": "TTS not configured (GOOGLE_TTS_API_KEY missing)"}
    if not text or not text.strip():
        return {"available": False, "message": "No text to synthesize"}

    voice = _VOICE_MAP.get(lang, _VOICE_MAP[_DEFAULT_LANG])
    api_key = os.environ[_API_KEY_ENV]

    try:
        resp = requests.post(
            f"{_ENDPOINT}?key={api_key}",
            json={
                "input": {"text": text},
                "voice": voice,
                "audioConfig": {"audioEncoding": "MP3"},
            },
            timeout=_TIMEOUT_SECONDS,
        )
    except requests.RequestException as e:
        return {"available": False, "message": f"TTS request failed: {e}"}

    if resp.status_code != 200:
        return {"available": False, "message": f"TTS API error ({resp.status_code}): {resp.text[:200]}"}

    try:
        audio_b64 = resp.json().get("audioContent")
    except ValueError:
        return {"available": False, "message": "TTS API returned a non-JSON response"}

    if not audio_b64:
        return {"available": False, "message": "TTS API response had no audioContent"}

    return {"available": True, "audio_bytes": base64.b64decode(audio_b64), "format": "mp3"}
