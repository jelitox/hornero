"""Resource-bounded subprocess runner with sanitized environment."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


class SandboxError(RuntimeError):
    pass


@dataclass(frozen=True)
class SandboxLimits:
    cpu_seconds: int = 900
    memory_bytes: int = 2 * 1024 * 1024 * 1024
    output_bytes: int = 1_000_000
    processes: int = 128


def _limits(policy: SandboxLimits):
    def apply() -> None:
        try:
            import resource

            resource.setrlimit(resource.RLIMIT_CPU, (policy.cpu_seconds, policy.cpu_seconds))
            resource.setrlimit(resource.RLIMIT_AS, (policy.memory_bytes, policy.memory_bytes))
            resource.setrlimit(resource.RLIMIT_FSIZE, (policy.output_bytes, policy.output_bytes))
            resource.setrlimit(resource.RLIMIT_NPROC, (policy.processes, policy.processes))
        except (ImportError, OSError, ValueError):
            pass
    return apply


class SandboxRunner:
    def __init__(
        self, prefix: list[str], *, require: bool = False,
        limits: SandboxLimits | None = None,
    ) -> None:
        if require and not prefix:
            raise SandboxError("an explicit sandbox_command is required")
        self._prefix = list(prefix)
        self._limits = limits or SandboxLimits()

    def run(
        self, command: list[str], *, cwd: Path, input: str | None = None,
        timeout: float = 900,
    ) -> subprocess.CompletedProcess[str]:
        if not command or not all(isinstance(item, str) and item for item in command):
            raise SandboxError("sandbox command must be a non-empty argv list")
        env = {
            key: value for key, value in os.environ.items()
            if key in {"PATH", "LANG", "LC_ALL", "HOME", "TMPDIR"}
        }
        env["HORNERO_SANDBOX"] = "1"
        argv = [*self._prefix, *command]
        try:
            result = subprocess.run(
                argv, cwd=cwd, input=input, capture_output=True, text=True,
                check=False, timeout=timeout, env=env,
                preexec_fn=_limits(self._limits) if os.name == "posix" else None,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise SandboxError(str(exc)) from exc
        stdout = result.stdout[: self._limits.output_bytes]
        stderr = result.stderr[: self._limits.output_bytes]
        return subprocess.CompletedProcess(argv, result.returncode, stdout, stderr)
