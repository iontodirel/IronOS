#include "BSP.h"
#include "I2C_Wrapper.hpp"
#include "TipThermoModel.h"
#include "main.hpp"
#include "ts21.h"
#include <limits.h>

volatile struct TS21Status ts21_status;
const uint16_t             powerPWM = 255;
uint16_t                   totalPWM = 255;

static StaticSemaphore_t sampleLockBuffer;
static SemaphoreHandle_t sampleLock;
static TS21Sample        sensors;
static bool              sensorsValid;
static int16_t           handleTemperature;

static void sampleSensors() {
  configASSERT(xSemaphoreTake(sampleLock, portMAX_DELAY) == pdTRUE);
  TS21Sample next = {};
  sensorsValid    = ts21_sample_sensors(&next);
  if (sensorsValid) {
    sensors                = next;
    sensorsValid           = ts21_handle_c_x10(next.handle, &handleTemperature);
    ts21_status.raw_adc[0] = next.tip;
    ts21_status.raw_adc[1] = next.handle;
    ts21_status.raw_adc[2] = next.auxiliary;
    ts21_status.raw_adc[3] = next.input;
  }
  ts21_status.adc_valid_mask = sensorsValid ? 15 : 0;
  if (!sensorsValid) {
    ts21_status.errors |= TS21_ERROR_SENSOR;
  }
  xSemaphoreGive(sampleLock);
}

extern "C" void ts21_run_constructors(void) {
  extern void (*__init_array_start[])(void);
  extern void (*__init_array_end[])(void);
  for (auto function = __init_array_start; function != __init_array_end; ++function) {
    (*function)();
  }
}

void ts21_fault(uint32_t error) {
  __asm volatile("csrrci zero, mstatus, 8" ::: "memory");
  ts21_status.errors |= error;
  for (;;) {
    ts21_heater_inhibit();
    ts21_watchdog_refresh();
  }
}

void BSPInit(void) {
  ts21_status.signature = 0x54533231;
  if (!ts21_board_init()) {
    ts21_fault(TS21_ERROR_CLOCK);
  }
  sampleLock = xSemaphoreCreateMutexStatic(&sampleLockBuffer);
  configASSERT(sampleLock != nullptr);
  FRToSI2C::FRToSInit();
  sampleSensors();
}

void preRToSInit() { BSPInit(); }
void postRToSInit() {}
void resetWatchdog() { ts21_watchdog_refresh(); }

int16_t getHandleTemperature(uint8_t) { return sensorsValid ? handleTemperature : INT16_MAX; }

uint16_t getTipRawTemp(uint8_t refresh) {
  if (refresh) {
    sampleSensors();
  }
  return sensorsValid ? sensors.tip : ADC_MAX_READING - 1;
}

uint16_t getInputVoltageX10(uint16_t divisor, uint8_t) {
  if (!sensorsValid || divisor == 0) {
    ts21_status.errors |= TS21_ERROR_SENSOR;
    return 0;
  }
  return ts21_input_voltage_x10(sensors.input) * VOLTAGE_DIV / divisor;
}

uint8_t getButtonA() { return (ts21_buttons() & 1) != 0; }
uint8_t getButtonB() { return (ts21_buttons() & 2) != 0; }

void delay_ms(uint16_t count) {
  while (count--) {
    if (!ts21_delay_us(1000)) {
      ts21_fault(TS21_ERROR_CLOCK);
    }
    resetWatchdog();
  }
}

void reboot() {
  ts21_heater_inhibit();
  __asm volatile("csrrci zero, mstatus, 8" ::: "memory");
  *(volatile uint32_t *)0xE000E048 = 0xBEEF0080;
  ts21_fault(TS21_ERROR_TRAP);
}

void     unstick_I2C() { ts21_fault(TS21_ERROR_I2C_BUS); }
void     showBootLogoIfavailable() {}
void     showBootLogo() {}
bool     getHallSensorFitted() { return false; }
int16_t  getRawHallEffect() { return 0; }
bool     getIsPoweredByDCIN() { return false; }
void     log_system_state(int32_t) {}
bool     getFUS302IRQLow() { return false; }
void     power_check() { ts21_uart_poll(); }
uint8_t  getTipResistanceX10() { return 0; } // Not measured; this build never drives the cartridge.
uint16_t getTipThermalMass() { return 0; }
uint16_t getTipInertia() { return 0; }
uint8_t  preStartChecks() { return sensorsValid; }
uint8_t  preStartChecksDone() { return sensorsValid; }
bool     isTipShorted() { return false; }
bool     isTipDisconnected() { return !sensorsValid || sensors.tip == 0 || sensors.tip >= 4090; }
void     setStatusLED(const enum StatusLED) {}
void     setBuzzer(bool) {}

uint64_t getDeviceID() {
  const volatile uint32_t *uid = (const volatile uint32_t *)0x1FFFF7E8;
  return ((uint64_t)uid[1] << 32) | uid[0];
}

TemperatureType_t getCustomTipMaxInC() { return 500; }
TemperatureType_t TipThermoModel::convertTipRawADCToDegC(uint16_t rawADC) {
  int16_t value;
  if (!ts21_tip_delta_c(rawADC, &value)) {
    ts21_status.errors |= TS21_ERROR_SENSOR;
    return getCustomTipMaxInC();
  }
  return value;
}
