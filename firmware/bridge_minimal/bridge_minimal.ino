#include <Arduino_RouterBridge.h>

String face_guard_ping() {
  return String("pong");
}

void setup() {
  Bridge.begin();
  Bridge.provide("face_guard_ping", face_guard_ping);
}

void loop() {
  delay(100);
}
