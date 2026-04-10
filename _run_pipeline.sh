#!/bin/bash
cd /c/Users/shieru_k/Documents/security-agent
unset VIRTUAL_ENV
exec uv run python3 scripts/run_phase.py --target 04 --workers 4 --force
