#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 -m unittest discover -s tests -v
python3 -m compileall -q briefmint scripts
python3 scripts/package_skill.py
