from arduino.app_utils import *
import time


def call_bridge(name, *args):
    for attempt in range(1, 6):
        try:
            value = Bridge.call(name, *args)
            print(f"RPC,{name},OK,{value}", flush=True)
            return value
        except Exception as exc:
            print(f"RPC,{name},ERROR,attempt={attempt},{exc}", flush=True)
            time.sleep(1)
    return None


def loop():
    print("PROBE_START", flush=True)
    call_bridge("face_guard_ping")
    call_bridge("scanner_ping")
    call_bridge("scanner_boot_step")
    distance_found = call_bridge("distance_found")
    buzzer_found = call_bridge("buzzer_found")
    call_bridge("buzz_test")

    print(f"DISTANCE,{'FOUND' if distance_found else 'NOT_FOUND'}", flush=True)
    print(f"BUZZER,{'FOUND' if buzzer_found else 'NOT_FOUND'}", flush=True)

    for _ in range(20):
        value = call_bridge("read_distance_mm")
        print(f"DISTANCE_MM,{value}", flush=True)
        time.sleep(0.5)

    print("PROBE_DONE", flush=True)
    while True:
        time.sleep(60)


App.run(user_loop=loop)
