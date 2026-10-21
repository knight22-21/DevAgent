"""Regression tests for UTF-8 file I/O in background jobs (issue #80).

On Windows with a non-UTF-8 system locale (GBK, Shift-JIS, ...), text-mode
file I/O without an explicit encoding falls back to the locale codec. The
background job log would then be written with the locale codec: child output
containing characters outside the locale (e.g. emoji) raises
UnicodeEncodeError inside the detached job, and the log/state files cannot be
round-tripped between machines with different locales.
"""

import json
import subprocess
from dataclasses import asdict
from pathlib import Path

from devagent.background.jobs import (
    BackgroundJob,
    _load,
    _save,
    launch,
)


def _sample_job(state_path: str) -> BackgroundJob:
    return BackgroundJob(
        id="t1",
        task="分析 中文仓库 🚀",
        pid=123,
        log_path="bg_t1.log",
        state_path=state_path,
        started_at=0.0,
        status="running",
    )


def test_save_writes_utf8_state(tmp_path: Path):
    job = _sample_job(str(tmp_path / "bg_t1.json"))

    _save(job)

    raw = Path(job.state_path).read_bytes()
    data = json.loads(raw.decode("utf-8"))
    assert data["task"] == "分析 中文仓库 🚀"


def test_load_reads_utf8_state(tmp_path: Path):
    job = _sample_job(str(tmp_path / "bg_t1.json"))
    # A state file written on a UTF-8 machine may contain raw non-ASCII bytes.
    (tmp_path / "bg_t1.json").write_text(
        json.dumps(asdict(job), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    loaded = _load(job.state_path)

    assert loaded.task == "分析 中文仓库 🚀"


def test_launch_log_file_is_utf8(tmp_path: Path, monkeypatch):
    """Simulated child output with non-locale characters must survive.

    The fake Popen writes through the log handle exactly like the detached
    child process would. With the old locale-dependent handle this raises
    UnicodeEncodeError on a GBK system and produced mixed-codec logs.
    """

    class FakeProc:
        pid = 4321

    def fake_popen(cmd, **kwargs):
        fh = kwargs["stdout"]
        fh.write("分析完成: 找到 3 个 issue 🚀\n")
        fh.write("error: 路径不存在\n")
        return FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    job = launch("分析 中文仓库 🚀", tmp_path)

    text = Path(job.log_path).read_bytes().decode("utf-8")
    assert "分析完成: 找到 3 个 issue 🚀" in text
    assert "error: 路径不存在" in text


def test_is_running_invalid_pid():
    from devagent.background.jobs import _is_running
    assert _is_running(0) is False
    assert _is_running(-1) is False
    assert _is_running(-999) is False


def test_launch_creates_state_and_log_files(tmp_path: Path, monkeypatch):
    class FakeProc:
        pid = 9999

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: FakeProc())

    job = launch("echo hello", tmp_path)
    assert Path(job.log_path).exists()
    assert Path(job.state_path).exists()

    state = json.loads(Path(job.state_path).read_text(encoding="utf-8"))
    assert state["id"] == job.id
    assert state["task"] == "echo hello"
    assert state["pid"] == 9999
    assert state["status"] == "running"


def test_poll_running_process(tmp_path: Path, monkeypatch):
    from devagent.background.jobs import poll

    job = _sample_job(str(tmp_path / "bg_t1.json"))
    _save(job)

    monkeypatch.setattr("devagent.background.jobs._is_running", lambda pid: True)
    polled = poll(job)
    assert polled.status == "running"
    assert polled.exit_code is None


def test_poll_exit_zero(tmp_path: Path, monkeypatch):
    from devagent.background.jobs import poll

    job = _sample_job(str(tmp_path / "bg_t1.json"))
    _save(job)
    # Write exit code 0 to companion .exit file
    Path(tmp_path / "bg_t1.exit").write_text("0\n", encoding="utf-8")

    monkeypatch.setattr("devagent.background.jobs._is_running", lambda pid: False)
    polled = poll(job)
    assert polled.status == "done"
    assert polled.exit_code == 0

    reloaded = _load(job.state_path)
    assert reloaded.status == "done"
    assert reloaded.exit_code == 0


def test_poll_exit_nonzero(tmp_path: Path, monkeypatch):
    from devagent.background.jobs import poll

    job = _sample_job(str(tmp_path / "bg_t1.json"))
    _save(job)
    # Write exit code 1 to companion .exit file
    Path(tmp_path / "bg_t1.exit").write_text("1\n", encoding="utf-8")

    monkeypatch.setattr("devagent.background.jobs._is_running", lambda pid: False)
    polled = poll(job)
    assert polled.status == "failed"
    assert polled.exit_code == 1


def test_poll_exit_no_journal(tmp_path: Path, monkeypatch):
    from devagent.background.jobs import poll

    job = _sample_job(str(tmp_path / "bg_t1.json"))
    _save(job)
    # No .exit file written

    monkeypatch.setattr("devagent.background.jobs._is_running", lambda pid: False)
    polled = poll(job)
    assert polled.status == "unknown"
    assert polled.exit_code is None


def test_list_jobs_empty(tmp_path: Path):
    from devagent.background.jobs import list_jobs
    assert list_jobs(tmp_path) == []


def test_list_jobs_mixed(tmp_path: Path, monkeypatch):
    from devagent.background.jobs import list_jobs

    d = tmp_path / ".devagent"
    d.mkdir(parents=True)

    job1 = BackgroundJob(
        id="j1",
        task="task 1",
        pid=101,
        log_path=str(d / "bg_j1.log"),
        state_path=str(d / "bg_j1.json"),
        started_at=100.0,
        status="running",
    )
    job2 = BackgroundJob(
        id="j2",
        task="task 2",
        pid=102,
        log_path=str(d / "bg_j2.log"),
        state_path=str(d / "bg_j2.json"),
        started_at=200.0,
        status="running",
    )
    _save(job1)
    _save(job2)
    (d / "bg_j2.exit").write_text("0\n", encoding="utf-8")

    def mock_is_running(pid):
        return pid == 101

    monkeypatch.setattr("devagent.background.jobs._is_running", mock_is_running)

    jobs = list_jobs(tmp_path)
    assert len(jobs) == 2
    by_id = {j.id: j for j in jobs}
    assert by_id["j1"].status == "running"
    assert by_id["j2"].status == "done"

