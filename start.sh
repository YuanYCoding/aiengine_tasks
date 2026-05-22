#!/bin/bash
set -e

echo "[START] Cleaning up leftover X locks..."
rm -f /tmp/.X*-lock /tmp/.X11-unix/X*

echo "[START] Starting Python app on port ${PORT} (multi-user mode)..."
exec python main.py
