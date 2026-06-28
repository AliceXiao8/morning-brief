#!/bin/bash
cd "$(dirname "$0")"
if ! pgrep -x "ollama" > /dev/null; then
    ollama serve &
    sleep 4
fi
python3 morning_brief.py
