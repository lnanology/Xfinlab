# 2026-07-26: BDD regression guard for the exact bug class fixed twice in
# recent sessions -- an i18n key (pair_input_label, hero_ask_ai_placeholder,
# etc.) gets added for a couple of languages when a feature ships, but never
# filled in for the rest, so most non-English/non-Chinese users silently see
# raw fallback English text. This scenario re-checks the whole translation
# table on every push instead of waiting for a user to screenshot the gap.
#
# Read-only: only imports and inspects services/i18n.py's TRANSLATIONS dict.
# Never modifies data, calls no external API, touches no user data.

Feature: i18n translation coverage
  As the XFINLAB team, we want every UI text key to be translated into all
  supported languages, so users never see raw English/Chinese fallback text
  in an otherwise-translated interface.

  Scenario: Every language block exposes the same set of keys
    Given the i18n translation table is loaded
    When each language's key set is compared against the union of all keys
    Then no language should be missing any key that another language has

  Scenario: The supported-language list matches what the site advertises
    Given the i18n translation table is loaded
    Then the translation table should contain at least 46 languages
    And English ("en") should be present as the baseline language
