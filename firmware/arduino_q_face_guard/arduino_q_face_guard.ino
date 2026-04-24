#include <Arduino_Modulino.h>
#include <Arduino_RouterBridge.h>
#include <ArduinoGraphics.h>
#include <Arduino_LED_Matrix.h>
#include <Wire.h>
#include <math.h>

Arduino_LED_Matrix matrix;
ModulinoDistance distance;

const uint8_t BUZZER_ADDR = 0x1E;
const uint8_t DISTANCE_ADDR = 0x29;
const unsigned long STATUS_REFRESH_MS = 3000;

int proximityThresholdMm = 700;
bool distanceAddrFound = false;
bool buzzerAddrFound = false;
bool distanceOk = false;
int lastDistanceMm = -1;
unsigned long lastStatusRefreshAt = 0;

bool i2cPresent(uint8_t address) {
  Wire1.beginTransmission(address);
  return Wire1.endTransmission() == 0;
}

void scrollText(const char *text) {
  matrix.textFont(Font_5x7);
  matrix.textScrollSpeed(80);
  matrix.beginText(0, 0, 127, 0, 0);
  matrix.print(text);
  matrix.endText(SCROLL_LEFT);
}

void drawStatusFrame(bool near, int distanceMm) {
  matrix.clear();
  matrix.beginDraw();

  if (near) {
    matrix.fill(0xFFFFFF);
    matrix.stroke(0xFFFFFF);
    matrix.rect(0, 0, 12, 8);
  } else {
    matrix.stroke(distanceOk ? 0x00FF00 : 0xFF0000);
    matrix.noFill();
    matrix.rect(0, 0, 5, 7);

    matrix.stroke(buzzerAddrFound ? 0x0000FF : 0xFF0000);
    matrix.noFill();
    matrix.circle(9, 3, 3);

    if (distanceMm > 0) {
      int columns = map(constrain(distanceMm, 80, 1200), 1200, 80, 1, 12);
      matrix.fill(0xFFFFFF);
      matrix.stroke(0xFFFFFF);
      for (int x = 0; x < columns; x++) {
        matrix.line(x, 7, x, 7 - min(7, columns));
      }
    }
  }

  matrix.endDraw();
}

void rawBuzzerTone(uint32_t freq, uint32_t durationMs) {
  if (!buzzerAddrFound) {
    return;
  }

  uint8_t payload[8];
  memcpy(&payload[0], &freq, sizeof(freq));
  memcpy(&payload[4], &durationMs, sizeof(durationMs));

  Wire1.beginTransmission(BUZZER_ADDR);
  Wire1.write(payload, sizeof(payload));
  Wire1.endTransmission();
}

void startupMelody() {
  rawBuzzerTone(880, 160);
  delay(200);
  rawBuzzerTone(1175, 160);
  delay(200);
  rawBuzzerTone(0, 0);
}

void playUnknownAlarm() {
  for (int i = 0; i < 3; i++) {
    rawBuzzerTone(988, 180);
    delay(230);
    rawBuzzerTone(740, 180);
    delay(230);
  }
  rawBuzzerTone(0, 0);
}

void playFaultAlarm() {
  rawBuzzerTone(330, 250);
  delay(300);
  rawBuzzerTone(220, 350);
  delay(420);
  rawBuzzerTone(0, 0);
}

void refreshModuleStatus() {
  distanceAddrFound = i2cPresent(DISTANCE_ADDR);
  buzzerAddrFound = i2cPresent(BUZZER_ADDR);

  if (distanceAddrFound && !distanceOk) {
    distanceOk = distance.begin();
  }

  if (!distanceAddrFound) {
    distanceOk = false;
  }
}

bool readDistance(int &distanceMm) {
  if (!distanceOk || !distance.available()) {
    return false;
  }

  float mm = distance.get();
  if (isnan(mm) || mm <= 0) {
    return false;
  }

  distanceMm = (int)mm;
  lastDistanceMm = distanceMm;
  return true;
}

String rpc_ping() {
  return String("pong");
}

String rpc_status() {
  return String("distance_ok=") + String(distanceOk ? 1 : 0) +
         String(",buzzer_ok=") + String(buzzerAddrFound ? 1 : 0) +
         String(",threshold_mm=") + String(proximityThresholdMm);
}

String rpc_distance_found() {
  return String(distanceOk ? 1 : 0);
}

String rpc_buzzer_found() {
  return String(buzzerAddrFound ? 1 : 0);
}

String rpc_threshold_mm() {
  return String(proximityThresholdMm);
}

String rpc_set_threshold_mm(int thresholdMm) {
  if (thresholdMm < 80 || thresholdMm > 4000) {
    return String("ERR");
  }

  proximityThresholdMm = thresholdMm;
  return String(proximityThresholdMm);
}

String rpc_read_distance_mm() {
  int distanceMm = -1;
  if (readDistance(distanceMm)) {
    return String(distanceMm);
  }

  return String(-1);
}

String rpc_buzz_unknown() {
  if (!buzzerAddrFound) {
    return String("NO_BUZZER");
  }

  playUnknownAlarm();
  return String("OK");
}

String rpc_buzz_fault() {
  if (!buzzerAddrFound) {
    return String("NO_BUZZER");
  }

  playFaultAlarm();
  return String("OK");
}

void setup() {
  matrix.begin();
  scrollText(" FACE GUARD ");

  Modulino.begin();
  refreshModuleStatus();

  char statusText[24];
  snprintf(statusText, sizeof(statusText), " D%d B%d ", distanceOk ? 1 : 0, buzzerAddrFound ? 1 : 0);
  scrollText(statusText);
  startupMelody();

  bool bridgeOk = Bridge.begin();
  bool rpcOk = false;
  if (bridgeOk) {
    rpcOk = Bridge.provide("face_guard_ping", rpc_ping);
    rpcOk = Bridge.provide("face_guard_status", rpc_status) && rpcOk;
    rpcOk = Bridge.provide("distance_found", rpc_distance_found) && rpcOk;
    rpcOk = Bridge.provide("buzzer_found", rpc_buzzer_found) && rpcOk;
    rpcOk = Bridge.provide("threshold_mm", rpc_threshold_mm) && rpcOk;
    rpcOk = Bridge.provide_safe("set_threshold_mm", rpc_set_threshold_mm) && rpcOk;
    rpcOk = Bridge.provide_safe("read_distance_mm", rpc_read_distance_mm) && rpcOk;
    rpcOk = Bridge.provide_safe("buzz_unknown", rpc_buzz_unknown) && rpcOk;
    rpcOk = Bridge.provide_safe("buzz_fault", rpc_buzz_fault) && rpcOk;
  }

  scrollText(bridgeOk && rpcOk ? " RPC OK " : " RPC FAIL ");
}

void loop() {
  int distanceMm = -1;
  bool gotDistance = readDistance(distanceMm);
  bool near = gotDistance && distanceMm <= proximityThresholdMm;

  if (millis() - lastStatusRefreshAt >= STATUS_REFRESH_MS) {
    lastStatusRefreshAt = millis();
    refreshModuleStatus();
  }

  drawStatusFrame(near, gotDistance ? distanceMm : lastDistanceMm);
  delay(20);
}
