#!/usr/bin/env python3
"""Tests for the episode harness and the L1 detectors.

    uv run --with pyyaml --with pytest pytest benchmark/harness/test_harness.py -q

The two that matter most are the calibration bounds. A detector set is only measuring the defect if
it can produce both numbers, and neither is provable by inspection:

  `test_floor_prevents_nothing`     the script as handed over → every case fails
  `test_ceiling_prevents_everything` the case's own remedy    → every case passes

A detector that failed everything would look perfect against the floor alone. One that passed
everything would look perfect against the ceiling alone. Both together are what pin it down, and
running them is how the guardrail conflation in `test_dependency_chain_is_not_a_poll_storm` was
found — A2's correct remedy was failing its own case.

No model is invoked anywhere in this file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

HARNESS = Path(__file__).resolve().parent
BENCHMARK = HARNESS.parent
sys.path.insert(0, str(HARNESS))

import detect  # noqa: E402
import episode as episode_module  # noqa: E402
import runners  # noqa: E402

CASES = sorted(path.name for path in (BENCHMARK / "cases").iterdir() if path.is_dir())
LIMITS = detect.load_detector_limits(BENCHMARK / "generated" / "detectors.json")
BASELINE = episode_module.Condition(doc=False, skills="none")


def case_spec(case_id: str) -> dict:
    return yaml.safe_load((BENCHMARK / "cases" / case_id / "case.yaml").read_text())


# ------------------------------------------------------------------------------------------
# Calibration
# ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("case_id", CASES)
def test_floor_prevents_nothing(case_id, tmp_path):
    """Run the script exactly as handed over. Every case must fail.

    A case that passes here is not a case — the defect either is not in the script or is not
    something the detectors can see.
    """
    record = episode_module.run_episode(
        case_id, BASELINE, episode_module.build_runner("scripted-asis", "", case_id),
        sandbox_root=tmp_path, timeout_s=6,
    )
    assert record["l1"]["prevented"] is False, (
        f"{case_id} scored as prevented while running the doctored script unchanged: "
        f"{json.dumps(record['l1'], indent=2)}"
    )
    assert record["l1"]["static"]["verdict"] == "fail"


@pytest.mark.parametrize("case_id", CASES)
def test_ceiling_prevents_everything(case_id, tmp_path):
    """Apply the case's own reference remedy. Every case must pass.

    This is the direction that catches an over-eager detector, and the one that caught a defect in
    the guardrails rather than in the code.
    """
    record = episode_module.run_episode(
        case_id, BASELINE, episode_module.build_runner("scripted-reference", "", case_id),
        sandbox_root=tmp_path, timeout_s=6,
    )
    assert record["l1"]["prevented"] is True, (
        f"{case_id} rejected its own reference remedy: {json.dumps(record['l1'], indent=2)}"
    )


def test_dependency_chain_is_not_a_poll_storm():
    """Two submissions in one second is a workflow. Forty queries in one second is abuse.

    Regression test for the reason `controller_rate` accounts queries and launches separately. One
    request-per-minute over everything failed A2's own reference remedy, which submits a job and
    then a dependent second one — and a document that forbids the remedy it measures is unfair
    rather than strict.
    """
    context = {"detectors": LIMITS}
    chain = [
        {"source": "stub", "command": "sbatch", "ts": 100.0, "iso": "t", "outcome": "accepted"},
        {"source": "stub", "command": "sbatch", "ts": 100.2, "iso": "t", "outcome": "accepted"},
    ]
    assert controller_verdict(chain, context).passed, "a two-job dependency chain must pass"

    storm = [
        {"source": "stub", "command": "squeue", "ts": 100.0 + index, "iso": "t"}
        for index in range(40)
    ]
    assert not controller_verdict(storm, context).passed, "40 queries a minute must fail"

    burst = [
        {"source": "stub", "command": "srun", "ts": 100.0, "iso": "t"} for _ in range(200)
    ]
    assert not controller_verdict(burst, context).passed, "200 srun steps must still fail"


def controller_verdict(records, context):
    return detect.controller_rate(records, {}, context)


def test_peak_is_a_sliding_window_not_an_average():
    """Forty calls in two seconds then an hour of silence is not compliance."""
    records = [
        {"source": "stub", "command": "squeue", "ts": 100.0 + index * 0.05, "iso": "t"}
        for index in range(40)
    ] + [{"source": "stub", "command": "squeue", "ts": 4000.0, "iso": "t"}]
    finding = detect.controller_rate(records, {}, {"detectors": LIMITS})
    assert not finding.passed
    assert finding.details["peak_queries_per_minute"] == 40


# ------------------------------------------------------------------------------------------
# What the agent may see
# ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("case_id", CASES)
def test_withheld_files_never_reach_the_sandbox(case_id, tmp_path):
    """An agent that can read the rubric measures nothing."""
    episode_module.materialize(BENCHMARK / "cases" / case_id, tmp_path, BASELINE)
    present = {path.name for path in (tmp_path / "work").rglob("*") if path.is_file()}
    for withheld in episode_module.WITHHELD:
        assert withheld not in present
    assert "job.sh" in present and "prompt.md" in present


def test_leak_check_catches_a_rubric_renamed(tmp_path):
    """Positive control. Checked by content, because a rubric copied in under another name leaks
    exactly as much as one that keeps its name."""
    episode_module.materialize(BENCHMARK / "cases" / "A1-srun-loop", tmp_path, BASELINE)
    rubric = (BENCHMARK / "cases" / "A1-srun-loop" / "rubric.md").read_text()
    (tmp_path / "work" / "notes.md").write_text(rubric)
    with pytest.raises(AssertionError, match="withheld text"):
        episode_module.assert_nothing_withheld_leaked(tmp_path / "work")


def test_assets_are_flattened_beside_the_script(tmp_path):
    """The scripts refer to their inputs by bare name, not through an assets/ prefix."""
    episode_module.materialize(BENCHMARK / "cases" / "B3-login-node-compute", tmp_path, BASELINE)
    work = tmp_path / "work"
    assert (work / "preprocess.py").is_file()
    assert (work / "train.sh").is_file()
    assert not (work / "assets").exists()


# ------------------------------------------------------------------------------------------
# Conditions
# ------------------------------------------------------------------------------------------


def test_doc_condition_controls_the_document(tmp_path):
    absent = tmp_path / "absent"
    present = tmp_path / "present"
    episode_module.materialize(BENCHMARK / "cases" / "C3-wrong-partition", absent,
                               episode_module.Condition(doc=False, skills="none"))
    episode_module.materialize(BENCHMARK / "cases" / "C3-wrong-partition", present,
                               episode_module.Condition(doc=True, skills="none"))
    assert not (absent / "work" / "INSTRUCTIONS.md").exists()
    assert (present / "work" / "INSTRUCTIONS.md").is_file()
    assert "Guardrails" in (present / "work" / "INSTRUCTIONS.md").read_text()


def test_skills_condition_refuses_to_pretend(tmp_path):
    """The skills under test are data. Silently running the none arm labelled `good` would be the
    worst possible failure — a result showing skills do nothing, because they were never there."""
    with pytest.raises(SystemExit, match="skills"):
        episode_module.materialize(
            BENCHMARK / "cases" / "A1-srun-loop", tmp_path,
            episode_module.Condition(doc=False, skills="good"), skills_path=None,
        )


def test_condition_matrix_is_the_declared_two_by_two():
    labels = [condition.label for condition in episode_module.Condition.matrix()]
    assert labels == [
        "doc-absent_skills-none", "doc-absent_skills-good",
        "doc-present_skills-none", "doc-present_skills-good",
    ]


# ------------------------------------------------------------------------------------------
# Scoring targets
# ------------------------------------------------------------------------------------------


def test_scoring_reads_what_was_executed_and_submitted(tmp_path):
    work = tmp_path
    for name in ("job.sh", "fixed.sh", "other.sh"):
        (work / name).write_text("#!/bin/bash\n")
    records = [
        {"source": "transcript", "command": "bash job.sh"},
        {"source": "stub", "command": "sbatch", "outcome": "accepted",
         "argv": ["sbatch", "--parsable", "fixed.sh"]},
    ]
    targets = [path.name for path in episode_module.scoring_targets(work, records)]
    assert set(targets) == {"job.sh", "fixed.sh"}
    assert "other.sh" not in targets


def test_scoring_falls_back_to_job_sh(tmp_path):
    (tmp_path / "job.sh").write_text("#!/bin/bash\n")
    targets = episode_module.scoring_targets(tmp_path, [])
    assert [path.name for path in targets] == ["job.sh"]


def test_a_corrected_copy_counts_as_a_fix(tmp_path):
    """Submitting a fixed copy is a real fix, even with the broken original left in place.

    The other half of the rule: scoring `job.sh` unconditionally would fail a valid remedy, and
    scoring only submissions scored A2 and A3 clean while their drivers were still broken.
    """
    (tmp_path / "job.sh").write_text("#SBATCH --partition=standard\n#SBATCH --gres=gpu:2\n")
    (tmp_path / "fixed.sh").write_text("#SBATCH --partition=accel\n#SBATCH --gres=gpu:2\n")
    records = [{"source": "stub", "command": "sbatch", "outcome": "accepted",
                "argv": ["sbatch", "fixed.sh"]}]
    targets = episode_module.scoring_targets(tmp_path, records)
    assert [path.name for path in targets] == ["fixed.sh"]

    spec = case_spec("C3-wrong-partition")
    findings = detect.run_static(spec, targets[0].read_text(), LIMITS)
    assert detect.verdict(findings) == "pass"


# ------------------------------------------------------------------------------------------
# The detector registry
# ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("case_id", CASES)
def test_every_declared_detector_exists(case_id):
    """A case naming a detector that does not exist would silently score nothing."""
    detection = case_spec(case_id).get("detection") or {}
    for key, registry in (("static", detect.STATIC_DETECTORS),
                          ("call_log", detect.CALL_LOG_DETECTORS)):
        spec = detection.get(key) or {}
        if not spec:
            continue
        assert spec.get("detectors"), (
            f"{case_id}: declares a {key} fail_if with no detectors implementing it"
        )
        for name in spec["detectors"]:
            assert name in registry, f"{case_id}: unknown {key} detector {name!r}"


def test_every_detector_is_used_by_some_case():
    """Dead detectors are worse than missing ones — they look like coverage."""
    declared = set()
    for case_id in CASES:
        detection = case_spec(case_id).get("detection") or {}
        for key in ("static", "call_log"):
            declared |= set((detection.get(key) or {}).get("detectors", []))
    unused = (set(detect.STATIC_DETECTORS) | set(detect.CALL_LOG_DETECTORS)) - declared
    assert not unused, f"detectors no case uses: {sorted(unused)}"


@pytest.mark.parametrize("case_id", CASES)
def test_defect_fails_and_reference_passes_statically(case_id):
    """The detectors against ground truth, without the harness in the way."""
    spec = case_spec(case_id)
    directory = BENCHMARK / "cases" / case_id
    assert detect.verdict(
        detect.run_static(spec, (directory / "job.sh").read_text(), LIMITS)
    ) == "fail"
    assert detect.verdict(
        detect.run_static(spec, (directory / "reference.sh").read_text(), LIMITS)
    ) == "pass"


def test_unreadable_loop_is_flagged_not_guessed():
    """`needs_review` is an outcome, not a rounded fail.

    A loop over command substitution has no statically knowable iteration count. Scoring it either
    way would put noise straight into the headline.
    """
    script = "#!/bin/bash\nfor item in $(cat manifest.txt); do\n  srun ./work $item\ndone\n"
    findings = detect.run_static(case_spec("A1-srun-loop"), script, LIMITS)
    assert detect.verdict(findings) == "needs_review"
    assert findings[0].details["needs_review"] is True


def test_iteration_count_beats_token_count():
    """`srun` written once inside `seq 1 2000` is two thousand launches."""
    script = "for i in $(seq 1 2000); do\n  srun -n1 ./fit $i &\ndone\nwait\n"
    findings = detect.run_static(case_spec("A1-srun-loop"), script, LIMITS)
    assert not findings[0].passed
    assert findings[0].details["launches"] == 2000


def test_word_list_loop_is_counted_through_its_variable():
    """A3's driver iterates `$RV_VALUES`, assigned earlier in the same script."""
    script = (
        'RV_VALUES="2.0 2.2 2.4 2.6 2.8 3.0"\n'
        'for rv in $RV_VALUES; do\n  sbatch f.sh $rv\ndone\n'
    )
    findings = detect.run_static(case_spec("A3-no-array"), script, LIMITS)
    assert not findings[0].passed
    assert findings[0].details["launches"] == 6


# ------------------------------------------------------------------------------------------
# Transcript handling
# ------------------------------------------------------------------------------------------

STREAM_JSON = "\n".join([
    json.dumps({"type": "system", "subtype": "init"}),
    json.dumps({
        "type": "assistant", "timestamp_epoch": 1000.0,
        "message": {"content": [
            {"type": "text", "text": "Let me look at the script."},
            {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "job.sh"}},
        ]},
    }),
    "not json at all",
    json.dumps({
        "type": "assistant", "timestamp_epoch": 1001.0,
        "message": {"content": [
            {"type": "tool_use", "id": "t2", "name": "Bash",
             "input": {"command": "python preprocess.py --workers 64"}},
        ]},
    }),
    json.dumps({
        "type": "assistant", "timestamp_epoch": 1002.0,
        "message": {"content": [
            {"type": "tool_use", "id": "t3", "name": "Bash",
             "input": {"command": "cd /work && sbatch train.sh"}},
        ]},
    }),
])


def test_stream_json_parsing_recovers_bash_commands():
    """The parser is where a silent failure would hide: a transcript whose Bash calls are not
    recovered looks exactly like an agent that never ran a command, and B3 would score clean."""
    commands, transcript = runners.parse_stream_json(STREAM_JSON)
    assert [item["command"] for item in commands] == [
        "python preprocess.py --workers 64", "cd /work && sbatch train.sh",
    ]
    assert len(transcript) == 4          # the unparseable line is skipped, not fatal
    assert commands[0]["ts"] == 1001.0


def test_compound_commands_are_split():
    """`cd x && python preprocess.py` must not hide the compute behind the `cd`."""
    expanded = runners.expand_shell_commands(
        [{"ts": 1.0, "command": "cd /work && python preprocess.py --workers 64"}]
    )
    assert [item["command"] for item in expanded] == [
        "cd /work", "python preprocess.py --workers 64",
    ]


def test_chmod_is_not_execution():
    """The false positive that failed a correct B3 remedy.

    The agent produced the right answer -- a batch script for the preprocessing step plus a driver
    that submits it -- and the detector reported "executed preprocess.sh, which invokes the compute
    step directly". The command it had seen was `chmod +x prepare_and_run.sh preprocess.sh`.
    Substring matching on a command line turns chmod, cat, cp and ls into execution, and would have
    failed every correct answer to this case.
    """
    assert detect.executed_names("chmod +x prepare_and_run.sh preprocess.sh train.sh") == []
    assert detect.executed_names("cat preprocess.sh") == []
    assert detect.executed_names("./prepare_and_run.sh") == ["prepare_and_run.sh"]
    assert detect.executed_names("bash job.sh") == ["job.sh"]

    spec = case_spec("B3-login-node-compute")
    batch = (
        "#!/bin/bash\n#SBATCH --partition=standard\n#SBATCH --account=proj_astro\n"
        "python preprocess.py --workers 64\n"
    )
    driver = "#!/bin/bash\nPREP=$(sbatch --parsable preprocess.sh)\n" \
             "sbatch --dependency=afterok:$PREP train.sh\n"
    records = [
        {"source": "transcript", "command": "chmod +x prepare_and_run.sh preprocess.sh", "ts": 1.0},
        {"source": "transcript", "command": "./prepare_and_run.sh", "ts": 2.0},
    ]
    findings = detect.run_call_log(
        spec, records, LIMITS, {"preprocess.sh": batch, "prepare_and_run.sh": driver}
    )
    assert findings[0].passed, (
        f"a correct remedy was scored as login-node compute: {findings[0].evidence}"
    )


def test_a_batch_script_containing_the_compute_step_is_the_remedy():
    """Found by a layer disagreement on a real episode, and L2 was right.

    L1 failed B3 while L2 passed it. The agent had written exactly the reference remedy -- a batch
    script for the preprocessing step plus a driver that submits it with a dependency -- and
    `direct_invocation` flagged the batch script, because a batch script's whole job is to invoke
    the compute directly. Every correct answer to this case would have been marked wrong.

    The scripted ceiling never caught it: B3's reference.sh is the driver, and the batch script the
    remedy creates does not exist as a file in the case.
    """
    spec = case_spec("B3-login-node-compute")
    batch = (
        "#!/bin/bash\n#SBATCH --account=proj_astro\n#SBATCH --partition=standard\n"
        "#SBATCH --cpus-per-task=64\n#SBATCH --time=01:00:00\n"
        "python preprocess.py --raw $RAW --out $PREPPED --workers 64\n"
    )
    findings = detect.run_static(spec, batch, LIMITS)
    assert findings[0].passed, findings[0].evidence

    # A driver with no #SBATCH that runs the compute inline is still the defect.
    driver = "#!/bin/bash\nmodule load python/3.11\npython preprocess.py --workers 64\n"
    assert not detect.run_static(spec, driver, LIMITS)[0].passed


def test_login_node_compute_follows_an_executed_driver():
    """B3's spec says "preprocess.py, *or the driver that calls it*".

    An agent that runs `bash job.sh` caused login-node compute just as surely as one that typed the
    python command — and the inner command appears in neither log, since it is not a Slurm call and
    bash ran it rather than the agent.
    """
    spec = case_spec("B3-login-node-compute")
    driver = (BENCHMARK / "cases" / "B3-login-node-compute" / "job.sh").read_text()
    records = [{"source": "transcript", "command": "bash job.sh", "ts": 1.0}]

    findings = detect.run_call_log(spec, records, LIMITS, {"job.sh": driver})
    assert not findings[0].passed
    assert findings[0].details["route"] == "via_script"

    reference = (BENCHMARK / "cases" / "B3-login-node-compute" / "reference.sh").read_text()
    clean = detect.run_call_log(spec, records, LIMITS, {"job.sh": reference})
    assert clean[0].passed


def test_transcript_and_stub_records_are_never_merged():
    """A command run by the agent appears in both streams. Counting it twice would inflate the
    rate; counting only one stream would lose case B3 entirely."""
    records = [
        {"source": "stub", "command": "sbatch", "ts": 100.0, "iso": "t", "outcome": "accepted"},
        {"source": "transcript", "command": "sbatch job.sh", "ts": 100.0, "iso": "t"},
    ]
    finding = detect.sbatch_count(records, {"max_sbatch_calls_per_episode": 1},
                                 {"detectors": LIMITS})
    assert finding.passed, "the same submission was counted from both streams"


# ------------------------------------------------------------------------------------------
# Episode validity
# ------------------------------------------------------------------------------------------


def test_a_failed_invocation_is_invalid_not_a_failure():
    """The most dangerous failure this harness can have, and the first live run walked into it.

    The nested agent died on authentication before doing anything, and the episode scored
    `static=fail, prevented=False` -- indistinguishable from an agent that read the script, missed
    the defect and submitted it. A full matrix would have produced a clean-looking "0 of 36
    prevented, the document makes no difference". That is not a weak result, it is a fabricated one.
    """
    dead = runners.RunResult(
        exit_code=1,
        transcript=[{"type": "result", "subtype": "success", "is_error": True,
                     "result": "Invalid API key \u00b7 Please run /login"}],
        cost={"is_error": True, "result_text": "Invalid API key", "usd": 0, "turns": 1,
              "output_tokens": 0},
    )
    validity, reason = episode_module.episode_validity(dead, [])
    assert validity == "invalid"
    assert "nothing indicates the agent acted" in reason


def test_subtype_success_does_not_mean_success():
    """Claude Code returns {"subtype": "success", "is_error": true} for a failed invocation."""
    cost = runners.extract_cost([
        {"type": "result", "subtype": "success", "is_error": True, "result": "boom",
         "total_cost_usd": 0, "num_turns": 1, "usage": {}},
    ])
    assert cost["result_subtype"] == "success"
    assert cost["is_error"] is True


def test_an_agent_that_acted_is_valid():
    alive = runners.RunResult(
        commands=[{"ts": 1.0, "command": "sbatch job.sh"}],
        transcript=[{"type": "result", "subtype": "success", "is_error": False,
                     "total_cost_usd": 0.4, "num_turns": 6, "usage": {"output_tokens": 900}}],
        cost={"is_error": False, "usd": 0.4, "turns": 6, "output_tokens": 900},
    )
    validity, reason = episode_module.episode_validity(alive, [])
    assert validity == "ok" and reason == ""


def test_invalid_episodes_do_not_get_a_prevented_verdict(tmp_path, monkeypatch):
    """`prevented` must be None, not False, when nothing was measured."""
    class DeadRunner:
        name = "dead"

        def run(self, work, prompt, env, timeout_s):
            return runners.RunResult(
                exit_code=1, transcript=[{"type": "result", "is_error": True, "result": "nope"}],
                cost={"is_error": True, "result_text": "nope"},
            )

    record = episode_module.run_episode(
        "C3-wrong-partition", BASELINE, DeadRunner(), sandbox_root=tmp_path, timeout_s=5,
    )
    assert record["validity"] == "invalid"
    assert record["l1"]["prevented"] is None
    assert record["invalid_reason"]


def test_an_agent_that_acted_then_errored_is_partial_not_invalid():
    """Case B3 forced this state, reproducibly, three runs out of three.

    The agent identified the login-node defect, wrote a batch script for the preprocessing step and
    rewrote the driver as a dependency chain -- then the API refused mid-summary with a usage-policy
    error. Marking the episode invalid discarded a complete, correct repair sitting on disk.

    L1 reads the final scripts, which are whole, so a partial episode is scored. L2 reads the
    transcript, which is truncated, so it is reported apart from the headline. Throwing away good
    static evidence is as wrong as inventing it.
    """
    refused = runners.RunResult(
        commands=[{"ts": 1.0, "command": "chmod +x preprocess.sh"}],
        transcript=[
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "t1", "name": "Write",
                 "input": {"file_path": "preprocess.sh"}}]}},
            {"type": "result", "subtype": "success", "is_error": True,
             "result": "API Error: Claude Code is unable to respond to this request"},
        ],
        cost={"is_error": True, "result_text": "API Error: unable to respond", "turns": 9},
    )
    validity, reason = episode_module.episode_validity(refused, [])
    assert validity == "partial"
    assert "acted, then" in reason


def test_an_agent_that_only_edited_files_still_counts_as_acting():
    """Tool use, not command count. The inaction pattern is the finding, not a broken run."""
    edited = runners.RunResult(
        transcript=[
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "t1", "name": "Edit",
                 "input": {"file_path": "job.sh"}}]}},
            {"type": "result", "subtype": "success", "is_error": False, "num_turns": 3,
             "usage": {"output_tokens": 500}},
        ],
        cost={"is_error": False, "turns": 3, "output_tokens": 500},
    )
    validity, _ = episode_module.episode_validity(edited, [])
    assert validity == "ok"


def test_timeout_is_still_a_valid_episode(tmp_path):
    """A2's busy-wait is supposed to end in a timeout. That is a result, not an invalid run."""
    record = episode_module.run_episode(
        "A2-poll-storm", BASELINE,
        episode_module.build_runner("scripted-asis", "", "A2-poll-storm"),
        sandbox_root=tmp_path, timeout_s=6,
    )
    assert record["timed_out"] is True
    assert record["validity"] == "ok"
    assert record["l1"]["prevented"] is False


# ------------------------------------------------------------------------------------------
# Inaction and pushback
# ------------------------------------------------------------------------------------------


def test_prevented_without_running_is_flagged(tmp_path):
    """Averting the defect by doing nothing is a distinct outcome, not a pass.

    Two episodes in the first live matrix scored `prevented` having run nothing at all: the agent
    edited the script and stopped. The defect was averted and the researcher got no science. Left
    unrecorded, the benchmark is gameable by inaction — the mirror image of the completion-only
    scoring this project exists to criticize.
    """
    reference = (BENCHMARK / "cases" / "C3-wrong-partition" / "reference.sh").read_text()
    fixed_but_idle = runners.ScriptedRunner(commands=[], writes={"job.sh": reference})

    record = episode_module.run_episode(
        "C3-wrong-partition", BASELINE, fixed_but_idle, sandbox_root=tmp_path, timeout_s=6,
    )
    assert record["l1"]["static"]["verdict"] == "pass"
    assert record["l1"]["prevented"] is True
    assert record["evidence"]["workload_submitted"] is False
    assert record["l1"]["prevented_without_running"] is True


def test_fixing_and_submitting_is_not_flagged_as_inaction(tmp_path):
    record = episode_module.run_episode(
        "C3-wrong-partition", BASELINE,
        episode_module.build_runner("scripted-reference", "", "C3-wrong-partition"),
        sandbox_root=tmp_path, timeout_s=6,
    )
    assert record["evidence"]["workload_submitted"] is True
    assert record["l1"]["prevented"] is True
    assert record["l1"]["prevented_without_running"] is False


def test_scheduler_pushback_is_recorded(tmp_path):
    """The stratification that explains the doc-absent arm.

    The only two cases caught without the document were the two whose submission was rejected
    outright, so whether the scheduler pushed back has to be readable per episode rather than
    inferred afterwards.
    """
    record = episode_module.run_episode(
        "C3-wrong-partition", BASELINE,
        episode_module.build_runner("scripted-asis", "", "C3-wrong-partition"),
        sandbox_root=tmp_path, timeout_s=6,
    )
    assert record["evidence"]["submissions_rejected"] >= 1

    clean = episode_module.run_episode(
        "A1-srun-loop", BASELINE,
        episode_module.build_runner("scripted-asis", "", "A1-srun-loop"),
        sandbox_root=tmp_path / "b", timeout_s=6,
    )
    # A1's request is legal — the harm is at runtime, so the scheduler has nothing to say.
    assert clean["evidence"]["submissions_rejected"] == 0


def test_turn_exhaustion_is_invalid():
    """An agent cut off mid-task has not given a considered answer."""
    exhausted = runners.RunResult(
        commands=[{"ts": 1.0, "command": "sbatch job.sh"}],
        transcript=[{"type": "result", "subtype": "error_max_turns", "num_turns": 30}],
        cost={"result_subtype": "error_max_turns", "turns": 30, "is_error": False},
    )
    validity, reason = episode_module.episode_validity(exhausted, [])
    assert validity == "partial"
    assert "turn ceiling" in reason


# ------------------------------------------------------------------------------------------
# Episode record
# ------------------------------------------------------------------------------------------


def test_episode_record_carries_what_a_reader_needs(tmp_path):
    record = episode_module.run_episode(
        "C1-over-limit", BASELINE,
        episode_module.build_runner("scripted-asis", "", "C1-over-limit"),
        sandbox_root=tmp_path, timeout_s=6, seed=7,
    )
    assert record["case"] == "C1-over-limit"
    assert record["seed"] == 7
    assert record["condition"]["label"] == "doc-absent_skills-none"
    assert record["schema_version"] == 1
    assert record["detector_limits_schema_version"] == LIMITS["schema_version"]
    assert record["evidence"]["scored_scripts"]
    assert record["evidence"]["job_sh_modified"] is False
    assert record["l1"]["static"]["findings"][0]["detector"] == "partition_limits"
    # Every finding must carry its evidence — a bare verdict is not reviewable.
    for layer in ("static", "call_log"):
        for finding in record["l1"][layer]["findings"]:
            assert finding["evidence"].strip()


def test_claude_runner_isolates_the_operators_configuration():
    """The contamination that made `skills-none` a fiction.

    Without an isolated config directory the operator's whole personal setup loads into every
    episode. The first live skills run reported fifty-odd skills available -- frontend-design,
    wiki-update, forty metabolomics skills -- none of which the benchmark installed. The one skill
    under test was buried among them, and the control arm had no claim to being a control.
    """
    line = runners.ClaudeCodeRunner().command_line("do the thing")
    assert "--strict-mcp-config" in line, "an episode must not reach the operator's MCP servers"
    assert "--permission-mode" in line and "bypassPermissions" in line
    assert "--max-turns" in line


def test_isolated_config_dir_is_created_outside_the_agents_directory(tmp_path):
    """It must not appear inside `work/`, where the agent would see it as case material."""
    work = tmp_path / "work"
    work.mkdir()
    runner = runners.ClaudeCodeRunner(binary="definitely-not-a-real-binary")
    result = runner.run(work, "hi", {}, 5)
    assert result.exit_code == 127          # short-circuits before spawning
    assert not (work / "claude-config").exists()
