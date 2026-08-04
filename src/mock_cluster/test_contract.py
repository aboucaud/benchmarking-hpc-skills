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


def test_real_docker_limits_remain_laptop_sized():
    base = yaml.safe_load(BASE_COMPOSE.read_text())
    services = base["services"]

    assert services["login"]["cpus"] == 1.0
    assert services["login"]["mem_limit"] == "2g"
    for name in ("c1", "c2", "c3"):
        assert services[name]["cpus"] == 2.0
        assert services[name]["mem_limit"] == "4g"


def test_agent_visible_slurm_resources_are_production_shaped():
    config = (BASE_COMPOSE.parent / "slurm.conf").read_text()
    base = yaml.safe_load(BASE_COMPOSE.read_text())
    instructions = (
        BASE_COMPOSE.parent.parent / "agents" / "INSTRUCTIONS.md"
    ).read_text()

    assert "NodeName=scc-c[0001-0002] CPUs=128 RealMemory=256000" in config
    assert "NodeName=scc-c[0003-0400] CPUs=128 RealMemory=256000 State=CLOUD" in config
    assert "NodeName=scc-g001 CPUs=64 RealMemory=512000" in config
    assert "NodeName=scc-g[002-040] CPUs=64 RealMemory=512000 State=CLOUD" in config
    assert base["services"]["c1"]["hostname"] == "scc-c0001"
    assert base["services"]["c2"]["hostname"] == "scc-c0002"
    assert base["services"]["c3"]["hostname"] == "scc-g001"

    # `agents/INSTRUCTIONS.md` is now generated from `benchmark/center.yaml` (#29) rather than
    # hand-maintained, so these assert the *facts* this test is about — the document advertises
    # the production machine, not the two-container one — instead of the wording that used to
    # carry them. Wording is the renderer's business and will change; the contract is that the
    # numbers the agent reads match the ones `slurm.conf` declares.
    #
    # That the document was hand-maintained is how it drifted from the descriptor in the first
    # place, and why the echo-stub and Docker substrates spent the whole pilot serving two
    # different documents under one condition label.
    center = yaml.safe_load(
        (BASE_COMPOSE.parent.parent / "benchmark" / "center.yaml").read_text()
    )
    # Every node class is named; only the compute classes advertise a shape, because the
    # document's business with login nodes is that you do not compute on them. Asserting cores
    # and memory for login too would have passed for the wrong reason — login and `standard`
    # both have 128 cores, so the login assertion would have been satisfied by the `standard`
    # line whether or not the document said anything about login at all.
    for name, node in center["nodes"].items():
        assert node["hostname_pattern"] in instructions, f"{name} not advertised"
        if name == "login":
            continue
        assert f"{node['count']} nodes (`{node['hostname_pattern']}`), {node['cores']} cores, " \
               f"{node['memory_gb']} GB memory" in instructions, f"{name} shape not advertised"
    accel = center["nodes"]["accel"]
    assert f"{accel['gpus_per_node']}× {accel['gpu_model']}" in instructions
    assert f"{center['account']['allocation_node_hours']:,} node-hours" in instructions

    # The container shape must never reach the document: an agent that believes it is on a
    # 2-core machine right-sizes for one, and every resource case would be measuring the mock.
    assert "2 CPU cores and 4 GiB" not in instructions
    assert "4g" not in instructions


def test_client_image_replaces_every_monitored_slurm_path():
    dockerfile = (OVERLAY_COMPOSE.parent / "Dockerfile.client").read_text()
    proxy = (OVERLAY_COMPOSE.parent / "client_proxy.py").read_text()

    for command in ("sbatch", "squeue", "sacct", "scontrol", "scancel", "srun"):
        assert command in dockerfile
    assert "site-slurm-client" in dockerfile
    assert "site-process-monitor" in dockerfile
    assert "mock-cluster-slurm-client" not in dockerfile
    assert 'command = Path(sys.argv[0]).name' in proxy
    assert "OPENAI_API_KEY" not in proxy
    assert "HPCBENCH_EPISODE" not in proxy
