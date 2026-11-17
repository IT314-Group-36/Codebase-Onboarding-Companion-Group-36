"""Apply hard Linux resource limits before exec'ing Git.

Use a separate interpreter rather than preexec_fn: indexing starts subprocesses
from worker threads, where preexec_fn can deadlock. Windows uses the parent's
disk/time watchdog; production Docker/Linux also gets these kernel limits.
"""
import os
import sys


def main():
    memory, file_bytes, cpu = (int(value) for value in sys.argv[1:4])
    if sys.platform == "linux":
        import resource

        for kind, value in (
            (resource.RLIMIT_AS, memory),
            (resource.RLIMIT_FSIZE, file_bytes),
            (resource.RLIMIT_CPU, cpu),
            (resource.RLIMIT_CORE, 0),
        ):
            resource.setrlimit(kind, (value, value))
    os.execvp(sys.argv[4], sys.argv[4:])


if __name__ == "__main__":
    main()
