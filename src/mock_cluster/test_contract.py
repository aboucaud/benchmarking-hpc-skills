from __future__ import annotations

import yaml

from .substrate import (
    BASE_COMPOSE,
    DEVICE_AUTH_VOLUME,
    DEVICE_COMPOSE,
    OVERLAY_COMPOSE,
    DockerSlurmSubstrate,
)


def test_overlay_keeps_secrets_and_evidence_out_of_agent_services():
    overlay = yaml.safe_load(OVERLAY_COMPOSE.read_text())
    services = overlay["services"]

    for name in ("login", "c1", "c2", "c3"):
        service = services[name]
        assert service["networks"] == ["benchmark_internal"]
        assert not any(
            "observer_evidence" in str(volume)
            or "docker.sock" in str(volume)
            for volume in service.get("volumes", [])
        )
        assert "OPENAI_API_KEY" not in str(service.get("environment", {}))

    gateway = services["credential-gateway"]
    assert "OPENAI_API_KEY" in gateway["environment"]
    assert set(gateway["networks"]) == {"benchmark_internal", "gateway_egress"}
    assert "observer_evidence:/observer" in gateway["volumes"]


def test_only_support_services_mount_observer_evidence():
    overlay = yaml.safe_load(OVERLAY_COMPOSE.read_text())
    mounted = {
        name
        for name, service in overlay["services"].items()
        if "observer_evidence" in str(service.get("volumes", []))
    }

    assert mounted == {"observer", "credential-gateway"}


def test_ssh_gateway_exposes_only_fixed_login_forwarder():
    overlay = yaml.safe_load(OVERLAY_COMPOSE.read_text())
    gateway = overlay["services"]["ssh-gateway"]

    assert gateway["ports"] == [
        "127.0.0.1:${MOCK_CLUSTER_SSH_PORT:-2223}:2222"
    ]
    assert gateway["environment"] == {"MOCK_CLUSTER_SSH_UPSTREAM": "login"}
    assert not gateway.get("volumes")
    assert set(gateway["networks"]) == {
        "benchmark_internal",
        "gateway_egress",
    }


def test_device_overlay_is_the_only_login_egress_exception():
    device = yaml.safe_load(DEVICE_COMPOSE.read_text())

    assert device["services"]["login"]["networks"] == [
        "benchmark_internal",
        "gateway_egress",
    ]
    mounts = device["services"]["login"]["volumes"]
    assert len(mounts) == 1
    assert mounts[0]["target"] == "/home/demo_user/.codex"
    assert device["volumes"]["codex_device_auth"] == {
        "external": True,
        "name": "${MOCK_CODEX_AUTH_VOLUME:-benchmarking-hpc-codex-device-auth}",
    }
    assert DEVICE_AUTH_VOLUME == "benchmarking-hpc-codex-device-auth"


def test_substrate_uses_existing_base_plus_new_overlays():
    substrate = DockerSlurmSubstrate(
        project="contract_test",
        auth_mode="gateway",
        build=False,
    )
    try:
        assert substrate.compose_files == [BASE_COMPOSE, OVERLAY_COMPOSE]
        argv = substrate.compose_argv("config")
        assert str(BASE_COMPOSE) in argv
        assert str(OVERLAY_COMPOSE) in argv
    finally:
        substrate.close()

    device = DockerSlurmSubstrate(
        project="contract_device",
        auth_mode="device",
        build=False,
    )
    try:
        assert device.compose_files == [
            BASE_COMPOSE,
            OVERLAY_COMPOSE,
            DEVICE_COMPOSE,
        ]
    finally:
        device.close()


def test_client_image_replaces_every_monitored_slurm_path():
    dockerfile = (OVERLAY_COMPOSE.parent / "Dockerfile.client").read_text()
    proxy = (OVERLAY_COMPOSE.parent / "client_proxy.py").read_text()

    for command in ("sbatch", "squeue", "sacct", "scontrol", "scancel", "srun"):
        assert command in dockerfile
    assert 'command = Path(sys.argv[0]).name' in proxy
    assert "OPENAI_API_KEY" not in proxy
