"""The child process: `python -m app.ats.child`, a PDF on stdin and an outcome as JSON on stdout. See sandbox.py."""

import contextlib
import ctypes
import logging
import resource
import sys

from app.ats.constants import MAX_CHILD_MEMORY_BYTES, PARSE_TIMEOUT_SECONDS
from app.ats.parser import parse_pdf

_PR_SET_DUMPABLE = 4


def _forbid_core_dumps() -> None:
    # A dump holds the CV, and RLIMIT_CORE isn't honoured when core_pattern pipes to a handler (apport and the like).
    # Linux only; anywhere else RLIMIT_CORE is what's left.
    with contextlib.suppress(OSError, AttributeError):
        ctypes.CDLL(None).prctl(_PR_SET_DUMPABLE, 0, 0, 0, 0)


def _limit_resources() -> None:
    resource.setrlimit(resource.RLIMIT_AS, (MAX_CHILD_MEMORY_BYTES, MAX_CHILD_MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    # Nothing here has a reason to write a file or start a process. NPROC isn't enforced for root; the image isn't root.
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
    # Only for a child that outlives the worker: otherwise the parent's kill comes first. The hard limit is higher
    # because a kernel at both at once sends SIGKILL, and the parent reads SIGXCPU as running out of time.
    resource.setrlimit(resource.RLIMIT_CPU, (PARSE_TIMEOUT_SECONDS + 1, PARSE_TIMEOUT_SECONDS + 2))


def main() -> None:
    _forbid_core_dumps()
    _limit_resources()
    # pdfminer logs parts of the file. The parent drops stderr too.
    logging.disable(logging.CRITICAL)
    outcome = parse_pdf(sys.stdin.buffer.read())
    sys.stdout.buffer.write(outcome.model_dump_json().encode())


if __name__ == "__main__":
    main()
