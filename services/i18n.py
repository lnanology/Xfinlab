"""Internationalization Module - Handles language translation and loading"""

import json
from pathlib import Path
from typing import Dict


class I18N:
    """Manages language translations"""

    def __init__(self):
        self.translations: Dict[str, Dict[str, str]] = {}
        self.load_languages()

    def load_languages(self) -> None:
        """Load all translation files"""
        locale_path = Path("locales")
        for lang_file in locale_path.glob("*.json"):
            with open(lang_file, "r", encoding="utf-8") as f:
                self.translations[lang_file.stem] = json.load(f)

    def translate(self, key: str, lang: str = "en") -> str:
        """
        Translate a key to specified language

        Args:
            key (str): Translation key
            lang (str): Language code (default: 'en')

        Returns:
            str: Translated text
        """
        return self.translations.get(lang, {}).get(key, key)

    def get_supported_languages(self) -> List[str]:
        """
        Get list of supported languages

        Returns:
            List[str]: List of language codes
        """
        return list(self.translations.keys())


# Example usage
if __name__ == "__main__":
    i18n = I18N()
    print(i18n.translate("market_risk_radar", "ja"))
