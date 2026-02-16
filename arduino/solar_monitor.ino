#include <Wire.h>
#include <Adafruit_ADS1X15.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// ---------- Pin and hardware setup ----------
constexpr uint8_t ONE_WIRE_BUS = 2;
constexpr uint8_t CURRENT_SENSOR_PIN = A0;

Adafruit_ADS1115 ads;
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature tempSensors(&oneWire);

// ---------- Serial + sample timing ----------
constexpr unsigned long SERIAL_BAUD = 115200;
constexpr unsigned long SAMPLE_INTERVAL_MS = 500; // ~2 Hz

// ---------- Voltage divider + ADS1115 calibration ----------
// Example: R_HIGH = 180k, R_LOW = 10k -> divider ratio = 19.0
float dividerRatio = 19.0f;
float voltageGainCal = 1.000f;
float voltageOffsetCal = 0.000f;

// ADS1115 gain influences max measurable ADC input voltage
// GAIN_ONE = +/-4.096V full scale. Safe for 0..3.3V input.
adsGain_t adsGain = GAIN_ONE;

// ---------- Current sensor calibration ----------
// ACS712-30A sensitivity around 66 mV/A, mid-point at Vcc/2.
float currentZeroVolts = 2.500f;
float currentMvPerAmp = 66.0f;
float currentGainCal = 1.000f;
float currentOffsetCal = 0.000f;

// ---------- Runtime state ----------
unsigned long lastSampleMs = 0;
DeviceAddress tempAddress0;
DeviceAddress tempAddress1;

static bool compareAddress(const DeviceAddress &a, const DeviceAddress &b) {
  for (uint8_t i = 0; i < 8; i++) {
    if (a[i] != b[i]) {
      return false;
    }
  }
  return true;
}

void printAddress(const DeviceAddress deviceAddress) {
  for (uint8_t i = 0; i < 8; i++) {
    if (deviceAddress[i] < 16) Serial.print("0");
    Serial.print(deviceAddress[i], HEX);
  }
}

float readPanelVoltageVolts() {
  int16_t raw = ads.readADC_SingleEnded(0);
  float adcVolts = ads.computeVolts(raw);
  float panelVolts = (adcVolts * dividerRatio);
  panelVolts = panelVolts * voltageGainCal + voltageOffsetCal;
  return panelVolts;
}

float readCurrentAmps() {
  constexpr int samples = 20;
  long total = 0;
  for (int i = 0; i < samples; i++) {
    total += analogRead(CURRENT_SENSOR_PIN);
    delayMicroseconds(500);
  }

  float avgCounts = total / static_cast<float>(samples);
  float sensorVolts = avgCounts * (5.0f / 1023.0f);
  float deltaMv = (sensorVolts - currentZeroVolts) * 1000.0f;
  float amps = (deltaMv / currentMvPerAmp);
  amps = amps * currentGainCal + currentOffsetCal;

  if (fabs(amps) < 0.03f) {
    amps = 0.0f;
  }
  return amps;
}

void autoZeroCurrentSensor() {
  constexpr int samples = 500;
  long total = 0;
  for (int i = 0; i < samples; i++) {
    total += analogRead(CURRENT_SENSOR_PIN);
    delay(2);
  }
  float avgCounts = total / static_cast<float>(samples);
  currentZeroVolts = avgCounts * (5.0f / 1023.0f);

  Serial.print("{\"event\":\"current_zero_calibrated\",\"zero_volts\":");
  Serial.print(currentZeroVolts, 5);
  Serial.println("}");
}

void setupTemperatureSensors() {
  tempSensors.begin();
  tempSensors.setWaitForConversion(true);

  if (tempSensors.getDeviceCount() < 2) {
    Serial.println("{\"event\":\"warning\",\"message\":\"Less than 2 DS18B20 sensors found\"}");
    return;
  }

  tempSensors.getAddress(tempAddress0, 0);
  tempSensors.getAddress(tempAddress1, 1);

  Serial.print("{\"event\":\"temp_sensor_0\",\"address\":\"");
  printAddress(tempAddress0);
  Serial.println("\"}");

  Serial.print("{\"event\":\"temp_sensor_1\",\"address\":\"");
  printAddress(tempAddress1);
  Serial.println("\"}");
}

void handleSerialCommands() {
  if (!Serial.available()) return;

  String cmd = Serial.readStringUntil('\n');
  cmd.trim();

  if (cmd == "CAL_ZERO") {
    autoZeroCurrentSensor();
    return;
  }

  if (cmd.startsWith("SET_DIVIDER=")) {
    dividerRatio = cmd.substring(String("SET_DIVIDER=").length()).toFloat();
    Serial.print("{\"event\":\"divider_updated\",\"ratio\":");
    Serial.print(dividerRatio, 5);
    Serial.println("}");
    return;
  }

  if (cmd.startsWith("SET_CURRENT_MV_PER_AMP=")) {
    currentMvPerAmp = cmd.substring(String("SET_CURRENT_MV_PER_AMP=").length()).toFloat();
    Serial.print("{\"event\":\"current_scale_updated\",\"mv_per_amp\":");
    Serial.print(currentMvPerAmp, 5);
    Serial.println("}");
    return;
  }

  Serial.print("{\"event\":\"unknown_command\",\"cmd\":\"");
  Serial.print(cmd);
  Serial.println("\"}");
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(300);

  Wire.begin();
  ads.setGain(adsGain);
  if (!ads.begin()) {
    Serial.println("{\"event\":\"fatal\",\"message\":\"ADS1115 not detected\"}");
    while (true) {
      delay(1000);
    }
  }

  setupTemperatureSensors();
  autoZeroCurrentSensor();
}

void loop() {
  handleSerialCommands();

  unsigned long now = millis();
  if (now - lastSampleMs < SAMPLE_INTERVAL_MS) {
    return;
  }
  lastSampleMs = now;

  float voltageV = readPanelVoltageVolts();
  float currentA = readCurrentAmps();
  float powerW = voltageV * currentA;

  tempSensors.requestTemperatures();
  float tempFrontC = tempSensors.getTempC(tempAddress0);
  float tempBackC = tempSensors.getTempC(tempAddress1);

  Serial.print("{");
  Serial.print("\"type\":\"sample\",");
  Serial.print("\"uptime_ms\":");
  Serial.print(now);
  Serial.print(",\"voltage_v\":");
  Serial.print(voltageV, 3);
  Serial.print(",\"current_a\":");
  Serial.print(currentA, 3);
  Serial.print(",\"power_w\":");
  Serial.print(powerW, 3);
  Serial.print(",\"temp_front_c\":");
  Serial.print(tempFrontC, 2);
  Serial.print(",\"temp_back_c\":");
  Serial.print(tempBackC, 2);
  Serial.println("}");
}
