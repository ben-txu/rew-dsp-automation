#!/bin/zsh
# Double-click launcher for the native macOS PC-Tool bridge.
# Keep it next to pctool_bridge_mac.py. Leave the window open during runs.
# Add --solo-modifier control below if Command+digit does not solo.
cd "$(dirname "$0")"
/usr/bin/env python3 -u pctool_bridge_mac.py "$@"
