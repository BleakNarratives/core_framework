import json
import subprocess
import re
import os

def get_test_metrics():
    # Only run pytest on the tests/ directory
    if not os.path.exists("tests"):
        return {"status": "error", "message": "tests/ directory not found"}
        
    try:
        # Prepare environment with PYTHONPATH set to the root
        env = os.environ.copy()
        env["PYTHONPATH"] = "."
        
        # pytest exit codes: 0 = passed, 1 = tests failed
        result = subprocess.run(['pytest', 'tests/', '-q'], capture_output=True, text=True, env=env)
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
