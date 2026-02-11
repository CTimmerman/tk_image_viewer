#!/usr/bin/env python
"""Cross-platform pre-commit hook"""

import os
import subprocess
import sys

# Detect repo root using git (robust even if run from subfolders)
try:
    repo_root = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], text=True
    ).strip()
except subprocess.CalledProcessError:
    # fallback: current file's parent
    repo_root = os.path.dirname(os.path.abspath(__file__))

python_exe: str = sys.executable
# Detect venv
for name in ("venv", ".venv"):
    venv_python = (
        os.path.join(repo_root, name, "Scripts", "python.exe")
        if os.name == "nt"
        else os.path.join(repo_root, name, "bin", "python")
    )
    if os.path.isfile(venv_python):
        python_exe = venv_python
        break

# Determine files to check
files = sys.argv[1:] if len(sys.argv) > 1 else [repo_root]


def run_cmd(cmd):
    "Function to run a command and capture output"
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    print(result.stdout, end="")
    print(result.stderr, end="")
    return result.returncode


# Run Black
black_exit = run_cmd([python_exe, "-m", "black", "--check"] + files)

# Run Pylint
pylint_exit = run_cmd([python_exe, "-m", "pylint", "-rn", "-sn"] + files)

# Exit with max return code to indicate failure if either fails
sys.exit(max(black_exit, pylint_exit))
