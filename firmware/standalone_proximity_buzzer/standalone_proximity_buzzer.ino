#include <Arduino_Modulino.h>
#include <math.h>

ModulinoDistance distance;
ModulinoBuzzer buzzer;

const int PROXIMITY_THRESHOLD_MM = 700;
bool distanceOk = false;
bool buzzerOk = false;
bool personPresent = false;
unsigned long lastBeepAt = 0;

void alarm() {
  if (!buzzerOk) {
    return;
  }

  buzzer.tone(988, 150);
  delay(190);
  buzzer.tone(740, 150);
  delay(190);
  buzzer.noTone();
}

void setup() {
  Modulino.begin();
  distanceOk = distance.begin();
  buzzerOk = buzzer.begin();

  if (buzzerOk) {
    buzzer.tone(660, 120);
    delay(160);
    buzzer.noTone();
  }
}

void loop() {
  if (!distanceOk || !buzzerOk || !distance.available()) {
    delay(20);
    return;
  }

  float mm = distance.get();
  if (isnan(mm) || mm <= 0) {
    delay(20);
    return;
  }

  if (mm > PROXIMITY_THRESHOLD_MM + 150) {
    personPresent = false;
  }

  if (mm <= PROXIMITY_THRESHOLD_MM && !personPresent && millis() - lastBeepAt > 1200) {
    personPresent = true;
    lastBeepAt = millis();
    alarm();
  }

  delay(20);
}
