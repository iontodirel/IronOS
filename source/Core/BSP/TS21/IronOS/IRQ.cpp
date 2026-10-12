#include "BSP.h"
#include "Interrupts.h"
#include "main.hpp"

extern "C" void vPortSetupTimerInterrupt(void) {
  // Keep the pre-RTOS 1 MHz free-running clock used by the bounded I2C/ADC delays.
  NVIC_SetPriority(Software_IRQn, 0xF0);
  NVIC_SetPriority(SysTicK_IRQn, 0xF0);
  SysTick->SR   = 0;
  SysTick->CMP  = ts21_timer_now() + 1000;
  SysTick->CTLR = 3;
}

extern "C" void ts21_tick_reload(void) {
  SysTick->SR         = 0;
  uint64_t       next = SysTick->CMP + 1000;
  const uint64_t now  = ts21_timer_now();
  // Allow time to write both compare halves at the 8 MHz core clock.
  if (next <= now + 100) {
    next = now + 1000;
  }
  SysTick->CMP = next;
}

extern "C" void vApplicationTickHook(void) {
  static unsigned sampleTicks;
  ts21_uart_poll();
  if (++sampleTicks == configTICK_RATE_HZ / PID_TIM_HZ) {
    sampleTicks = 0;
    if (pidTaskNotification != nullptr) {
      BaseType_t wake = pdFALSE;
      vTaskNotifyGiveFromISR(pidTaskNotification, &wake);
      portYIELD_FROM_ISR(wake);
    }
  }
}
