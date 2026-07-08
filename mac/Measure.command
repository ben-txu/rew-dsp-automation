#!/bin/zsh
# Double-click launcher: runs the measurement in a Terminal window
# (prompts + live log). Keep this file next to dv_speaker_measure.py.
cd "$(dirname "$0")"
/usr/bin/env python3 dv_speaker_measure.py
echo ""
echo "── Done. You can close this window. ──"
