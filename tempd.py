#!/usr/bin/python3

import asyncio
import subprocess
import sys
import statistics

import numpy as np

def linear_lubricant(vals):
    weights = range(1, len(vals)+1)
    norm = sum(weights)
    weights = [i/norm for i in weights]
    weighted = [val*weight for val, weight in zip(vals, weights)]
    return statistics.mean(weighted)*len(vals)

class Tempd:
    def __init__(self, loop, sensors):
        self.raw_history = {}
        self.loop = loop
        self.sensors = sensors
        self.output_history_size = 12
        self.output_history = dict()
        self.output_window_size = 3
        self.stats = dict()

    def reset_stats(self, sensor):
        self.stats[sensor] = {
            "filtered": 0,
            "accepted": 0
        }

    async def start_child(self):
        self.child = await asyncio.create_subprocess_exec(
            "/home/leon/test",
            stdout=subprocess.PIPE,
            loop=self.loop
        )

    async def start_server(self):
        self.server = await asyncio.start_server(
            self.handle_connect,
            host="127.0.0.1",
            port=31338,
            loop=self.loop,
        )

    def sensor_name(self, sensor):
        if sensor in self.sensors:
            return self.sensors[sensor]
        else:
            return sensor

    def get_output(self, sensor):
        if len(self.raw_history[sensor]) < 5:
            return statistics.median(self.raw_history[sensor])
        else:  # normal case
            middle = sorted(self.raw_history[sensor])[2:-2]
            return statistics.mean(middle)

    def write_output_history(self, sensor, median):
        if sensor not in self.output_history:
            self.output_history[sensor] = []

        self.output_history[sensor].append(median)

        if len(self.output_history[sensor]) > self.output_history_size:
            self.output_history[sensor].pop(0)

    def get_cur_flow(self, sensor):
        pad = self.output_history_size - len(self.output_history[sensor]) - 1
        diff = [0] * pad + list(np.diff(self.output_history[sensor]))

        return linear_lubricant(diff)/5*60

    def get_cur_ratio(self, sensor):
        return 100 * self.stats[sensor]["filtered"] / (
            self.stats[sensor]["filtered"] +
            self.stats[sensor]["accepted"]
        )

    def handle_connect(self, client_reader, client_writer):
        print("incoming connection… ", end="", file=sys.stderr, flush=True)
        for sensor in self.raw_history:
            sensor_name = self.sensor_name(sensor)

            try:
                out = self.get_output(sensor)
                self.write_output_history(sensor, out)
            except statistics.StatisticsError:
                out = "NaN"

            try:
                flow = self.get_cur_flow(sensor)
            except (KeyError, statistics.StatisticsError):
                flow = "NaN"

            try:
                ratio = self.get_cur_ratio(sensor)
            except (KeyError, ZeroDivisionError):
                ration = "NaN"

            msg = "multigraph sensors\n"
            msg += "{}.value {}\n".format(sensor_name, out)
            msg += "multigraph sensors_flow\n"
            msg += "{}-flow.value {}\n".format(sensor_name, flow)
            msg += "multigraph sensors_stats\n"
            msg += "{}-ratio.value {}\n".format(sensor_name, ratio)

            print("sending {}".format(msg), file=sys.stderr, flush=True)
            client_writer.write(msg.encode("utf-8"))

            self.raw_history[sensor] = []
            self.reset_stats(sensor)

        client_writer.close()
        print("raw_history:", self.raw_history, file=sys.stderr, flush=True)
        print("output_history:", self.output_history, file=sys.stderr, flush=True)

    async def run(self, loop):
        await asyncio.wait([self.start_child(), self.start_server()])
        while self.child.returncode is None:
            line = await self.child.stdout.readline()
            if not line:
                print("child process has died, exiting…", file=sys.stderr)
                return

            line = line.decode().strip()
            addr, val = line.split(" ")
            val = float(val)

            if addr not in self.stats:
                self.reset_stats(addr)

            if val < 0 or val > 80:
                print(
                    "skipping bad value {}".format(val),
                    file=sys.stderr,
                    flush=True
                )
                self.stats[addr]["filtered"] += 1
                continue

            self.stats[addr]["accepted"] += 1

            if addr not in self.raw_history:
                self.raw_history[addr] = []

            self.raw_history[addr].append(val)
            print(self.raw_history, file=sys.stderr, flush=True)



if __name__ == "__main__":
    sensors = {
        "2846b25204000054": "wohnzimmer"
    }
    loop = asyncio.get_event_loop()
    tempd = Tempd(loop, sensors)
    loop.run_until_complete(tempd.run(loop))
