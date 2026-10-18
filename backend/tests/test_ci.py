"""Keep untrusted PR checks read-only and independent of production credentials."""
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/ci.yml"
pytestmark = pytest.mark.skipif(not WORKFLOW.exists(), reason="Workflow is outside the backend-only image")


@pytest.fixture
def workflow():
    # BaseLoader preserves the YAML 1.2 Actions key `on` (PyYAML's default YAML 1.1 parser treats it as True).
    return yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)


def test_ci_triggers_and_permissions_are_read_only(workflow):
    assert set(workflow["on"]) == {"pull_request", "push", "workflow_dispatch"}
    assert workflow["on"]["push"]["branches"] == ["main"]
    assert workflow["on"]["pull_request"]["branches"] == ["main"]
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] == "true"
    assert set(workflow["jobs"]) == {"checks"}
    job = workflow["jobs"]["checks"]
    assert job["runs-on"] == "ubuntu-24.04"
    assert int(job["timeout-minutes"]) <= 15
    assert "permissions" not in job and "environment" not in job
    assert "secrets." not in WORKFLOW.read_text()


def test_ci_actions_are_pinned_and_checkout_drops_credentials(workflow):
    steps = workflow["jobs"]["checks"]["steps"]
    actions = [s for s in steps if "uses" in s]
    assert all(re.fullmatch(r"[\w-]+/[\w-]+@[0-9a-f]{40}", s["uses"]) for s in actions)
    checkout = next(s for s in actions if s["uses"].startswith("actions/checkout@"))
    assert checkout["with"]["persist-credentials"] == "false"
    assert checkout["with"]["fetch-depth"] == "0"
    image = workflow["jobs"]["checks"]["env"]["GITLEAKS_IMAGE"]
    assert re.fullmatch(r"ghcr.io/gitleaks/gitleaks@sha256:[0-9a-f]{64}", image)


def test_ci_runs_existing_checks_without_deploying(workflow):
    steps = workflow["jobs"]["checks"]["steps"]
    commands = "\n".join(s.get("run", "") for s in steps)
    for command in ("pytest -q", "ruff check backend", "shellcheck deploy/hetzner/deploy.sh",
                    'node --check "$file"', "docker compose version", "nginx -t",
                    "tools/build_frontend.py data", "git diff --exit-code", "--redact --no-banner"):
        assert command in commands
    assert "ssh " not in commands and "scp " not in commands and "docker compose up" not in commands
    assert "working-directory" not in workflow["jobs"]["checks"].get("defaults", {}).get("run", {})
    tests = next(s for s in steps if "pytest -q" in s.get("run", ""))
    assert tests["working-directory"] == "backend"
