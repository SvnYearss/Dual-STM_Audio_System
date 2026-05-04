import serial
import subprocess
import sys
import time
import os

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(SCRIPT_DIR, "raw_ADC_values.data")
C_FILE = os.path.join(SCRIPT_DIR, "file_conversion.c")
EXE_FILE = os.path.join(SCRIPT_DIR, "file_conversion.exe")

PORT = "COM5"
BAUDRATE = 230400
SAMPLE_RATE = 8000
RECORD_SECONDS = 5   # MVP requirement: hard-coded length
TOTAL_BYTES = SAMPLE_RATE * RECORD_SECONDS

print(f"--- MVP Audio Acquisition ---")
print(f"Target: {RECORD_SECONDS} seconds @ {SAMPLE_RATE} Hz ({TOTAL_BYTES} bytes)")

try:
    with serial.Serial(port=PORT, baudrate=BAUDRATE, bytesize=8, parity="N", stopbits=1, timeout=5) as ser:
        print(f"Connected to {ser.name}")
        
        # Send start command
        ser.write(b'M')
        print("Sent 'M' to start STM32 sampling.")
        
        captured = 0
        with open(DATA_FILE, "wb") as f:
            while captured < TOTAL_BYTES:
                chunk = ser.read(min(500, TOTAL_BYTES - captured))
                if len(chunk) == 0:
                    print(f"\nTimeout! Captured {captured}/{TOTAL_BYTES}")
                    break
                f.write(chunk)
                captured += len(chunk)
                
                # Progress
                print(f"\rProgress: {captured}/{TOTAL_BYTES} bytes", end="")
        
        print() # Newline
        # Send stop command
        ser.write(b'S')
        print("Sent 'S' to stop STM32 sampling.")

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
run_res = subprocess.run([EXE_FILE], capture_output=True, text=True, cwd=SCRIPT_DIR)
print(run_res.stdout)

if run_res.returncode == 0:
    print("MVP pipeline complete! You can now play output.wav")
else:
    print(f"Conversion failed: {run_res.stderr}")