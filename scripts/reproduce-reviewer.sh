#!/bin/sh
set -eu
PYTHONDONTWRITEBYTECODE=1 python3 scripts/reviewer_f1_f11.py --generate
