#include "ts21.h"

#ifndef TS21_HOST_TEST
static uint32_t ts21_mmio_read(uint32_t address) { return *(volatile uint32_t *)(uintptr_t)address; }
static void     ts21_mmio_write(uint32_t address, uint32_t value) { *(volatile uint32_t *)(uintptr_t)address = value; }
#endif

static bool                uart_ready;
static bool                adc_ready;
static struct TS21PDParser pd_parser;

static void modify(uint32_t address, uint32_t clear, uint32_t set) { ts21_mmio_write(address, (ts21_mmio_read(address) & ~clear) | set); }

static void gpio_mode(uint32_t port, unsigned pin, uint32_t mode) {
  const unsigned shift = (pin % 8) * 4;
  modify(port + (pin < 8 ? 0U : 4U), UINT32_C(15) << shift, mode << shift);
}

static bool wait_bits(uint32_t address, uint32_t mask, uint32_t expected) {
  for (unsigned remaining = 100000; remaining; --remaining) {
    if ((ts21_mmio_read(address) & mask) == expected) {
      return true;
    }
    ts21_uart_poll();
  }
  return false;
}

void ts21_heater_inhibit(void) {
  modify(TS21_RCC + 0x18, 0, 4);
  // Stock firmware clears PA10 before sampling the thermocouple.
  ts21_mmio_write(TS21_GPIOA + 0x14, TS21_HEATER_EN);
  gpio_mode(TS21_GPIOA, 10, 2);

  modify(TS21_RCC + 0x1C, 0, 2);
  ts21_mmio_write(TS21_TIM3, 0);
  ts21_mmio_write(TS21_TIM3 + 0x20, 0);
  ts21_mmio_write(TS21_TIM3 + 0x34, 0);
  ts21_mmio_write(TS21_GPIOA + 0x14, TS21_HEATER_IN);
  gpio_mode(TS21_GPIOA, 6, 2);
}

void ts21_watchdog_refresh(void) { ts21_mmio_write(TS21_IWDG, 0xAAAA); }

uint32_t ts21_micros(void) { return ts21_mmio_read(TS21_SYSTICK + 8); }

bool ts21_delay_us(uint32_t duration) {
  if (duration > 100000) {
    ts21_status.errors |= TS21_ERROR_ARGUMENT;
    return false;
  }
  const uint32_t start     = ts21_micros();
  uint32_t       remaining = duration * 16 + 128;
  while ((uint32_t)(ts21_micros() - start) < duration) {
    if (!remaining--) {
      ts21_status.errors |= TS21_ERROR_CLOCK;
      return false;
    }
    ts21_uart_poll();
  }
  return true;
}

static bool clock_init(void) {
  modify(TS21_RCC, 0, 1);
  if (!wait_bits(TS21_RCC, 2, 2)) {
    return false;
  }
  modify(TS21_RCC + 4, 3, 0);
  if (!wait_bits(TS21_RCC + 4, 12, 0)) {
    return false;
  }
  // The diagnostic needs neither PLL nor high-voltage power negotiation.
  modify(TS21_RCC + 4, 0xFFF0, 0);
  modify(TS21_RCC, UINT32_C(1) << 24, 0);
  ts21_mmio_write(TS21_SYSTICK, 0);
  ts21_mmio_write(TS21_SYSTICK + 4, 0);
  ts21_mmio_write(TS21_SYSTICK + 8, 0);
  ts21_mmio_write(TS21_SYSTICK + 12, 0);
  ts21_mmio_write(TS21_SYSTICK + 16, UINT32_MAX);
  ts21_mmio_write(TS21_SYSTICK + 20, UINT32_MAX);
  ts21_mmio_write(TS21_SYSTICK, 1); // HCLK/8 = 1 MHz; no interrupts.
  return true;
}

static void uart_init(void) {
  modify(TS21_RCC + 0x1C, 0, UINT32_C(1) << 17);
  gpio_mode(TS21_GPIOA, 3, 4);
  ts21_mmio_write(TS21_USART2 + 12, 0);
  ts21_mmio_write(TS21_USART2 + 16, 0);
  ts21_mmio_write(TS21_USART2 + 20, 0);
  ts21_mmio_write(TS21_USART2 + 8, (TS21_CLOCK_HZ + 4800) / 9600);
  ts21_mmio_write(TS21_USART2 + 12, 0x2004); // UE + RE only. Never enable TX.
  pd_parser.used = 0;
  uart_ready     = true;
}

void ts21_uart_poll(void) {
  if (!uart_ready) {
    return;
  }
  for (unsigned remaining = 8; remaining; --remaining) {
    const uint32_t status = ts21_mmio_read(TS21_USART2);
    if (status & 15U) {
      (void)ts21_mmio_read(TS21_USART2 + 4);
      pd_parser.used = 0;
      ts21_status.errors |= TS21_ERROR_UART;
      continue;
    }
    if (!(status & 0x20U)) {
      return;
    }
    const uint8_t      byte = (uint8_t)ts21_mmio_read(TS21_USART2 + 4);
    struct TS21PDFrame frame;
    if (ts21_pd_feed(&pd_parser, byte, &frame)) {
      ts21_status.pd_voltage = frame.voltage;
      ts21_status.pd_status  = frame.status;
      ts21_status.pd_last_us = ts21_micros();
      ++ts21_status.pd_frames;
    }
  }
}

static bool adc_init(void) {
  gpio_mode(TS21_GPIOA, 1, 0);
  gpio_mode(TS21_GPIOA, 2, 0);
  gpio_mode(TS21_GPIOA, 4, 0);
  gpio_mode(TS21_GPIOB, 1, 0);
  modify(TS21_RCC + 0x18, 0, UINT32_C(1) << 9);
  modify(TS21_RCC + 0x0C, 0, UINT32_C(1) << 9);
  modify(TS21_RCC + 0x0C, UINT32_C(1) << 9, 0);
  ts21_mmio_write(TS21_ADC1 + 4, 0);
  ts21_mmio_write(TS21_ADC1 + 0x2C, 0);
  ts21_mmio_write(TS21_ADC1 + 0x30, 0);
  ts21_mmio_write(TS21_ADC1 + 8, 0xE0001);
  if (!ts21_delay_us(10)) {
    return false;
  }
  modify(TS21_ADC1 + 8, 0, 8);
  if (!wait_bits(TS21_ADC1 + 8, 8, 0)) {
    return false;
  }
  modify(TS21_ADC1 + 8, 0, 4);
  return wait_bits(TS21_ADC1 + 8, 4, 0);
}

bool ts21_adc_read(uint8_t channel, uint16_t *value) {
  if (value == NULL || (channel != 1 && channel != 2 && channel != 4 && channel != 9)) {
    ts21_status.errors |= TS21_ERROR_ARGUMENT;
    return false;
  }
  if (!adc_ready) {
    ts21_status.errors |= TS21_ERROR_ADC;
    return false;
  }
  const unsigned shift = channel * 3;
  modify(TS21_ADC1 + 0x10, UINT32_C(7) << shift, UINT32_C(7) << shift);
  ts21_mmio_write(TS21_ADC1 + 0x34, channel);
  (void)ts21_mmio_read(TS21_ADC1 + 0x4C);
  ts21_mmio_write(TS21_ADC1, 0);
  modify(TS21_ADC1 + 8, 0, 0x500000);
  if (!wait_bits(TS21_ADC1, 2, 2)) {
    ts21_status.errors |= TS21_ERROR_ADC;
    return false;
  }
  *value = (uint16_t)(ts21_mmio_read(TS21_ADC1 + 0x4C) & 0xFFFU);
  return true;
}

uint8_t ts21_buttons(void) {
  const uint32_t pins = ts21_mmio_read(TS21_GPIOA + 8);
  return (uint8_t)(((pins & (1U << 5)) ? 0U : 1U) | ((pins & (1U << 7)) ? 0U : 2U));
}

static void scl_low(void) { ts21_mmio_write(TS21_GPIOB + 0x14, TS21_SCL); }
static void sda_low(void) { ts21_mmio_write(TS21_GPIOB + 0x14, TS21_SDA); }
static void sda_release(void) { ts21_mmio_write(TS21_GPIOB + 0x10, TS21_SDA); }

static bool scl_release(void) {
  ts21_mmio_write(TS21_GPIOB + 0x10, TS21_SCL);
  if (!wait_bits(TS21_GPIOB + 8, TS21_SCL, TS21_SCL)) {
    ts21_status.errors |= TS21_ERROR_I2C_BUS;
    return false;
  }
  return true;
}

static bool i2c_stop(void) {
  scl_low();
  sda_low();
  if (!ts21_delay_us(4) || !scl_release() || !ts21_delay_us(4)) {
    sda_release();
    return false;
  }
  sda_release();
  return ts21_delay_us(4);
}

static bool i2c_start(void) {
  sda_release();
  if (!scl_release() || !ts21_delay_us(4)) {
    return false;
  }
  if (!(ts21_mmio_read(TS21_GPIOB + 8) & TS21_SDA)) {
    ts21_status.errors |= TS21_ERROR_I2C_BUS;
    return false;
  }
  sda_low();
  if (!ts21_delay_us(4)) {
    return false;
  }
  scl_low();
  return true;
}

static bool i2c_byte(uint8_t value) {
  for (unsigned bit = 0; bit < 8; ++bit) {
    if (value & 0x80U) {
      sda_release();
    } else {
      sda_low();
    }
    if (!ts21_delay_us(4) || !scl_release() || !ts21_delay_us(4)) {
      return false;
    }
    scl_low();
    value = (uint8_t)(value << 1);
  }
  sda_release();
  if (!ts21_delay_us(4) || !scl_release() || !ts21_delay_us(4)) {
    return false;
  }
  const bool acknowledged = !(ts21_mmio_read(TS21_GPIOB + 8) & TS21_SDA);
  scl_low();
  if (!acknowledged) {
    ts21_status.errors |= TS21_ERROR_I2C_NACK;
  }
  return acknowledged;
}

bool ts21_oled_write(uint8_t control, const uint8_t *data, size_t size) {
  if ((control != 0 && control != 0x40) || data == NULL || size == 0 || size > 128) {
    ts21_status.errors |= TS21_ERROR_ARGUMENT;
    return false;
  }
  bool success = i2c_start() && i2c_byte(0x78) && i2c_byte(control);
  for (size_t i = 0; success && i < size; ++i) {
    success = i2c_byte(data[i]);
  }
  const bool stopped = i2c_stop();
  return success && stopped;
}

bool ts21_board_init(void) {
  uart_ready = false;
  adc_ready  = false;
  ts21_heater_inhibit();
  if (!clock_init()) {
    ts21_status.errors |= TS21_ERROR_CLOCK;
    return false;
  }
  modify(TS21_RCC + 0x18, 0, 8);
  ts21_mmio_write(TS21_GPIOA + 0x10, (1U << 5) | (1U << 7));
  gpio_mode(TS21_GPIOA, 5, 8);
  gpio_mode(TS21_GPIOA, 7, 8);
  ts21_mmio_write(TS21_GPIOB + 0x10, TS21_SCL | TS21_SDA);
  gpio_mode(TS21_GPIOB, 10, 6);
  gpio_mode(TS21_GPIOB, 11, 6);
  uart_init();
  adc_ready = adc_init();
  if (!adc_ready) {
    ts21_status.errors |= TS21_ERROR_ADC;
  }
  ts21_heater_inhibit();
  return true;
}
