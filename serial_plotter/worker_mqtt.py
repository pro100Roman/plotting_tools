import logging
from collections import deque
import paho.mqtt.client as paho
from paho.mqtt.enums import CallbackAPIVersion
from threading import Event
import json
import time

t0 = time.time()
class WorkerMqtt:
    def __init__(
            self, logger_name:str,
            device,
            stop_event:Event,
            ready_event:Event,
            server = "3.69.177.92",
            port = 1883,
            client_id = "test_station",
            x_src:deque=[], y_src:deque=[],
    ):
        if logger_name:
            self.logger = logging.getLogger(logger_name)
        else:
            self.logger = logging.getLogger("worker_csv")

        self.server = server
        self.port = port
        self.client_id = client_id
        self.device = device
        self.stop_event = stop_event
        self.ready_event = ready_event
        self.x_src = x_src
        self.y_src = y_src
        self.keys = list(y_src.keys())
        self.logger.info(f"Keys={self.keys}")

        self.logger.info("Reading... Close the plot window or Ctrl+C to stop.")

        self.client = paho.Client(callback_api_version=CallbackAPIVersion.VERSION1,
                             protocol=paho.MQTTv31, client_id=self.client_id,
                             userdata={"logger":self.logger, "device":self.device, "keys":self.keys, "rdy_evt":self.ready_event, "x":self.x_src, "y": self.y_src})


        self.client.on_connect = on_connect
        self.client.on_message = on_message

    def start(self):
        self.client.connect(self.server, self.port, 60)
        self.client.loop_start()

    def join(self, timeout=None):
        self.client.disconnect()
        self.client.loop_stop()

def on_connect(client, userdata, flags, rc):
    userdata["logger"].info(f"Connected to {client.host} status:{rc}")
    client.subscribe("/device/status/response")

def on_message(client, userdata, msg):
    msg_str = msg.payload.decode()
    data = json.loads(msg_str)
    if "nameDevice" in data and data["nameDevice"] == userdata["device"]:
        global t0
        userdata["logger"].info(f"Received message on topic '{msg.topic}': {msg_str}")
        ts = time.time() - t0
        userdata["x"].append(ts)

        for key in userdata["keys"]:
            userdata["y"][key].append(float(data[key]))

        if not userdata["rdy_evt"].is_set():
            userdata["rdy_evt"].set()
