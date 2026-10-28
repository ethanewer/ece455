/* Host stand-in for the Pico SDK's stdio header. */
#ifndef ECE455_HOST_PICO_STDIO_H
#define ECE455_HOST_PICO_STDIO_H

#include <stdbool.h>
#include <stdio.h>

static inline void stdio_put_string(const char *s, int len, bool newline, bool cr_translation) {
    (void)newline; (void)cr_translation; fwrite(s, 1, (size_t)len, stdout);
}
static inline void stdio_flush(void) { fflush(stdout); }

#endif
