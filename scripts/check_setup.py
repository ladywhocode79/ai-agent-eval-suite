#!/usr/bin/env python3
"""
Pre-flight setup checker for the AI Agent Eval Suite.

Usage:
    python scripts/check_setup.py
"""

import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)

PASS, FAIL, WARN, INFO = "  [PASS]", "  [FAIL]", "  [WARN]", "  [INFO]"
errors = []


def check(label, fn):
    try:
        result = fn()
        print(f"{PASS} {label}" + (f" — {result}" if result else ""))
    except Exception as e:
        print(f"{FAIL} {label}\n         {e}")
        errors.append(label)


def _import(pkg):
    __import__(pkg)


print("\n=== AI Agent Eval Suite — Setup Check ===\n")

if sys.version_info >= (3, 10):
    print(f"{PASS} Python version — {sys.version.split()[0]}")
else:
    print(f"{WARN} Python version — {sys.version.split()[0]} (3.10+ recommended)")

print()
for label, pkg in [
    ("anthropic package", "anthropic"),
    ("deepeval package", "deepeval"),
    ("pytest package", "pytest"),
    ("pytest-html package", "pytest_html"),
    ("pytest-xdist package", "xdist"),
    ("scikit-learn (Cohen's Kappa)", "sklearn"),
    ("python-dotenv", "dotenv"),
]:
    check(label, lambda p=pkg: _import(p))

for label, pkg in [("ollama package (optional, local judge)", "ollama"),
                   ("google-genai package (optional, Gemini judge)", "google.genai")]:
    try:
        _import(pkg)
        print(f"{PASS} {label}")
    except ImportError:
        print(f"{INFO} {label} — not installed")

print()
from dotenv import load_dotenv

load_dotenv(os.path.join(ROOT, ".env"))

key = os.environ.get("ANTHROPIC_API_KEY", "")
gem = os.environ.get("GEMINI_API_KEY", "")
if key and key != "your-api-key-here":
    print(f"{PASS} ANTHROPIC_API_KEY — set ({key[:8]}...)")
elif gem:
    print(f"{PASS} GEMINI_API_KEY — set")
else:
    print(f"{WARN} No cloud key set — a judge is only available if Ollama is running")

print(f"{INFO} EVAL_JUDGE_BACKEND — {os.environ.get('EVAL_JUDGE_BACKEND', os.environ.get('JUDGE_BACKEND', 'auto'))}")


def _resolve_judge():
    from frameworks.evals.judge_factory import get_judge_model

    j = get_judge_model()
    return f"{type(j).__name__} ({j.get_model_name()})"


check("Judge model resolves", _resolve_judge)

print()
for name in ("golden_set.json", "human_annotated_sets.json"):
    path = os.path.join(ROOT, "datasets", name)
    check(f"datasets/{name}", lambda p=path: "found" if os.path.exists(p) else (_ for _ in ()).throw(FileNotFoundError(p)))

print()
if not errors:
    print("=== All checks passed. You're ready to run tests! ===\n")
    print("    pytest -m calibration -s")
    print("    pytest -m evals -n auto\n")
else:
    print(f"=== {len(errors)} issue(s) found. Fix the above before running tests. ===\n")
    for e in errors:
        print(f"      - {e}")
    print()
    sys.exit(1)
