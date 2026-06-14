#!/usr/bin/env bash
# Returns 0 if all tests pass, non-zero otherwise.
set -e
cd "$(dirname "${BASH_SOURCE[0]}")/src"
pytest -q test_search.py
