import serial
import subprocess
import sys
import time
import os

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(SCRIPT_DIR, "raw_ADC_values.data")
TXT_FILE = os.path.join(SCRIPT_DIR, "raw_ADC_values.txt")
C_FILE = os.path.join(SCRIPT_DIR, "file_conversion.c")
EXE_FILE = os.path.join(SCRIPT_DIR, "file_conversion.exe")

PORT = "COM5"
BAUDRATE = 921600
NOMINAL_SAMPLE_RATE = 22038
RECORD_SECONDS = 5   # MVP requirement: hard-coded length

print(f"--- MVP Audio Acquisition ---")
print(f"Target: {RECORD_SECONDS} seconds, nominal {NOMINAL_SAMPLE_RATE} Hz")

try:
    with serial.Serial(port=PORT, baudrate=BAUDRATE, bytesize=8, parity="N", stopbits=1, timeout=0.02) as ser:
        print(f"Connected to {ser.name}")
        ser.reset_input_buffer()
        
        # Send start command
        ser.write(b'M')
        print("Sent 'M' to start STM32 sampling.")
        
        captured = 0
        start_time = time.monotonic()
        deadline = start_time + RECORD_SECONDS
        with open(DATA_FILE, "wb") as data_file, open(TXT_FILE, "w") as txt_file:
            txt_file.write(f"Sample Rate: measured after capture, nominal {NOMINAL_SAMPLE_RATE} Hz\n")
            txt_file.write("Amplitude\n")
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                read_size = max(1, min(1024, int(NOMINAL_SAMPLE_RATE * min(0.05, remaining))))
                chunk = ser.read(read_size)
                if len(chunk) == 0:
                    continue
                data_file.write(chunk)
                txt_file.write("".join(f"{sample}\n" for sample in chunk))
                captured += len(chunk)
                
                # Progress
                elapsed = max(0.001, time.monotonic() - start_time)
                print(f"\rProgress: {elapsed:4.1f}/{RECORD_SECONDS}s, {captured} bytes", end="")
        
        elapsed = max(0.001, time.monotonic() - start_time)
        measured_rate = max(1, int(round(captured / elapsed)))
        print() # Newline
        # Send stop command
        ser.write(b'S')
        print("Sent 'S' to stop STM32 sampling.")
        print(f"Measured sample rate: {measured_rate} Hz")
        print(f"Saved raw samples to {DATA_FILE}")
        print(f"Saved text samples to {TXT_FILE}")

except Exception as e:
    print(f"Serial error: {e}")
    sys.exit(1)

print("\nCompiling C converter...")
compile_res = subprocess.run(["gcc", C_FILE, "-o", EXE_FILE], capture_output=True, text=True, cwd=SCRIPT_DIR)

if compile_res.returncode != 0:
    print("Compilation failed:")
    print(compile_res.stderr)
    sys.exit(1)

print("Running C converter...")
run_res = subprocess.run([EXE_FILE, str(measured_rate)], capture_output=True, text=True, cwd=SCRIPT_DIR)
print(run_res.stdout)

if run_res.returncode == 0:
    print("MVP pipeline complete! You can now play output.wav")
else:
    print(f"Conversion failed: {run_res.stderr}")
