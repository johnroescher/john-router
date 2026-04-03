#!/usr/bin/env python3
"""John Router V1 QA Runner.

Runs the automated QA harness:
  Layer 1: API scenarios + quality judge (pytest)
  Layer 2: Browser flows (manual — prints instructions for MCP execution)
  Layer 3: Rideability checks (included in Layer 1 pytest)

Usage:
  cd "V1 - Claude Code/backend"
  .venv/bin/python scripts/run_v1_qa.py [--skip-browser] [--api-only]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
TESTS_DIR = BACKEND_DIR / "tests"
QA_DIR = TESTS_DIR / "qa"
SCREENSHOTS_DIR = BACKEND_DIR / "qa_screenshots"


def check_backend():
    """Verify backend is reachable."""
    import urllib.request
    try:
        r = urllib.request.urlopen("http://localhost:8000/api/health", timeout=5)
        data = json.loads(r.read())
        if data.get("status") == "healthy":
            print("  Backend: healthy")
            return True
    except Exception as e:
        print(f"  Backend: UNREACHABLE ({e})")
    return False


def check_frontend():
    """Verify frontend is reachable."""
    import urllib.request
    try:
        r = urllib.request.urlopen("http://localhost:3000/planner", timeout=5)
        if r.status == 200:
            print("  Frontend: healthy")
            return True
    except Exception as e:
        print(f"  Frontend: UNREACHABLE ({e})")
    return False


def run_api_scenarios():
    """Run Layer 1 + Layer 3 via pytest."""
    print("\n" + "=" * 60)
    print("LAYER 1+3: API Scenarios + Rideability")
    print("=" * 60)

    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            str(QA_DIR / "scenarios.py"),
            "-v", "-s",
            "--tb=short",
            "--no-header",
            "-p", "tests.qa.scenarios",
        ],
        cwd=str(BACKEND_DIR),
        capture_output=False,
    )
    return result.returncode == 0


def print_browser_instructions():
    """Print instructions for running browser flows via MCP."""
    print("\n" + "=" * 60)
    print("LAYER 2: Browser Flows")
    print("=" * 60)
    print("""
  Browser flows use the cursor-ide-browser MCP and must be run
  from the AI assistant. Ask the assistant:

    "Run the V1 browser QA flows defined in
     backend/tests/qa/browser_flows.py"

  The assistant will:
  1. Navigate to http://localhost:3000/planner
  2. Execute each flow (chat, sport switching, error resilience)
  3. Take screenshots saved to backend/qa_screenshots/
  4. Report pass/fail for each flow

  Alternatively, run Playwright e2e tests:
    cd "V1 - Claude Code/frontend"
    npx playwright test
""")


def main():
    skip_browser = "--skip-browser" in sys.argv
    api_only = "--api-only" in sys.argv

    SCREENSHOTS_DIR.mkdir(exist_ok=True)

    print("=" * 60)
    print("JOHN ROUTER V1 QA HARNESS")
    print("=" * 60)
    print()
    print("Pre-flight checks:")

    backend_ok = check_backend()
    if not backend_ok:
        print("\n  ABORT: Backend not running. Start it first:")
        print('  cd "V1 - Claude Code/backend"')
        print("  .venv/bin/uvicorn app.main:app --port 8000 --reload")
        sys.exit(1)

    frontend_ok = check_frontend()

    # Layer 1 + 3: API tests
    api_passed = run_api_scenarios()

    # Layer 2: Browser flows
    if not skip_browser and not api_only and frontend_ok:
        print_browser_instructions()
    elif not frontend_ok:
        print("\n  SKIP: Browser flows (frontend not running)")

    # Summary
    print("\n" + "=" * 60)
    print("QA SUMMARY")
    print("=" * 60)
    print(f"  API + Rideability:  {'PASSED' if api_passed else 'FAILED'}")
    if frontend_ok and not skip_browser and not api_only:
        print("  Browser Flows:     PENDING (run via assistant)")
    elif not frontend_ok:
        print("  Browser Flows:     SKIPPED (no frontend)")
    else:
        print("  Browser Flows:     SKIPPED (--skip-browser)")

    if api_passed:
        print("\n  Result: API layer is SHIP-READY")
    else:
        print("\n  Result: FIX FAILURES before shipping")

    sys.exit(0 if api_passed else 1)


if __name__ == "__main__":
    main()
