/*
  Mini heliostato impreso - firmware MVP

  Pruebas iniciales:
  - mover motores DC con puente H,
  - leer encoders incrementales,
  - detectar finales de carrera,
  - homing por eje,
  - movimiento relativo por conteos.

  No usa PID. El movimiento es discreto por conteos.
*/

#include <Arduino.h>
#if defined(ESP32)
#include <esp_arduino_version.h>
#endif

struct AxisConfig {
  const char* name;
  uint8_t pwmPin;
  uint8_t in1Pin;
  uint8_t in2Pin;
  uint8_t encAPin;
  uint8_t encBPin;
  uint8_t homePin;
  uint8_t limitPin;
  uint8_t pwmChannel;
};

struct AxisState {
  volatile long counts;
  bool moving;
  int direction;
};

AxisConfig az = {"az", 25, 26, 27, 34, 35, 32, 33, 0};
AxisConfig el = {"el", 14, 12, 13, 36, 39, 18, 19, 1};

AxisState azState = {0, false, 0};
AxisState elState = {0, false, 0};

const int PWM_FREQ = 20000;
const int PWM_RES_BITS = 8;
const int DEFAULT_PWM = 110;
const int HOME_PWM = 80;
const long HOME_BACKOFF_COUNTS = 80;
const unsigned long MOVE_TIMEOUT_MS = 15000;

void setupPwm(AxisConfig& axis) {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttach(axis.pwmPin, PWM_FREQ, PWM_RES_BITS);
#else
  ledcSetup(axis.pwmChannel, PWM_FREQ, PWM_RES_BITS);
  ledcAttachPin(axis.pwmPin, axis.pwmChannel);
#endif
}

void writePwm(AxisConfig& axis, int value) {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(axis.pwmPin, value);
#else
  ledcWrite(axis.pwmChannel, value);
#endif
}

void IRAM_ATTR onAzEncoderA() {
  bool a = digitalRead(az.encAPin);
  bool b = digitalRead(az.encBPin);
  azState.counts += (a == b) ? 1 : -1;
}

void IRAM_ATTR onElEncoderA() {
  bool a = digitalRead(el.encAPin);
  bool b = digitalRead(el.encBPin);
  elState.counts += (a == b) ? 1 : -1;
}

AxisState* stateFor(AxisConfig& axis) {
  if (axis.name[0] == 'a') return &azState;
  return &elState;
}

void setupAxis(AxisConfig& axis) {
  pinMode(axis.in1Pin, OUTPUT);
  pinMode(axis.in2Pin, OUTPUT);
  pinMode(axis.encAPin, INPUT);
  pinMode(axis.encBPin, INPUT);
  pinMode(axis.homePin, INPUT_PULLUP);
  pinMode(axis.limitPin, INPUT_PULLUP);

  setupPwm(axis);

  digitalWrite(axis.in1Pin, LOW);
  digitalWrite(axis.in2Pin, LOW);
  writePwm(axis, 0);
}

bool homeActive(AxisConfig& axis) {
  return digitalRead(axis.homePin) == LOW;
}

bool limitActive(AxisConfig& axis) {
  return digitalRead(axis.limitPin) == LOW;
}

void stopAxis(AxisConfig& axis) {
  AxisState* s = stateFor(axis);
  writePwm(axis, 0);
  digitalWrite(axis.in1Pin, LOW);
  digitalWrite(axis.in2Pin, LOW);
  s->moving = false;
  s->direction = 0;
}

void stopAll() {
  stopAxis(az);
  stopAxis(el);
}

void runAxis(AxisConfig& axis, int direction, int pwm) {
  AxisState* s = stateFor(axis);
  pwm = constrain(pwm, 0, 255);

  if (direction > 0) {
    digitalWrite(axis.in1Pin, HIGH);
    digitalWrite(axis.in2Pin, LOW);
  } else if (direction < 0) {
    digitalWrite(axis.in1Pin, LOW);
    digitalWrite(axis.in2Pin, HIGH);
  } else {
    stopAxis(axis);
    return;
  }

  writePwm(axis, pwm);
  s->moving = true;
  s->direction = direction;
}

long axisCounts(AxisConfig& axis) {
  AxisState* s = stateFor(axis);
  noInterrupts();
  long value = s->counts;
  interrupts();
  return value;
}

void setAxisCounts(AxisConfig& axis, long value) {
  AxisState* s = stateFor(axis);
  noInterrupts();
  s->counts = value;
  interrupts();
}

AxisConfig* parseAxis(String token) {
  token.trim();
  token.toLowerCase();
  if (token == "az") return &az;
  if (token == "el") return &el;
  return nullptr;
}

void printStatus() {
  Serial.print("az counts=");
  Serial.print(axisCounts(az));
  Serial.print(" home=");
  Serial.print(homeActive(az));
  Serial.print(" limit=");
  Serial.print(limitActive(az));
  Serial.print(" | el counts=");
  Serial.print(axisCounts(el));
  Serial.print(" home=");
  Serial.print(homeActive(el));
  Serial.print(" limit=");
  Serial.println(limitActive(el));
}

bool moveRelative(AxisConfig& axis, long deltaCounts, int pwm) {
  if (deltaCounts == 0) return true;

  long start = axisCounts(axis);
  long target = start + deltaCounts;
  int direction = (deltaCounts > 0) ? 1 : -1;
  unsigned long t0 = millis();

  runAxis(axis, direction, pwm);

  while (millis() - t0 < MOVE_TIMEOUT_MS) {
    long current = axisCounts(axis);
    bool reached = (direction > 0) ? (current >= target) : (current <= target);
    if (reached) {
      stopAxis(axis);
      return true;
    }

    if (limitActive(axis)) {
      stopAxis(axis);
      Serial.println("ERROR: limit active");
      return false;
    }

    delay(2);
  }

  stopAxis(axis);
  Serial.println("ERROR: move timeout");
  return false;
}

bool homeAxis(AxisConfig& axis) {
  Serial.print("Homing ");
  Serial.println(axis.name);

  unsigned long t0 = millis();
  runAxis(axis, -1, HOME_PWM);

  while (!homeActive(axis)) {
    if (millis() - t0 > MOVE_TIMEOUT_MS) {
      stopAxis(axis);
      Serial.println("ERROR: home timeout");
      return false;
    }
    delay(2);
  }

  stopAxis(axis);
  delay(150);

  moveRelative(axis, HOME_BACKOFF_COUNTS, HOME_PWM);
  delay(150);

  t0 = millis();
  runAxis(axis, -1, HOME_PWM / 2);

  while (!homeActive(axis)) {
    if (millis() - t0 > MOVE_TIMEOUT_MS) {
      stopAxis(axis);
      Serial.println("ERROR: second home timeout");
      return false;
    }
    delay(2);
  }

  stopAxis(axis);
  setAxisCounts(axis, 0);
  Serial.println("home ok");
  return true;
}

String nextToken(String& line) {
  line.trim();
  int idx = line.indexOf(' ');
  if (idx < 0) {
    String token = line;
    line = "";
    return token;
  }
  String token = line.substring(0, idx);
  line = line.substring(idx + 1);
  return token;
}

void handleCommand(String line) {
  line.trim();
  if (line.length() == 0) return;

  String cmd = nextToken(line);
  cmd.toLowerCase();

  if (cmd == "status") {
    printStatus();
    return;
  }

  if (cmd == "stop") {
    stopAll();
    Serial.println("stopped");
    return;
  }

  if (cmd == "home") {
    AxisConfig* axis = parseAxis(nextToken(line));
    if (!axis) {
      Serial.println("ERROR: axis must be az or el");
      return;
    }
    homeAxis(*axis);
    return;
  }

  if (cmd == "jog") {
    AxisConfig* axis = parseAxis(nextToken(line));
    String dirToken = nextToken(line);
    int pwm = nextToken(line).toInt();
    if (!axis || (dirToken != "+" && dirToken != "-")) {
      Serial.println("ERROR: use jog az + 120");
      return;
    }
    if (pwm <= 0) pwm = DEFAULT_PWM;
    runAxis(*axis, dirToken == "+" ? 1 : -1, pwm);
    Serial.println("jogging");
    return;
  }

  if (cmd == "move") {
    AxisConfig* axis = parseAxis(nextToken(line));
    long delta = nextToken(line).toInt();
    int pwm = nextToken(line).toInt();
    if (!axis) {
      Serial.println("ERROR: axis must be az or el");
      return;
    }
    if (pwm <= 0) pwm = DEFAULT_PWM;
    moveRelative(*axis, delta, pwm);
    printStatus();
    return;
  }

  Serial.println("ERROR: unknown command");
}

void setup() {
  Serial.begin(115200);
  delay(500);

  setupAxis(az);
  setupAxis(el);

  attachInterrupt(digitalPinToInterrupt(az.encAPin), onAzEncoderA, CHANGE);
  attachInterrupt(digitalPinToInterrupt(el.encAPin), onElEncoderA, CHANGE);

  Serial.println("Mini heliostato MVP ready");
  Serial.println("Commands: status, stop, home az, home el, jog az + 120, move az 500 100");
}

void loop() {
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    handleCommand(line);
  }
}
