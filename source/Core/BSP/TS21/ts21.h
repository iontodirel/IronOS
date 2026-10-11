#ifndef BSP_TS21_BRINGUP_H
#define BSP_TS21_BRINGUP_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define TS21_RCC       UINT32_C(0x40021000)
#define TS21_GPIOA     UINT32_C(0x40010800)
#define TS21_GPIOB     UINT32_C(0x40010C00)
#define TS21_TIM3      UINT32_C(0x40000400)
#define TS21_ADC1      UINT32_C(0x40012400)
#define TS21_USART2    UINT32_C(0x40004400)
#define TS21_IWDG      UINT32_C(0x40003000)
#define TS21_SYSTICK   UINT32_C(0xE000F000)
#define TS21_CLOCK_HZ  UINT32_C(8000000)
#define TS21_HEATER_EN (UINT32_C(1) << 10)
#define TS21_HEATER_IN (UINT32_C(1) << 6)
#define TS21_SCL       (UINT32_C(1) << 10)
#define TS21_SDA       (UINT32_C(1) << 11)

enum TS21Error {
  TS21_ERROR_CLOCK    = 1U << 0,
  TS21_ERROR_ADC      = 1U << 1,
  TS21_ERROR_I2C_BUS  = 1U << 2,
  TS21_ERROR_I2C_NACK = 1U << 3,
  TS21_ERROR_UART     = 1U << 4,
  TS21_ERROR_ARGUMENT = 1U << 5,
  TS21_ERROR_TRAP     = 1U << 6,
};

struct TS21PDParser {
  uint8_t bytes[4];
  uint8_t used;
};

struct TS21PDFrame {
  uint8_t voltage;
  uint8_t status;
};

struct TS21Status {
  uint32_t signature;
  uint32_t errors;
  uint32_t iterations;
  uint32_t pd_frames;
  uint32_t pd_last_us;
  uint16_t raw_adc[4];
  uint8_t  adc_valid_mask;
  uint8_t  buttons;
  uint8_t  pd_voltage;
  uint8_t  pd_status;
  uint8_t  page;
};

extern volatile struct TS21Status ts21_status;

uint8_t ts21_crc8(const uint8_t *data, size_t size);
bool    ts21_pd_feed(struct TS21PDParser *parser, uint8_t byte, struct TS21PDFrame *frame);

void     ts21_heater_inhibit(void);
void     ts21_watchdog_refresh(void);
bool     ts21_board_init(void);
uint32_t ts21_micros(void);
bool     ts21_delay_us(uint32_t duration);
uint8_t  ts21_buttons(void);
bool     ts21_adc_read(uint8_t channel, uint16_t *value);
void     ts21_uart_poll(void);
bool     ts21_oled_write(uint8_t control, const uint8_t *data, size_t size);
void     ts21_fault(uint32_t error) __attribute__((noreturn));

#ifdef TS21_HOST_TEST
uint32_t ts21_mmio_read(uint32_t address);
void     ts21_mmio_write(uint32_t address, uint32_t value);
#endif

#endif
