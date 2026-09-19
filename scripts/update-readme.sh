#!/bin/bash

# Generate metrics
python3 tools/README_metrics_generator.py

# Read metrics
PASSING=$(python3 -c "import json; print(json.load(open('metrics.json'))['passing_tests'])")
FAILING=$(python3 -c "import json; print(json.load(open('metrics.json'))['failing_tests'])")

# Determine badge color and text
if [ "$FAILING" -gt 0 ]; then
    COLOR="red"
    TEXT="${PASSING}%20passing%2C%20${FAILING}%20failed"
else
    COLOR="brightgreen"
    TEXT="${PASSING}%20passing"
fi

NEW_BADGE="[![Tests](https://img.shields.io/badge/tests-${TEXT}-${COLOR})](#tests)"

# Update README.md using more robust approach
# Remove old badge between markers and insert new one
sed -i "/<!-- METRICS:START -->/,/<!-- METRICS:END -->/{
    /<!-- METRICS:START -->/b
    /<!-- METRICS:END -->/b
    d
}" README.md
sed -i "/<!-- METRICS:START -->/a $NEW_BADGE" README.md

echo "README.md updated with badge: $NEW_BADGE"
