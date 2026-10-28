"""Pico 2W ADS1256 plotter. Pairs with PicoProgramECE455_50ms_FullWaveform.c.

The Pico sends its full capture as raw signed 32-bit little-endian ADC codes.
This program shows the entire signal and a detailed 100–150 ms section.
"""

import array
import sys
import time

import matplotlib.pyplot as plt
import serial
from serial.tools import list_ports

# ============================================================
# User settings: keep the COM port used in your working script
# ============================================================
# The Pico's serial port: the first command-line argument, else the
# first port with the Raspberry Pi USB vendor ID (0x2E8A), else COM5.
PORT = sys.argv[1] if len(sys.argv) > 1 else next(
    (port.device for port in list_ports.comports() if port.vid == 0x2E8A), "COM5")
BAUD = 115200  # USB CDC ignores the baud rate but pyserial requires one.
ADC_VREF = 2.08
ADC_PGA = 64.0
ADC_MAX_CODE = 8388607.0
FOCUS_START_MS = 100.0  # Relative to first ADC sample, NOT MOSFET turn-off
FOCUS_END_MS = 150.0
MAX_CAPTURE_SAMPLES = 100_000
PACKET_TIMEOUT_S = 20.0


# ============================================================
# Serial connection
# ============================================================
def show_available_ports():
    ports = list(list_ports.comports())
    if not ports:
        print("No serial ports detected.")
    for port in ports:
        print(f"  {port.device}: {port.description}")


def open_pico_serial():
    """Retry after reboot, unplug/replug, or another program releases COM port."""
    last_message = None
    while True:
        try:
            connection = serial.Serial(PORT, BAUD, timeout=0.25)
            connection.reset_input_buffer()
            print(f"Connected to Pico on {PORT}.")
            return connection
        except (serial.SerialException, OSError) as exc:
            if str(exc) != last_message:
                print(f"Unable to open {PORT}: {exc}")
                print("Close VS Code's serial monitor if it is using the port.")
                show_available_ports()
                last_message = str(exc)
            time.sleep(2)


# ============================================================
# Binary waveform protocol
# ============================================================
def read_exactly(connection, byte_count):
    """Return exactly N bytes (binary can contain newlines/zeroes)."""
    data = bytearray()
    last_progress = time.monotonic()
    while len(data) < byte_count:
        block = connection.read(min(8192, byte_count - len(data)))
        if block:
            data.extend(block)
            last_progress = time.monotonic()
        elif time.monotonic() - last_progress > PACKET_TIMEOUT_S:
            raise TimeoutError(
                f"Incomplete capture: received {len(data)} / {byte_count} bytes"
            )
    return bytes(data)


def decode_adc_codes(payload):
    """Decode little-endian signed 32-bit ADC samples into Python integers."""
    if len(payload) % 4:
        raise ValueError("Invalid ADC packet length")
    codes = array.array("i")
    if codes.itemsize != 4:
        raise RuntimeError("This Python runtime has a non-32-bit int array")
    codes.frombytes(payload)
    if sys.byteorder != "little":
        codes.byteswap()
    return codes


def parse_metadata(line):
    parts = line.split(",")
    if len(parts) != 10:
        raise ValueError(f"Expected 9 DATA_META values, got {len(parts)-1}")
    return {
        "captured_samples": int(parts[1]),
        "plot_samples": int(parts[2]),
        "capture_time_ms": float(parts[3]),
        "sample_rate": float(parts[4]),
        "vpp_mv": float(parts[5]),
        "dc_offset_mv": float(parts[6]),
        "zero_crossings": int(parts[7]),
        "frequency_hz": float(parts[8]),
        "bfield_nt": float(parts[9]),
    }


# ============================================================
# Plotting
# ============================================================
def measurement_text(metadata, recent_measurements):
    frequency = metadata["frequency_hz"]
    bfield_nt = metadata["bfield_nt"]
    frequency_str = f"{frequency:.5f} Hz" if frequency >= 0 else "N/A"
    field_str = (
        f"{bfield_nt:.3f} nT\n({bfield_nt / 1000.0:.6f} uT)"
        if bfield_nt >= 0 else "N/A"
    )
    lines = [
        f"Captured: {metadata['captured_samples']} samples",
        f"Capture time: {metadata['capture_time_ms']:.3f} ms",
        f"Measured SPS: {metadata['sample_rate']:.2f}",
        f"Measured Vpp: {metadata['vpp_mv']:.3f} mV",
        f"DC offset: {metadata['dc_offset_mv']:+.6f} mV",
        f"Zero crossings: {metadata['zero_crossings']}",
        f"Frequency: {frequency_str}",
        f"Proton field: {field_str}",
        "",
        "Last 3 captures:",
    ]
    for result in recent_measurements[-3:]:
        if result["frequency_hz"] < 0:
            lines.append(f"#{result['capture_number']}: N/A")
        else:
            lines.append(
                f"#{result['capture_number']}: "
                f"{result['frequency_hz']:.5f} Hz\n"
                f"  {result['bfield_nt']:.3f} nT"
            )
    return "\n".join(lines)


def update_graph(fig, axes, codes, metadata, capture_number, history):
    """Render one complete-record plot and one 100–150 ms zoom."""
    ax_full, ax_zoom = axes
    ax_full.clear()
    ax_zoom.clear()

    sample_rate = metadata["sample_rate"]
    if sample_rate <= 0:
        raise ValueError("Invalid sample rate in DATA_META")

    # Time zero = first ADC sample, which occurs ~50 ms after MOSFET off.
    times_ms = [i * 1000.0 / sample_rate for i in range(len(codes))]
    mv_per_code = 1000.0 * (2.0 * ADC_VREF) / (ADC_PGA * ADC_MAX_CODE)
    voltages_mv = [code * mv_per_code for code in codes]

    ax_full.plot(times_ms, voltages_mv, linewidth=0.55)
    ax_full.axvspan(FOCUS_START_MS, FOCUS_END_MS, alpha=0.15, color="tab:orange")
    ax_full.set_title(f"Complete waveform — Capture {capture_number}")
    ax_full.set_ylabel("Voltage (mV)")
    ax_full.set_xlabel("Time since ADC capture started (ms)")
    ax_full.set_xlim(0, max(1.0, times_ms[-1]))
    ax_full.grid(True)

    first = max(0, int(FOCUS_START_MS * sample_rate / 1000.0))
    last = min(len(codes), int(FOCUS_END_MS * sample_rate / 1000.0) + 1)
    if first < last:
        ax_zoom.plot(times_ms[first:last], voltages_mv[first:last], linewidth=1)
    else:
        ax_zoom.text(0.5, 0.5, "Capture shorter than 100 ms", ha="center",
                     va="center", transform=ax_zoom.transAxes)
    ax_zoom.set_title("Close-up: 100–150 ms after ADC acquisition begins")
    ax_zoom.set_xlabel("Time since ADC capture started (ms)")
    ax_zoom.set_ylabel("Voltage (mV)")
    ax_zoom.set_xlim(FOCUS_START_MS, FOCUS_END_MS)
    ax_zoom.grid(True)

    # Remove only our metadata panel; preserve the figure's suptitle.
    old_panel = getattr(fig, "_mag_measure_text", None)
    if old_panel is not None:
        old_panel.remove()
    fig._mag_measure_text = fig.text(
        0.705, 0.91, measurement_text(metadata, history),
        ha="left", va="top", family="monospace", fontsize=9.5
    )
    fig.suptitle("ADS1256 Magnetometer", fontsize=14)
    fig.subplots_adjust(left=0.08, right=0.68, top=0.89,
                        bottom=0.09, hspace=0.47)
    fig.canvas.draw_idle()
    fig.canvas.flush_events()
    plt.pause(0.05)


# ============================================================
# Main loop
# ============================================================
def main():
    plt.ion()
    fig, axes = plt.subplots(2, 1, figsize=(14.8, 8.2))
    plt.show(block=False)

    connection = open_pico_serial()
    metadata = None
    capture_number = 0
    recent_measurements = []

    print("Waiting for a button-triggered capture...")
    print("The plot shows the entire waveform and the 100–150 ms region.")
    print("Both plots update after each DATA_END. Press Ctrl+C to stop.\n")

    try:
        while True:
            try:
                raw_line = connection.readline()
                if not raw_line:
                    plt.pause(0.01)
                    continue
                line = raw_line.decode("utf-8", errors="replace").strip()

                if line.startswith("DATA_META,"):
                    try:
                        new_metadata = parse_metadata(line)
                        n = new_metadata["plot_samples"]
                        if n <= 0 or n > MAX_CAPTURE_SAMPLES:
                            raise ValueError(f"Invalid waveform size: {n}")
                        metadata = new_metadata
                        print(f"Capture {capture_number + 1}: expecting {n} full waveform samples")
                    except ValueError as exc:
                        metadata = None
                        print(f"Bad metadata: {exc}")
                    continue

                if line == "DATA_START_BIN":
                    if metadata is None:
                        print("Received binary waveform with no valid metadata; reconnecting.")
                        raise TimeoutError("Unframed binary data")
                    # EXACT binary read: never use readline() on sample bytes.
                    raw = read_exactly(connection, metadata["plot_samples"] * 4)
                    codes = decode_adc_codes(raw)
                    ending = connection.readline().decode("ascii", errors="replace").strip()
                    if ending != "DATA_END":
                        raise TimeoutError(f"Missing DATA_END after binary payload: {ending[:60]!r}")

                    capture_number += 1
                    recent_measurements.append({
                        "capture_number": capture_number,
                        "frequency_hz": metadata["frequency_hz"],
                        "bfield_nt": metadata["bfield_nt"],
                    })
                    recent_measurements = recent_measurements[-3:]
                    update_graph(fig, axes, codes, metadata, capture_number,
                                 recent_measurements)
                    print(f"Capture {capture_number} complete: {len(codes)} samples")
                    print(measurement_text(metadata, recent_measurements) + "\n")
                    metadata = None
                    continue

                if line == "DATA_START":
                    print("OLD firmware uses CSV data. Flash the matching FULL waveform C file.")
                    metadata = None
                    continue

                if line:
                    print(f"Pico: {line}")

            except (serial.SerialException, OSError, TimeoutError) as exc:
                print(f"Serial connection/packet error: {exc}")
                print("Reopening Pico serial connection...")
                try:
                    connection.close()
                except Exception:
                    pass
                metadata = None
                time.sleep(1)
                connection = open_pico_serial()

    except KeyboardInterrupt:
        print("\nStopping waveform plotter...")
    finally:
        connection.close()
        plt.ioff()
        if plt.fignum_exists(fig.number):
            plt.show()


if __name__ == "__main__":
    main()
