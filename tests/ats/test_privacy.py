"""No CV text in logs or on the worker's stderr, at the most verbose level, whichever way a file ends."""

import asyncio
import dataclasses
import logging
import os
import sys

import pytest

from app.ats import sandbox
from app.ats.constants import MAX_PAGES
from app.ats.parser import parse_pdf
from app.ats.sandbox import ParserFailed, parse_in_child
from tests.ats import samples

pytestmark = pytest.mark.asyncio

MARKER = "ZQXMARKER9917"
CV = dataclasses.replace(
    samples.CV,
    name=f"Alex {MARKER}",
    email=f"{MARKER.lower()}@example.com",
    summary=(f"Distinctive summary line {MARKER} for the log check.",),
)
SANDBOX_LOGGER = sandbox.logger.name
# A stub child that dumps everything it is given to stderr, as a crashing parser's traceback might.
ECHO_TO_STDERR = (
    "import sys; data = sys.stdin.buffer.read(); sys.stderr.buffer.write(data); sys.stderr.buffer.flush(); "
    'print(\'{"outcome": "rejected", "reason": "corrupt"}\')'
)


async def test_the_samples_carry_their_text_in_the_clear() -> None:
    """The leak checks below mean nothing if a compressed file hides the marker from the child and the logs."""
    for pdf in (samples.clean_pdf(CV), samples.truncated_pdf(samples.clean_pdf(CV))):
        assert MARKER.encode() in pdf


def _secrets() -> list[str]:
    values = [MARKER, MARKER.lower(), *CV.summary, CV.phone, CV.location, *CV.links]
    values += [job.company for job in CV.experience]
    return values


def _assert_no_cv_text(caplog: pytest.LogCaptureFixture) -> None:
    logged = caplog.text + "\n".join(str(record.args) + record.getMessage() for record in caplog.records)
    for secret in _secrets():
        assert secret not in logged


def _sandbox_warnings(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == SANDBOX_LOGGER and r.levelno >= logging.WARNING]


@pytest.fixture(autouse=True)
def verbose_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)


async def test_the_capture_can_see_the_sandbox_logging(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """If this fails, the other tests in this file would pass without proving anything."""
    monkeypatch.setattr(sandbox, "CHILD_COMMAND", (sys.executable, "-c", "import time; time.sleep(60)"))

    await parse_in_child(samples.clean_pdf(CV), time_limit=0.5)

    assert _sandbox_warnings(caplog)


async def test_parsing_samples_logs_no_cv_text(caplog: pytest.LogCaptureFixture) -> None:
    odd_dates = samples.Job("Analyst", "Example Ltd", "Spring 2019", "'21", ())
    files = [
        samples.clean_pdf(CV),
        samples.two_column_pdf(CV),
        samples.tables_pdf(CV),
        samples.header_text_pdf(CV),
        samples.pages_pdf(MAX_PAGES + 1, CV),  # rejected: too many pages
        samples.truncated_pdf(samples.clean_pdf(CV)),  # rejected: corrupt, with CV text still in the bytes
        samples.encrypted_pdf(CV),  # rejected: encrypted
        samples.scanned_pdf(CV),
        samples.owner_password_only_pdf(CV),
        samples.page_kinds_pdf(["text", "image"], CV),
        # The field stages see every kind of CV line: contacts, headings, skills.
        samples.clean_pdf(dataclasses.replace(CV, experience=(odd_dates,))),
        samples.clean_pdf(dataclasses.replace(CV, email="", phone="", experience=(), education=())),
    ]
    for pdf in files:
        parse_pdf(pdf)
        await parse_in_child(pdf)

    _assert_no_cv_text(caplog)


@pytest.mark.parametrize(
    ("code", "logs_a_warning"),
    [
        ("import sys; sys.exit(1)", False),
        ("import sys; sys.stdin.buffer.read(); sys.stderr.buffer.write(b'leak'); print('junk')", False),
        ("import time; time.sleep(60)", True),
        ("import os, signal; os.kill(os.getpid(), signal.SIGKILL)", False),
        ("import os, signal; os.kill(os.getpid(), signal.SIGSEGV)", True),
    ],
    ids=["exit-1", "junk-output", "timeout", "killed", "segfault"],
)
async def test_a_failing_child_logs_no_cv_text(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, code: str, logs_a_warning: bool
) -> None:
    monkeypatch.setattr(sandbox, "CHILD_COMMAND", (sys.executable, "-c", code))

    try:
        await parse_in_child(samples.clean_pdf(CV), time_limit=1)
    except ParserFailed as failure:
        assert MARKER not in str(failure)

    if logs_a_warning:
        assert _sandbox_warnings(caplog), "the sandbox should have logged this, so the check below can see it"
    _assert_no_cv_text(caplog)


async def test_the_child_s_stderr_does_not_reach_the_workers(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    os.write(2, b"stderr-capture-sanity\n")
    assert "stderr-capture-sanity" in capfd.readouterr().err  # fd 2 is being captured, so absence below means something

    monkeypatch.setattr(sandbox, "CHILD_COMMAND", (sys.executable, "-c", ECHO_TO_STDERR))
    await asyncio.wait_for(parse_in_child(samples.clean_pdf(CV)), 30)

    captured = capfd.readouterr()
    for secret in _secrets():
        assert secret not in captured.err
        assert secret not in captured.out


async def test_the_real_child_writes_no_cv_text_to_stderr(capfd: pytest.CaptureFixture[str]) -> None:
    for pdf in (samples.clean_pdf(CV), samples.truncated_pdf(samples.clean_pdf(CV)), samples.encrypted_pdf(CV)):
        await asyncio.wait_for(parse_in_child(pdf), 30)

    captured = capfd.readouterr()
    for secret in _secrets():
        assert secret not in captured.err
        assert secret not in captured.out


async def test_a_bug_in_a_later_stage_leaks_no_cv_text_to_logs_or_stderr(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, capfd: pytest.CaptureFixture[str]
) -> None:
    code = (
        "import app.ats.parser as parser\n"
        "def boom(*args, **kwargs):\n"
        "    raise RuntimeError('stage bug')\n"
        "parser.extract_contact = boom\n"
        "import app.ats.child as child\n"
        "child.main()\n"
    )
    monkeypatch.setattr(sandbox, "CHILD_COMMAND", (sys.executable, "-c", code))

    with pytest.raises(ParserFailed) as failure:
        await asyncio.wait_for(parse_in_child(samples.clean_pdf(CV)), 30)

    assert MARKER not in str(failure.value)
    _assert_no_cv_text(caplog)
    captured = capfd.readouterr()
    for secret in _secrets():
        assert secret not in captured.err
        assert secret not in captured.out
