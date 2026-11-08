import os

import pytest

from mozhi.omniroute import OmniRoute


def test_binary_in_the_working_directory_is_never_used(monkeypatch, tmp_path):
    name = "omniroute.cmd" if os.name == "nt" else "omniroute"
    (tmp_path / name).write_text("echo planted")
    (tmp_path / name).chmod(0o755)
    safe = tmp_path / "safe"
    safe.mkdir()
    monkeypatch.delenv("OMNIROUTE_BIN", raising=False)
    monkeypatch.setenv("PATH", os.pathsep.join(["", ".", str(safe)]))
    monkeypatch.chdir(tmp_path)
    assert OmniRoute.executable() is None


def test_explicit_binary_must_be_an_absolute_existing_file(monkeypatch, tmp_path):
    exe = tmp_path / "omniroute-real"
    exe.write_text("x")
    monkeypatch.setenv("OMNIROUTE_BIN", str(exe))
    assert OmniRoute.executable() == str(exe)
    monkeypatch.setenv("OMNIROUTE_BIN", "omniroute")
    assert OmniRoute.executable() is None


def test_status_never_reveals_hosts_or_error_text(monkeypatch):
    monkeypatch.delenv("MOZHI_MANAGE_OMNIROUTE", raising=False)
    m = OmniRoute()
    m.ensure("https://gateway.internal.example/v1/chat/completions")
    assert (m.state, m.detail) == ("remote", "")
    monkeypatch.setenv("OMNIROUTE_BIN", "/definitely/not/here")
    monkeypatch.setattr(OmniRoute, "healthy", staticmethod(lambda base, timeout=1.5: False))
    m.ensure("http://localhost:20999/v1/chat/completions")
    assert m.state == "failed" and "/" not in m.detail and "localhost" not in m.detail


@pytest.mark.skipif(os.name != "nt", reason="job objects are Windows only")
def test_job_object_terminates_the_child(tmp_path):
    import subprocess
    import sys

    m = OmniRoute()
    m.proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    from mozhi.omniroute import _kill_on_close_job

    m._job = _kill_on_close_job(m.proc)
    assert m._job
    m.state = "started"
    m.stop()
    assert m.proc is None and m.state == "off"
