"""Oracle evaluator — runs an oracle_check shell command and returns pass/fail."""

from __future__ import annotations

import subprocess


class OracleEvaluator:
    """Evaluates whether a task was solved by running its oracle_check command."""

    def evaluate(
        self,
        oracle_check: str,
        cwd: str,
        pass_exit_code: int = 0,
        timeout: int = 60,
    ) -> bool:
        """Run oracle_check in cwd and return True if the exit code matches pass_exit_code."""
        try:
            result = subprocess.run(
                oracle_check,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode == pass_exit_code
        except subprocess.TimeoutExpired:
            return False
        except Exception:
            return False

    def evaluate_verbose(
        self,
        oracle_check: str,
        cwd: str,
        pass_exit_code: int = 0,
        timeout: int = 60,
    ) -> tuple[bool, str]:
        """Same as evaluate() but also returns stdout+stderr for debugging."""
        try:
            result = subprocess.run(
                oracle_check,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = (result.stdout + result.stderr).strip()
            return result.returncode == pass_exit_code, output
        except subprocess.TimeoutExpired:
            return False, "[oracle timed out]"
        except Exception as exc:
            return False, f"[oracle error] {exc}"
