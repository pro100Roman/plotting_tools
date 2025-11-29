import logging
from collections import deque
from time import sleep

import pandas as pd
from threading import Event
from threading import Thread
import os

class WorkerCsv:
    def __init__(
            self, logger_name:str,
            file_csv,
            stop_event:Event,
            ready_event:Event,
            x_src:deque=[], y_src:deque=[],
    ):
        if logger_name:
            self.logger = logging.getLogger(logger_name)
        else:
            self.logger = logging.getLogger("worker_csv")

        if not os.path.exists(file_csv):
            raise Exception(f"file {file_csv} nor found")
        self.file_csv = file_csv
        self.stop_event = stop_event
        self.ready_event = ready_event
        self.x_src = x_src
        self.y_src = y_src
        self.keys = list(y_src.keys())
        self.logger.info(f"Keys={self.keys}")

        self.logger.info("Reading... Close the plot window or Ctrl+C to stop.")

        self.reader = Thread(
            target=csv_reader,
            args=(self.logger, self.file_csv, self.keys, self.x_src, self.y_src, ready_event, stop_event),
            daemon=True
        )

    def start(self):
        self.reader.start()

    def join(self, timeout=None):
        self.reader.join(timeout)


def csv_reader(logger, file_csv, keys, x_src, y_src, ready_event, stop_event):
    with open(file_csv, mode='r', newline='') as file:
        df = pd.read_csv(file_csv)
        header = df.columns.tolist()
        logger.info(f"headers: {header}")
        for index, row in df.iterrows():
            # considering that first row in csv file is timestamp
            x_src.append(row[0])
            for n in keys:
                y_src[n].append(row[n])

            if not ready_event.is_set():
                ready_event.set()
            sleep(0.001)
