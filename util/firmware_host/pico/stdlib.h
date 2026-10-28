/* Host stand-in for the Pico SDK header used by firmware/PicoProgramECE455.c.
   Only the estimator is exercised on the host; hardware calls do nothing. */
#ifndef ECE455_HOST_PICO_STDLIB_H
#define ECE455_HOST_PICO_STDLIB_H

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#define GPIO_IN 0
#define GPIO_OUT 1
#define GPIO_FUNC_SPI 1

static inline void stdio_init_all(void) {}
static inline void sleep_ms(uint32_t ms) { (void)ms; }
static inline void sleep_us(uint64_t us) { (void)us; }
static inline uint64_t time_us_64(void) { return 0; }
static inline void tight_loop_contents(void) {}
static inline void gpio_init(unsigned int pin) { (void)pin; }
static inline void gpio_set_dir(unsigned int pin, bool out) { (void)pin; (void)out; }
static inline void gpio_pull_up(unsigned int pin) { (void)pin; }
static inline void gpio_set_function(unsigned int pin, int function) { (void)pin; (void)function; }
static inline void gpio_put(unsigned int pin, bool value) { (void)pin; (void)value; }
static inline bool gpio_get(unsigned int pin) { (void)pin; return false; }

#endif
