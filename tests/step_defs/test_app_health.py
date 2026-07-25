"""
BDD steps for tests/features/app_health.feature.

Read-only, in-process (no live network call): boots the same FastAPI app
object Railway runs (backend.main.app) via TestClient, same pattern as
tests/test_level1.py.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from pytest_bdd import scenarios, given, when, then, parsers
from fastapi.testclient import TestClient

from backend.main import app

scenarios("../features/app_health.feature")


@pytest.fixture
def health_context():
    return {}


@given("a test client for the XFINLAB app", target_fixture="health_context")
def given_health_test_client():
    return {"client": TestClient(app)}


@when(parsers.parse('a request is made to "{path}"'))
def make_request(health_context, path):
    health_context["response"] = health_context["client"].get(path)


@then(parsers.parse("the response status should be {code:d}"))
def assert_status(health_context, code):
    assert health_context["response"].status_code == code
