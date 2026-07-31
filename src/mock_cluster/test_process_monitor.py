from __future__ import annotations

from .process_monitor import invoked_scripts


def test_process_monitor_records_only_argv_invocations():
    assert invoked_scripts(["python3", "preprocess.py", "--workers", "4"]) == [
        "preprocess.py"
    ]
    assert invoked_scripts(["bash", "./job.sh"]) == ["job.sh"]
    assert invoked_scripts(["./preprocess.py", "--workers", "4"]) == [
        "preprocess.py"
    ]


def test_process_monitor_does_not_promote_shell_command_mentions():
    command = "sed -n '1,260p' preprocess.py && cat job.sh"

    assert invoked_scripts(["bash", "-lc", command]) == []
    assert invoked_scripts(["sed", "-n", "1,260p", "preprocess.py"]) == []
