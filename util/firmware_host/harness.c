/* Host harness for firmware/PicoProgramECE455.c.

   The firmware is compiled unchanged, with util/firmware_host on the include
   path in place of the Pico SDK, so its static functions are reachable here.
   stdin: the sample rate in samples/s, the sample count, then that many
   signed ADC codes. stdout: one "name value" line per result. */
#include <stdlib.h>

#define main firmware_main
#include "PicoProgramECE455.c"
#undef main

int main(void)
{
    double rate;
    unsigned long count;
    if (scanf("%lf %lu", &rate, &count) != 2 || count == 0)
    {
        return 2;
    }
    int32_t *samples = malloc(count * sizeof *samples);
    if (samples == NULL)
    {
        return 2;
    }
    for (unsigned long i = 0; i < count; i++)
    {
        long code;
        if (scanf("%ld", &code) != 1)
        {
            return 2;
        }
        samples[i] = (int32_t)code;
    }
    double frequency = 0.0, dc_offset = 0.0, hysteresis = 0.0;
    uint32_t crossings = 0, rejected = 0;
    bool valid = calculate_frequency(samples, (uint32_t)count, rate, &frequency, &crossings,
                                     &rejected, &dc_offset, &hysteresis);
    printf("valid %d\n", valid ? 1 : 0);
    printf("frequency_hz %.9f\n", frequency);
    printf("crossings %lu\n", (unsigned long)crossings);
    printf("rejected %lu\n", (unsigned long)rejected);
    printf("dc_offset_v %.9g\n", dc_offset);
    printf("vpp_v %.9g\n", calculate_vpp(samples, (uint32_t)count));
    printf("bfield_nt %.6f\n", frequency_to_bfield_nt(frequency));
    free(samples);
    return 0;
}
