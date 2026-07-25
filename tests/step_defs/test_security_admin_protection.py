"""
BDD steps for tests/features/security_admin_protection.feature.

Purely defensive/read-only: uses FastAPI's in-process TestClient (same
pattern as tests/test_level1.py) to confirm protected admin routes still
reject unauthenticated/invalid-token requests. Never supplies a real admin
token, never touches production data, makes no outbound network calls.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from pytest_bdd import scenarios, given, when, then, parsers
from fastapi.testclient import TestClient

from backend.main import app

scenarios("../features/security_admin_protection.feature")


@pytest.fixture
def admin_context():
    return {}


@given("a test client for the XFINLAB app", target_fixture="admin_context")
def given_admin_test_client():
    # Named given_* (not test_*) so pytest's own discovery doesn't also
    # pick this fixture function up as a standalone test case.
    return {"client": TestClient(app)}


@when(parsers.parse('an unauthenticated request is made to "{path}"'))
def call_without_token(admin_context, path):
    # No `token` query param at all -- FastAPI's own request validation
    # (token: str is a required param on every admin route) rejects this
    # before verify_admin() even runs.
    admin_context["response"] = admin_context["client"].get(path)


@when(parsers.parse('a request with an invalid token is made to "{path}"'))
def call_with_invalid_token(admin_context, path):
    # A syntactically-plausible but bogus token -- verify_token() will fail
    # to validate it and verify_admin() raises 401, never reaching any
    # actual user data.
    admin_context["response"] = admin_context["client"].get(
        path, params={"token": "not-a-real-admin-token"}
    )


@then("the response should be rejected with a 4xx status")
def assert_4xx(admin_context):
    status = admin_context["response"].status_code
    assert 400 <= status < 500, f"expected a 4xx rejection, got {status}"


@then("the rejection should not leak any user or stats data")
def assert_no_data_leak(admin_context):
    body = admin_context["response"].json()
    # The only acceptable shape for a rejected admin call is an error
    # envelope (FastAPI's {"detail": ...}) -- anything containing actual
    # stats/user fields would mean the guard let real data through.
    assert set(body.keys()) <= {"detail"}, f"unexpected fields in rejection body: {body.keys()}"
