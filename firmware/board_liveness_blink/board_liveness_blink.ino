void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  pinMode(LED3_R, OUTPUT);
  pinMode(LED3_G, OUTPUT);
  pinMode(LED3_B, OUTPUT);
  pinMode(LED4_R, OUTPUT);
  pinMode(LED4_G, OUTPUT);
  pinMode(LED4_B, OUTPUT);
}

void loop() {
  digitalWrite(LED_BUILTIN, HIGH);
  digitalWrite(LED3_R, HIGH);
  digitalWrite(LED3_G, LOW);
  digitalWrite(LED3_B, LOW);
  digitalWrite(LED4_R, HIGH);
  digitalWrite(LED4_G, LOW);
  digitalWrite(LED4_B, LOW);
  delay(250);
  digitalWrite(LED3_R, LOW);
  digitalWrite(LED3_G, HIGH);
  digitalWrite(LED3_B, LOW);
  digitalWrite(LED4_R, LOW);
  digitalWrite(LED4_G, HIGH);
  digitalWrite(LED4_B, LOW);
  delay(250);
  digitalWrite(LED3_R, LOW);
  digitalWrite(LED3_G, LOW);
  digitalWrite(LED3_B, HIGH);
  digitalWrite(LED4_R, LOW);
  digitalWrite(LED4_G, LOW);
  digitalWrite(LED4_B, HIGH);
  delay(250);
  delay(120);
  digitalWrite(LED_BUILTIN, LOW);
  digitalWrite(LED3_R, LOW);
  digitalWrite(LED3_G, LOW);
  digitalWrite(LED3_B, LOW);
  digitalWrite(LED4_R, LOW);
  digitalWrite(LED4_G, LOW);
  digitalWrite(LED4_B, LOW);
  delay(120);
}
