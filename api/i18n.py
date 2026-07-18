import os
import requests
from fastapi import APIRouter, Request
from services.i18n import get_translations, detect_language_from_country, SUPPORTED_LANGUAGES
from services.request_ip import get_client_ip

router = APIRouter()


def get_country_from_ip(ip: str) -> str:
    """Get country code from IP using free API"""
    try:
        if ip in ("127.0.0.1", "localhost", "::1"):
            return "HK"  # Default for local
        res = requests.get(f"https://ipapi.co/{ip}/country/", timeout=5)
        if res.status_code == 200:
            return res.text.strip()
    except:
        pass
    return "US"


@router.get("/i18n/detect")
def detect_language(request: Request):
    """Detect user language from IP"""
    ip = get_client_ip(request)  # was a local, near-duplicate copy of this logic -- now shared, see services/request_ip.py
    country = get_country_from_ip(ip)
    lang = detect_language_from_country(country)
    translations = get_translations(lang)

    return {
        "ip": ip,
        "country": country,
        "language": lang,
        "language_name": SUPPORTED_LANGUAGES.get(lang, "English"),
        "translations": translations,
        "supported_languages": SUPPORTED_LANGUAGES
    }


@router.get("/i18n/{lang}")
def get_language(lang: str):
    """Get translations for specific language"""
    translations = get_translations(lang)
    return {
        "language": lang,
        "translations": translations,
        "supported_languages": SUPPORTED_LANGUAGES
    }
