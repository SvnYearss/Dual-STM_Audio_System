import os
import subprocess
import sys

import matplotlib.pyplot as plt
import numpy as np
import serial


# --- Configuration Parameters ---
PORT = "COM5"
BAUD = 230400
FS = 8000  # Sampling rate from the STM32 configuration
TEAM_ID = "T12"
BIT_DEPTH = 8
DISTANCE_TRIGGER_DEFAULT_CM = 10
DISTANCE_TRIGGER_MIN_CM = 2
DISTANCE_TRIGGER_MAX_CM = 200


def output_filename(mode_name, extension):
    """Builds Task 2 compliant output names with team ID and sample rate."""
    safe_mode = "".join(c if c.isalnum() else "_" for c in mode_name).strip("_")
    while "__" in safe_mode:
        safe_mode = safe_mode.replace("__", "_")
    if not safe_mode:
        safe_mode = "Recording"
    return f"{TEAM_ID}_{FS}Hz_{BIT_DEPTH}bit_{safe_mode}.{extension}"


def compile_and_run_c_converter(raw_data, mode_name):
    """Saves binary data and calls the C converter to create a WAV file."""
    with open("raw_ADC_values.data", "wb") as f:
        f.write(raw_data)

    print("  Compiling C converter...")
    subprocess.run(
        ["gcc", "03_PC_File_Conversion/file_conversion.c", "-o", "converter"],
        check=True,
    )

    print("  Running C converter...")
    exe_name = "converter.exe" if sys.platform == "win32" else "./converter"
    subprocess.run([exe_name], check=True)

    wav_name = output_filename(mode_name, "wav")
    if os.path.exists("output.wav"):
        os.replace("output.wav", wav_name)
        print(f"  -> Generated {wav_name}")
    else:
        print("  -> C converter finished, but output.wav was not found.")


def generate_csv(data_array, mode_name):
    """Generates a CSV file with the first row indicating the sample rate."""
    csv_name = output_filename(mode_name, "csv")
    with open(csv_name, "w") as f:
        f.write(f"Sample Rate:,{FS}\n")
        f.write("Amplitude\n")
        np.savetxt(f, data_array, delimiter=",", fmt="%d")
    print(f"  -> Generated {csv_name}")


def generate_png(data_array, mode_name):
    """Generates a plot of amplitude vs time with proper labels."""
    png_name = output_filename(mode_name, "png")
    time_axis = np.arange(len(data_array)) / FS

    plt.figure(figsize=(10, 4))
    plt.plot(time_axis, data_array, color="blue", linewidth=0.5)
    plt.title(f"Audio Waveform ({mode_name})")
    plt.xlabel("Time (seconds)")
    plt.ylabel("Amplitude (8-bit PCM)")
    plt.grid(True)
    plt.savefig(png_name)
    plt.close()
    print(f"  -> Generated {png_name}")


def process_outputs(raw_data, options, mode_name):
    """Processes the raw serial bytes into the formats requested by the user."""
    print("\nProcessing outputs...")

    if "WAV" in options:
        compile_and_run_c_converter(raw_data, mode_name)

    if "CSV" in options or "PNG" in options:
        data_array = np.frombuffer(raw_data, dtype=np.uint8)

        if "CSV" in options:
            generate_csv(data_array, mode_name)

        if "PNG" in options:
            generate_png(data_array, mode_name)

    print("Outputs generated successfully!")


def get_output_preferences():
    """Prompts the user to select which outputs they want."""
    print("\nSelect Output Formats (y/n for each):")
    want_wav = input("  1. Generate .WAV file? (y/n): ").strip().lower() == "y"
    want_png = input("  2. Generate .PNG waveform plot? (y/n): ").strip().lower() == "y"
    want_csv = input("  3. Generate .CSV data file? (y/n): ").strip().lower() == "y"

    options = []
    if want_wav:
        options.append("WAV")
    if want_png:
        options.append("PNG")
    if want_csv:
        options.append("CSV")
    return options


def get_distance_threshold():
    """Gets a configurable ultrasonic trigger distance from the user."""
    prompt = (
        f"Enter trigger distance in cm "
        f"({DISTANCE_TRIGGER_MIN_CM}-{DISTANCE_TRIGGER_MAX_CM}, "
        f"default {DISTANCE_TRIGGER_DEFAULT_CM}): "
    )
    while True:
        value = input(prompt).strip()
        if value == "":
            return DISTANCE_TRIGGER_DEFAULT_CM

        try:
            distance_cm = int(value)
        except ValueError:
            print("Invalid distance. Please enter a whole number.")
            continue

        if DISTANCE_TRIGGER_MIN_CM <= distance_cm <= DISTANCE_TRIGGER_MAX_CM:
            return distance_cm

        print(
            f"Distance must be between "
            f"{DISTANCE_TRIGGER_MIN_CM} and {DISTANCE_TRIGGER_MAX_CM} cm."
        )


def configure_distance_threshold(ser, distance_cm):
    """Sends R + one-byte distance to the Processing STM32."""
    ser.write(b"R")
    ser.write(bytes([distance_cm]))

    ack = ser.readline().decode(errors="ignore").strip()
    expected = f"ACK:R:{distance_cm}"
    if ack == expected:
        print(f"Distance trigger threshold set to {distance_cm}cm.")
    else:
        print(f"Warning: expected {expected}, received {ack or 'no ACK'}.")


def manual_recording_mode():
    print("\n--- Manual Recording Mode ---")
    try:
        duration_str = input("Enter recording duration in seconds: ")
        duration = float(duration_str)
    except ValueError:
        print("Invalid duration. Returning to menu.")
        return

    options = get_output_preferences()
    bytes_to_read = int(FS * duration)

    try:
        with serial.Serial(PORT, BAUD, timeout=10) as ser:
            input("\nPress Enter to START recording...")
            ser.write(b"M")
            print(f"Recording for {duration} seconds...")
            raw_data = ser.read(bytes_to_read)
            ser.write(b"S")
            print("Recording complete!")

        if options:
            process_outputs(raw_data, options, "Manual Mode")
    except Exception as e:
        print(f"Serial Error: {e}")


def distance_trigger_mode():
    print("\n--- Distance Trigger Mode ---")
    options = get_output_preferences()
    distance_cm = get_distance_threshold()

    print(f"\n[Distance Mode] The system will auto-record when an object is within {distance_cm}cm.")
    print("Press Ctrl+C to exit mode.\n")

    ser = None
    try:
        import time

        ser = serial.Serial(PORT, BAUD, timeout=1)
        ser.reset_input_buffer()

        # Ensure clean state before entering distance mode.
        ser.write(b"S")
        time.sleep(0.3)
        ser.reset_input_buffer()

        configure_distance_threshold(ser, distance_cm)
        ser.reset_input_buffer()
        ser.write(b"D")

        trigger_num = 0
        while True:
            print("[Distance Mode] Waiting for proximity trigger...")

            # Wait for first byte, which means sensor-triggered ADC data is flowing.
            trigger_byte = ser.read(1)
            if trigger_byte:
                trigger_num += 1
                print(f"\n[!] Trigger #{trigger_num} detected! Recording started...")
                raw_data = trigger_byte

                # Keep reading until timeout, which means the STM stopped sending data.
                while True:
                    chunk = ser.read(8000)
                    if chunk:
                        raw_data += chunk
                    else:
                        print("[!] Object left. Recording stopped.")
                        break

                print(f"Captured {len(raw_data)} bytes of audio.")
                if options and len(raw_data) > 0:
                    process_outputs(raw_data, options, f"Distance Trigger {distance_cm}cm #{trigger_num}")

                print()
    except KeyboardInterrupt:
        print("\nExiting Distance Trigger Mode.")
    except Exception as e:
        print(f"Serial Error: {e}")
    finally:
        if ser and ser.is_open:
            try:
                ser.write(b"S")
            except Exception:
                pass
            ser.close()


# --- CLI Main Program Architecture ---
if __name__ == "__main__":
    print("Welcome to the Dual-Board Audio Processing System CLI!")

    while True:
        print("\n" + "=" * 30)
        print("--- Main Menu ---")
        print("1: Manual Recording Mode")
        print("2: Distance Trigger Mode")
        print("q: Quit Program")

        choice = input("Please enter your choice: ").strip().lower()

        if choice == "1":
            manual_recording_mode()
        elif choice == "2":
            distance_trigger_mode()
        elif choice == "q":
            print("Exiting program. Goodbye!")
            # Send S to ensure system is cleanly stopped.
            try:
                with serial.Serial(PORT, BAUD, timeout=1) as ser:
                    ser.write(b"S")
            except Exception:
                pass
            break
        else:
            print("Invalid input, please try again.")
