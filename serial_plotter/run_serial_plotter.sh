#!/bin/bash
SCRIPT_DIR="/Volumes/Macintosh HD/Users/roman/Work/Tools/Software"
echo $SCRIPT_DIR
source "$SCRIPT_DIR/.venv/bin/activate"
python "$SCRIPT_DIR/serial_plotter/serial_plotter.py" "$@"
deactivate