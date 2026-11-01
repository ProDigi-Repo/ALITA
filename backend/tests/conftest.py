"""Tests never read the instance's real accounts (REQ-77): docker compose passes ACCOUNTS_FILE to the test service too."""
import os

for _var in ("ACCOUNTS_FILE", "ACCOUNT_SESSION_SECRET"):
    os.environ.pop(_var, None)
