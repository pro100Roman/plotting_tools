import logging
import re
from collections import deque
from threading import Event
from threading import Thread
import time
import serial
import serial.tools.list_ports
import serial.tools.list_ports as lp

class SerialStr:
    def __init__(
            self, logger_name:str,
            port:str, baudrate:int, timeout:int,
            stop_event:Event,
            ready_event:Event,
            delta_time:int=0,
            x_src:deque=[], y_src:deque=[],
            regex=r"-?\d+(?:\.\d+)?"
    ):
        if logger_name:
            self.logger = logging.getLogger(logger_name)
        else:
            self.logger = logging.getLogger("worker serial_str")

        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.stop_event = stop_event
        self.ready_event = ready_event
        self.delta_time = delta_time
        self.x_src = x_src
        self.y_src = y_src
        self.regex = regex

        self.keys = list(y_src.keys())

        self.logger.info(f"Keys={self.keys}")

        try:
            self.ser = serial.Serial(port=self.port, baudrate=self.baudrate, timeout=self.timeout)
            self.logger.info(f"Opened '{self.ser.port}' @ {self.ser.baudrate} (timeout={self.ser.timeout}s)")
        except Exception as e:
            try:
                ports = [p.device for p in lp.comports()]
            except Exception:
                ports = []
            self.logger.error(f"[error] Failed to open '{port}': {e}\nAvailable ports: {ports}")
            stop_event.set()
            return

        self.logger.info("Reading... Close the plot window or Ctrl+C to stop.")

        self.reader = Thread(
            target=serial_reader,
            args=(self.logger, self.regex, self.ser, self.keys, self.x_src, self.y_src, ready_event, stop_event, self.delta_time),
            daemon=True
        )

    def start(self):
        self.reader.start()

    def join(self, timeout=None):
        self.reader.join(timeout)

def parse_line(line: str, keys, regex):
    vals = {}
    for k in keys:
        m = re.search(rf"\b{re.escape(k)}\s*[:=]\s*({regex})\b", line)
        if not m:
            return None
        vals[k] = float(m.group(1))
    return vals


def serial_reader(logger, regex, ser, keys, x_src, y_src, ready_event, stop_event, x_delta:int=0):
    t_rel = 0
    start = time.monotonic()
    try:
        while not stop_event.is_set():
            while True:
                line = f"{ser.readline()}"
                if line is None:
                    break
                if line != "":
                    logger.info(line)
                    vals = parse_line(line, keys, regex)
                    if vals is not None:
                        if not x_delta:
                            t_rel = (time.monotonic() - start)
                        else:
                            t_rel += x_delta

                        x_src.append(t_rel / 1000)
                        for k in keys:
                            y_src[k].append(vals[k])
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