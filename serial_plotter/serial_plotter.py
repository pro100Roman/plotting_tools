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
from pathlib import Path

def keyboard_input(logger, in_q: queue.Queue):
    """Reads user input and pushes it to the queue."""
    while True:
        line = sys.stdin.readline()
        logger.info(f"---> {line[:-1]}")
        # in_q.put(line)

class TrackedDeque(deque):
    """deque that also remembers min/max of every value ever appended (not limited by maxlen)."""
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.lo = None
        self.hi = None

    def append(self, v):
        super().append(v)
        try:
            f = float(v)
        except (TypeError, ValueError):
            return
        if self.lo is None or f < self.lo:
            self.lo = f
        if self.hi is None or f > self.hi:
            self.hi = f

STATS_WIDTH = 42  # characters

def compute_noise(x, y):
    """Return (freqs, ASD, stats dict) of y, or None if not enough data."""
    import numpy as np
    try:
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
    except (TypeError, ValueError):
        return None
    n = min(len(x), len(y))
    if n < 16:
        return None
    x, y = x[-n:], y[-n:]
    dt = np.median(np.diff(x))
    if not np.isfinite(dt) or dt <= 0:
        return None
    fs = 1.0 / dt
    mean = float(y.mean())
    yd = y - mean
    win = np.hanning(n)
    spec = np.fft.rfft(yd * win)
    # one-sided amplitude spectral density [unit/sqrt(Hz)]
    psd = (2.0 / (fs * np.sum(win ** 2))) * np.abs(spec) ** 2
    freqs = np.fft.rfftfreq(n, dt)[1:]
    asd = np.maximum(np.sqrt(psd[1:]), 1e-12)  # keep positive for log scale
    ipk = int(np.argmax(asd))
    floor = float(np.median(asd))
    stats = {
        "n": n, "fs": fs, "mean": mean,
        "std": float(yd.std()), "pp": float(y.max() - y.min()),
        "floor": floor,                      # median ASD ~ white noise density
        "f_pk": float(freqs[ipk]), "asd_pk": float(asd[ipk]),
        "pk_db": float(20 * np.log10(asd[ipk] / floor)),  # peak above noise floor
    }
    return freqs, asd, stats

def noise_update(ax_n, noise_lines, x_buf, y_bufs, text):
    x = list(x_buf)
    out = []
    for k, line in noise_lines.items():
        res = compute_noise(x, list(y_bufs[k]))
        if res is None:
            continue
        f, asd, st = res
        buf = y_bufs[k]
        if getattr(buf, "lo", None) is not None:
            st["pp"] = buf.hi - buf.lo  # p-p over all samples seen, not just the window
        line.set_data(f, asd)
        if not out:
            out.append(f"N={st['n']}  fs={st['fs']:.4g} Hz")
        out.append(
            f"{k}:\n"
            f"    mean={st['mean']:.4g}  \u03c3={st['std']:.4g}\n"
            f"    p-p={st['pp']:.4g}\n"
            f"    floor={st['floor']:.3g}/\u221aHz\n"
            f"    peak={st['f_pk']:.3g} Hz ({st['asd_pk']:.3g}, +{st['pk_db']:.0f} dB)"
        )
    if out:
        # pad every line to a fixed width (monospace font) so the box doesn't resize
        lines_txt = "\n".join(out).split("\n")
        text.set_text("\n".join(l.ljust(STATS_WIDTH) for l in lines_txt))
        ax_n.relim()
        ax_n.autoscale_view()

def plot_update(frame, ax, lines, ready_event:threading.Event, x_buf:deque, y_bufs:deque,
                ax_n=None, noise_lines=None, noise_text=None):
    # Update data each frame
    if ready_event.is_set():
        ready_event.clear()
        for line_i in lines:
            lines[line_i].set_data(x_buf, y_bufs[line_i])

        ax.relim()
        ax.autoscale_view(scaley=True)

        if ax_n is not None:
            noise_update(ax_n, noise_lines, x_buf, y_bufs, noise_text)

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
    p.add_argument("-st", default=5,    type=int, help="time between samples in ms")
    p.add_argument("-s",  dest="start_time", default=0,    type=int, help="time between samples in ms")
    p.add_argument("-f",  dest="file",  help="if set data will be saved to this file in case of worker_csv csv file to open and plot")
    p.add_argument("-n",  dest="name",  default=None, help="plot name")
    p.add_argument("-na", "--noise", dest="noise", nargs="*", default=None, metavar="KEY",
                   help="add a subplot with noise analysis (amplitude spectral density); optionally list signals to analyze, e.g. '-na out filt' (default: all)")
    args = p.parse_args()

    log_file_name = f"{args.file}_{datetime.now().strftime('%Y-%m-%d_%H_%M_%S')}.log" if args.file else "data plotter"
    logger = logging.getLogger(log_file_name)
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    plt = None

    try:

        if (args.file and
                args.worker != "worker_csv" and
                args.worker != "worker_log" and
                args.worker != "worker_log_cut"):
            file_handler = logging.FileHandler(log_file_name)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

        in_q = queue.Queue()
        keyboard_thread = threading.Thread(target=keyboard_input, args=(logger, in_q,), daemon=True)
        keyboard_thread.start()

        stop_event = threading.Event()
        ready_event = threading.Event()

        x_buf  = deque(maxlen=args.wp)
        y_bufs = {k: TrackedDeque(maxlen=args.wp) for k in args.keys}

        if args.worker == "worker_serial_str":
            from worker_serial_str import WorkerSerialStr
            try:
                y_bufs["filt"] = TrackedDeque(maxlen=args.wp)
                worker = WorkerSerialStr(
                    log_file_name,
                    args.port, int(args.baudrate), float(args.timeout),
                    stop_event, ready_event,
                    args.st,
                    x_src = x_buf, y_src = y_bufs
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
                    x_src = x_buf, y_src = y_bufs
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
                    x_src = x_buf, y_src = y_bufs,
                    ts_inc_us = args.st * 1000
                )
            except Exception as e:
                logger.error(f"An unexpected error occurred: {e}")

        elif args.worker == "worker_log_cut":
            from worker_log_cut import WorkerLogCut
            try:
                worker = WorkerLogCut(
                    log_file_name,
                    args.file,
                    stop_event, ready_event,
                    x_src = x_buf, y_src = y_bufs,
                    ts_inc_us = args.st * 1000,
                    start_time_s = args.start_time,
                    sample_duration_ms = args.wp
                )
            except Exception as e:
                logger.error(f"An unexpected error occurred: {e}")

        elif args.worker == "worker_mqtt":
            from worker_mqtt import WorkerMqtt
            try:
                worker = WorkerMqtt(
                    log_file_name,
                    args.name,
                    stop_event, ready_event,
                    x_src = x_buf, y_src = y_bufs
                )
            except Exception as e:
                logger.error(f"An unexpected error occurred: {e}")
        else:
            raise Exception("worker script not provided")

        worker.start()

        import matplotlib.pyplot as plt
        import matplotlib.animation as animation

        if args.worker != "worker_log":
            plt.ion()

        ax_n = None
        if args.noise is not None:
            fig, (ax, ax_n) = plt.subplots(2, 1, figsize=(12, 9), height_ratios=(2, 1))
        else:
            fig, ax = plt.subplots(figsize=(12, 6))
        fig.canvas.mpl_connect('close_event', lambda event: on_close(event, stop_event))

        if not args.name and args.file:
            args.name = Path(args.file).stem
        elif not args.name:
            args.name = "data"

        fig.canvas.manager.set_window_title(args.name)

        lines = {}
        for k in args.keys:
            if args.worker == "worker_log":
                line, = ax.plot(x_buf, y_bufs[k], label=k)
            else:
                line, = ax.plot([], [], label=k)  # no explicit colors
                lines[k] = line

        if "filt" in y_bufs:
            line, = ax.plot([], [], label="filt")  # no explicit colors
            lines["filt"] = line

        noise_lines = None
        noise_text = None
        if ax_n is not None:
            available = list(args.keys) + (["filt"] if "filt" in y_bufs else [])
            noise_keys = args.noise or available
            unknown = [k for k in noise_keys if k not in available]
            if unknown:
                raise ValueError(f"-na: unknown signal(s) {unknown}, available: {available}")
            noise_lines = {}
            for k in noise_keys:
                noise_lines[k], = ax_n.plot([], [], label=k)
            ax_n.set_xscale("log")
            ax_n.set_yscale("log")
            ax_n.set_xlim(0.1, 100)
            ax_n.set_ylim(1e-6, 1)
            ax_n.set_xlabel("Frequency [Hz]")
            ax_n.set_ylabel("ASD [unit/√Hz]")
            ax_n.set_title("Noise spectrum")
            noise_text = ax_n.text(0.01, 0.02, "", transform=ax_n.transAxes, va="bottom", ha="left",
                                   family="monospace", fontsize=8,
                                   bbox=dict(boxstyle="round", fc="white", alpha=0.8))
            ax_n.legend(loc='upper left', bbox_to_anchor=(1, 1))
            ax_n.grid(True, which="both", linestyle="--", alpha=0.5)
            if args.worker == "worker_log":
                noise_update(ax_n, noise_lines, x_buf, y_bufs, noise_text)

        ax.set_xlabel("Time [s]")
        ax.set_ylabel("Value")
        ax.set_title(args.name)
        ax.legend(loc='upper left', bbox_to_anchor=(1, 1))
        ax.grid(True, linestyle="--", alpha=0.5)

        if ax_n is not None:
            fig.tight_layout()  # after titles/labels/legends are set so nothing is clipped

        if args.worker != "worker_log":
            anim = animation.FuncAnimation(fig,
                                           plot_update,
                                           fargs=(ax, lines, ready_event, x_buf, y_bufs, ax_n, noise_lines, noise_text),
                                           interval=10,
                                           blit=False,
                                           cache_frame_data=False)
            while not stop_event.is_set():
                plt.pause(0.05)

        plt.show()

    except KeyboardInterrupt:
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
    finally:
        if plt:
            plt.close(fig)
        stop_event.set()
        worker.join(timeout=0.1)
        keyboard_thread.join(timeout=0.1)
        sys.exit(0)

if __name__ == "__main__":
    sys.exit(main())
