import logging
from collections import deque
from time import sleep
import re
from threading import Event
from threading import Thread
import os
from worker_serial_str import parse_line

class WorkerLog:
    def __init__(
            self, logger_name:str,
            file_log,
            stop_event:Event,
            ready_event:Event,
            x_src:deque=[], y_src:deque=[],
    ):
        if logger_name:
            self.logger = logging.getLogger(logger_name)
        else:
            self.logger = logging.getLogger("worker_csv")

        if not os.path.exists(file_log):
            raise Exception(f"file {file_log} nor found")
        self.file_log = file_log
        self.stop_event = stop_event
        self.ready_event = ready_event
        self.x_src = x_src
        self.y_src = y_src
        self.keys = list(y_src.keys())
        self.logger.info(f"Keys={self.keys}")

        self.logger.info("Reading... Close the plot window or Ctrl+C to stop.")

        self.reader = Thread(
            target=log_reader,
            args=(self.logger, self.file_log, self.keys, self.x_src, self.y_src, ready_event, stop_event),
            daemon=True
        )

    def start(self):
        self.reader.start()

    def join(self, timeout=None):
        self.reader.join(timeout)


def log_reader(logger, file_log, keys, x_src, y_src, ready_event, stop_event):
    regex=r"-?\d+(?:\.\d+)?"
    with open(file_log, mode='r', newline='') as file:
        lines = file.readlines()
        offset = None
        for line in lines:
            data = parse_line(line, keys, regex)
            if data:
                match = re.search(r"b'([^[]+)\[", line)
                ts = int(match.group(1).strip())
                if not offset:
                    offset = ts
                x_src.append((ts - offset) // 1000)
                for n in keys:
                    y_src[n].append(data[n])

                if not ready_event.is_set():
                    ready_event.set()
                sleep(0.001)
