#include <cassert>
#include <cstdio>

// Exercise the actual shared controller, including its private timing state.
#include "PIDThread.cpp"

static TickType_t testTicks;
TickType_t        xTaskGetTickCount() { return testTicks; }
uint32_t          availableW10(uint8_t) { return 125; }
uint16_t          getSettingValue(SettingsOptions option) { return option == SettingsOptions::PowerLimit ? 5 : 0; }
uint16_t          getTipThermalMass() { return TIP_THERMAL_MASS; }
uint16_t          getTipInertia() { return TIP_THERMAL_INERTIA; }

int main() {
  static_assert(TIP_THERMAL_MASS == 10 && TIP_THERMAL_INERTIA == 128, "Use the SEQURE S60/S60P C210 tuning");
  static_assert(SOLDERING_TEMP == 320 && MAX_TEMP_C == 450 && MAX_TEMP_F == 850, "Use normal IronOS temperature settings");
  testTicks = 5000;
  assert(getPIDResultX10Watts(320, 25) == 50);
  assert(getPIDResultX10Watts(450, 25) == 50);
  testTicks += 20000;
  assert(getPIDResultX10Watts(320, 25) == 50);
  testTicks = UINT32_MAX - 10;
  assert(getPIDResultX10Watts(320, 25) == 50);
  testTicks = 20;
  assert(getPIDResultX10Watts(320, 25) == 50);
  for (unsigned i = 0; i < 100; ++i) {
    testTicks += 125;
    const int32_t output = getPIDResultX10Watts(320, 500);
    assert(output >= -50 && output <= 0);
  }
  puts("TS21 C210 controller tests passed: shared tuning, idle/same-tick/rollover timing and bounded output");
}
