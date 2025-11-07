#!/bin/bash
SCRIPT_DIR="./"
echo $SCRIPT_DIR
source "$SCRIPT_DIR/.venv/bin/activate"
python "$SCRIPT_DIR/serial_plotter/serial_plotter.py" "$@"
deactivate