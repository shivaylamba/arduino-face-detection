# Arduino UNO Q Face Guard

Arduino UNO Q Face Guard is a proximity-triggered face recognition project.
An Arduino UNO Q watches a Modulino Distance sensor, a laptop captures a face
frame from the camera, CavaFace creates a face embedding, and a Modulino Buzzer
sounds only when the face is unknown.

## Flow

1. Modulino Distance detects something close to the sensor.
2. The laptop polls the UNO Q firmware through Arduino RouterBridge.
3. The laptop captures frames from a browser camera bridge using the FaceTime HD
   camera or another browser-accessible camera.
4. OpenCV detects the largest frontal face in the frame.
5. Qualcomm AI Hub Models CavaFace creates a 512-dimensional embedding.
6. The app compares that embedding with enrolled known faces using cosine
   similarity.
7. If the face is unknown, the laptop calls the UNO Q firmware and the Modulino
   Buzzer sounds.

## Hardware

- Arduino UNO Q
- Modulino Distance
- Modulino Buzzer
- Laptop with Chrome and a camera

Connect the Modulino Distance and Modulino Buzzer on the UNO Q Qwiic chain. The
order does not matter because both are I2C devices.

## Project Layout

```text
firmware/arduino_q_face_guard/       Main UNO Q RouterBridge firmware
firmware/modulino_i2c_visual_probe/  Matrix + Modulino hardware probe
firmware/matrix_liveness/            UNO Q LED matrix liveness test
laptop_ai_guard/run_guard.py         Laptop camera, recognition, and buzzer bridge
laptop_ai_guard/enroll_faces.py      Known-user enrollment script
laptop_ai_guard/face_engine.py       Face detection, embeddings, cosine matching
```

Runtime artifacts are intentionally ignored by git:

- `laptop_ai_guard/.venv/`
- `laptop_ai_guard/captures/`
- `laptop_ai_guard/known_faces/*.npz`
- `*.log`

This avoids committing private face images and face embeddings.

## Firmware Setup

Install Arduino CLI or Arduino IDE with the UNO Q core, then install:

- `Arduino_Modulino`
- `Arduino_RouterBridge`

Upload the main firmware:

```bash
arduino-cli compile --fqbn arduino:zephyr:unoq firmware/arduino_q_face_guard
arduino-cli upload -p /dev/cu.usbmodem23446390822 --fqbn arduino:zephyr:unoq firmware/arduino_q_face_guard
```

After upload, the UNO Q LED matrix scrolls status text. `D1 B1` means the
Distance and Buzzer Modulinos were found.

## Laptop Setup

From the laptop app folder:

```bash
cd laptop_ai_guard
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

CavaFace downloads model assets on first use. Internet is needed for the first
model load.

## Enroll A Known Face

Enroll from saved images:

```bash
python enroll_faces.py --name current_user \
  --image ./captures/example_1.jpg \
  --image ./captures/example_2.jpg
```

Or enroll from an OpenCV camera:

```bash
python enroll_faces.py --name current_user --camera --samples 8 --camera-index 0
```

Enrollment creates `laptop_ai_guard/known_faces/embeddings.npz`.

## Run The Guard

The current working path uses UNO Q RouterBridge plus a browser camera bridge.
This avoids macOS camera permission issues with direct OpenCV capture and works
well with the FaceTime HD Camera through Chrome.

```bash
cd laptop_ai_guard
source .venv/bin/activate

python -u run_guard.py \
  --hardware-source routerbridge \
  --camera-source browser \
  --browser-app "Google Chrome" \
  --adb-path ~/Library/Arduino15/packages/arduino/tools/adb/32.0.0/adb \
  --threshold 0.60 \
  --proximity-threshold-mm 100 \
  --exit-hysteresis 50 \
  --trigger-cooldown 2
```

Open or reload:

```text
http://127.0.0.1:8765/
```

Allow camera access and keep the tab open. The app prints events such as:

```text
STATUS,distance_ok=1,buzzer_ok=1,threshold_mm=100
PROXIMITY,64
KNOWN,current_user,0.728
UNKNOWN,0.251
```

## Tuning

Recognition threshold:

- Lower values accept more faces as known.
- Higher values reject more faces as unknown.
- In testing, `0.60` worked better than the CavaFace default-style `0.50` while
  avoiding false rejects that happened around `0.65`.

Proximity threshold:

- `--proximity-threshold-mm 100` triggers under about 10 cm.
- `--exit-hysteresis 50` rearms after the distance rises above about 15 cm.

For better accuracy, enroll several images of the known user from different
angles and lighting conditions.

## Diagnostics

If the app does not trigger:

1. Upload `firmware/matrix_liveness` and confirm the UNO Q matrix scrolls.
2. Upload `firmware/modulino_i2c_visual_probe` and confirm it shows `D1 B1`.
3. Upload `firmware/arduino_q_face_guard` and run the laptop app.

Useful checks:

```bash
arduino-cli board list
~/Library/Arduino15/packages/arduino/tools/adb/32.0.0/adb devices
~/Library/Arduino15/packages/arduino/tools/adb/32.0.0/adb shell arduino-router-cli face_guard_status
```

## Notes

This is a prototype for experimentation. It is face recognition by embedding
similarity, not liveness detection or secure access control. For a real security
system, add consent, liveness checks, audit controls, tamper resistance, and
clear privacy handling for stored face images and embeddings.
