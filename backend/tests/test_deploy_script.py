"""Exercise the deploy/rollback state machine with real Git and a fake Docker CLI."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy/hetzner/deploy.sh"
pytestmark = pytest.mark.skipif(not SCRIPT.exists() or os.name != "posix", reason="Linux operator script is outside the backend image")

DOCKER = r'''#!/usr/bin/env python3
import json, os, stat, sys
from pathlib import Path
args = sys.argv[1:]
state = Path(os.environ["FAKE_DOCKER_STATE"])
with (state / "calls.jsonl").open("a") as f:
    f.write(json.dumps(args) + "\n")
phase = os.environ.get("FAIL_PHASE", "")
if args[:3] == ["compose", "--profile", "*"]:
    args = ["compose", *args[3:]]

def fail_once(name):
    marker = state / ("failed-" + name)
    if phase == name and not marker.exists():
        marker.touch()
        raise SystemExit(1)

if args[:2] == ["compose", "config"]:
    config = {"services": {
        "backend": {"image": "research-rag-backend:latest", "environment": {"ACCESS_ENABLED": "true", "NEO4J_PASSWORD": "synthetic-secret-not-for-deployment"}},
        "seed": {"profiles": ["seed"]}, "frontend": {},
    }}
    if os.environ.get("EXPOSE_PORT"):
        config["services"]["backend"]["ports"] = ["8000:8000"]
    if os.environ.get("DISABLE_ACCESS"):
        config["services"]["backend"]["environment"]["ACCESS_ENABLED"] = "false"
    if os.environ.get("AUTO_SEED"):
        config["services"]["seed"]["profiles"] = []
    print(json.dumps(config))
elif args[:2] == ["compose", "ps"]:
    print("test-backend-container")
elif args[0] == "inspect":
    print("research-rag-backend:latest" if "Config.Image" in args[-1] else "sha256:previous-image")
elif args[:2] == ["compose", "build"]:
    fail_once("build")
elif args[0] == "run":
    path = Path("backend/app/__init__.py")
    assert stat.S_IMODE(path.stat().st_mode) == 0o644, "Root-only source copied into candidate"
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o755
    fail_once("import")
elif args[:2] == ["compose", "up"]:
    assert "--no-deps" in args and args[-1] in {"backend", "frontend"}
    if phase == "rollback-up" and args[-1] == "backend":
        raise SystemExit(1)
    fail_once("health" if args[-1] == "backend" else "frontend")
elif args[:2] == ["compose", "exec"]:
    if "nginx" in args:
        fail_once("nginx")
    elif "wget" in args:
        assert "http://127.0.0.1/api/health" in args
        if phase == "proxy":
            marker = state / "proxy-attempts"
            attempts = int(marker.read_text()) + 1 if marker.exists() else 1
            marker.write_text(str(attempts))
            if attempts <= 10:
                raise SystemExit(1)
    else:
        sys.stdin.read()
        marker = state / "counted"
        after = marker.exists()
        marker.touch()
        print(json.dumps({"collections": {"rr_documents": 999 if after and phase == "counts" else 1275}}))
        if after and phase == "env-changed":
            Path(".env").write_text("operator-updated-config\n")
elif args[:2] == ["compose", "logs"]:
    print("Synthetic backend diagnostic")
elif args[:2] != ["image", "tag"]:
    raise SystemExit("Unexpected Docker operation")
'''


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()


@pytest.fixture
def deployment(tmp_path):
    repo = tmp_path / "app"
    repo.mkdir()
    git(repo, "init", "--initial-branch=main")
    git(repo, "config", "user.email", "operator@example.org")
    git(repo, "config", "user.name", "Test operator")
    (repo / ".gitignore").write_text(".env\n.secrets/\ncompose.host.yml\nresearch/*\n!research/.gitkeep\n")
    for name, text in {"backend/app/__init__.py": "# previous\n", "frontend/index.html": "previous\n",
                       "docker/nginx.conf": "# previous\n", "research/.gitkeep": ""}.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    git(repo, "add", ".")
    git(repo, "commit", "-m", "test(deploy): add previous fixture")
    previous = git(repo, "rev-parse", "HEAD")
    (repo / "backend/app/__init__.py").write_text("# candidate\n")
    (repo / "frontend/new.js").write_text("// candidate\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "test(deploy): add candidate fixture")
    target = git(repo, "rev-parse", "HEAD")
    git(repo, "switch", "--detach", previous)
    (repo / ".env").write_text("SYNTHETIC_SECRET=never-print-this-test-value\n")
    (repo / ".env").chmod(0o600)
    (repo / "compose.host.yml").write_text("# private host override\n")
    secrets = repo / ".secrets"
    secrets.mkdir(mode=0o700)
    (secrets / "token").write_text("not-a-real-token")
    (secrets / "token").chmod(0o600)
    # Reproduce the restrictive checkout permissions that broke the first live deployment.
    (repo / "backend/app/__init__.py").chmod(0o600)
    (repo / "backend/app").chmod(0o700)
    (repo / "research").chmod(0o700)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(DOCKER)
    docker.chmod(0o755)
    operator_script = tmp_path / "deploy.sh"
    shutil.copyfile(SCRIPT, operator_script)
    state = tmp_path / "deployments"
    fake_state = tmp_path / "fake-docker"
    fake_state.mkdir()
    env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ["PATH"],
               ALITA_DEPLOY_STATE_DIR=str(state), FAKE_DOCKER_STATE=str(fake_state))
    return {"repo": repo, "script": operator_script, "state": state, "fake": fake_state,
            "env": env, "previous": previous, "target": target}


def run_deploy(d, *args, **env):
    return subprocess.run(["bash", str(d["script"]), *(args or [d["target"]])], cwd=d["repo"],
                          env=d["env"] | env, text=True, capture_output=True, timeout=30)


def calls(d):
    file = d["fake"] / "calls.jsonl"
    return [json.loads(line) for line in file.read_text().splitlines()] if file.exists() else []


def test_success_preserves_secrets_and_fixes_source_permissions(deployment):
    d = deployment
    env_before = (d["repo"] / ".env").read_bytes()
    result = run_deploy(d)
    assert result.returncode == 0, result.stderr
    assert git(d["repo"], "rev-parse", "HEAD") == d["target"]
    assert (d["state"] / "status").read_text().strip() == "DEPLOYED"
    backup = Path((d["state"] / "current-backup").read_text().strip())
    assert (backup / ".env").read_bytes() == env_before == (d["repo"] / ".env").read_bytes()
    for path in (backup, d["state"]):
        assert path.stat().st_mode & 0o777 == 0o700
    assert (backup / ".env").stat().st_mode & 0o777 == 0o600
    assert (d["repo"] / ".secrets/token").stat().st_mode & 0o777 == 0o600
    assert (d["repo"] / "research").stat().st_mode & 0o777 == 0o700
    assert "never-print" not in result.stdout + result.stderr
    assert "synthetic-secret" not in result.stdout + result.stderr
    assert all(c[-1] in {"backend", "frontend"} and "--no-deps" in c for c in calls(d) if c[:2] == ["compose", "up"])
    assert not any("down" in c or "push" in c for c in calls(d))


@pytest.mark.parametrize("phase", ["build", "import", "health", "frontend", "nginx", "proxy", "counts"])
def test_failures_restore_previous_revision_and_image(deployment, phase):
    d = deployment
    result = run_deploy(d, FAIL_PHASE=phase)
    assert result.returncode != 0
    assert git(d["repo"], "rev-parse", "HEAD") == d["previous"]
    assert (d["state"] / "status").read_text().strip() == "ROLLBACK_OK", result.stderr
    assert ["image", "tag", "sha256:previous-image", "research-rag-backend:latest"] in calls(d)
    if phase in {"build", "import"}:
        assert not any(c[:2] == ["compose", "up"] for c in calls(d))
    else:
        assert sum(c[:2] == ["compose", "up"] and c[-1] == "backend" for c in calls(d)) == 2
    assert "never-print" not in result.stdout + result.stderr


@pytest.mark.parametrize("phase", ["rollback-up", "env-changed"])
def test_incomplete_rollback_is_not_reported_as_success(deployment, phase):
    d = deployment
    result = run_deploy(d, FAIL_PHASE=phase)
    assert result.returncode != 0
    assert (d["state"] / "status").read_text().strip() == "ROLLBACK_NEEDS_ATTENTION"
    if phase == "env-changed":
        assert (d["repo"] / ".env").read_text() == "operator-updated-config\n"
        assert git(d["repo"], "rev-parse", "HEAD") == d["target"]


def test_dirty_checkout_is_left_untouched(deployment):
    d = deployment
    file = d["repo"] / "frontend/index.html"
    file.write_text("operator changes\n")
    assert run_deploy(d).returncode != 0
    assert file.read_text() == "operator changes\n"
    assert not calls(d)


@pytest.mark.parametrize("setting", ["EXPOSE_PORT", "DISABLE_ACCESS", "AUTO_SEED"])
def test_unsafe_configuration_is_rejected_before_checkout(deployment, setting):
    d = deployment
    result = run_deploy(d, **{setting: "1"})
    assert result.returncode != 0
    assert git(d["repo"], "rev-parse", "HEAD") == d["previous"]
    assert not any(c[:2] == ["compose", "build"] for c in calls(d))


def test_non_fast_forward_is_rejected(deployment):
    d = deployment
    git(d["repo"], "switch", "--detach", d["target"])
    result = run_deploy(d, d["previous"])
    assert result.returncode != 0
    assert git(d["repo"], "rev-parse", "HEAD") == d["target"]
    assert not calls(d)


def test_bundle_head_must_match_requested_commit(deployment):
    d = deployment
    bundle = d["repo"].parent / "main.bundle"
    git(d["repo"], "bundle", "create", str(bundle), "main")
    result = run_deploy(d, d["previous"], str(bundle))
    assert result.returncode != 0
    assert git(d["repo"], "rev-parse", "HEAD") == d["previous"]
    assert not calls(d)


def test_matching_local_bundle_deploys_without_remote_credentials(deployment):
    d = deployment
    bundle = d["repo"].parent / "main.bundle"
    git(d["repo"], "bundle", "create", str(bundle), "main")
    result = run_deploy(d, d["target"], str(bundle))
    assert result.returncode == 0, result.stderr
    assert git(d["repo"], "rev-parse", "HEAD") == d["target"]


def test_target_cannot_replace_private_host_configuration(deployment):
    d = deployment
    git(d["repo"], "switch", "--detach", d["target"])
    git(d["repo"], "add", "-f", "compose.host.yml")
    git(d["repo"], "commit", "-m", "test(deploy): track private configuration fixture")
    target = git(d["repo"], "rev-parse", "HEAD")
    git(d["repo"], "switch", "--detach", d["previous"])
    result = run_deploy(d, target)
    assert result.returncode != 0
    assert "must not track private" in result.stderr
    assert not calls(d)


def test_backup_directory_cannot_be_inside_checkout(deployment):
    d = deployment
    result = run_deploy(d, ALITA_DEPLOY_STATE_DIR=str(d["repo"] / "backups"))
    assert result.returncode != 0
    assert not (d["repo"] / "backups").exists()
    assert not calls(d)


def test_insecure_env_permissions_are_rejected(deployment):
    d = deployment
    (d["repo"] / ".env").chmod(0o644)
    result = run_deploy(d)
    assert result.returncode != 0
    assert "mode 0600" in result.stderr
    assert not calls(d)


def test_parallel_deploy_is_rejected(deployment):
    import fcntl
    d = deployment
    d["state"].mkdir()
    with (d["state"] / "lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = run_deploy(d)
    assert result.returncode != 0
    assert "Another deployment" in result.stderr
    assert not calls(d)


@pytest.mark.parametrize("revision", ["main", "v2.1.0", "--help", "abc"])
def test_revision_must_be_explicit_full_sha(deployment, revision):
    assert run_deploy(deployment, revision).returncode == 2
