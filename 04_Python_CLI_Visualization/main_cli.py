"""
ECE2071 Project — Dual-STM Audio System
PC-side CLI & Visualization Module

This script provides:
  1. Interactive CLI menu for recording mode selection
  2. Serial data reception from the Processing STM via pyserial
  3. Subprocess call to the compiled C converter (processing.c → WAV)
  4. Waveform plotting via matplotlib
"""

import serial
import serial.tools.list_ports
import subprocess
import struct
import sys
import os
import time
import argparse

# ---------------------------------------------------------------------------
# Configuration Constants
# ---------------------------------------------------------------------------
DEFAULT_BAUDRATE = 230400
DEFAULT_SAMPLE_RATE = 22050   # Must match processing.c and STM32 timer config
RAW_OUTPUT_FILE = "raw_ADC_values.data"
WAV_OUTPUT_FILE = "output_audio.wav"
CONVERTER_EXE = "file_conversion"   # Name of the compiled C executable (no .exe)

# STM32 command bytes (must match firmware HAL_UART_RxCpltCallback)
CMD_MANUAL_START = b'M'
CMD_STOP = b'S'
CMD_DISTANCE_MODE = b'D'


# ---------------------------------------------------------------------------
# Utility: Auto-detect or select COM port
# ---------------------------------------------------------------------------
def select_com_port():
    """List available COM ports and let the user choose one."""
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("  Error: No COM ports detected. Is the STM32 plugged in?")
        return None

    print("\n  Available COM Ports:")
    for i, port in enumerate(ports):
        print(f"    [{i + 1}] {port.device} — {port.description}")

    if len(ports) == 1:
        print(f"  Auto-selected: {ports[0].device}")
        return ports[0].device

    while True:
        try:
            choice = input(f"  Select port [1-{len(ports)}]: ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(ports):
                return ports[idx].device
        except (ValueError, IndexError):
            pass
        print("  Invalid selection, try again.")


# ---------------------------------------------------------------------------
# Core: Serial Data Capture
# ---------------------------------------------------------------------------
def capture_serial_data(ser, duration_seconds):
    """
    Capture raw ADC data from serial for the specified duration.
    Each sample is 1 byte (uint8_t).
    Returns the number of bytes captured.
    """
    total_bytes_expected = DEFAULT_SAMPLE_RATE * 1 * duration_seconds
    chunk_size = 500
    total_captured = 0

    print(f"\n  Recording for {duration_seconds} seconds...")
    print(f"  Expected: ~{total_bytes_expected} bytes "
          f"({DEFAULT_SAMPLE_RATE * duration_seconds} samples)")

    with open(RAW_OUTPUT_FILE, "wb") as f:
        start_time = time.time()
        while total_captured < total_bytes_expected:
            remaining = total_bytes_expected - total_captured
            to_read = min(chunk_size, remaining)
            data = ser.read(to_read)

            if len(data) == 0:
                elapsed = time.time() - start_time
                print(f"\n  Warning: Serial timeout after {elapsed:.1f}s "
                      f"({total_captured} bytes captured)")
                break

            f.write(data)
            total_captured += len(data)

            # Progress bar
            progress = total_captured / total_bytes_expected
            bar_len = 30
            filled = int(bar_len * progress)
            bar = '█' * filled + '░' * (bar_len - filled)
            print(f"\r  [{bar}] {progress * 100:.0f}%  "
                  f"({total_captured}/{total_bytes_expected} bytes)", end="")

    print()  # newline after progress bar
    return total_captured


# ---------------------------------------------------------------------------
# Core: WAV Conversion (subprocess call to C program)
# ---------------------------------------------------------------------------
def convert_to_wav():
    """Call the compiled C converter to produce a .wav file."""
    # Try common executable names/paths
    exe_candidates = [
        CONVERTER_EXE,
        f"./{CONVERTER_EXE}",
        f"./{CONVERTER_EXE}.exe",
        f"../{CONVERTER_EXE}",
        f"../{CONVERTER_EXE}.exe",
    ]

    exe_path = None
    for candidate in exe_candidates:
        if os.path.isfile(candidate):
            exe_path = candidate
            break

    if exe_path is None:
        print(f"\n  Error: Cannot find '{CONVERTER_EXE}' executable.")
        print(f"  Please compile processing.c first:")
        print(f"    gcc processing.c -o {CONVERTER_EXE}")
        return False

    print(f"\n  Running converter: {exe_path}")
    try:
        result = subprocess.run(
            [exe_path],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            print(f"  {result.stdout.strip()}")
            return True
        else:
            print(f"  Converter error (exit code {result.returncode}):")
            print(f"  {result.stderr.strip()}")
            return False
    except subprocess.TimeoutExpired:
        print("  Error: Converter timed out.")
        return False
    except Exception as e:
        print(f"  Error running converter: {e}")
        return False


# ---------------------------------------------------------------------------
# Core: Waveform Plotting
# ---------------------------------------------------------------------------
def plot_waveform(filename=RAW_OUTPUT_FILE):
    """
    Read the raw ADC data file and generate an Amplitude vs Time waveform plot.
    Saves the plot as a .png file.
    """
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("\n  Error: matplotlib and numpy are required for plotting.")
        print("  Install with: pip install matplotlib numpy")
        return

    if not os.path.isfile(filename):
        print(f"\n  Error: '{filename}' not found. Record data first.")
        return

    # Read raw 8-bit unsigned samples
    with open(filename, "rb") as f:
        raw_bytes = f.read()

    num_samples = len(raw_bytes)
    if num_samples == 0:
        print("\n  Error: Data file is empty.")
        return

    # Unpack as uint8
    samples = struct.unpack(f'{num_samples}B', raw_bytes)
    samples = np.array(samples, dtype=np.float64)

    # Scale to signed: center at 128, scale to ±1.0
    samples_signed = (samples - 128.0) / 128.0

    # Time axis
    duration = num_samples / DEFAULT_SAMPLE_RATE
    time_axis = np.linspace(0, duration, num_samples, endpoint=False)

    # Plot
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
    fig.suptitle("ECE2071 — Audio Waveform Analysis",
                 fontsize=14, fontweight='bold')

    # Top: full waveform
    ax1.plot(time_axis, samples_signed, linewidth=0.3, color='#2196F3')
    ax1.set_ylabel("Normalized Amplitude")
    ax1.set_title("Full Waveform (Amplitude vs. Time)")
    ax1.grid(True, alpha=0.3)
    ax1.set_ylim(-1.1, 1.1)

    # Bottom: zoomed first 50ms
    zoom_samples = min(int(DEFAULT_SAMPLE_RATE * 0.05), num_samples)
    ax2.plot(time_axis[:zoom_samples], samples_signed[:zoom_samples],
             linewidth=0.5, color='#FF5722')
    ax2.set_xlabel("Time (seconds)")
    ax2.set_ylabel("Normalized Amplitude")
    ax2.set_title("Zoomed View (First 50ms)")
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()

    # Save
    png_filename = filename.replace('.data', '_waveform.png')
    if png_filename == filename:
        png_filename = "waveform_plot.png"
    plt.savefig(png_filename, dpi=150)
    print(f"\n  Waveform plot saved as: {png_filename}")

    # Also display if possible
    try:
        plt.show()
    except Exception:
        pass  # Headless environment


# ---------------------------------------------------------------------------
# CLI Menu
# ---------------------------------------------------------------------------
def print_menu():
    """Print the main CLI menu."""
    print("\n" + "=" * 50)
    print("  ECE2071 Dual-STM Audio System — Main Menu")
    print("=" * 50)
    print("  [1] Manual Recording Mode")
    print("  [2] Distance Trigger Mode")
    print("  [3] Convert Raw Data to WAV")
    print("  [4] Plot Waveform from Data")
    print("  [5] Full Pipeline (Record → Convert → Plot)")
    print("  [q] Quit")
    print("-" * 50)


def manual_recording_mode(ser):
    """Handle manual recording: user specifies duration."""
    while True:
        try:
            duration_input = input("  Enter recording duration (seconds): ").strip()
            duration = float(duration_input)
            if duration <= 0:
                raise ValueError
            break
        except ValueError:
            print("  Please enter a positive number.")

    # Send Manual Start command to STM32
    ser.write(CMD_MANUAL_START)
    print(f"  Sent 'M' command to STM32 — Manual mode activated.")

    # Small delay for the STM32 to start sampling
    time.sleep(0.1)

    # Capture data
    total_captured = capture_serial_data(ser, int(duration))

    # Send Stop command
    ser.write(CMD_STOP)
    print(f"  Sent 'S' command to STM32 — Sampling stopped.")

    # Flush any remaining bytes in the serial buffer
    ser.reset_input_buffer()

    print(f"  Captured {total_captured} bytes → {RAW_OUTPUT_FILE}")
    return total_captured > 0


def distance_trigger_mode(ser):
    """Handle distance trigger mode: STM32 controls when recording starts/stops."""
    print("\n  Distance Trigger Mode")
    print("  The STM32 will start recording when an object is within 10cm.")
    print("  Press Ctrl+C to stop waiting.\n")

    # Send Distance mode command to STM32
    ser.write(CMD_DISTANCE_MODE)
    print(f"  Sent 'D' command to STM32 — Distance trigger armed.")

    # In this mode, we continuously capture whatever the STM sends.
    # The STM32 firmware handles the trigger logic internally.
    try:
        total_captured = 0
        with open(RAW_OUTPUT_FILE, "wb") as f:
            print("  Waiting for proximity trigger...")
            while True:
                data = ser.read(500)
                if len(data) > 0:
                    f.write(data)
                    total_captured += len(data)
                    print(f"\r  Capturing... {total_captured} bytes", end="")

    except KeyboardInterrupt:
        # Send Stop command
        ser.write(CMD_STOP)
        print(f"\n\n  Stopped. Sent 'S' command to STM32.")
        ser.reset_input_buffer()
        print(f"  Captured {total_captured} bytes → {RAW_OUTPUT_FILE}")
        return total_captured > 0


def main():
    """Main entry point for the CLI application."""
    print("\n" + "=" * 50)
    print("  ECE2071 — Dual-STM Audio System CLI")
    print("  Initializing...")
    print("=" * 50)

    # Select COM port
    com_port = select_com_port()
    if com_port is None:
        sys.exit(1)

    # Open serial connection
    try:
        ser = serial.Serial(
            port=com_port,
            baudrate=DEFAULT_BAUDRATE,
            bytesize=8,
            parity='N',
            stopbits=1,
            timeout=5
        )
        print(f"  Connected to {ser.name} at {DEFAULT_BAUDRATE} baud.")
    except serial.SerialException as e:
        print(f"  Error opening serial port: {e}")
        sys.exit(1)

    try:
        while True:
            print_menu()
            choice = input("  Select option: ").strip().lower()

            if choice == '1':
                manual_recording_mode(ser)

            elif choice == '2':
                distance_trigger_mode(ser)

            elif choice == '3':
                convert_to_wav()

            elif choice == '4':
                plot_waveform()

            elif choice == '5':
                print("\n  === Full Pipeline ===")
                success = manual_recording_mode(ser)
                if success:
                    if convert_to_wav():
                        plot_waveform()

            elif choice == 'q':
                break

            else:
                print("  Invalid option. Please try again.")

    except KeyboardInterrupt:
        print("\n\n  Interrupted by user.")

    finally:
        # Ensure STM32 stops and serial port is released
        try:
            ser.write(CMD_STOP)
        except Exception:
            pass
        ser.close()
        print("  Serial port closed. Goodbye!")


if __name__ == "__main__":
    main()