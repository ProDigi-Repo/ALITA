"""Check the effective production Compose configuration, not just the override text."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_hetzner_compose_has_no_origin_bypass():
    if not shutil.which("docker") or subprocess.run(["docker", "compose", "version"], capture_output=True).returncode:
        pytest.skip("Docker Compose not installed")
    env = dict(os.environ, NEO4J_PASSWORD="test-password-not-for-deployment", ACCESS_ENABLED="false",
               ACCESS_TEAM_DOMAIN="alita-test.cloudflareaccess.com", ACCESS_AUDIENCE="test-audience",
               PUBLIC_ORIGIN="https://alita.example.org", ADMIN_EMAILS="admin@example.org")
    result = subprocess.run(["docker", "compose", "--env-file", "/dev/null", "-f", "docker-compose.yml",
                             "-f", "deploy/hetzner/docker-compose.hetzner.yml", "--profile", "*", "config", "--format", "json"],
                            cwd=ROOT, env=env, capture_output=True, text=True, check=True)
    services = json.loads(result.stdout)["services"]
    assert all(not service.get("ports") for service in services.values())
    assert services["backend"]["environment"]["ACCESS_ENABLED"] == "true"
    assert services["backend"]["environment"]["NEO4J_PASSWORD"] == env["NEO4J_PASSWORD"]
    assert "seed" in services["seed"]["profiles"]
    assert set(services["cloudflared"]["networks"]) == {"edge"}
    assert set(services["frontend"]["networks"]) == {"edge", "app"}
    for service in ["neo4j", "qdrant"]:
        assert set(services[service]["networks"]) == {"data"}
    assert services["cloudflared"]["secrets"][0]["source"] == "cloudflare_tunnel_token"
