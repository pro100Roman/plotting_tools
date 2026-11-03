import logging
from collections import deque
from time import sleep
import re
from threading import Event
from threading import Thread
import os
from worker_serial_str import parse_line
from datetime import datetime
import alive_progress

"""
Cuts log from the start point for the provided duration 
"""

class WorkerLogCut:
    def __init__(
            self, logger_name: str,
            file_log,
            stop_event: Event,
            ready_event: Event,
            x_src: deque = [], y_src: deque = [],
            ts_inc_us=0,
            start_time_s=0,
            sample_duration_ms=0
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
        self.ts_inc_us = ts_inc_us
        self.sample_duration_ms = sample_duration_ms
        self.start_time_s = start_time_s

        self.logger.info("Reading file... Close the plot window or Ctrl+C to stop.")

    def start(self):
        self.ready_event.clear()
        log_reader(
            self.logger, self.file_log, self.keys, self.x_src, self.y_src,
            self.ts_inc_us, self.start_time_s, self.sample_duration_ms
        )
        self.ready_event.set()

    def join(self, timeout=None):
        pass


def log_reader(logger, file_log, keys, x_src, y_src, ts_inc_us, start_time_s, sample_duration_ms):
    regex = r"-?\d+(?:\.\d+)?"
    with open(file_log, mode='r', newline='', encoding="utf-8") as file:
        lines = file.readlines()
        offset = None
        ts = 0
        file_to_save = None
        with alive_progress.alive_bar(len(lines)) as bar:
            for line in lines:
                data = parse_line(line, keys, regex)
                if data:
                    if ts_inc_us == 0:
                        match = re.search(r"b'([^[]+)\[", line)
                        if not match:
                            match = re.search(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\]", line)
                            if not match:
                                continue
                            ts = int(datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S.%f").timestamp())
                        else:
                            ts = int(match.group(1).strip())
                    else:
                        ts += ts_inc_us

                    if not offset:
                        offset = ts
                    # set time in sec
                    _ts = (ts - offset) / 1000000
                    bar()
                    if start_time_s <= _ts <= (start_time_s + sample_duration_ms / 1000):
                        if not file_to_save:
                            file_to_save = open(file_log[:-4] + "_cut.log", mode='w', newline='', encoding="utf-8")
                        else:
                            file_to_save.write(line)
                        x_src.append(_ts)
                        for n in keys:
                            y_src[n].append(data[n])
                    elif _ts > (start_time_s + sample_duration_ms):
                        logger.info("Done")
                        if file_to_save:
                            file_to_save.flush()
                            file_to_save.close()
                        break
