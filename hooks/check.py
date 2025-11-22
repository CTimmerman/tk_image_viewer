#!/usr/bin/env python
"""Run Black formatter & PyLint linter on Python code."""
import os
import subprocess
import sys

python = (
    os.path.join("venv", "Scripts", "python.exe")
    if os.name == "nt"
    else os.path.join("venv", "bin", "python")
)

result = subprocess.run([python, "-m", "black", "--check", "."], check=False)
if result:
    sys.exit(result.returncode)

# Run Pylint with all arguments passed from pre-commit
result = subprocess.run([python, "-m", "pylint"] + sys.argv[1:], check=False)
sys.exit(result.returncode)
