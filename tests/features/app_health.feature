# 2026-07-26: BDD-style rewrite of the existing tests/test_level1.py root/
# docs smoke test, kept as a small, readable example of the Given-When-Then
# format for anyone (including non-engineers) reviewing test coverage. Not
# a replacement for test_level1.py, which stays as the hard CI gate.

Feature: Application health
  As the XFINLAB team, we want the deployed app to always boot and serve
  its root and docs routes, so a broken deploy is caught before it reaches
  production ("keep go build").

  Scenario: The app root responds successfully
    Given a test client for the XFINLAB app
    When a request is made to "/"
    Then the response status should be 200

  Scenario: The API docs page responds successfully
    Given a test client for the XFINLAB app
    When a request is made to "/docs"
    Then the response status should be 200
