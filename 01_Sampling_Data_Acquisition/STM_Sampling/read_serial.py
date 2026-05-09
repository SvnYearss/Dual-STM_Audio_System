import os
import shutil
import subprocess
import sys
import time

import serial


PORT = "COM5"
BAUD_RATE = 921600
RECORD_SECONDS = 5.0
NOMINAL_SAMPLE_RATE = 44100
SAMPLE_WIDTH_BYTES = 2


def read_recording():
    raw = bytearray()

    with serial.Serial(
        port=PORT,
        baudrate=BAUD_RATE,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=0.1,
    ) as ser:
        print(f"Connected to {ser.name} at {BAUD_RATE} baud.")
        ser.reset_input_buffer()
        ser.write(b"M")
        ser.flush()

        start_time = time.perf_counter()
        try:
            while (time.perf_counter() - start_time) < RECORD_SECONDS:
                chunk = ser.read(4096)
                if chunk:
                    raw.extend(chunk)
        finally:
            ser.write(b"S")
            ser.flush()

    elapsed = time.perf_counter() - start_time
    usable_len = len(raw) - (len(raw) % SAMPLE_WIDTH_BYTES)
    if usable_len != len(raw):
        raw = raw[:usable_len]

    sample_count = len(raw) // SAMPLE_WIDTH_BYTES
    measured_rate = round(sample_count / elapsed) if elapsed > 0 else NOMINAL_SAMPLE_RATE
    return bytes(raw), sample_count, measured_rate


def build_and_run_converter(sample_rate):
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    converter_src = os.path.join(repo_root, "03_PC_File_Conversion", "file_conversion.c")
    exe_name = "converter.exe" if os.name == "nt" else "converter"
    exe_path = os.path.join(os.getcwd(), exe_name)

    if shutil.which("gcc") is None:
        print("gcc not found; skipped WAV conversion.")
        return

    subprocess.run(["gcc", converter_src, "-o", exe_path], check=True)
    converter_cmd = [exe_path if os.name == "nt" else f"./{exe_name}", str(sample_rate)]
    subprocess.run(converter_cmd, check=True)


def main():
    raw, sample_count, measured_rate = read_recording()
    with open("raw_ADC_values.data", "wb") as data_file:
        data_file.write(raw)
    with open("recording.bin", "wb") as converter_input:
        converter_input.write(raw)

    print(f"Captured {len(raw)} bytes ({sample_count} 12-bit samples).")
    print(f"Measured sample rate: {measured_rate} Hz")
    build_and_run_converter(measured_rate)


if __name__ == "__main__":
    try:
        main()
    except serial.SerialException as exc:
        print(f"Serial error: {exc}")
        sys.exit(1)
    except subprocess.CalledProcessError as exc:
        print(f"Converter failed: {exc}")
        sys.exit(1)
