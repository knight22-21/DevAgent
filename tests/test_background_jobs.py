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
