#include <Arduino_Modulino.h>
#include <Arduino_RouterBridge.h>
#include <math.h>

ModulinoDistance distance;
ModulinoBuzzer buzzer;

bool distanceOk = false;
bool buzzerOk = false;
int bootStep = 0;

int scanner_ping() {
  return 42;
}

int scanner_boot_step() {
  return bootStep;
}

bool distance_found() {
  return distanceOk;
}

bool buzzer_found() {
  return buzzerOk;
}

int read_distance_mm() {
  if (!distanceOk || !distance.available()) {
    return -1;
  }

  float mm = distance.get();
  if (isnan(mm) || mm <= 0) {
    return -1;
  }

  return (int)mm;
}

bool buzz_test() {
  if (!buzzerOk) {
    return false;
  }

  buzzer.tone(880, 120);
  delay(160);
  buzzer.noTone();
  return true;
}

void setup() {
  bootStep = 1;
  Bridge.begin();
  bootStep = 2;
  Bridge.provide("scanner_ping", scanner_ping);
  Bridge.provide("scanner_boot_step", scanner_boot_step);
  Bridge.provide("distance_found", distance_found);
  Bridge.provide("buzzer_found", buzzer_found);
  Bridge.provide("read_distance_mm", read_distance_mm);
  Bridge.provide("buzz_test", buzz_test);

  bootStep = 3;
  Modulino.begin();
  bootStep = 4;
  distanceOk = distance.begin();
  bootStep = 5;
  buzzerOk = buzzer.begin();
  bootStep = 6;
}

void loop() {
  delay(20);
}
