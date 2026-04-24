#include <Arduino_Modulino.h>
#include <ArduinoGraphics.h>
#include <Arduino_LED_Matrix.h>
#include <Wire.h>
#include <math.h>

Arduino_LED_Matrix matrix;
ModulinoDistance distance;

const uint8_t BUZZER_ADDR = 0x1E;
const uint8_t DISTANCE_ADDR = 0x29;
const int PROXIMITY_THRESHOLD_MM = 700;

bool distanceAddrFound = false;
bool buzzerAddrFound = false;
bool distanceOk = false;
unsigned long lastToneAt = 0;
unsigned long lastStatusAt = 0;

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
  int filledColumns = 0;
  if (distanceMm > 0) {
    filledColumns = map(constrain(distanceMm, 80, 1200), 1200, 80, 1, 12);
  }

  matrix.clear();
  matrix.beginDraw();

  if (distanceAddrFound) {
    matrix.stroke(0x00FF00);
    matrix.noFill();
    matrix.rect(0, 0, 5, 7);
  } else {
    matrix.stroke(0xFF0000);
    matrix.line(0, 0, 5, 7);
    matrix.line(5, 0, 0, 7);
  }

  if (buzzerAddrFound) {
    matrix.stroke(0x0000FF);
    matrix.noFill();
    matrix.circle(9, 3, 3);
  } else {
    matrix.stroke(0xFF0000);
    matrix.line(7, 0, 11, 7);
    matrix.line(11, 0, 7, 7);
  }

  if (near) {
    matrix.fill(0xFFFFFF);
    matrix.stroke(0xFFFFFF);
    matrix.rect(0, 0, 12, 8);
  } else if (distanceMm > 0) {
    matrix.fill(0xFFFFFF);
    matrix.stroke(0xFFFFFF);
    for (int x = 0; x < filledColumns; x++) {
      matrix.line(x, 7, x, 7 - min(7, filledColumns));
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
  if (!buzzerAddrFound) {
    return;
  }

  rawBuzzerTone(880, 180);
  delay(220);
  rawBuzzerTone(1175, 180);
  delay(220);
  rawBuzzerTone(0, 0);
}

void refreshModuleStatus() {
  distanceAddrFound = i2cPresent(DISTANCE_ADDR);
  buzzerAddrFound = i2cPresent(BUZZER_ADDR);
}

void setup() {
  matrix.begin();
  scrollText(" MODULINO PROBE ");

  Modulino.begin();
  refreshModuleStatus();

  if (distanceAddrFound) {
    distanceOk = distance.begin();
  }

  char status[24];
  snprintf(status, sizeof(status), " D%d B%d ", distanceAddrFound ? 1 : 0, buzzerAddrFound ? 1 : 0);
  scrollText(status);
  startupMelody();
}

void loop() {
  int distanceMm = -1;
  bool near = false;

  if (millis() - lastStatusAt > 3000) {
    lastStatusAt = millis();
    refreshModuleStatus();
  }

  if (distanceOk && distance.available()) {
    float mm = distance.get();
    if (!isnan(mm) && mm > 0) {
      distanceMm = (int)mm;
      near = distanceMm <= PROXIMITY_THRESHOLD_MM;
    }
  }

  if (near && millis() - lastToneAt > 450) {
    lastToneAt = millis();
    rawBuzzerTone(988, 300);
  }

  drawStatusFrame(near, distanceMm);
  delay(40);
}
