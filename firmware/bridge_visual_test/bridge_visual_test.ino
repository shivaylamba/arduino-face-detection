#include <Arduino_RouterBridge.h>
#include <ArduinoGraphics.h>
#include <Arduino_LED_Matrix.h>

Arduino_LED_Matrix matrix;

int ping() {
  return 42;
}

int add(int a, int b) {
  return a + b;
}

void scrollText(const char *text) {
  matrix.textFont(Font_5x7);
  matrix.textScrollSpeed(80);
  matrix.beginText(0, 0, 127, 0, 0);
  matrix.print(text);
  matrix.endText(SCROLL_LEFT);
}

void setup() {
  matrix.begin();
  scrollText(" BRIDGE TEST ");

  bool bridgeOk = Bridge.begin();
  scrollText(bridgeOk ? " BRIDGE OK " : " BRIDGE FAIL ");

  bool pingOk = bridgeOk && Bridge.provide("face_guard_ping", ping);
  bool addOk = bridgeOk && Bridge.provide("face_guard_add", add);

  if (pingOk && addOk) {
    scrollText(" RPC OK ");
  } else {
    scrollText(" RPC FAIL ");
  }
}

void loop() {
  matrix.clear();
  matrix.beginDraw();
  matrix.stroke(0x00FF00);
  matrix.noFill();
  matrix.rect(0, 0, 12, 8);
  matrix.endDraw();
  delay(500);

  matrix.clear();
  matrix.beginDraw();
  matrix.stroke(0x00FF00);
  matrix.line(0, 0, 11, 7);
  matrix.line(11, 0, 0, 7);
  matrix.endDraw();
  delay(500);
}
