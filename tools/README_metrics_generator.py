"""Regenerate the README test-count badge metrics.

Writes `metrics.json` in the repository root and prints the same object. It is
normally run through `scripts/update-readme.sh`, which reads that file and rewrites
the `<!-- METRICS:START -->` block; running this alone leaves `README.md` untouched.

Dependency, recorded because it is undeclared: this generator shells out to
`pytest`, which appears in neither `package.json` nor a requirements file. It works
on this machine only because pytest happens to be installed at `~/bin/pytest`. If
pytest is not on `PATH`, the result is a `status: error` object naming that cause,
so the badge is left alone instead of being rewritten from zeroes.
"""

import json
import os
import re
import shutil
import subprocess


def get_test_metrics():
    # Only run pytest on the tests/ directory
    if not os.path.exists("tests"):
        return {"status": "error", "message": "tests/ directory not found"}

    # Fail with a named cause rather than an unhandled FileNotFoundError, which the
    # broad except below would otherwise report as an opaque message.
    pytest_bin = shutil.which("pytest")
    if pytest_bin is None:
        return {
            "status": "error",
            "message": "pytest not found on PATH (undeclared dependency of this generator)",
        }

    try:
        # Prepare environment with PYTHONPATH set to the root
        env = os.environ.copy()
        env["PYTHONPATH"] = "."
        
        # pytest exit codes: 0 = passed, 1 = tests failed
        result = subprocess.run([pytest_bin, 'tests/', '-q'], capture_output=True, text=True, env=env)
        output = result.stdout + result.stderr
        
        # Look for the summary line: "70 passed, 2 failed in 0.1s"
        pass_match = re.search(r'(\d+) passed', output)
        fail_match = re.search(r'(\d+) failed', output)
        error_match = re.search(r'(\d+) error', output)
        
        passing_count = int(pass_match.group(1)) if pass_match else 0
        failing_count = int(fail_match.group(1)) if fail_match else 0
        error_count = int(error_match.group(1)) if error_match else 0
            
    except Exception as e:
        return {"status": "error", "message": str(e)}
        
    return {
        "status": "success",
        "passing_tests": passing_count,
        "failing_tests": failing_count,
        "error_tests": error_count
    }

if __name__ == "__main__":
    metrics = get_test_metrics()
    with open("metrics.json", "w") as f:
        json.dump(metrics, f, indent=4)
    print(f"Metrics generated: {json.dumps(metrics)}")
