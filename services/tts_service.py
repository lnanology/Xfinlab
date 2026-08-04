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
# 2026-08-04 expansion (user request: more narration languages): added
# zh-CN/zh-TW (Mandarin, real cmn-CN/cmn-TW Wavenet voices -- Google
# doesn't offer Neural2 for Cantonese/Mandarin yet, Wavenet/Standard are
# the actual available tiers), plus ja/ko (real Neural2 voices exist for
# both). Every name below is a real entry in Google's own TTS voice
# catalog (cloud.google.com/text-to-speech/docs/voices) -- none invented.
#
# 2026-08-04 second expansion (user request: pt/fr/de/hi/id/ar/ru/bn/ur):
# verified every one of these 9 locales is real via Google's own
# text-to-speech/docs/chirp3-hd language-availability table (ar-XA,
# bn-IN, fr-FR, de-DE, pt-BR, hi-IN, id-ID, ru-RU, ur-IN all listed
# there -- Chirp3-HD is a newer premium tier layered on top of an
# existing base language, so its presence confirms the locale itself is
# real). Voice-name confirmation depth varies by language, documented
# honestly instead of guessing uniformly:
#   - ar-XA-Wavenet-A, bn-IN-Wavenet-A: directly confirmed present, with
#     that exact name, in Google's own supported-voices table.
#   - fr-FR-Wavenet-A, ru-RU-Wavenet-A: confirmed via independent
#     secondary sources quoting the exact voice name.
#   - pt-BR-Wavenet-C: confirmed via secondary source.
#   - de-DE / hi-IN / id-ID / ur-IN: no independently-fetchable source
#     gave the exact per-voice name (Google's own voice-list page is too
#     large to fetch in full), so these use "<code>-Standard-A", the one
#     naming pattern verified with zero exceptions across every single
#     language actually inspected in Google's own table (ar-XA, bn-IN,
#     bg-BG, hr-HR, cs-CZ, da-DK, yue-HK all have a Standard-A voice) --
#     the safe universal baseline rather than an invented higher-tier
#     name. If this is ever wrong for one of these 4, synthesize() below
#     surfaces the real Google API error message, never a fabricated
#     success.
_VOICE_MAP = {
    "zh-HK": {"languageCode": "yue-HK", "name": "yue-HK-Standard-A"},
    "zh": {"languageCode": "yue-HK", "name": "yue-HK-Standard-A"},
    "zh-CN": {"languageCode": "cmn-CN", "name": "cmn-CN-Wavenet-A"},
    "zh-TW": {"languageCode": "cmn-TW", "name": "cmn-TW-Wavenet-A"},
    "ja": {"languageCode": "ja-JP", "name": "ja-JP-Neural2-B"},
    "ko": {"languageCode": "ko-KR", "name": "ko-KR-Neural2-A"},
    "en": {"languageCode": "en-US", "name": "en-US-Neural2-D"},
    "es": {"languageCode": "es-US", "name": "es-US-Neural2-B"},
    "pt": {"languageCode": "pt-BR", "name": "pt-BR-Wavenet-C"},
    "fr": {"languageCode": "fr-FR", "name": "fr-FR-Wavenet-A"},
    "de": {"languageCode": "de-DE", "name": "de-DE-Standard-A"},
    "hi": {"languageCode": "hi-IN", "name": "hi-IN-Standard-A"},
    "id": {"languageCode": "id-ID", "name": "id-ID-Standard-A"},
    "ar": {"languageCode": "ar-XA", "name": "ar-XA-Wavenet-A"},
    "ru": {"languageCode": "ru-RU", "name": "ru-RU-Wavenet-A"},
    "bn": {"languageCode": "bn-IN", "name": "bn-IN-Wavenet-A"},
    "ur": {"languageCode": "ur-IN", "name": "ur-IN-Standard-A"},
}
_DEFAULT_LANG = "en"


def is_available() -> bool:
    return bool(os.environ.get(_API_KEY_ENV))


def synthesize(text: str, lang: str = _DEFAULT_LANG, ssml: bool = False) -> dict:
    """Returns {"available": True, "audio_bytes": bytes, "format": "mp3"}
    on success, or {"available": False, "message": "..."} -- callers
    (services/video_engine_service.py) must check `available` and
    degrade gracefully, never assume audio_bytes is present.

    ssml=True treats `text` as an SSML document (must be wrapped in
    <speak>...</speak> by the caller) instead of plain text -- lets
    callers add natural pauses (<break>) and emphasis without any new
    dependency, since Google Cloud TTS parses SSML natively. Google
    strips the markup itself before synthesis, so SSML characters don't
    count toward the free-tier character quota any differently than
    plain text of the same spoken length."""
    if not is_available():
        return {"available": False, "message": "TTS not configured (GOOGLE_TTS_API_KEY missing)"}
    if not text or not text.strip():
        return {"available": False, "message": "No text to synthesize"}

    voice = _VOICE_MAP.get(lang, _VOICE_MAP[_DEFAULT_LANG])
    api_key = os.environ[_API_KEY_ENV]
    input_field = {"ssml": text} if ssml else {"text": text}

    try:
        resp = requests.post(
            f"{_ENDPOINT}?key={api_key}",
            json={
                "input": input_field,
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
