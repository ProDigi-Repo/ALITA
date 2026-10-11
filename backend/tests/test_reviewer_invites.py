"""The operator tool must preserve secrets and store only invitation hashes."""
import hashlib
import importlib.util
import json
import re
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[2] / "tools/reviewer_invites.py"
pytestmark = pytest.mark.skipif(not TOOL.exists(), reason="Operator tools are outside the backend-only image")


def test_issue_and_revoke(tmp_path):
    spec = importlib.util.spec_from_file_location("reviewer_invites", TOOL)
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    env = tmp_path / ".env"
    original = "NEO4J_PASSWORD=existing-test-value\nADMIN_EMAILS=admin@example.org\nPUBLIC_ORIGIN=https://alita.example.org\n"
    env.write_text(original)
    result = tool.configure(env, origin="https://review.example.org", days=30, revoke=None)
    code = result.split("Secret code (shown once): ")[1]
    digest = hashlib.sha256(code.encode()).hexdigest()
    text = env.read_text()
    assert original in text and code not in text
    invites = json.loads(re.search(r"^REVIEW_INVITES=(.*)$", text, re.M)[1])
    assert digest in invites and len(code) == 32
    assert env.stat().st_mode & 0o777 == 0o600
    tool.configure(env, origin=None, days=30, revoke=digest[:12])
    assert "REVIEW_INVITES={}" in env.read_text()
    before = env.read_text()
    for origin in ["http://review.example.org", "https://alita.example.org", "https://review.example.org/path"]:
        with pytest.raises(ValueError):
            tool.configure(env, origin=origin, days=30, revoke=None)
        assert env.read_text() == before
