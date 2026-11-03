#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR/.."
echo $SCRIPT_DIR
source "$ROOT_DIR/.venv/bin/activate"
python "$SCRIPT_DIR/serial_plotter.py" "$@"
deactivate