#include "Font.h"
#include "Settings.h"
#include "power.hpp"
#include <cassert>
#include <cstdio>

const uint16_t  powerPWM = 255;
uint16_t        totalPWM = 255;
static unsigned calls;

void setTipPWM(uint8_t pulse, bool) {
  assert(pulse == 0);
  ++calls;
}
uint16_t getInputVoltageX10(uint16_t, uint8_t) { return 50; }
uint8_t  getTipResistanceX10() { return 20; }
uint16_t getSettingValue(SettingsOptions) { return VOLTAGE_DIV; }

void           ui_pre_render_assets(void);
extern uint8_t buttonAF[sizeof(buttonA)];
extern uint8_t buttonBF[sizeof(buttonB)];
extern uint8_t disconnectedTipF[sizeof(disconnectedTip)];

int main() {
  for (int32_t watts = -100; watts <= 2000; ++watts) {
    setTipX10Watts(watts);
    assert(x10WattHistory.average() == 0);
  }
  setTipX10Watts(INT32_MAX);
  setTipX10Watts(INT32_MIN);
  assert(calls == 2103);
  assert(x10WattHistory.average() == 0);

  ui_pre_render_assets();
  for (unsigned row = 0; row < 4; ++row) {
    for (unsigned x = 0; x < 56; ++x) {
      const unsigned source = row * 56 + 55 - x, destination = row * 56 + x;
      assert(buttonAF[destination] == buttonA[source]);
      assert(buttonBF[destination] == buttonB[source]);
      assert(disconnectedTipF[destination] == disconnectedTip[source]);
    }
  }
  puts("TS21 IronOS tests passed: zero requested/reported heater power and complete 128x32 asset rotation");
}
