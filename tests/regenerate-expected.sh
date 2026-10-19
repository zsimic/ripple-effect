#!/bin/sh
# Regenerate the expected `show` output of each sample config (compared by test_samples), then review with `git diff`
cd "$(dirname "$0")/.." || exit 1
for f in tests/samples/*.yml; do
    (.venv/bin/ripple-effect -c "$f" show 2>&1) > "${f%.yml}.txt"
done
