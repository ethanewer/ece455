/* Host stand-in for the Pico SDK SPI header. */
#ifndef ECE455_HOST_HARDWARE_SPI_H
#define ECE455_HOST_HARDWARE_SPI_H

#include <stddef.h>
#include <stdint.h>
#include <string.h>

typedef struct spi_inst spi_inst_t;
#define spi0 ((spi_inst_t *)0)

typedef enum { SPI_CPOL_0, SPI_CPOL_1 } spi_cpol_t;
typedef enum { SPI_CPHA_0, SPI_CPHA_1 } spi_cpha_t;
typedef enum { SPI_LSB_FIRST, SPI_MSB_FIRST } spi_order_t;

static inline unsigned int spi_init(spi_inst_t *spi, unsigned int baud) { (void)spi; return baud; }
static inline void spi_set_format(spi_inst_t *spi, unsigned int bits, spi_cpol_t cpol,
                                  spi_cpha_t cpha, spi_order_t order) {
    (void)spi; (void)bits; (void)cpol; (void)cpha; (void)order;
}
static inline int spi_write_blocking(spi_inst_t *spi, const uint8_t *src, size_t len) {
    (void)spi; (void)src; return (int)len;
}
static inline int spi_read_blocking(spi_inst_t *spi, uint8_t tx, uint8_t *dst, size_t len) {
    (void)spi; (void)tx; memset(dst, 0, len); return (int)len;
}
static inline int spi_write_read_blocking(spi_inst_t *spi, const uint8_t *src, uint8_t *dst,
                                          size_t len) {
    (void)spi; (void)src; memset(dst, 0, len); return (int)len;
}

#endif
