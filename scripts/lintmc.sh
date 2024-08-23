#!/usr/bin/env bash

# tiny script to lint jami_commander.py

FN="jami_commander.py"

if ! [ -f "$FN" ]; then
    FN="jami_commander/$FN"
    if ! [ -f "$FN" ]; then
        echo -n "ERROR: $(basename -- "$FN") not found. "
        echo "Neither in local nor in child directory."
        exit 1
    fi
fi
isort "$FN" && flake8 "$FN" && python3 -m black --line-length 79 "$FN"
