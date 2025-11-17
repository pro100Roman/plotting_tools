#!/usr/bin/env python3
"""
todo: add routing keyboard input to serial
"""

from datetime import datetime
import argparse
import re
import sys
import time
import threading
import queue
from collections import deque
import csv, os
import logging
import matplotlib.pyplot as plt
import matplotlib.animation as animation

logger = logging.getLogger('serial data')
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

def keyboard_input(in_q: queue.Queue):
    """Reads user input and pushes it to the queue."""
    while True:
        line = sys.stdin.readline()
        in_q.put(line)

def parse_line(line: str, keys):
    number_re = r"-?\d+(?:\.\d+)?"
    # Any-order: per-key search (accept ":" or "=" with optional spaces)
    vals = {}
    for k in keys:
        m = re.search(rf"\b{re.escape(k)}\s*[:=]\s*({number_re})\b", line)
        if not m:
            return None
        vals[k] = float(m.group(1))
    return vals

def serial_reader(port, baud, timeout_s, x_buf:deque, y_bufs:deque, out_q: queue.Queue, ready_event, stop_event: threading.Event, args=None):
    """Background thread: read bytes, split lines, parse, push samples to out_q."""
    try:
        import serial
        import serial.tools.list_ports
    except Exception as e:
        logger.error(f"[error] pyserial not installed: {e}")
        stop_event.set()
        return
    
    if not args:
        raise Exception("args should be provided")

    # Try to open serial
    try:
        ser = serial.Serial(port=port, baudrate=baud, timeout=timeout_s)
        ser.flush()
    except Exception as e:
        try:
            import serial.tools.list_ports as lp
            ports = [p.device for p in lp.comports()]
        except Exception:
            ports = []
        logger.error(f"[error] Failed to open '{port}': {e}\nAvailable ports: {ports}")
        stop_event.set()
        return
    
    t_rel = 0
    logger.info(f"Opened {ser.port} @ {ser.baudrate} (timeout={ser.timeout}s)")
    logger.info(f"Keys={args.k}")
    logger.info("Reading... Close the plot window or Ctrl+C to stop.")

    start = time.monotonic()
    try:
        while not stop_event.is_set():
            while True:
                line = f"{ser.readline()}"
                if line is None:
                    break
                if line != "" and args.o:
                    logger.info(line)
                vals = parse_line(line, args.k)
                if vals is not None:
                    if args.st is None:
                        t_rel = (time.monotonic() - start)
                    else:
                        t_rel += args.st

                    out_q.put({"t": t_rel, **vals})
                    x_buf.append(t_rel)
                    for k in args.k:
                        y_bufs[k].append(vals[k])
                    if not ready_event.is_set():
                        ready_event.set()

                elif line != "":
                    logger.warning(f"Unparsed line: {line}")

    except Exception as e:
        logger.error(f"Reader error: {e}")
    finally:
        try:
            ser.close()
        except Exception:
            pass
        stop_event.set()
        logger.info("Reader stopped.]")

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
    p = argparse.ArgumentParser(description="Plot data from serial port")
    p.add_argument("-p",  dest="port",    required=False, default="/dev/tty.usbserial-1444100", help="serial port, e.g. /dev/cu.usbmodem143302, COM3")
    p.add_argument("-b",  dest="baud",    default=115200, help="serial port baud rate, default=115200")
    p.add_argument("-t",  dest="timeout", default=1, help="serial port timeout in s, default=1")
    p.add_argument("-k",  default=("out", "down", "up",), nargs="+", help="key word to find")
    p.add_argument("-wp", default=500, type=int, help="number of data points to show")
    p.add_argument("-st", default=5,   type=int, help="time between samples in ms")
    p.add_argument("-f",  help="if set data will be saved to this file")
    p.add_argument("-o",  action="store_true", help="show input data")
    p.add_argument("-n",  dest="name", default="test", help="plot name")
    args = p.parse_args()

    # Rolling buffers
    x_buf  = deque(maxlen=args.wp)
    y_bufs = {k: deque(maxlen=args.wp) for k in args.k}

    # Queues & thread
    out_q = queue.Queue()
    stop_event = threading.Event()
    ready_event = threading.Event()

    reader = threading.Thread(
        target=serial_reader,
        args=(args.port, args.baud, args.timeout, x_buf, y_bufs, out_q, ready_event, stop_event, args),
        daemon=True
    )
    reader.start()

    in_q = queue.Queue()
    keyboard_thread = threading.Thread(target=keyboard_input, args=(in_q,), daemon=True)
    keyboard_thread.start()

    # CSV logging setup
    csv_fp = None
    csv_wr = None
    csv_file = f"{args.f}_{datetime.now().strftime('%Y-%m-%d_%H_%M_%S')}.csv"

    if args.f:
        csv_fp = open(csv_file, "w", newline='')
        csv_wr = csv.writer(csv_fp)
        if not os.path.exists(csv_file) or os.path.getsize(csv_file) == 0:
            csv_wr.writerow(['t', *args.k])
        logger.info(f"Logging to CSV: {csv_file}")

    plt.ion()
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.canvas.mpl_connect('close_event', lambda event: on_close(event, stop_event))

    lines = {}
    for k in args.k:
        line, = ax.plot([], [], label=k)  # no explicit colors
        lines[k] = line

    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Value")
    ax.set_title(args.name)
    ax.legend(loc='upper right', bbox_to_anchor=(1, 1))
    ax.grid(True, linestyle="--", alpha=0.5)

    anim = animation.FuncAnimation(fig,
                                   plot_update,
                                   fargs=(ax, lines, ready_event, x_buf, y_bufs),
                                   interval=100,
                                   blit=False,
                                   cache_frame_data=False)

    is_start = False
    single_csv_fp = None
    single_csv_wr = None
    try:
        while not stop_event.is_set():
            try:
                single_csv_file = in_q.get_nowait()
                if single_csv_file:
                    if single_csv_file == "\n":
                        #start-stop signal
                        is_start = False
                        if single_csv_fp:
                            single_csv_fp.flush()
                            single_csv_fp.close()
                        logger.info(f"STOP received")
                if single_csv_file != "\n" and not is_start:
                    is_start = True
                    single_csv_file = f"{single_csv_file[:-1]}_{datetime.now().strftime('%Y-%m-%d_%H_%M_%S')}.csv"
                    single_csv_fp = open(single_csv_file, "w", newline='')
                    single_csv_wr = csv.writer(single_csv_fp)
                    if not os.path.exists(single_csv_file) or os.path.getsize(single_csv_file) == 0:
                        single_csv_wr.writerow(['t', *args.k])
                    logger.info(f"Logging to single CSV: {single_csv_file}")
                    single_csv_fp.flush()
            except queue.Empty:
                pass

            drained = 0
            rows_to_write = []
            try:
                while True:
                    rec = out_q.get_nowait()
                    if csv_wr or single_csv_wr:
                        rows_to_write.append([rec['t']] + [rec.get(k, float('nan')) for k in args.k])
            except queue.Empty:
                pass

            if is_start and single_csv_wr and rows_to_write:
                single_csv_wr.writerows(rows_to_write)
                single_csv_fp.flush()
            # Write CSV rows (even if no draw this iteration)
            if csv_wr and rows_to_write:
                csv_wr.writerows(rows_to_write)
                csv_fp.flush()

            plt.pause(0.01)

    except KeyboardInterrupt:
        raise
    
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")

    finally:
        plt.close(fig)
        stop_event.set()
        reader.join(timeout=0.1)
        keyboard_thread.join(timeout=0.1)

        if single_csv_fp:
            try:
                single_csv_fp.flush()
                single_csv_fp.close()
            except Exception:
                pass

        if csv_fp is not None:
            try:
                csv_fp.flush()
                csv_fp.close()
                logger.info(f"[info] CSV closed: {csv_file}")
            except Exception:
                pass
        sys.exit(0)

if __name__ == "__main__":
    sys.exit(main())
