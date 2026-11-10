"""Tests never read the instance's real accounts (REQ-77): docker compose passes ACCOUNTS_FILE to the test service too."""
import os

for _var in ("ACCOUNTS_FILE", "ACCOUNT_SESSION_SECRET"):
    os.environ.pop(_var, None)

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_document_cache():
    """REQ-83: the document cache must not carry one test's fake index into the next."""
    from app import store
    store.invalidate_cache()
    yield
    store.invalidate_cache()
