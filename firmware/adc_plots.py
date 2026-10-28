import time
import serial
from serial.tools import list_ports
import matplotlib.pyplot as plt


# ============================================================
# User settings
# ============================================================

PORT = "COM5"
BAUD = 115200

# The Pico sends only the first 10 ms of each capture for plotting.
PLOT_TIME_MS = 10.0


# ============================================================
# Open Pico serial connection
# ============================================================

def show_available_ports():
    ports = list(list_ports.comports())

    if not ports:
        print("No serial ports are currently detected.")
        return

    print("Detected serial ports:")

    for port in ports:
        description = port.description or "Unknown device"
        print(f"  {port.device}: {description}")


def open_pico_serial():
    last_message = None

    while True:
        try:
            ser = serial.Serial(
                PORT,
                BAUD,
                timeout=0.25
            )

            # Discard a partial line that may have been left in the
            # Windows serial buffer before Python connected.
            ser.reset_input_buffer()

            print(f"Connected to Pico on {PORT}.")
            return ser

        except (serial.SerialException, PermissionError) as error:
            message = str(error)

            if message != last_message:
                print()
                print(f"Could not open {PORT}.")

                if "Access is denied" in message or "PermissionError" in message:
                    print(f"{PORT} is currently in use by another program.")
                    print("Stop VS Code Serial Monitor so Python can use the Pico port.")
                    print("Python will keep retrying automatically.")
                else:
                    print(f"Serial error: {error}")
                    print("Check that the Pico is connected and PORT is correct.")

                show_available_ports()
                print("Retrying in 2 seconds... Press Ctrl+C to stop.\n")
                last_message = message

            time.sleep(2.0)


ser = open_pico_serial()


# ============================================================
# Storage for one capture
# ============================================================

times_ms = []
voltages_mv = []
collecting = False
capture_number = 0

# Keep frequency and proton-field results for the latest three captures.
recent_measurements = []

metadata = {
    "captured_samples": None,
    "plot_samples": None,
    "capture_time_ms": None,
    "sample_rate": None,
    "vpp_mv": None,
    "dc_offset_mv": None,
    "zero_crossings": None,
    "frequency_hz": None,
    "bfield_nt": None,
}


# Do not create the plot window until the first complete waveform
# packet has been received.
fig = None
ax = None
measurement_text = None


print("Waiting for a complete waveform capture...")
print("The plot opens after the first DATA_END packet is received.")
print("It will update automatically for every later capture.")
print("Press Ctrl+C in this terminal to stop.\n")


# ============================================================
# Format the measurement block shown inside the graph window
# ============================================================

def build_measurement_text():
    captured = metadata["captured_samples"]
    capture_time = metadata["capture_time_ms"]
    sample_rate = metadata["sample_rate"]
    vpp = metadata["vpp_mv"]
    dc_offset = metadata["dc_offset_mv"]
    crossings = metadata["zero_crossings"]
    frequency = metadata["frequency_hz"]
    bfield_nt = metadata["bfield_nt"]

    frequency_text = (
        f"{frequency:.5f} Hz"
        if frequency is not None and frequency >= 0.0
        else "N/A"
    )

    bfield_text = (
        f"{bfield_nt:.3f} nT  ({bfield_nt / 1000.0:.6f} uT)"
        if bfield_nt is not None and bfield_nt >= 0.0
        else "N/A"
    )

    history_lines = ["", "Last 3 captures:"]

    if recent_measurements:
        for item in recent_measurements:
            if item["frequency_hz"] is not None and item["frequency_hz"] >= 0.0:
                history_lines.append(
                    f"#{item['capture_number']}: "
                    f"{item['frequency_hz']:.5f} Hz   "
                    f"{item['bfield_nt']:.3f} nT "
                    f"({item['bfield_nt'] / 1000.0:.6f} uT)"
                )
            else:
                history_lines.append(
                    f"#{item['capture_number']}: frequency / B field N/A"
                )
    else:
        history_lines.append("No completed captures yet")

    return (
        f"Captured: {captured if captured is not None else 'N/A'} samples\n"
        f"Capture time: {capture_time:.3f} ms\n"
        f"Measured sample rate: {sample_rate:.2f} SPS\n"
        f"Measured Vpp: {vpp:.3f} mV\n"
        f"Measured DC offset: {dc_offset:+.6f} mV\n"
        f"Positive zero crossings: {crossings if crossings is not None else 'N/A'}\n"
        f"Calculated frequency: {frequency_text}\n"
        f"Equivalent proton B field: {bfield_text}\n"
        + "\n".join(history_lines)
    )


# ============================================================
# Update the single 10 ms graph
# ============================================================

def update_graph():
    global fig, ax, measurement_text, capture_number

    if not times_ms:
        return

    if fig is None or not plt.fignum_exists(fig.number):
        plt.ion()
        fig, ax = plt.subplots(figsize=(11, 6.5))
        plt.show(block=False)

    ax.clear()

    ax.plot(times_ms, voltages_mv)
    ax.set_title(f"ADS1256 Waveform - Capture {capture_number}")
    ax.set_xlabel("Time (ms)")
    ax.set_ylabel("Voltage (mV)")
    ax.set_xlim(0.0, PLOT_TIME_MS)
    ax.grid(True)

    # Put the requested capture statistics directly inside the
    # display without creating a second graph.
    measurement_text = ax.text(
        1.02,
        0.98,
        build_measurement_text(),
        transform=ax.transAxes,
        va="top",
        ha="left",
        family="monospace"
    )

    # Leave room on the right for the measurement block.
    fig.subplots_adjust(right=0.64)

    fig.canvas.draw_idle()
    fig.canvas.flush_events()
    plt.pause(0.05)


# ============================================================
# Continuously receive captures
# ============================================================

try:
    while True:
        raw_line = ser.readline()

        if not raw_line:
            if fig is not None:
                plt.pause(0.01)
            continue

        line = raw_line.decode(errors="ignore").strip()

        if not line:
            continue

        # ----------------------------------------------------
        # Metadata packet from the Pico
        #
        # DATA_META,
        # captured_samples,
        # plot_samples,
        # capture_time_ms,
        # sample_rate,
        # vpp_mV,
        # dc_offset_mV,
        # zero_crossings,
        # frequency_Hz,
        # bfield_nT
        # ----------------------------------------------------
        if line.startswith("DATA_META,"):
            try:
                parts = line.split(",")

                metadata["captured_samples"] = int(parts[1])
                metadata["plot_samples"] = int(parts[2])
                metadata["capture_time_ms"] = float(parts[3])
                metadata["sample_rate"] = float(parts[4])
                metadata["vpp_mv"] = float(parts[5])
                metadata["dc_offset_mv"] = float(parts[6])
                metadata["zero_crossings"] = int(parts[7])
                metadata["frequency_hz"] = float(parts[8])
                metadata["bfield_nt"] = float(parts[9])

                print(
                    f"Preparing capture {capture_number + 1}: "
                    f"{metadata['captured_samples']} total samples, "
                    f"{metadata['plot_samples']} samples sent for the 10 ms plot."
                )

            except (ValueError, IndexError):
                print(f"Could not parse metadata: {line}")

            continue

        # ----------------------------------------------------
        # Start of 10 ms waveform data
        # ----------------------------------------------------
        if line == "DATA_START":
            times_ms = []
            voltages_mv = []
            collecting = True
            continue

        # ----------------------------------------------------
        # End of waveform data
        # ----------------------------------------------------
        if line == "DATA_END":
            collecting = False
            capture_number += 1

            # Save this capture's frequency and equivalent proton field
            # so the graph always shows the latest three results.
            recent_measurements.append({
                "capture_number": capture_number,
                "frequency_hz": metadata["frequency_hz"],
                "bfield_nt": metadata["bfield_nt"],
            })

            if len(recent_measurements) > 3:
                del recent_measurements[:-3]

            print(f"Received {len(times_ms)} plot samples.")

            if not times_ms:
                print("No waveform samples were received. Waiting for next capture.\n")
                continue

            update_graph()

            print(build_measurement_text())
            print(f"Graph updated for capture {capture_number}.\n")
            continue

        # ----------------------------------------------------
        # Waveform line: time_seconds,voltage_mV
        # ----------------------------------------------------
        if collecting:
            try:
                time_s, voltage_mv = line.split(",")

                times_ms.append(float(time_s) * 1000.0)
                voltages_mv.append(float(voltage_mv))

            except ValueError:
                pass

            continue

        # ----------------------------------------------------
        # Echo the Pico's normal human-readable output to this
        # terminal.  This includes the same Captured / Vpp /
        # frequency results printed by the firmware.
        # ----------------------------------------------------
        print(f"Pico: {line}")


except KeyboardInterrupt:
    print("\nStopping waveform plotter...")

finally:
    ser.close()

    if fig is not None:
        plt.ioff()
        plt.show()
