#!/usr/bin/env python3
"""
todo: add routing keyboard input to serial
"""

from datetime import datetime
import argparse
import sys
import threading
import queue
from collections import deque
import logging
import matplotlib.pyplot as plt
import matplotlib.animation as animation

def keyboard_input(in_q: queue.Queue):
    """Reads user input and pushes it to the queue."""
    while True:
        line = sys.stdin.readline()
        in_q.put(line)

def plot_update(frame, ax, lines, ready_event:threading.Event, x_buf:deque, y_bufs:deque):
    # Update data each frame
    if ready_event.is_set():
        ready_event.clear()
        for line_i in lines:
            lines[line_i].set_data(x_buf, y_bufs[line_i])

        ax.relim()
        ax.autoscale_view(scaley=True)

    return lines,

def on_close(event, stop_event):
        stop_event.set()

def main():
    p = argparse.ArgumentParser(description="Data plotter")
    p.add_argument("-w",  dest="worker",   required=True,  help="worker script for gathering data, e.g: 'worker_serial_str'")
    p.add_argument("-p",  dest="port",     required=False, default="/dev/tty.usbserial-1444100", help="serial port, e.g. /dev/cu.usbmodem143302, COM3")
    p.add_argument("-b",  dest="baudrate", default=115200, help="serial port baud rate, default=115200")
    p.add_argument("-t",  dest="timeout",  default=1,      help="serial port timeout in s, default=1")
    p.add_argument("-k",  dest="keys",     default=("out", "down", "up",), nargs="+", help="key word to find")
    p.add_argument("-wp", default=5000, type=int, help="number of data points to show")
    p.add_argument("-st", default=5,   type=int, help="time between samples in ms")
    p.add_argument("-f",  dest="file", help="if set data will be saved to this file in case of worker_csv csv file to open and plot")
    p.add_argument("-n",  dest="name", default="test", help="plot name")
    args = p.parse_args()

    log_file_name = f"{args.file}_{datetime.now().strftime('%Y-%m-%d_%H_%M_%S')}.log" if args.file else "data plotter"
    logger = logging.getLogger(log_file_name)
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    if args.file and args.worker != "worker_csv" and args.worker != "worker_log":
        file_handler = logging.FileHandler(log_file_name)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    stop_event = threading.Event()
    ready_event = threading.Event()

    x_buf  = deque(maxlen=args.wp)
    y_bufs = {k: deque(maxlen=args.wp) for k in args.keys}

    if args.worker == "worker_serial_str":
        from worker_serial_str import WorkerSerialStr
        try:
            worker = WorkerSerialStr(
                log_file_name,
                args.port, int(args.baudrate), float(args.timeout),
                stop_event, ready_event,
                args.st,
                x_buf, y_bufs
            )
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
    elif args.worker == "worker_csv":
        from worker_csv import WorkerCsv
        try:
            worker = WorkerCsv(
                log_file_name,
                args.file,
                stop_event, ready_event,
                x_buf, y_bufs
            )
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
    elif args.worker == "worker_log":
        from worker_log import WorkerLog
        try:
            worker = WorkerLog(
                log_file_name,
                args.file,
                stop_event, ready_event,
                x_buf, y_bufs
            )
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
    else:
        raise Exception("worker script not provided")

    worker.start()

    in_q = queue.Queue()
    keyboard_thread = threading.Thread(target=keyboard_input, args=(in_q,), daemon=True)
    keyboard_thread.start()

    plt.ion()
    fig, ax = plt.subplots(figsize=(12, 6))
    fig.canvas.mpl_connect('close_event', lambda event: on_close(event, stop_event))

    lines = {}
    for k in args.keys:
        line, = ax.plot([], [], label=k)  # no explicit colors
        lines[k] = line

    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Value")
    ax.set_title(args.name)
    ax.legend(loc='upper left', bbox_to_anchor=(1, 1))
    ax.grid(True, linestyle="--", alpha=0.5)

    anim = animation.FuncAnimation(fig,
                                   plot_update,
                                   fargs=(ax, lines, ready_event, x_buf, y_bufs),
                                   interval=25,
                                   blit=False,
                                   cache_frame_data=False)

    try:
        while not stop_event.is_set():
            plt.pause(0.01)
    except KeyboardInterrupt:
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
    finally:
        plt.close(fig)
        stop_event.set()
        worker.join(timeout=0.1)
        keyboard_thread.join(timeout=0.1)
        sys.exit(0)

if __name__ == "__main__":
    sys.exit(main())
