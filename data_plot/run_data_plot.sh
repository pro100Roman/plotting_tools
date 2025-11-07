#!/bin/bash
SCRIPT_DIR="./"
echo $SCRIPT_DIR
source "$SCRIPT_DIR/.venv/bin/activate"
python "$SCRIPT_DIR/data_plot/data_plot.py" "$@"
deactivate