"""Static contract tests for the laptop-sized Docker Slurm substrate."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent
MOCK = ROOT / "mock-cluster"
CASES = ROOT / "benchmark" / "cases"


def compose() -> dict:
    return yaml.safe_load((MOCK / "compose.yaml").read_text())


def test_topology_and_physical_limits():
    services = compose()["services"]

    assert services["login"]["cpus"] == 1.0
    assert services["login"]["mem_limit"] == "2g"
    for name in ("c1", "c2", "c3"):
        assert services[name]["cpus"] == 2.0
        assert services[name]["mem_limit"] == "4g"
        assert services[name]["pids_limit"] == 256


def test_laptop_support_services_are_bounded():
    services = compose()["services"]

    for name in ("mysql", "slurmdbd", "cluster-init", "slurmctld"):
        assert services[name].get("cpus"), f"{name} has no CPU ceiling"
        assert services[name].get("mem_limit"), f"{name} has no memory ceiling"
        assert services[name].get("pids_limit"), f"{name} has no PID ceiling"


def test_benchmark_storage_reaches_login_and_compute_nodes():
    services = compose()["services"]
    required = {"/home", "/scratch", "/archive", "/episode/work"}
    for name in ("login", "c1", "c2", "c3"):
        targets = {
            mount["target"] if isinstance(mount, dict) else mount.split(":", 1)[1]
            for mount in services[name]["volumes"]
        }
        assert required <= targets


def test_compute_nodes_disable_parallel_volume_copy_up():
    services = compose()["services"]
    shared_targets = {"/home", "/scratch", "/archive", "/episode/work", "/data"}

    for name in ("c1", "c2", "c3"):
        shared = [
            mount
            for mount in services[name]["volumes"]
            if isinstance(mount, dict) and mount["target"] in shared_targets
        ]
        assert {mount["target"] for mount in shared} == shared_targets
        assert all(mount["volume"]["nocopy"] for mount in shared)


def test_image_installs_codex_without_the_gosu_download_path():
    dockerfile = (MOCK / "Dockerfile").read_text()

    assert "@openai/codex@${CODEX_VERSION}" in dockerfile
    assert 'ARG BUILD_JOBS=2' in dockerfile
    assert 'make -j"${BUILD_JOBS}"' in dockerfile
    assert "tianon/gosu" not in dockerfile
    assert "COPY gres.conf /etc/slurm/gres.conf" in dockerfile
    assert "COPY codex-benchmark /usr/local/bin/codex-benchmark" in dockerfile


def test_synthetic_identity_is_consistent():
    dockerfile = (MOCK / "Dockerfile").read_text()
    entrypoint = (MOCK / "docker-entrypoint.sh").read_text()

    assert "useradd --uid 5001" in dockerfile
    assert "demo_user" in dockerfile
    assert 'ACCOUNT_NAME: proj_astro' in (MOCK / "compose.yaml").read_text()
    assert '${BENCHMARK_USER:-demo_user}' in entrypoint
    assert '${ACCOUNT_NAME:-proj_astro}' in entrypoint


def test_codex_model_is_explicit_and_cheap_by_default():
    compose_text = (MOCK / "compose.yaml").read_text()
    entrypoint = (MOCK / "docker-entrypoint.sh").read_text()
    helper = (MOCK / "codex-benchmark").read_text()

    assert "CODEX_MODEL: ${CODEX_MODEL:-gpt-5.6-terra}" in compose_text
    assert '${CODEX_MODEL:-gpt-5.6-terra}' in entrypoint
    assert '--model "${CODEX_MODEL}"' in helper
    assert "--json" in helper
    assert "--ephemeral" in helper
    assert "--skip-git-repo-check" in helper


def test_fake_gpu_inventory_uses_four_harmless_count_only_devices():
    gres = (MOCK / "gres.conf").read_text()

    assert gres.count("Name=gpu") == 4
    assert gres.count("Flags=CountOnly") == 4
    for device in ("/dev/null", "/dev/zero", "/dev/full", "/dev/random"):
        assert f"File={device}" in gres


def test_every_case_has_a_small_functional_asset():
    required_assets = {
        "A1-srun-loop": {"fit_lightcurve.py"},
        "A2-poll-storm": {"fit_catalogue.sh", "make_summary.py", "summarise.sh"},
        "A3-no-array": {"fit_one.sh", "fit_array.sh"},
        "B1-small-files": {"extract_cutouts.py"},
        "B2-home-output": {"nbody"},
        "B3-login-node-compute": {"preprocess.py", "preprocess.sh", "train.sh"},
        "C1-over-limit": {"mhd_relax"},
        "C2-over-request": {"infer.py"},
        "C3-wrong-partition": {"train_photoz.py"},
    }

    for case, expected in required_assets.items():
        assets = CASES / case / "assets"
        assert expected <= {path.name for path in assets.iterdir()}
        assert sum(path.stat().st_size for path in assets.iterdir()) < 16_384


def test_two_node_fixture_matches_laptop_topology():
    for script_name in ("job.sh", "reference.sh"):
        script = (CASES / "B2-home-output" / script_name).read_text()
        assert "#SBATCH --nodes=2" in script
        assert "#SBATCH --nodes=8" not in script


def test_runtime_fixtures_do_not_implement_nominal_large_work():
    asset_text = "\n".join(
        path.read_text()
        for path in CASES.glob("*/assets/*")
        if path.is_file()
    )

    assert "range(500000)" not in asset_text
    assert "seq 1 2000" not in asset_text
    assert "import torch" not in asset_text
    assert "nvidia-smi" not in asset_text
