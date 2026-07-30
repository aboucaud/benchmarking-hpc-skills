from __future__ import annotations

from pathlib import Path

from .episode import (
    CASES,
    Condition,
    events_for_episode,
    materialize_condition,
    prompt_for_condition,
)


def test_condition_materializes_only_visible_a1_inputs():
    files = materialize_condition(CASES / "A1-srun-loop", Condition())

    assert {"job.sh", "prompt.md", "fit_lightcurve.py"} <= set(files)
    assert not {"case.yaml", "reference.sh", "rubric.md"} & set(files)
    assert "agents/INSTRUCTIONS.md" not in files


def test_document_and_codex_skill_layout(tmp_path: Path):
    skill = tmp_path / "hpc-safety"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: hpc-safety\ndescription: safe Slurm use\n---\n"
    )
    (skill / "guide.md").write_text("Use arrays for many similar tasks.\n")
    (skill / ".git").mkdir()
    (skill / ".git" / "config").write_text("not part of the skill\n")

    files = materialize_condition(
        CASES / "A1-srun-loop",
        Condition(doc=True, skills="good"),
        skill,
    )

    assert "agents/INSTRUCTIONS.md" in files
    root = ".agents/skills/hpc-safety"
    assert f"{root}/SKILL.md" in files
    assert f"{root}/guide.md" in files
    assert not any(".git" in Path(name).parts for name in files)


def test_skills_arm_requires_a_real_manifest(tmp_path: Path):
    empty = tmp_path / "empty"
    empty.mkdir()

    try:
        materialize_condition(
            CASES / "A1-srun-loop",
            Condition(skills="good"),
            empty,
        )
    except ValueError as error:
        assert "SKILL.md" in str(error)
    else:
        raise AssertionError("skills-good silently accepted an empty directory")


def test_document_aware_prompt_points_to_instructions_only_when_present():
    case = CASES / "A1-srun-loop"
    absent = prompt_for_condition(case, Condition(doc=False))
    present = prompt_for_condition(case, Condition(doc=True))

    assert "/agents/INSTRUCTIONS.md" not in absent
    assert present.startswith(
        "Before doing the task, read `/agents/INSTRUCTIONS.md` and follow "
        "its cluster guidance"
    )
    assert absent in present


def test_scoring_excludes_infrastructure_healthchecks():
    events = [
        {"episode_id": "unscoped", "command": "scontrol"},
        {"episode_id": "A1/seed0", "command": "sbatch"},
        {
            "episode_id": "A1/seed0",
            "event": "circuit_cancel",
            "command": "scancel",
        },
        {"episode_id": "another-run", "command": "squeue"},
    ]

    assert events_for_episode(events, "A1/seed0") == events[1:3]
