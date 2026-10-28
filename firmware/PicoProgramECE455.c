// ADS1256 / Raspberry Pi Pico 2W — reliable 15 kSPS version.
// Restores single-conversion RDATA reads, not RDATAC.
// Keeps DATA_META fields, transfers complete waveform as compact binary.
// Hardware validation required: check the reported sample rate.
// Fix: report frequency even if a long DRDY interval triggers a timing warning.
// Button-triggered magnetometer sequence: polarize, 50 ms settle, capture.
// Enforce 10 s minimum between accepted button presses (start-to-start).

#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>

#include "pico/stdlib.h"
#include "pico/stdio.h"
#include "hardware/spi.h"


// ============================================================
// SPI pin definitions
// ============================================================

#define ADS_SPI  spi0

// Use conservative SPI timing as in the earlier working 15 kSPS build.
#define ADS_SPI_HZ 1000000

#define PIN_MISO 16     // ADS1256 DOUT
#define PIN_CS   17
#define PIN_SCLK 18
#define PIN_MOSI 19     // ADS1256 DIN
#define PIN_DRDY 20

// ============================================================
// Polarization coil output and trigger button
// ============================================================
// Physical pins on Pico 2W: GP0 = pin 1, GP1 = pin 2.
// Button (SW3 on the signal board) connects GP27 to GND; use the internal pull-up.
// GPIO0 HIGH enables the external MOSFET gate driver; LOW disables it.
#define PIN_POLARIZER      0
#define PIN_START_BUTTON   27

#define POLARIZE_MS        8000U
#define SETTLE_MS          50U
#define BUTTON_DEBOUNCE_MS 30U
// 10 seconds from one ACCEPTED button press to the next.
#define MIN_PRESS_INTERVAL_US 10000000ULL


// ============================================================
// ADS1256 register addresses
// ============================================================

#define REG_STATUS  0x00
#define REG_MUX     0x01
#define REG_ADCON   0x02
#define REG_DRATE   0x03
#define REG_IO      0x04

#define REG_OFC0    0x05
#define REG_OFC1    0x06
#define REG_OFC2    0x07

#define REG_FSC0    0x08
#define REG_FSC1    0x09
#define REG_FSC2    0x0A


// ============================================================
// ADS1256 commands
// ============================================================

#define CMD_WAKEUP   0x00
#define CMD_RDATA    0x01
#define CMD_RDATAC   0x03
#define CMD_SDATAC   0x0F

#define CMD_RREG     0x10
#define CMD_WREG     0x50

#define CMD_SELFCAL  0xF0

#define CMD_SYNC     0xFC
#define CMD_STANDBY  0xFD
#define CMD_RESET    0xFE


// ============================================================
// ADS1256 configuration
// ============================================================

// STATUS:
// ORDER = 0 -> MSB first
// ACAL  = 0 -> automatic calibration OFF
// BUFEN = 1 -> analog input buffer ON
#define ADS_STATUS_CONFIG  0x02


// MUX = 0x10:
//
// Positive input = AIN1
// Negative input = AIN0
//
// ADC measures:
//
//      AIN1 - AIN0
//
#define ADS_MUX_CONFIG     0x10


// ADCON:
//
// CLKOUT = OFF
// Sensor detect = OFF
// PGA = 64
#define ADS_ADCON_CONFIG   0x06


// DRATE:
//
// 0xE0 = nominal 15,000 conversions/second at 7.68 MHz ADC clock.
#define ADS_DRATE_CONFIG   0xE0


// GPIO register
#define ADS_IO_CONFIG      0xE0


// ============================================================
// ADC scaling
// ============================================================

// Your currently calibrated/measured reference value.
//
// Change this if you later determine a more accurate
// VREFP - VREFN value.
#define ADS_VREF           2.08

#define ADS_PGA            64.0

#define ADS_MAX_CODE       8388607.0

// Proton gyromagnetic ratio gamma/(2*pi), in Hz/T.
// For proton-precession magnetometry:
//
//     f = GAMMA * B
//     B = f / GAMMA
//
// Therefore 1 Hz corresponds to about 23.49 nT, and
// 1 nT corresponds to about 0.04258 Hz.
#define PROTON_GYROMAGNETIC_HZ_PER_T 42577478.92


// ============================================================
// Sampling configuration
// ============================================================

// This is only the NOMINAL sample rate.
//
// Frequency still uses the sample rate measured over the
// actual capture interval with the Pico clock.
#define ADS_NOMINAL_SAMPLE_RATE  15000.0


// ============================================================
// Expected magnetometer signal frequency range
// ============================================================

// These limits are used only to reject physically impossible
// duplicate crossings and to recover the correct cycle number
// if an occasional crossing is missed.
//
// Planned bench tests / magnetometer range: 1.5 kHz to 2.5 kHz.
#define EXPECTED_FREQ_MIN_HZ                 1500.0
#define EXPECTED_FREQ_MAX_HZ                 2500.0
#define EXPECTED_FREQ_CENTER_HZ              2000.0

// Hysteresis half-band, expressed as a fraction of the Vpp
// measured during the first 100 ms of the capture.
//
// 1% gives, for example:
//   5 mVpp  -> +/-0.05 mV hysteresis
//   25 mVpp -> +/-0.25 mV hysteresis
//
// This is intentionally much smaller than the final 10%-amplitude
// stop level, so a decaying waveform can still be tracked near the
// end of the useful record.
#define ZERO_CROSS_HYSTERESIS_VPP_FRACTION   0.01

// Real crossings at 2.5 kHz are separated by one full period.
// Any newly detected crossing closer than 70% of that minimum
// expected period is treated as a glitch / duplicate.
#define MIN_CROSSING_SPACING_FRACTION        0.70


// Stop the capture when EITHER:
//
// 1. Three seconds have elapsed, OR
// 2. The measured AC signal amplitude has fallen to 10%
//    of the amplitude measured during the first window.
//
// The amplitude check uses 100 ms windows.  For a sinusoid,
// AC RMS falls by the same ratio as peak amplitude, but RMS
// is less sensitive to single-sample noise spikes.
#define MAX_CAPTURE_US           3000000ULL
#define AMPLITUDE_WINDOW_US      100000ULL
#define DECAY_STOP_FRACTION      0.10


// 48,000 x 4 bytes = 192,000 bytes SRAM. Allows 3 s at 15 kSPS.
// Leaves plenty of space for USB, stack, and other firmware allocations.
#define MAX_SAMPLES              48000


// The entire ADC capture is sent to Python as native little-endian int32_t codes.
// This is ~180 kB for a 3-second capture at 15 kSPS (vs much more as text).
// The PC converts codes to mV and plots both the complete waveform
// and the 100-150 ms section. The frequency fit uses the same full buffer.


// ============================================================
// Sample storage
// ============================================================

// ADC conversion codes
static int32_t sample_buffer[MAX_SAMPLES];


typedef enum
{
    CAPTURE_STOP_TIME_LIMIT,
    CAPTURE_STOP_DECAY_LIMIT,
    CAPTURE_STOP_BUFFER_LIMIT
} capture_stop_reason_t;


// ============================================================
// Polarizer GPIO initialization and debounced start-button handling
// ============================================================
static void init_polarization_controls(void)
{
    // First set the output latch LOW, then enable output drive.
    // Add an EXTERNAL gate pull-down: GPIOs float while resetting.
    gpio_init(PIN_POLARIZER);
    gpio_put(PIN_POLARIZER, 0);
    gpio_set_dir(PIN_POLARIZER, GPIO_OUT);

    gpio_init(PIN_START_BUTTON);
    gpio_set_dir(PIN_START_BUTTON, GPIO_IN);
    gpio_pull_up(PIN_START_BUTTON);
}

// Do not accept buttons during the lockout. Require the button to be
// released and stable HIGH before accepting a new, stable LOW press.
// This prevents one long hold from starting repeated measurements.
static void wait_for_new_button_press(uint64_t next_allowed_us)
{
    while (time_us_64() < next_allowed_us) {
        sleep_ms(10);
    }

    uint64_t release_since_us = 0;
    while (true) {
        uint64_t now = time_us_64();
        if (gpio_get(PIN_START_BUTTON)) {  // HIGH = released
            if (release_since_us == 0) release_since_us = now;
            if (now - release_since_us >=
                (uint64_t)BUTTON_DEBOUNCE_MS * 1000ULL) break;
        } else {
            release_since_us = 0;
        }
        sleep_ms(5);
    }

    printf("Ready: press GP%d button to polarize and capture.\n", PIN_START_BUTTON);
    while (true) {
        if (!gpio_get(PIN_START_BUTTON)) { // LOW = pressed
            sleep_ms(BUTTON_DEBOUNCE_MS);
            if (!gpio_get(PIN_START_BUTTON)) return;
        }
        sleep_ms(5);
    }
}

// ============================================================
// Chip select
// ============================================================

static void ads_select(void)
{
    gpio_put(PIN_CS, 0);
}


static void ads_deselect(void)
{
    gpio_put(PIN_CS, 1);
}


// ============================================================
// Wait for DRDY LOW
//
// DRDY LOW = new conversion data is ready
// ============================================================

static bool ads_wait_drdy(uint32_t timeout_ms)
{
    uint64_t timeout =
        time_us_64() +
        ((uint64_t)timeout_ms * 1000);

    while (gpio_get(PIN_DRDY))
    {
        if (time_us_64() >= timeout)
        {
            return false;
        }

        tight_loop_contents();
    }

    return true;
}


// ============================================================
// Send one ADS1256 command
// ============================================================

static void ads_send_command(uint8_t command)
{
    ads_select();

    spi_write_blocking(
        ADS_SPI,
        &command,
        1
    );

    ads_deselect();

    sleep_us(2);
}


// ============================================================
// Read one ADS1256 register
// ============================================================

static uint8_t ads_read_register(uint8_t reg)
{
    uint8_t tx;
    uint8_t rx = 0;

    ads_select();


    // RREG command:
    //
    // 0001 rrrr
    tx = CMD_RREG | (reg & 0x0F);

    spi_write_blocking(
        ADS_SPI,
        &tx,
        1
    );


    // Number of registers to read minus 1.
    //
    // 0 = one register
    tx = 0x00;

    spi_write_blocking(
        ADS_SPI,
        &tx,
        1
    );


    // ADS1256 t6 delay
    sleep_us(10);


    // Dummy byte to generate 8 SPI clocks
    tx = 0xFF;

    spi_write_read_blocking(
        ADS_SPI,
        &tx,
        &rx,
        1
    );


    ads_deselect();

    return rx;
}


// ============================================================
// Write one ADS1256 register
// ============================================================

static void ads_write_register(
    uint8_t reg,
    uint8_t value
)
{
    uint8_t tx[3];


    // WREG command:
    //
    // 0101 rrrr
    tx[0] =
        CMD_WREG |
        (reg & 0x0F);


    // Number of registers to write minus 1.
    //
    // 0 = one register
    tx[1] = 0x00;


    // New register value
    tx[2] = value;


    ads_select();

    spi_write_blocking(
        ADS_SPI,
        tx,
        3
    );

    ads_deselect();


    sleep_us(2);
}


// ============================================================
// Configure ADS1256
// ============================================================

static void ads_configure(void)
{
    printf("\nConfiguring ADS1256...\n");


    // ACAL OFF
    // Buffer ON
    ads_write_register(
        REG_STATUS,
        ADS_STATUS_CONFIG
    );


    // Measure:
    //
    // AIN1 - AIN0
    ads_write_register(
        REG_MUX,
        ADS_MUX_CONFIG
    );


    // PGA = 64
    ads_write_register(
        REG_ADCON,
        ADS_ADCON_CONFIG
    );


    // Nominal 15,000 SPS
    ads_write_register(
        REG_DRATE,
        ADS_DRATE_CONFIG
    );


    ads_write_register(
        REG_IO,
        ADS_IO_CONFIG
    );
}


// ============================================================
// Print ADS1256 registers
// ============================================================

static void ads_print_registers(void)
{
    printf("\nADS1256 registers:\n");

    printf(
        "STATUS = 0x%02X\n",
        ads_read_register(REG_STATUS)
    );

    printf(
        "MUX    = 0x%02X\n",
        ads_read_register(REG_MUX)
    );

    printf(
        "ADCON  = 0x%02X\n",
        ads_read_register(REG_ADCON)
    );

    printf(
        "DRATE  = 0x%02X\n",
        ads_read_register(REG_DRATE)
    );

    printf(
        "IO     = 0x%02X\n",
        ads_read_register(REG_IO)
    );

    printf(
        "OFC0   = 0x%02X\n",
        ads_read_register(REG_OFC0)
    );

    printf(
        "OFC1   = 0x%02X\n",
        ads_read_register(REG_OFC1)
    );

    printf(
        "OFC2   = 0x%02X\n",
        ads_read_register(REG_OFC2)
    );

    printf(
        "FSC0   = 0x%02X\n",
        ads_read_register(REG_FSC0)
    );

    printf(
        "FSC1   = 0x%02X\n",
        ads_read_register(REG_FSC1)
    );

    printf(
        "FSC2   = 0x%02X\n",
        ads_read_register(REG_FSC2)
    );
}


// ============================================================
// Perform ADS1256 self calibration
// ============================================================

static bool ads_calibrate(void)
{
    printf("\nStarting SELFCAL...\n");


    // Make sure auto-calibration remains OFF
    ads_write_register(
        REG_STATUS,
        ADS_STATUS_CONFIG
    );


    // Internal offset + gain calibration
    ads_send_command(
        CMD_SELFCAL
    );


    // Give calibration time to begin
    sleep_us(20);


    // DRDY becomes LOW again when calibration is
    // complete and valid conversion data is available.
    if (!ads_wait_drdy(100))
    {
        printf(
            "ERROR: calibration timed out!\n"
        );

        return false;
    }


    // Restore our STATUS configuration explicitly
    ads_write_register(
        REG_STATUS,
        ADS_STATUS_CONFIG
    );


    printf(
        "Calibration complete.\n"
    );


    return true;
}


// ============================================================
// Read one ADS1256 conversion using the proven RDATA command.
// The ADC raises DRDY after all 24 data bits have been read.
// At 15 kSPS the 66.7 us conversion period is long enough for
// 1 MHz SPI + command + the minimum t6 delay.
// ============================================================
static void ads_read_data_ready(int32_t *signed_code)
{
    const uint8_t cmd = CMD_RDATA;
    uint8_t rx[3];
    ads_select();
    spi_write_blocking(ADS_SPI, &cmd, 1);
    // t6 >= 50 master clocks = 6.51 us at 7.68 MHz.
    sleep_us(8);
    spi_read_blocking(ADS_SPI, 0xFF, rx, 3);
    // t10 >= 8 master clocks before deasserting CS.
    sleep_us(2);
    ads_deselect();

    uint32_t raw = ((uint32_t)rx[0] << 16) |
                   ((uint32_t)rx[1] << 8)  |
                   ((uint32_t)rx[2]);
    *signed_code = (raw & 0x800000U)
        ? (int32_t)(raw | 0xFF000000U)
        : (int32_t)raw;
}

// Ensure a fresh LOW event, not a repeated read of the same sample.
static bool ads_wait_next_drdy(uint32_t timeout_ms)
{
    uint64_t deadline = time_us_64() + (uint64_t)timeout_ms * 1000ULL;
    // Reading 24 bits sets DRDY high. Require it before taking another.
    while (!gpio_get(PIN_DRDY)) {
        if (time_us_64() >= deadline) return false;
        tight_loop_contents();
    }
    while (gpio_get(PIN_DRDY)) {
        if (time_us_64() >= deadline) return false;
        tight_loop_contents();
    }
    return true;
}


// ============================================================
// Convert ADC code to differential voltage
//
// Voltage = AIN1 - AIN0
// ============================================================

static double ads_code_to_voltage(
    int32_t code
)
{
    return
        ((double)code *
         (2.0 * ADS_VREF)) /
        (ADS_PGA *
         ADS_MAX_CODE);
}


// ============================================================
// Convert proton-precession frequency to magnetic field.
//
// B[nT] = f[Hz] * 1e9 / gamma
// ============================================================

static double frequency_to_bfield_nt(
    double frequency_hz
)
{
    return
        frequency_hz *
        1000000000.0 /
        PROTON_GYROMAGNETIC_HZ_PER_T;
}


// ============================================================
// Transfer measurement metadata + FULL waveform to Python.
//
// DATA_META, captured_samples, transmitted_samples, capture_time_ms,
//            sample_rate, vpp_mV, dc_offset_mV, zero_crossings,
//            frequency_Hz, bfield_nT
// DATA_START_BIN (followed by a newline)
// [exactly transmitted_samples * 4 RAW BYTES: signed little-endian int32]
// DATA_END (followed by a newline)
//
// Binary transfer is MUCH faster than printf-ing ~45,000 decimal values.
// stdio_put_string(..., false, false) disables newline translation: ADC
// bytes may themselves contain 0x0A and must NOT be changed to CR-LF.
// Use the matching new adc_plots_full_and_100to150ms.py on the PC.
// ============================================================
static void send_waveform_to_python(
    const int32_t *samples,
    uint32_t number_of_samples,
    double capture_time_ms,
    double measured_sample_rate,
    double vpp,
    double dc_offset,
    uint32_t crossings,
    double frequency,
    bool frequency_valid
)
{
    if (number_of_samples == 0 || measured_sample_rate <= 0.0) return;

    const double frequency_to_send = frequency_valid ? frequency : -1.0;
    const double bfield_to_send = frequency_valid
        ? frequency_to_bfield_nt(frequency) : -1.0;

    // Retain all 9 metadata fields so the Python results panel stays intact.
    printf("DATA_META,%lu,%lu,%.6f,%.6f,%.6f,%.6f,%lu,%.6f,%.3f\n",
        (unsigned long)number_of_samples,
        (unsigned long)number_of_samples,
        capture_time_ms,
        measured_sample_rate,
        vpp * 1000.0,
        dc_offset * 1000.0,
        (unsigned long)crossings,
        frequency_to_send,
        bfield_to_send
    );
    printf("DATA_START_BIN\n");
    fflush(stdout);

    // RP2040/RP2350 use little-endian 32-bit int32_t samples.
    // Disable CR-LF translation to preserve all 4 bytes per sample.
    const int byte_count = (int)(number_of_samples * sizeof(samples[0]));
    stdio_put_string((const char *)samples, byte_count, false, false);
    stdio_flush();

    // Exact byte count is known from DATA_META, so no separator is needed.
    printf("DATA_END\n");
    fflush(stdout);
}


// ============================================================
// Capture fresh RDATA conversions for up to 3 seconds (or until
// the AC RMS signal falls below 10% of the first 100 ms window).
// No USB output during acquisition. Uses integer sums in the loop.
// ============================================================
static bool ads_capture_samples(
    int32_t *samples,
    uint32_t max_samples,
    uint32_t *samples_captured,
    uint64_t *first_sample_time_us,
    uint64_t *last_sample_time_us,
    uint32_t *long_sample_intervals,
    capture_stop_reason_t *stop_reason)
{
    *samples_captured = 0;
    *first_sample_time_us = 0;
    *last_sample_time_us = 0;
    *long_sample_intervals = 0;
    bool initial_amplitude_ready = false;
    double initial_ac_power = 0.0;
    int64_t window_sum = 0;
    uint64_t window_sum_squares = 0;
    uint32_t window_samples = 0;
    uint64_t window_start_us = 0;
    uint64_t capture_start_us = 0;

    // Prime DRDY and discard one result. This establishes a known
    // high->low transition even when DRDY was already low after
    // startup, calibration, or a previous capture.
    if (!ads_wait_drdy(100)) return false;
    int32_t discarded;
    ads_read_data_ready(&discarded);

    for (uint32_t i = 0; i < max_samples; ++i) {
        if (!ads_wait_next_drdy(100)) return false;
        uint64_t sample_time_us = time_us_64();
        if (i == 0) {
            capture_start_us = sample_time_us;
            window_start_us = sample_time_us;
            *first_sample_time_us = sample_time_us;
        } else if (sample_time_us - *last_sample_time_us > 105ULL) {
            // 15 kSPS = 66.67 us per conversion; >105 us may
            // indicate a missed sample (or timing problem).
            ++(*long_sample_intervals);
        }
        int32_t code;
        ads_read_data_ready(&code);
        samples[i] = code;
        *samples_captured = i + 1;
        *last_sample_time_us = sample_time_us;

        window_sum += (int64_t)code;
        window_sum_squares += (uint64_t)((int64_t)code * (int64_t)code);
        ++window_samples;

        if (sample_time_us - window_start_us >= AMPLITUDE_WINDOW_US) {
            double n = (double)window_samples;
            double mean = (double)window_sum / n;
            double ac_power = (double)window_sum_squares / n - mean * mean;
            if (ac_power < 0.0) ac_power = 0.0;
            if (!initial_amplitude_ready) {
                initial_ac_power = ac_power;
                initial_amplitude_ready = true;
            } else if (initial_ac_power > 0.0 &&
                       ac_power <= initial_ac_power *
                         DECAY_STOP_FRACTION * DECAY_STOP_FRACTION) {
                *stop_reason = CAPTURE_STOP_DECAY_LIMIT;
                return true;
            }
            window_start_us = sample_time_us;
            window_sum = 0;
            window_sum_squares = 0;
            window_samples = 0;
        }
        if (sample_time_us - capture_start_us >= MAX_CAPTURE_US) {
            *stop_reason = CAPTURE_STOP_TIME_LIMIT;
            return true;
        }
    }
    *stop_reason = CAPTURE_STOP_BUFFER_LIMIT;
    return true;
}


// ============================================================
// Calculate peak-to-peak voltage
// ============================================================

static double calculate_vpp(
    const int32_t *samples,
    uint32_t number_of_samples
)
{
    int32_t minimum =
        samples[0];

    int32_t maximum =
        samples[0];


    for (
        uint32_t i = 1;
        i < number_of_samples;
        i++
    )
    {
        if (samples[i] < minimum)
        {
            minimum =
                samples[i];
        }


        if (samples[i] > maximum)
        {
            maximum =
                samples[i];
        }
    }


    double minimum_voltage =
        ads_code_to_voltage(
            minimum
        );


    double maximum_voltage =
        ads_code_to_voltage(
            maximum
        );


    return
        maximum_voltage -
        minimum_voltage;
}


// ============================================================
// Calculate actual average sample rate
//
// The ADS1256 conversion timing is uniform, so we only need
// the timestamp of the first and last DRDY events.
//
// This avoids storing a 64-bit timestamp for every sample.
// ============================================================

static double calculate_measured_sample_rate(
    uint64_t first_sample_time_us,
    uint64_t last_sample_time_us,
    uint32_t number_of_samples
)
{
    if (number_of_samples < 2)
    {
        return 0.0;
    }


    uint64_t elapsed_us =
        last_sample_time_us -
        first_sample_time_us;


    if (elapsed_us == 0)
    {
        return 0.0;
    }


    // There are N - 1 intervals between N samples.
    return
        ((double)(number_of_samples - 1) *
         1000000.0) /
        (double)elapsed_us;
}


// ============================================================
// Calculate frequency using hysteretic positive-going crossings.
//
// Improvements over a simple zero-crossing counter:
//
// 1. Remove DC offset using the average of the full record.
//
// 2. Measure the initial Vpp over the first ~100 ms and create a
//    small hysteresis band around the center level.
//
// 3. A candidate crossing is counted only after the signal has:
//       - gone below the LOW threshold,
//       - crossed the CENTER level upward,
//       - then reached the HIGH threshold.
//
//    The actual crossing time is still interpolated at CENTER, so
//    the hysteresis does not introduce an amplitude-dependent phase
//    shift as a decaying sinusoid gets smaller.
//
// 4. Reject crossings that occur too soon to be physically possible
//    for the expected 1.5 kHz to 2.5 kHz signal range.
//
// 5. If a real crossing is occasionally missed, infer how many whole
//    cycles elapsed from the gap size so the least-squares cycle index
//    does not become permanently off by one.
//
// 6. Fit crossing position versus cycle number with least squares.
//    This uses all accepted crossings instead of relying on only the
//    first and last crossing.
// ============================================================

static bool calculate_frequency(
    const int32_t *samples,
    uint32_t number_of_samples,
    double measured_sample_rate,
    double *frequency,
    uint32_t *crossing_count,
    uint32_t *rejected_crossing_count,
    double *dc_offset_voltage,
    double *hysteresis_band_voltage
)
{
    if (
        (number_of_samples < 3) ||
        (measured_sample_rate <= 0.0)
    )
    {
        return false;
    }


    // --------------------------------------------------------
    // Calculate the center / DC offset from the full record.
    // --------------------------------------------------------

    int64_t sum = 0;

    for (
        uint32_t i = 0;
        i < number_of_samples;
        i++
    )
    {
        sum += samples[i];
    }


    double center =
        (double)sum /
        (double)number_of_samples;


    *dc_offset_voltage =
        ads_code_to_voltage(
            (int32_t)center
        );


    // --------------------------------------------------------
    // Estimate the initial signal amplitude from the first
    // ~100 ms of samples.
    // --------------------------------------------------------

    uint32_t initial_window_samples =
        (uint32_t)(
            measured_sample_rate *
            ((double)AMPLITUDE_WINDOW_US / 1000000.0)
        );


    if (initial_window_samples < 2)
    {
        initial_window_samples = 2;
    }


    if (initial_window_samples > number_of_samples)
    {
        initial_window_samples = number_of_samples;
    }


    int32_t initial_min = samples[0];
    int32_t initial_max = samples[0];


    for (
        uint32_t i = 1;
        i < initial_window_samples;
        i++
    )
    {
        if (samples[i] < initial_min)
        {
            initial_min = samples[i];
        }

        if (samples[i] > initial_max)
        {
            initial_max = samples[i];
        }
    }


    double initial_vpp_codes =
        (double)initial_max -
        (double)initial_min;


    if (initial_vpp_codes <= 0.0)
    {
        return false;
    }


    // Hysteresis is symmetric around the measured center.
    double hysteresis_band_codes =
        initial_vpp_codes *
        ZERO_CROSS_HYSTERESIS_VPP_FRACTION;


    double low_threshold =
        center - hysteresis_band_codes;


    double high_threshold =
        center + hysteresis_band_codes;


    *hysteresis_band_voltage =
        ads_code_to_voltage(
            (int32_t)hysteresis_band_codes
        );


    // --------------------------------------------------------
    // Minimum allowed spacing between accepted crossings.
    //
    // This rejects extra threshold chatter / glitches while still
    // leaving substantial margin below the shortest real period.
    // --------------------------------------------------------

    double minimum_crossing_spacing_samples =
        MIN_CROSSING_SPACING_FRACTION *
        measured_sample_rate /
        EXPECTED_FREQ_MAX_HZ;


    // --------------------------------------------------------
    // Least-squares accumulators.
    // --------------------------------------------------------

    uint32_t crossings = 0;
    uint32_t rejected_crossings = 0;

    double sum_cycle = 0.0;
    double sum_crossing = 0.0;
    double sum_cycle_squared = 0.0;
    double sum_cycle_crossing = 0.0;

    bool have_previous_crossing = false;
    double previous_crossing_sample = 0.0;

    uint32_t cycle_number = 0;


    // --------------------------------------------------------
    // Hysteresis state machine.
    // --------------------------------------------------------

    typedef enum
    {
        CROSS_WAIT_FOR_LOW,
        CROSS_WAIT_FOR_CENTER,
        CROSS_WAIT_FOR_HIGH
    } crossing_state_t;


    crossing_state_t state =
        CROSS_WAIT_FOR_LOW;


    double pending_crossing_sample = 0.0;


    for (
        uint32_t i = 1;
        i < number_of_samples;
        i++
    )
    {
        double previous =
            (double)samples[i - 1];


        double current =
            (double)samples[i];


        // ----------------------------------------------------
        // Re-arm only after the waveform has gone clearly below
        // center by the hysteresis amount.
        // ----------------------------------------------------

        if (state == CROSS_WAIT_FOR_LOW)
        {
            if (current <= low_threshold)
            {
                state =
                    CROSS_WAIT_FOR_CENTER;
            }

            continue;
        }


        // ----------------------------------------------------
        // After being armed below LOW, capture the precise
        // interpolated CENTER crossing.
        // ----------------------------------------------------

        if (state == CROSS_WAIT_FOR_CENTER)
        {
            if (
                (previous < center) &&
                (current >= center)
            )
            {
                double difference =
                    current - previous;


                if (difference != 0.0)
                {
                    double fraction =
                        (center - previous) /
                        difference;


                    pending_crossing_sample =
                        (double)(i - 1) +
                        fraction;


                    state =
                        CROSS_WAIT_FOR_HIGH;
                }
            }
        }


        // ----------------------------------------------------
        // Do not count the candidate crossing until the waveform
        // proves it was real by reaching HIGH.
        //
        // If it falls all the way back to LOW first, discard the
        // candidate and wait for another upward crossing.
        // ----------------------------------------------------

        if (state == CROSS_WAIT_FOR_HIGH)
        {
            if (current >= high_threshold)
            {
                bool accept_crossing = true;


                if (have_previous_crossing)
                {
                    double gap_samples =
                        pending_crossing_sample -
                        previous_crossing_sample;


                    if (
                        gap_samples <
                        minimum_crossing_spacing_samples
                    )
                    {
                        accept_crossing = false;
                        rejected_crossings++;
                    }
                }


                if (accept_crossing)
                {
                    if (have_previous_crossing)
                    {
                        double gap_samples =
                            pending_crossing_sample -
                            previous_crossing_sample;


                        // Estimate how many whole cycles elapsed.
                        // This keeps the regression cycle index correct
                        // even if one crossing is occasionally missed.
                        uint32_t cycles_elapsed =
                            (uint32_t)(
                                gap_samples *
                                EXPECTED_FREQ_CENTER_HZ /
                                measured_sample_rate +
                                0.5
                            );


                        if (cycles_elapsed < 1)
                        {
                            cycles_elapsed = 1;
                        }


                        cycle_number +=
                            cycles_elapsed;
                    }
                    else
                    {
                        cycle_number = 0;
                    }


                    double cycle =
                        (double)cycle_number;


                    sum_cycle +=
                        cycle;

                    sum_crossing +=
                        pending_crossing_sample;

                    sum_cycle_squared +=
                        cycle * cycle;

                    sum_cycle_crossing +=
                        cycle * pending_crossing_sample;


                    previous_crossing_sample =
                        pending_crossing_sample;

                    have_previous_crossing =
                        true;

                    crossings++;
                }


                // Require another complete LOW -> CENTER -> HIGH
                // excursion before another crossing can be counted.
                state =
                    CROSS_WAIT_FOR_LOW;
            }
            else if (current <= low_threshold)
            {
                // Candidate did not reach HIGH.  Discard it, but the
                // waveform is already below LOW so remain armed.
                state =
                    CROSS_WAIT_FOR_CENTER;
            }
        }
    }


    *crossing_count =
        crossings;


    *rejected_crossing_count =
        rejected_crossings;


    // At least three accepted crossings are desirable for a fit.
    if (crossings < 3)
    {
        return false;
    }


    // --------------------------------------------------------
    // Least-squares line fit:
    //
    // crossing_sample = intercept + period_samples * cycle
    // --------------------------------------------------------

    double count =
        (double)crossings;


    double denominator =
        count * sum_cycle_squared -
        sum_cycle * sum_cycle;


    if (denominator == 0.0)
    {
        return false;
    }


    double period_samples =
        (
            count * sum_cycle_crossing -
            sum_cycle * sum_crossing
        ) /
        denominator;


    if (period_samples <= 0.0)
    {
        return false;
    }


    *frequency =
        measured_sample_rate /
        period_samples;


    // Final sanity check for the planned magnetometer band.
    // Keep a small margin so bench tests near either endpoint are
    // not rejected because of tiny measurement error.
    if (
        (*frequency < (EXPECTED_FREQ_MIN_HZ * 0.95)) ||
        (*frequency > (EXPECTED_FREQ_MAX_HZ * 1.05))
    )
    {
        return false;
    }


    // Empirical calibration offset for the 1500-2500 Hz measurement range.
    // Apply only to valid measurements; downstream field and Python values
    // use the corrected frequency automatically.
    *frequency += 0.05;

    return true;
}


// ============================================================
// MAIN
// ============================================================

int main()
{
    // Initialize GP0 LOW before USB initialization or calibration.
    init_polarization_controls();
    stdio_init_all();


    // Allow USB serial connection to enumerate at startup only.
    sleep_ms(1000);


    printf("\n");
    printf("===============================\n");
    printf(" ADS1256 Magnetometer Test\n");
    printf("===============================\n");


    // ========================================================
    // SPI setup
    // ========================================================

    spi_init(
        ADS_SPI,
        ADS_SPI_HZ
    );


    gpio_set_function(
        PIN_SCLK,
        GPIO_FUNC_SPI
    );


    gpio_set_function(
        PIN_MOSI,
        GPIO_FUNC_SPI
    );


    gpio_set_function(
        PIN_MISO,
        GPIO_FUNC_SPI
    );


    // ========================================================
    // Chip select
    // ========================================================

    gpio_init(
        PIN_CS
    );


    gpio_set_dir(
        PIN_CS,
        GPIO_OUT
    );


    gpio_put(
        PIN_CS,
        1
    );


    // ========================================================
    // DRDY
    // ========================================================

    gpio_init(
        PIN_DRDY
    );


    gpio_set_dir(
        PIN_DRDY,
        GPIO_IN
    );


    gpio_pull_up(
        PIN_DRDY
    );


    // ========================================================
    // SPI mode
    //
    // Mode 1:
    //
    // CPOL = 0
    // CPHA = 1
    // ========================================================

    spi_set_format(
        ADS_SPI,
        8,
        SPI_CPOL_0,
        SPI_CPHA_1,
        SPI_MSB_FIRST
    );


    // Allow ADC/reference to settle
    sleep_ms(100);

    // Previous 30 kSPS firmware used RDATAC. If the ADS1256 stayed
    // powered while the Pico was reset, it might still be in that mode.
    // Exit continuous-read first, then reset to known defaults.
    if (!ads_wait_drdy(200)) {
        printf("ERROR: ADS1256 DRDY never went low at startup.\n");
        while (true) sleep_ms(1000);
    }
    ads_send_command(CMD_SDATAC);
    sleep_us(5);
    ads_send_command(CMD_RESET);
    sleep_ms(5);
    if (!ads_wait_drdy(200)) {
        printf("ERROR: ADS1256 not ready after reset.\n");
        while (true) sleep_ms(1000);
    }

    // ========================================================
    // Read initial STATUS
    // ========================================================

    uint8_t initial_status =
        ads_read_register(
            REG_STATUS
        );


    printf(
        "Initial STATUS = 0x%02X\n",
        initial_status
    );


    printf(
        "Device ID nibble = 0x%X\n",
        initial_status >> 4
    );


    // ========================================================
    // Configure ADC
    // ========================================================

    ads_configure();


    printf(
        "\nBefore SELFCAL:"
    );


    ads_print_registers();


    // ========================================================
    // Calibrate ADC
    // ========================================================

    if (!ads_calibrate())
    {
        printf(
            "Calibration failed.\n"
        );


        while (true)
        {
            sleep_ms(1000);
        }
    }


    printf(
        "\nAfter SELFCAL:"
    );


    ads_print_registers();


    // ========================================================
    // Verify STATUS configuration
    // ========================================================

    uint8_t status =
        ads_read_register(
            REG_STATUS
        );


    printf(
        "\nACAL bit = %d\n",
        (status >> 2) & 0x01
    );


    printf(
        "BUFEN bit = %d\n",
        (status >> 1) & 0x01
    );


    printf(
        "\nReady to measure frequency.\n"
    );


    printf(
        "Nominal ADC rate = %.0f SPS\n",
        ADS_NOMINAL_SAMPLE_RATE
    );


    printf(
        "Expected frequency range = %.0f to %.0f Hz\n",
        EXPECTED_FREQ_MIN_HZ,
        EXPECTED_FREQ_MAX_HZ
    );


    printf(
        "Equivalent proton field range = %.3f to %.3f uT\n",
        frequency_to_bfield_nt(EXPECTED_FREQ_MIN_HZ) / 1000.0,
        frequency_to_bfield_nt(EXPECTED_FREQ_MAX_HZ) / 1000.0
    );


    printf(
        "Maximum capture time = %.1f s\n",
        (double)MAX_CAPTURE_US /
        1000000.0
    );


    printf(
        "Decay stop threshold = %.0f%% of initial signal\n",
        DECAY_STOP_FRACTION *
        100.0
    );


    printf(
        "Maximum stored samples = %d\n\n",
        MAX_SAMPLES
    );


    // ============================================================
    // Button-triggered polarization and waveform capture
    // ============================================================
    // The 10-second lockout starts when an accepted press is detected,
    // NOT after finishing sample processing / Python output.
    uint64_t next_allowed_press_us = 0;

    while (true)
    {
        // Idle safely until a NEW debounced press occurs.
        gpio_put(PIN_POLARIZER, 0);
        wait_for_new_button_press(next_allowed_press_us);

        const uint64_t accepted_press_us = time_us_64();
        next_allowed_press_us = accepted_press_us + MIN_PRESS_INTERVAL_US;

        printf("Button accepted. Polarizing for %u ms...\n",
               (unsigned)POLARIZE_MS);
        printf("Then MOSFET OFF, settle %u ms, capture ADC.\n",
               (unsigned)SETTLE_MS);

        // No serial I/O while the coil is energized, or between coil
        // turn-off and ADC acquisition. The on-time is bounded normally
        // by sleep_ms(), but a hardware fail-safe is still recommended.
        gpio_put(PIN_POLARIZER, 1);
        sleep_ms(POLARIZE_MS);
        gpio_put(PIN_POLARIZER, 0);
        sleep_ms(SETTLE_MS);


        // ----------------------------------------------------
        // Acquire samples
        //
        // Capture ends automatically at:
        //   - 3 seconds, OR
        //   - 10% of the initial AC signal amplitude.
        // ----------------------------------------------------

        uint32_t samples_captured =
            0;

        uint64_t first_sample_time_us =
            0;

        uint64_t last_sample_time_us =
            0;

        uint32_t long_sample_intervals = 0;

        capture_stop_reason_t stop_reason =
            CAPTURE_STOP_BUFFER_LIMIT;


        if (!ads_capture_samples(
                sample_buffer,
                MAX_SAMPLES,
                &samples_captured,
                &first_sample_time_us,
                &last_sample_time_us,
                &long_sample_intervals,
                &stop_reason))
        {
            printf(
                "ERROR: DRDY timeout during capture!\n\n"
            );


            sleep_ms(1000);


            continue;
        }


        if (samples_captured < 3) {
            printf("ERROR: Too few samples to analyze.\n");
            sleep_ms(150);
            continue;
        }

        // ----------------------------------------------------
        // Calculate actual sample rate
        // ----------------------------------------------------

        double measured_sample_rate =
            calculate_measured_sample_rate(
                first_sample_time_us,
                last_sample_time_us,
                samples_captured
            );


        // ----------------------------------------------------
        // Calculate peak-to-peak amplitude over the complete
        // captured record.
        // ----------------------------------------------------

        double vpp =
            calculate_vpp(
                sample_buffer,
                samples_captured
            );


        // ----------------------------------------------------
        // Calculate frequency
        // ----------------------------------------------------

        double frequency =
            0.0;


        uint32_t crossings =
            0;


        uint32_t rejected_crossings =
            0;


        double dc_offset =
            0.0;


        double hysteresis_band =
            0.0;


        bool frequency_valid =
            calculate_frequency(
                sample_buffer,
                samples_captured,
                measured_sample_rate,
                &frequency,
                &crossings,
                &rejected_crossings,
                &dc_offset,
                &hysteresis_band
            );


        // IMPORTANT: Do not discard a valid sinusoidal frequency fit just
        // because one DRDY interval was measured as unusually long.
        // USB/interrupt jitter can delay the Pico's observation of DRDY
        // even when the ADC itself has converted at a steady rate.
        // A genuinely missed conversion can bias the frequency estimate,
        // however, so report a separate timing-quality warning below.
        // Python still receives the fit whenever calculate_frequency()
        // succeeds, retaining its original DATA_META packet format.
        bool timing_warning = (long_sample_intervals > 0);

        // ----------------------------------------------------
        // Calculate total capture time
        // ----------------------------------------------------

        double capture_time_ms =
            (double)(
                last_sample_time_us -
                first_sample_time_us
            ) /
            1000.0;


        // ----------------------------------------------------
        // Print results AFTER acquisition
        // ----------------------------------------------------

        printf(
            "Captured %lu samples\n",
            (unsigned long)samples_captured
        );


        printf(
            "Capture time = %.3f ms\n",
            capture_time_ms
        );


        if (stop_reason == CAPTURE_STOP_DECAY_LIMIT)
        {
            printf(
                "Capture stopped: signal reached 10%% "
                "of initial amplitude.\n"
            );
        }
        else if (stop_reason == CAPTURE_STOP_TIME_LIMIT)
        {
            printf(
                "Capture stopped: 3.0 second limit reached.\n"
            );
        }
        else
        {
            printf(
                "Capture stopped: sample buffer full "
                "(buffer capacity reached).\n"
            );
        }


        printf(
            "Measured sample rate = %.2f SPS\n",
            measured_sample_rate
        );

        // If noticeably below 15k, samples may be getting skipped.
        // Do not mistake a lower measured polling rate for a correctly
        // decimated 15k stream: the frequency estimate assumes that
        // every conversion has a corresponding sample in the buffer.
        if (measured_sample_rate < ADS_NOMINAL_SAMPLE_RATE * 0.98 ||
            measured_sample_rate > ADS_NOMINAL_SAMPLE_RATE * 1.02)
        {
            printf("WARNING: measured SPS differs from 15000. "
                   "Possible missed conversions / ADC clock mismatch.\n");
        }


        if (timing_warning)
        {
            printf("WARNING: %lu unusually long DRDY intervals detected.\n",
                   (unsigned long)long_sample_intervals);
            printf("The frequency fit is shown, but timing gaps may "
                   "make it less accurate.\n");
        }

        printf(
            "Measured Vpp = %.3f mV\n",
            vpp * 1000.0
        );
        // At PGA=64, full bipolar input span is +/-2*VREF/64.
        // A direct 360 mVpp generator input will clip severely.
        if (vpp > 0.98 * (4.0 * ADS_VREF / ADS_PGA)) {
            printf("WARNING: ADC at/near full-scale! Reduce input "
                   "amplitude or PGA gain.\n");
        }


        printf(
            "Measured DC offset = %+.6f mV\n",
            dc_offset * 1000.0
        );


        printf(
            "Positive zero crossings = %lu\n",
            (unsigned long)crossings
        );


        printf(
            "Rejected false crossings = %lu\n",
            (unsigned long)rejected_crossings
        );


        printf(
            "Zero-cross hysteresis = +/-%.6f mV\n",
            hysteresis_band * 1000.0
        );


        if (frequency_valid)
        {
            double magnetic_field_nt =
                frequency_to_bfield_nt(frequency);


            printf(
                "Calculated frequency = %.5f Hz\n",
                frequency
            );
            if (timing_warning) {
                printf("Frequency quality = CHECK TIMING "
                       "(possible missed conversions)\n");
            } else {
                printf("Frequency quality = No long DRDY intervals detected\n");
            }


            printf(
                "Equivalent proton B field = %.3f nT (%.6f uT)\n",
                magnetic_field_nt,
                magnetic_field_nt / 1000.0
            );
        }
        else
        {
            printf(
                "Could not calculate frequency.\n"
            );

            printf(
                "Check signal range, clipping, and DRDY intervals.\n"
            );
        }


        printf("\n");


        // ----------------------------------------------------
        // Send this completed capture to Python.
        //
        // The measurement results above are still printed in
        // the same human-readable format as before.  Python gets
        // a second, machine-readable copy of the waveform below.
        // ----------------------------------------------------

        send_waveform_to_python(
            sample_buffer,
            samples_captured,
            capture_time_ms,
            measured_sample_rate,
            vpp,
            dc_offset,
            crossings,
            frequency,
            frequency_valid
        );


        // Continue to the button wait state. The button must have been
        // released, and no new press is accepted until 10 seconds
        // after the previous accepted press.
    }
}