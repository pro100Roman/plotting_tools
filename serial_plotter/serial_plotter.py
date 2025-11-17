#!/usr/bin/env python3

# ===================== CONFIG (edit here) =====================
TIMEOUT_S           = 0.01                         # serial read timeout (seconds)
DATA_SAMPLE_RATE_HZ = 200                          # expected data rate (for reference only)
TIME_INC            = 1000 // DATA_SAMPLE_RATE_HZ  # expected time increment between samples (for reference only)
MAX_FPS             = 20                           # plot refresh rate (frames per second)
IDLE_EXIT_SEC       = None                         # set to a number to auto-exit if no bytes arrive for this many seconds
SAVE_FINAL_PNG      = None                         # e.g., "final_plot.png" to save on exit, or None to skip
CSV_APPEND          = True                         # True: append to existing file (write header only if file empty)
# ===============================================================

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

def pop_next_line_from_buf(buf: bytearray):
    """Pop the next decoded text line from buf handling CR, LF, or CRLF. Returns str or None."""
    if not buf:
        return None
    nl = buf.find(b"\n")
    cr = buf.find(b"\r")
    candidates = [i for i in (nl, cr) if i >= 0]
    if not candidates:
        return None
    idx = min(candidates)
    line_bytes = buf[:idx]
    end_char = buf[idx:idx+1]
    del buf[:idx+1]
    # handle CRLF
    if end_char == b"\r" and buf[:1] == b"\n":
        del buf[:1]
    try:
        return line_bytes.decode("utf-8", errors="replace")
    except Exception:
        return line_bytes.decode("latin-1", errors="replace")

def serial_reader(port, baud, timeout_s, out_q: queue.Queue, stop_event: threading.Event, args=None):
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

    buf = bytearray()
    start = time.monotonic()
    last_rx = start

    try:
        while not stop_event.is_set():
            chunk = ser.readline()
            if chunk:
                buf.extend(chunk)
                last_rx = time.monotonic()

            # Extract any complete lines available
            while True:
                line = pop_next_line_from_buf(buf)
                if line is None:
                    break
                if line != "" and args.o:
                    logger.info(line)
                vals = parse_line(line, args.k)
                if vals is not None:
                    if args.st is None:
                        # Use expected time increment between samples (for reference only)
                        t_rel = (time.monotonic() - start)
                    else:
                        t_rel += args.st
                    out_q.put({"t": t_rel, **vals})
                elif line != "":
                    logger.warning(f"Unparsed line: {line}")
                    buf.clear()

            # Optional idle exit
            if IDLE_EXIT_SEC is not None and (time.monotonic() - last_rx) >= IDLE_EXIT_SEC:
                logger.info(f"Idle for {IDLE_EXIT_SEC}s; stopping reader.")
                break
    except Exception as e:
        logger.error(f"Reader error: {e}")
    finally:
        try:
            ser.close()
        except Exception:
            pass
        stop_event.set()
        logger.info("Reader stopped.]")

def on_close(event, stop_event):
        stop_event.set()

def main():
    p = argparse.ArgumentParser(description="Plot data from serial port")
    p.add_argument("-p",  required=False, default="/dev/tty.usbmodem143300", help="serial port, e.g. /dev/cu.usbmodem143302, COM3")
    p.add_argument("-b",  default=115200, help="serial port baud rate, default=115200")
    p.add_argument("-k",  default=("out",), nargs="+", help="key word to find")
    p.add_argument("-wp", default=500, type=int, help="number of data points to show")
    p.add_argument("-st", default=None, type=int, help="time between samples in ms")
    p.add_argument("-f",  help="if set data will be saved to this file")
    p.add_argument("-o",  action="store_true", help="show input data")
    p.add_argument("-n",  dest="name", default="test", help="plot name")
    args = p.parse_args()

    # Queues & thread
    out_q = queue.Queue()
    stop_event = threading.Event()
    reader = threading.Thread(target=serial_reader, args=(args.p, args.b, TIMEOUT_S, out_q, stop_event, args), daemon=True)
    reader.start()

    in_q = queue.Queue()
    keyboard_thread = threading.Thread(target=keyboard_input, args=(in_q,), daemon=True)
    keyboard_thread.start()

    # CSV logging setup
    csv_fp = None
    csv_wr = None
    csv_file = f"{args.f}_{datetime.now().strftime('%Y-%m-%d_%H_%M_%S')}.csv"

    if args.f:
        mode = 'a' if CSV_APPEND else 'w'
        csv_fp = open(csv_file, mode, newline='')
        csv_wr = csv.writer(csv_fp)
        if not CSV_APPEND or (CSV_APPEND and (not os.path.exists(csv_file) or os.path.getsize(csv_file) == 0)):
            csv_wr.writerow(['t', *args.k])
        logger.info(f"Logging to CSV: {csv_file} (append={CSV_APPEND})")

    fig, ax = plt.subplots(figsize=(10, 5))
    fig.canvas.mpl_connect('close_event', lambda event: on_close(event, stop_event))

    # Rolling buffers
    t_buf = deque(maxlen=args.wp)
    y_bufs = {k: deque(maxlen=args.wp) for k in args.k}

    # Create one Line2D per key
    lines = {}
    for k in args.k:
        line, = ax.plot([], [], label=k)  # no explicit colors
        lines[k] = line

    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Value")
    ax.set_title(args.name)
    ax.legend(loc='upper right', bbox_to_anchor=(1, 1))
    ax.grid(True, linestyle="--", alpha=0.5)

    # Update loop (manual instead of FuncAnimation for clarity/control)
    last_draw = 0.0
    frame_period = 1.0 / float(MAX_FPS if MAX_FPS > 0 else 20)

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
                    mode = 'a' if CSV_APPEND else 'w'
                    single_csv_fp = open(single_csv_file, mode, newline='')
                    single_csv_wr = csv.writer(single_csv_fp)
                    if not CSV_APPEND or (CSV_APPEND and (not os.path.exists(single_csv_file) or os.path.getsize(single_csv_file) == 0)):
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
                    t_buf.append(rec["t"])
                    for k in args.k:
                        y_bufs[k].append(rec.get(k, float("nan")))
                    drained += 1
                    if csv_wr or single_csv_wr:
                        rows_to_write.append([rec['t']] + [rec.get(k, float('nan')) for k in args.k])
            except queue.Empty:
                pass

            now = time.monotonic()
            # Draw at most MAX_FPS
            if drained > 0 and (now - last_draw) >= frame_period:
                if len(t_buf) > 0:
                    tt = list(t_buf)
                    for k in args.k:
                        lines[k].set_data(tt, list(y_bufs[k]))
                    ax.relim()
                    ax.autoscale_view()
                fig.canvas.draw_idle()
                fig.canvas.flush_events()
                last_draw = now

            if is_start and single_csv_wr and rows_to_write:
                single_csv_wr.writerows(rows_to_write)
                single_csv_fp.flush()
            # Write CSV rows (even if no draw this iteration)
            if csv_wr and rows_to_write:
                csv_wr.writerows(rows_to_write)
                csv_fp.flush()

            # GUI events
            plt.pause(0.05)

    except KeyboardInterrupt:
        # stop_event.set()
        raise
    
    except Exception as e:
        # Handle other potential exceptions
        logger.error(f"An unexpected error occurred: {e}")

    finally:
        if SAVE_FINAL_PNG:
            try:
                fig.tight_layout()
                fig.savefig(SAVE_FINAL_PNG, dpi=150)
                logger.info(f"Saved final plot: {SAVE_FINAL_PNG}")
            except Exception as e:
                logger.warning(f"Could not save final plot: {e}")
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
