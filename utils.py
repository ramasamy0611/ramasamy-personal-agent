"""
Utilities — macOS Keychain secret management and logging.
Secrets are NEVER stored in files or environment variables.
"""

import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime


def get_secret(key: str) -> str | None:
    """Retrieve a secret from macOS Keychain."""
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", key, "-w"],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def set_secret(key: str, value: str) -> None:
    """Store a secret in macOS Keychain (creates or updates)."""
    subprocess.run(
        ["security", "delete-generic-password", "-s", key],
        capture_output=True
    )
    subprocess.run(
        ["security", "add-generic-password", "-s", key, "-a", "email-agent", "-w", value],
        check=True
    )
    print(f"Secret '{key}' saved to Keychain.")


def log(message: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {message}")


@contextmanager
def timer(label: str):
    """Context manager that prints elapsed time for a block."""
    start = time.perf_counter()
    yield
    elapsed = time.perf_counter() - start
    print(f"  ⏱  {label}: {elapsed:.2f}s")


# CLI helper: python utils.py set-secret <key> <value>
if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "set-secret":
        set_secret(sys.argv[2], sys.argv[3])
    else:
        print("Usage: python utils.py set-secret <key> <value>")
