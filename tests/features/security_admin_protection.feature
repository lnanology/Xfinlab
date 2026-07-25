# 2026-07-26: read-only security regression guard. This scenario only
# CONFIRMS the existing admin auth gate (api/admin.py's verify_admin(),
# hardened in an earlier session -- task #182) still rejects unauthenticated
# and invalid-token requests. It never supplies a real admin token, never
# reads or writes any secret, and never attempts to bypass or weaken the
# gate -- it exists purely to catch a future accidental regression (e.g. a
# new admin route added without calling verify_admin()) before it reaches
# production.

Feature: Admin endpoint protection
  As the XFINLAB team, we want every /api/admin/* endpoint to reject
  requests that don't present a valid admin token, so a regression can
  never silently expose user data or admin controls.

  Scenario: Admin stats endpoint rejects a request with no token at all
    Given a test client for the XFINLAB app
    When an unauthenticated request is made to "/api/admin/stats"
    Then the response should be rejected with a 4xx status

  Scenario: Admin stats endpoint rejects a request with an invalid token
    Given a test client for the XFINLAB app
    When a request with an invalid token is made to "/api/admin/stats"
    Then the response should be rejected with a 4xx status
    And the rejection should not leak any user or stats data
