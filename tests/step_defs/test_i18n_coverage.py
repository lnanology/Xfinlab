"""
BDD steps for tests/features/i18n_coverage.feature.

Read-only regression guard: imports services/i18n.py and inspects its
TRANSLATIONS dict in memory. Makes no network calls, touches no database,
modifies no files.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from services.i18n import TRANSLATIONS

scenarios("../features/i18n_coverage.feature")


@pytest.fixture
def i18n_context():
    return {}


@given("the i18n translation table is loaded", target_fixture="i18n_context")
def i18n_table_loaded():
    assert isinstance(TRANSLATIONS, dict)
    assert len(TRANSLATIONS) > 0
    return {"translations": TRANSLATIONS}


@when("each language's key set is compared against the union of all keys")
def compare_key_sets(i18n_context):
    translations = i18n_context["translations"]
    all_keys = set()
    for keys in translations.values():
        all_keys |= set(keys.keys())

    missing = {}
    for lang, keys in translations.items():
        gap = all_keys - set(keys.keys())
        if gap:
            missing[lang] = gap

    i18n_context["missing"] = missing


@then("no language should be missing any key that another language has")
def assert_no_missing_keys(i18n_context):
    missing = i18n_context["missing"]
    if missing:
        # Keep the failure message short and actionable: which language(s),
        # how many keys, and a small sample -- not a full dump of every key,
        # since that list can get long once a real gap is found.
        detail = "; ".join(
            f"{lang}: {len(keys)} missing (e.g. {sorted(keys)[:5]})"
            for lang, keys in sorted(missing.items())
        )
        pytest.fail(f"i18n coverage gap found in {len(missing)} language(s): {detail}")


@then(parsers.parse("the translation table should contain at least {count:d} languages"))
def assert_min_language_count(i18n_context, count):
    assert len(i18n_context["translations"]) >= count


@then(parsers.parse('English ("{lang}") should be present as the baseline language'))
def assert_english_present(i18n_context, lang):
    assert lang in i18n_context["translations"]
    assert len(i18n_context["translations"][lang]) > 0
