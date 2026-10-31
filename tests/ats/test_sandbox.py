"""The child process: timeouts, crashes, junk output and what the child can see. Stub children swap CHILD_COMMAND."""

import asyncio
import json
import subprocess
import sys
import time
from functools import cache
from pathlib import Path

import pytest

from app.ats import sandbox
from app.ats.constants import (
    CHILD_EXIT_GRACE_SECONDS,
    MAX_CHILD_MEMORY_BYTES,
    MAX_CHILD_OUTPUT_BYTES,
    MAX_CONCURRENT_PARSES,
    MAX_FILE_BYTES,
)
from app.ats.parser import parse_pdf
from app.ats.sandbox import ParserFailed, parse_in_child
from app.ats.schemas import Rejected
from app.core.config import settings
from tests.ats import samples

VALID_OUTCOME = json.dumps({"outcome": "rejected", "reason": "corrupt"})
PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Beyond anything a correct implementation spends on a stub: only here to turn a hang into a failure.
PATIENCE_SECONDS = 20


def use_stub(monkeypatch: pytest.MonkeyPatch, code: str) -> None:
    monkeypatch.setattr(sandbox, "CHILD_COMMAND", (sys.executable, "-c", code))


def _alive(pid: int) -> bool:
    """Running, as opposed to gone or a zombie that only waits to be reaped."""
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except (FileNotFoundError, ProcessLookupError):
        return False
    return state not in ("Z", "X")


async def _gone(pid: int, within: float = 3) -> bool:
    deadline = time.monotonic() + within
    while _alive(pid):
        if time.monotonic() > deadline:
            return False
        await asyncio.sleep(0.05)
    return True


async def _read_pid(path: Path) -> int:
    deadline = time.monotonic() + PATIENCE_SECONDS
    while time.monotonic() < deadline:
        if path.exists() and path.read_text():
            return int(path.read_text())
        await asyncio.sleep(0.02)
    raise AssertionError(f"{path} never appeared")


def _record_pid(path: Path) -> str:
    return f"import os; open({str(path)!r}, 'w').write(str(os.getpid()))\n"


@pytest.mark.parametrize("ignore_sigterm", [False, True], ids=["plain", "ignores-sigterm"])
@pytest.mark.asyncio
async def test_a_hanging_child_is_killed_at_the_time_limit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, ignore_sigterm: bool
) -> None:
    pid_file = tmp_path / "pid"
    code = (
        "import signal, time\n"
        f"{'signal.signal(signal.SIGTERM, signal.SIG_IGN)' if ignore_sigterm else ''}\n"
        f"{_record_pid(pid_file)}"
        "time.sleep(600)\n"
    )
    use_stub(monkeypatch, code)
    time_limit = 2.0

    started = time.monotonic()
    async with asyncio.timeout(time_limit + PATIENCE_SECONDS):
        outcome = await parse_in_child(samples.clean_pdf(), time_limit=time_limit)
    elapsed = time.monotonic() - started

    assert outcome == Rejected(reason="timed_out")
    assert time_limit * 0.9 <= elapsed < time_limit + CHILD_EXIT_GRACE_SECONDS + 3
    assert not _alive(int(pid_file.read_text())), "the hung child is still running"


@pytest.mark.parametrize(
    "code",
    [
        "import sys; sys.exit(3)",
        "import sys; sys.stderr.write('boom'); raise SystemExit(1)",
        "print('this is not json')",
        'print(\'{"outcome": "parsed"}\')',
        'print(\'{"outcome": "rejected", "reason": "made_up"}\')',
        "pass",
        "import sys; sys.stdout.buffer.write(bytes(range(256)))",
        # Valid outcome, but the exit status says the child failed.
        f"print({VALID_OUTCOME!r}); raise SystemExit(2)",
    ],
    ids=["exit-3", "exit-1", "not-json", "wrong-shape", "unknown-reason", "no-output", "binary-junk", "bad-exit"],
)
@pytest.mark.asyncio
async def test_a_broken_child_raises_parser_failed(monkeypatch: pytest.MonkeyPatch, code: str) -> None:
    use_stub(monkeypatch, code)

    with pytest.raises(ParserFailed):
        async with asyncio.timeout(PATIENCE_SECONDS):
            await parse_in_child(samples.clean_pdf())


@pytest.mark.parametrize(
    ("signal_name", "expected"),
    [
        ("SIGSEGV", Rejected(reason="corrupt")),
        ("SIGBUS", Rejected(reason="corrupt")),
        ("SIGABRT", Rejected(reason="corrupt")),
        ("SIGXCPU", Rejected(reason="timed_out")),
    ],
)
@pytest.mark.asyncio
async def test_a_child_that_faults_or_runs_out_of_cpu_maps_to_its_reason(
    monkeypatch: pytest.MonkeyPatch, signal_name: str, expected: Rejected
) -> None:
    use_stub(monkeypatch, f"import os, signal; os.kill(os.getpid(), signal.{signal_name})")

    async with asyncio.timeout(PATIENCE_SECONDS):
        assert await parse_in_child(samples.clean_pdf()) == expected


@pytest.mark.parametrize("signal_name", ["SIGKILL", "SIGTERM", "SIGINT", "SIGHUP"])
@pytest.mark.asyncio
async def test_a_child_stopped_by_another_signal_is_the_childs_failure(
    monkeypatch: pytest.MonkeyPatch, signal_name: str
) -> None:
    use_stub(monkeypatch, f"import os, signal; os.kill(os.getpid(), signal.{signal_name})")

    with pytest.raises(ParserFailed):
        async with asyncio.timeout(PATIENCE_SECONDS):
            await parse_in_child(samples.clean_pdf())


@pytest.mark.asyncio
async def test_a_child_that_exits_before_reading_all_its_input_does_not_deadlock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_stub(monkeypatch, f"print({VALID_OUTCOME!r})")

    async with asyncio.timeout(PATIENCE_SECONDS):
        outcome = await parse_in_child(b"%PDF-" + bytes(4 * 1024 * 1024))

    assert outcome == Rejected(reason="corrupt")


@pytest.mark.asyncio
async def test_a_well_behaved_stub_outcome_is_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    use_stub(monkeypatch, f"print({VALID_OUTCOME!r})")

    assert await parse_in_child(b"anything") == Rejected(reason="corrupt")


@pytest.mark.asyncio
async def test_a_child_flooding_stdout_fails_promptly_and_is_stopped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pid_file = tmp_path / "pid"
    use_stub(
        monkeypatch,
        f"import sys\n{_record_pid(pid_file)}chunk = b'x' * 65536\nwhile True: sys.stdout.buffer.write(chunk)\n",
    )
    time_limit = PATIENCE_SECONDS / 2

    started = time.monotonic()
    with pytest.raises(ParserFailed):
        async with asyncio.timeout(PATIENCE_SECONDS):
            await parse_in_child(samples.clean_pdf(), time_limit=time_limit)

    assert time.monotonic() - started < time_limit, "it should stop at the output limit, not wait for the time limit"
    assert await _gone(int(pid_file.read_text()))


@pytest.mark.asyncio
async def test_output_just_over_the_limit_is_refused_and_a_normal_outcome_is_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_stub(monkeypatch, f"import sys; sys.stdout.write(' ' * {MAX_CHILD_OUTPUT_BYTES + 1}); print({VALID_OUTCOME!r})")

    with pytest.raises(ParserFailed):
        async with asyncio.timeout(PATIENCE_SECONDS):
            await parse_in_child(b"x")


@pytest.mark.asyncio
async def test_a_descendant_holding_stdout_does_not_stall_and_is_killed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    descendant_pid_file = tmp_path / "descendant"
    descendant = f"import time\n{_record_pid(descendant_pid_file)}time.sleep(600)\n"
    use_stub(
        monkeypatch,
        f"import subprocess, sys\nsubprocess.Popen([sys.executable, '-c', {descendant!r}])\nprint({VALID_OUTCOME!r})\n",
    )
    time_limit = 2.0

    started = time.monotonic()
    async with asyncio.timeout(time_limit + PATIENCE_SECONDS):
        try:
            await parse_in_child(samples.clean_pdf(), time_limit=time_limit)
        except ParserFailed:
            pass  # Either outcome is fine; what matters is how long it takes and what is left running.
    elapsed = time.monotonic() - started

    assert elapsed < time_limit + CHILD_EXIT_GRACE_SECONDS + 3
    assert await _gone(await _read_pid(descendant_pid_file)), "a process the child started outlived the parse"


@pytest.mark.asyncio
async def test_the_child_environment_holds_no_secrets(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    secrets = {
        "DATABASE__PASSWORD": "sentinel-database-password",
        "REDIS__PASSWORD": "sentinel-redis-password",
        "S3__SECRET_ACCESS_KEY": "sentinel-s3-secret",
        "S3__ACCESS_KEY_ID": "sentinel-s3-key-id",
        "S3__ENDPOINT_URL": "http://sentinel-endpoint.invalid",
    }
    for name, value in secrets.items():
        monkeypatch.setenv(name, value)
    env_file = tmp_path / "env.json"
    use_stub(
        monkeypatch,
        f"import json, os; open({str(env_file)!r}, 'w').write(json.dumps(dict(os.environ))); print({VALID_OUTCOME!r})",
    )

    await parse_in_child(samples.clean_pdf())

    child_env = json.loads(env_file.read_text())
    dump = json.dumps(child_env)
    real_values = [
        settings.database.password.get_secret_value(),
        settings.redis.password.get_secret_value(),
        settings.s3.secret_access_key.get_secret_value(),
        settings.s3.access_key_id,
    ]
    for value in [*secrets.values(), *real_values]:
        assert value not in dump
    assert not [name for name in child_env if name.upper().startswith(("DATABASE", "REDIS", "S3", "AWS"))]


@pytest.mark.asyncio
async def test_the_real_child_returns_the_same_outcome_as_the_parser() -> None:
    pdf = samples.clean_pdf()

    assert await parse_in_child(pdf) == parse_pdf(pdf)


# --- the real child's own protections (the stubs above never run them) ---


@cache
def _bomb() -> bytes:
    pdf = samples.decompression_bomb_pdf(MAX_CHILD_MEMORY_BYTES * 2)
    assert len(pdf) < MAX_FILE_BYTES, "the sample must be a file the api would accept"
    return pdf


@pytest.mark.asyncio
async def test_a_decompression_bomb_is_rejected_as_corrupt_by_the_real_child() -> None:
    async with asyncio.timeout(PATIENCE_SECONDS * 3):
        assert await parse_in_child(_bomb()) == Rejected(reason="corrupt")


def test_the_real_child_applies_its_limits_before_parsing() -> None:
    """Runs the real `main()`, with the parser swapped for a function that reports the process's limits."""
    code = (
        "import ctypes, json, resource, sys\n"
        "import app.ats.child as child\n"
        "from app.ats.schemas import Rejected\n"
        "def report(pdf):\n"
        "    limits = {name: resource.getrlimit(getattr(resource, name)) for name in "
        "['RLIMIT_AS', 'RLIMIT_CORE', 'RLIMIT_FSIZE', 'RLIMIT_NPROC', 'RLIMIT_CPU']}\n"
        "    limits['dumpable'] = ctypes.CDLL(None).prctl(3, 0, 0, 0, 0)\n"
        "    sys.stderr.write(json.dumps(limits))\n"
        "    return Rejected(reason='corrupt')\n"
        "child.parse_pdf = report\n"
        "child.main()\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", code], input=b"x", capture_output=True, cwd=PROJECT_ROOT, env={}, timeout=60
    )
    assert done.returncode == 0, done.stderr
    limits = json.loads(done.stderr)

    assert limits["RLIMIT_AS"][0] <= MAX_CHILD_MEMORY_BYTES
    assert limits["RLIMIT_CORE"][0] == 0
    assert limits["RLIMIT_FSIZE"][0] == 0
    assert limits["RLIMIT_NPROC"][0] == 0
    assert 0 < limits["RLIMIT_CPU"][0] < 10**9, "a CPU limit must be set"
    assert limits["dumpable"] == 0, "the child must not be dumpable"


# --- slots and cancellation ---


@pytest.mark.asyncio
async def test_cancelling_a_parse_leaves_no_live_child(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pid_file = tmp_path / "pid"
    use_stub(monkeypatch, f"import time\n{_record_pid(pid_file)}time.sleep(600)\n")

    task = asyncio.create_task(parse_in_child(samples.clean_pdf()))
    pid = await _read_pid(pid_file)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        async with asyncio.timeout(PATIENCE_SECONDS):
            await task

    assert await _gone(pid)


def _overlap_stub(directory: Path, hold: float) -> str:
    return (
        "import json, os, time\n"
        f"start = time.monotonic(); time.sleep({hold}); end = time.monotonic()\n"
        f"open(os.path.join({str(directory)!r}, str(os.getpid())), 'w').write(json.dumps([start, end]))\n"
        f"print({VALID_OUTCOME!r})\n"
    )


def _max_overlap(directory: Path) -> int:
    intervals = [json.loads(path.read_text()) for path in directory.iterdir()]
    return int(max(sum(start <= point < end for start, end in intervals) for point, _ in intervals))


@pytest.mark.asyncio
async def test_no_more_children_run_at_once_than_the_limit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    use_stub(monkeypatch, _overlap_stub(tmp_path, hold=0.5))
    count = MAX_CONCURRENT_PARSES * 2 + 1

    async with asyncio.timeout(PATIENCE_SECONDS * 2):
        outcomes = await asyncio.gather(*(parse_in_child(b"x") for _ in range(count)))

    assert all(outcome == Rejected(reason="corrupt") for outcome in outcomes)
    assert len(list(tmp_path.iterdir())) == count
    assert _max_overlap(tmp_path) <= MAX_CONCURRENT_PARSES
    assert _max_overlap(tmp_path) >= min(MAX_CONCURRENT_PARSES, 2), "children should still run side by side"


def test_the_slots_work_across_event_loops(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    use_stub(monkeypatch, _overlap_stub(tmp_path, hold=0.2))

    async def burst() -> None:
        outcomes = await asyncio.wait_for(
            asyncio.gather(*(parse_in_child(b"x") for _ in range(MAX_CONCURRENT_PARSES + 2))), PATIENCE_SECONDS
        )
        assert all(outcome == Rejected(reason="corrupt") for outcome in outcomes)

    for _ in range(3):  # Each asyncio.run is a new loop, and each burst makes the slots contend.
        asyncio.run(burst())

    assert _max_overlap(tmp_path) <= MAX_CONCURRENT_PARSES
