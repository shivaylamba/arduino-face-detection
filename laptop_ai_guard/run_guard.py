from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import subprocess
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import webbrowser

import cv2
import numpy as np
import serial
from serial.tools import list_ports

from face_engine import CavaFaceRecognizer, FaceDatabase


DEFAULT_DATABASE = Path(__file__).resolve().parent / "known_faces" / "embeddings.npz"
DEFAULT_CAPTURE_DIR = Path(__file__).resolve().parent / "captures"
DEFAULT_ADB = Path.home() / "Library/Arduino15/packages/arduino/tools/adb/32.0.0/adb"


BROWSER_CAMERA_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Face Guard Camera</title>
  <style>
    :root { color-scheme: dark; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: #111; color: #f4f4f4; }
    main { width: min(920px, 92vw); }
    video { width: 100%; aspect-ratio: 16 / 9; background: #050505; border-radius: 8px; object-fit: cover; }
    p { color: #c9c9c9; line-height: 1.5; }
    .status { margin-top: 12px; font-variant-numeric: tabular-nums; }
  </style>
</head>
<body>
  <main>
    <video id="video" autoplay playsinline muted></video>
    <p class="status" id="status">Starting camera...</p>
  </main>
  <canvas id="canvas" hidden></canvas>
  <script>
    const video = document.getElementById("video");
    const canvas = document.getElementById("canvas");
    const statusEl = document.getElementById("status");
    let sent = 0;

    async function start() {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
        audio: false
      });
      video.srcObject = stream;
      await video.play();
      canvas.width = video.videoWidth || 1280;
      canvas.height = video.videoHeight || 720;
      statusEl.textContent = "Camera connected. Keep this tab open while Face Guard runs.";
      setInterval(capture, 250);
    }

    async function capture() {
      if (!video.videoWidth || !video.videoHeight) return;
      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      const image = canvas.toDataURL("image/jpeg", 0.82);
      try {
        const res = await fetch("/frame", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ image })
        });
        if (res.ok) {
          sent += 1;
          statusEl.textContent = `Camera connected. Frames sent: ${sent}. Keep this tab open.`;
        }
      } catch (err) {
        statusEl.textContent = `Camera connected, waiting for Python bridge... ${err}`;
      }
    }

    start().catch((err) => {
      statusEl.textContent = `Camera failed: ${err}`;
    });
  </script>
</body>
</html>
"""


class BrowserCameraBridge:
    def __init__(self, host: str, port: int, open_browser: bool, browser_app: str, first_frame_timeout_s: float):
        self.host = host
        self.port = port
        self.open_browser = open_browser
        self.browser_app = browser_app
        self.first_frame_timeout_s = first_frame_timeout_s
        self._frame = None
        self._frame_time = 0.0
        self._frame_count = 0
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    def start(self) -> "BrowserCameraBridge":
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args) -> None:
                return

            def do_GET(self) -> None:
                path = urlparse(self.path).path
                if path != "/":
                    self.send_error(404)
                    return

                page = BROWSER_CAMERA_PAGE.encode("utf-8")
                self.send_response(200)
                self.send_header("content-type", "text/html; charset=utf-8")
                self.send_header("content-length", str(len(page)))
                self.end_headers()
                self.wfile.write(page)

            def do_POST(self) -> None:
                path = urlparse(self.path).path
                if path != "/frame":
                    self.send_error(404)
                    return

                length = int(self.headers.get("content-length", "0"))
                payload = self.rfile.read(length)
                try:
                    body = json.loads(payload)
                    data_url = str(body["image"])
                    _, encoded = data_url.split(",", 1)
                    jpg = base64.b64decode(encoded)
                    buffer = np.frombuffer(jpg, dtype=np.uint8)
                    frame = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
                    if frame is None:
                        raise ValueError("Could not decode browser JPEG frame")
                except Exception as exc:
                    message = json.dumps({"ok": False, "error": str(exc)}).encode("utf-8")
                    self.send_response(400)
                    self.send_header("content-type", "application/json")
                    self.send_header("content-length", str(len(message)))
                    self.end_headers()
                    self.wfile.write(message)
                    return

                with bridge._lock:
                    bridge._frame = frame
                    bridge._frame_time = time.time()
                    bridge._frame_count += 1

                message = json.dumps({"ok": True, "frames": bridge._frame_count}).encode("utf-8")
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(message)))
                self.end_headers()
                self.wfile.write(message)

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

        print(f"Browser camera bridge: {self.url}")
        if self.open_browser:
            if self.browser_app:
                subprocess.run(["open", "-a", self.browser_app, self.url], check=False)
            else:
                webbrowser.open(self.url)

        deadline = time.time() + self.first_frame_timeout_s
        while time.time() < deadline:
            with self._lock:
                if self._frame is not None:
                    print("Browser camera connected.")
                    return self
            time.sleep(0.1)

        raise RuntimeError(
            f"No browser camera frames arrived. Open {self.url} in Chrome, allow camera access, "
            "and keep the tab open."
        )

    def read(self) -> tuple[bool, object]:
        with self._lock:
            if self._frame is None:
                return False, None
            return True, self._frame.copy()

    def release(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None


class RouterBridgeClient:
    def __init__(self, adb_path: Path, timeout_s: float = 4.0):
        self.adb_path = Path(adb_path)
        self.timeout_s = timeout_s

    def call(self, method: str, *args: object) -> str:
        cmd = [str(self.adb_path), "shell", "arduino-router-cli", method]
        cmd.extend(self._format_arg(arg) for arg in args)
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=self.timeout_s)
        output = (proc.stdout + proc.stderr).strip()
        if proc.returncode != 0 or "Got RPC error" in output or "panic:" in output:
            raise RuntimeError(output or f"arduino-router-cli failed for {method}")
        return output

    def call_value(self, method: str, *args: object) -> str:
        output = self.call(method, *args)
        for line in reversed([line.strip() for line in output.splitlines() if line.strip()]):
            match = re.search(r"(?:response|result|value)\s*:?\s*(.+)$", line, re.IGNORECASE)
            if match:
                return match.group(1).strip().strip('"')

            if re.fullmatch(r"-?\d+|true|false", line, re.IGNORECASE):
                return line

        match = re.search(r"(-?\d+|true|false)\s*$", output, re.IGNORECASE)
        if match:
            return match.group(1)

        raise RuntimeError(f"Could not parse RouterBridge response: {output}")

    def call_int(self, method: str, *args: object) -> int:
        return int(self.call_value(method, *args))

    def call_bool(self, method: str, *args: object) -> bool:
        value = self.call_value(method, *args).lower()
        if value in {"true", "1"}:
            return True
        if value in {"false", "0"}:
            return False
        raise RuntimeError(f"Expected boolean response from {method}, got: {value}")

    def call_text(self, method: str, *args: object) -> str:
        return self.call_value(method, *args).strip().strip('"')

    @staticmethod
    def _format_arg(arg: object) -> str:
        if isinstance(arg, bool):
            return "true" if arg else "false"
        if isinstance(arg, float):
            return f"f64:{arg}"
        return str(arg)


def list_serial_ports() -> None:
    ports = list(list_ports.comports())
    if not ports:
        print("No serial ports found.")
        return

    for port in ports:
        print(f"{port.device}\t{port.description}\t{port.hwid}")


def choose_serial_port() -> str:
    ports = list(list_ports.comports())
    if not ports:
        raise RuntimeError("No serial ports found. Connect the Arduino over USB.")

    preferred_tokens = ("arduino", "uno", "usbmodem", "ttyacm", "wchusbserial", "usb serial")
    for port in ports:
        haystack = f"{port.device} {port.description} {port.hwid}".lower()
        if any(token in haystack for token in preferred_tokens):
            return port.device

    return ports[0].device


def open_camera(camera_index: int) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open camera index {camera_index}")

    for _ in range(10):
        cap.read()
        time.sleep(0.05)
    return cap


def open_capture_source(args: argparse.Namespace):
    if args.camera_source == "browser":
        return BrowserCameraBridge(
            host=args.browser_host,
            port=args.browser_port,
            open_browser=not args.no_open_browser,
            browser_app=args.browser_app,
            first_frame_timeout_s=args.browser_timeout,
        ).start()

    return open_camera(args.camera_index)


def capture_best_face_frame(
    cap: cv2.VideoCapture,
    recognizer: CavaFaceRecognizer,
    attempts: int,
    delay_s: float,
) -> tuple[object, object]:
    best_frame = None
    best_face = None
    best_area = 0

    for _ in range(attempts):
        ok, frame = cap.read()
        if not ok or frame is None:
            time.sleep(delay_s)
            continue

        face = recognizer.detect_largest_face(frame)
        if face is not None:
            _, _, w, h = face.box
            area = w * h
            if area > best_area:
                best_frame = frame.copy()
                best_face = face
                best_area = area

        time.sleep(delay_s)

    if best_frame is None or best_face is None:
        raise ValueError("No face detected in webcam frames")

    return best_frame, best_face


def safe_serial_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)
    return cleaned[:48] or "known"


def send_line(ser: serial.Serial, line: str) -> None:
    print(f"> {line}")
    ser.write((line + "\n").encode("utf-8"))
    ser.flush()


def save_capture(frame, capture_dir: Path, label: str) -> Path:
    capture_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = capture_dir / f"{stamp}_{label}.jpg"
    cv2.imwrite(str(path), frame)
    return path


def recognize_face_event(
    cap,
    recognizer: CavaFaceRecognizer,
    database: FaceDatabase,
    threshold: float,
    capture_dir: Path,
    attempts: int,
    delay_s: float,
) -> tuple[bool, str, float, Path | None]:
    frame, _ = capture_best_face_frame(cap, recognizer, attempts, delay_s)
    embedding = recognizer.embedding_from_bgr(frame)
    match = database.match(embedding, threshold=threshold)
    label = safe_serial_name(match.name if match.known else "unknown")
    capture_path = save_capture(frame, capture_dir, f"{label}_{match.score:.3f}")
    return match.known, match.name, match.score, capture_path


def handle_proximity(
    ser: serial.Serial,
    cap: cv2.VideoCapture,
    recognizer: CavaFaceRecognizer,
    database: FaceDatabase,
    threshold: float,
    capture_dir: Path,
    attempts: int,
    delay_s: float,
) -> None:
    try:
        known, name, score, capture_path = recognize_face_event(
            cap, recognizer, database, threshold, capture_dir, attempts, delay_s
        )

        if known:
            print(f"Known face: {name} score={score:.3f} capture={capture_path}")
            send_line(ser, f"KNOWN,{safe_serial_name(name)},{score:.3f}")
        else:
            print(f"Unknown face: best={name} score={score:.3f} capture={capture_path}")
            send_line(ser, f"UNKNOWN,{score:.3f}")
    except Exception as exc:
        print(f"Recognition failed: {exc}")
        send_line(ser, "UNKNOWN,0.000")


def run_routerbridge_guard(
    args: argparse.Namespace,
    cap,
    recognizer: CavaFaceRecognizer,
    database: FaceDatabase,
) -> None:
    client = RouterBridgeClient(args.adb_path, timeout_s=args.router_timeout)

    print("Checking UNO Q RouterBridge firmware...")
    for attempt in range(1, 21):
        try:
            ping = client.call_text("face_guard_ping")
            if ping == "pong":
                break
        except Exception as exc:
            if attempt == 20:
                raise RuntimeError(f"RouterBridge firmware did not answer: {exc}") from exc
            time.sleep(0.5)

    distance_ok = client.call_bool("distance_found")
    buzzer_ok = client.call_bool("buzzer_found")
    threshold_mm = client.call_int("threshold_mm")
    if args.proximity_threshold_mm is not None:
        threshold_mm = client.call_int("set_threshold_mm", args.proximity_threshold_mm)
    print(f"STATUS,distance_ok={int(distance_ok)},buzzer_ok={int(buzzer_ok)},threshold_mm={threshold_mm}")
    if not distance_ok:
        raise RuntimeError("Modulino Distance was not found by the UNO Q firmware")
    if not buzzer_ok:
        print("Warning: Modulino Buzzer was not found; unknown faces cannot sound the alarm.")

    armed = True
    person_present = False
    last_trigger_at = 0.0
    last_reported_distance = None
    print("Polling Distance Modulino through RouterBridge. Press Ctrl+C to stop.")

    try:
        while True:
            distance_mm = client.call_int("read_distance_mm")
            now = time.time()

            if distance_mm > 0 and distance_mm != last_reported_distance:
                print(f"DISTANCE,{distance_mm}")
                last_reported_distance = distance_mm

            if distance_mm > threshold_mm + args.exit_hysteresis:
                person_present = False

            is_close = distance_mm > 0 and distance_mm <= threshold_mm
            in_cooldown = (now - last_trigger_at) < args.trigger_cooldown

            if armed and is_close and not person_present and not in_cooldown:
                person_present = True
                last_trigger_at = now
                print(f"PROXIMITY,{distance_mm}")

                try:
                    known, name, score, capture_path = recognize_face_event(
                        cap,
                        recognizer,
                        database,
                        threshold=args.threshold,
                        capture_dir=args.captures_dir,
                        attempts=args.attempts,
                        delay_s=args.delay,
                    )
                    if known:
                        print(f"KNOWN,{safe_serial_name(name)},{score:.3f},capture={capture_path}")
                    else:
                        print(f"UNKNOWN,{score:.3f},capture={capture_path}")
                        if buzzer_ok:
                            client.call_text("buzz_unknown")
                except Exception as exc:
                    print(f"Recognition failed: {exc}")
                    if buzzer_ok:
                        client.call_text("buzz_unknown")

            time.sleep(args.poll_interval)
    except KeyboardInterrupt:
        print("\nStopping.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Laptop AI bridge for Arduino Q Face Guard.")
    parser.add_argument("--port", default="auto", help="Arduino serial port, or 'auto'.")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate.")
    parser.add_argument(
        "--hardware-source",
        choices=("serial", "routerbridge"),
        default="serial",
        help="Use plain serial firmware, or UNO Q RouterBridge RPC firmware.",
    )
    parser.add_argument("--adb-path", type=Path, default=DEFAULT_ADB, help="Path to adb for UNO Q RouterBridge mode.")
    parser.add_argument("--router-timeout", type=float, default=4.0, help="Seconds to wait for one RouterBridge call.")
    parser.add_argument("--poll-interval", type=float, default=0.20, help="Seconds between Distance Modulino polls.")
    parser.add_argument("--trigger-cooldown", type=float, default=5.0, help="Seconds between proximity AI runs.")
    parser.add_argument(
        "--proximity-threshold-mm",
        type=int,
        default=None,
        help="Override the firmware proximity threshold in millimeters.",
    )
    parser.add_argument("--exit-hysteresis", type=int, default=150, help="Millimeters past threshold before re-arming.")
    parser.add_argument("--camera-index", type=int, default=0, help="OpenCV camera index.")
    parser.add_argument(
        "--camera-source",
        choices=("opencv", "browser"),
        default="opencv",
        help="Use OpenCV directly, or a browser tab that posts webcam frames to localhost.",
    )
    parser.add_argument("--browser-host", default="127.0.0.1", help="Browser camera bridge host.")
    parser.add_argument("--browser-port", type=int, default=8765, help="Browser camera bridge port.")
    parser.add_argument("--browser-app", default="Google Chrome", help="macOS browser app to open for camera capture.")
    parser.add_argument("--browser-timeout", type=float, default=60.0, help="Seconds to wait for browser frames.")
    parser.add_argument("--no-open-browser", action="store_true", help="Print the browser camera URL without opening it.")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE, help="Embedding database path.")
    parser.add_argument("--captures-dir", type=Path, default=DEFAULT_CAPTURE_DIR, help="Where captured frames are saved.")
    parser.add_argument("--threshold", type=float, default=0.50, help="Known-user cosine similarity threshold.")
    parser.add_argument("--attempts", type=int, default=10, help="Webcam frames to inspect after a proximity trigger.")
    parser.add_argument("--delay", type=float, default=0.12, help="Delay between frame attempts.")
    parser.add_argument("--flip", action="store_true", help="Use CavaFace flip ensemble for embeddings.")
    parser.add_argument("--list-ports", action="store_true", help="Print serial ports and exit.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.list_ports:
        list_serial_ports()
        return

    port = choose_serial_port() if args.port == "auto" else args.port
    database = FaceDatabase.load(args.database)
    if database.embeddings.size == 0:
        print(f"Warning: no known embeddings found at {args.database}; every face will be unknown.")
    else:
        print(f"Loaded {len(database.names)} known embedding(s) from {args.database}")

    print("Loading CavaFace model...")
    recognizer = CavaFaceRecognizer(use_flip=args.flip)
    print("Opening camera source...")
    cap = open_capture_source(args)

    if args.hardware_source == "routerbridge":
        try:
            run_routerbridge_guard(args, cap, recognizer, database)
        finally:
            cap.release()
        return

    print(f"Opening Arduino serial port {port} at {args.baud} baud...")
    with serial.Serial(port, args.baud, timeout=1) as ser:
        time.sleep(2.0)
        ser.reset_input_buffer()
        send_line(ser, "STATUS?")
        print("Listening for PROXIMITY events. Press Ctrl+C to stop.")

        try:
            while True:
                raw = ser.readline()
                if not raw:
                    continue

                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                print(f"< {line}")
                if line.startswith("PROXIMITY,"):
                    handle_proximity(
                        ser,
                        cap,
                        recognizer,
                        database,
                        threshold=args.threshold,
                        capture_dir=args.captures_dir,
                        attempts=args.attempts,
                        delay_s=args.delay,
                    )
        except KeyboardInterrupt:
            print("\nStopping.")
        finally:
            cap.release()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Fatal: {exc}", file=sys.stderr)
        raise SystemExit(1)
