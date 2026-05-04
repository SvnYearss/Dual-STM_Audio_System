import serial
import sys

# Configuration
PORT = "COM5"           # Change this to your actual COM port
BAUDRATE = 230400
READ_ITERATIONS = 100   # Number of read cycles
READ_CHUNK_SIZE = 500   # Bytes per read
OUTPUT_FILE = "raw_ADC_values.data"

try:
    with serial.Serial(port=PORT, baudrate=BAUDRATE, bytesize=8,
                       parity="N", stopbits=1, timeout=5) as ser:
        print(f"Connected to: {ser.name}")

        # Send 'M' command to STM32 to start sampling
        ser.write(b'M')
        print("Sent 'M' command to start STM32 sampling.")

        with open(OUTPUT_FILE, "wb") as file_1:
            for i in range(READ_ITERATIONS):
                x = ser.read(READ_CHUNK_SIZE)
                if len(x) == 0:
                    print(f"Warning: Read timeout at iteration {i}/{READ_ITERATIONS}")
                    break
                file_1.write(x)

                # Progress indicator
                if (i + 1) % 10 == 0:
                    print(f"  Progress: {i + 1}/{READ_ITERATIONS} "
                          f"({(i + 1) * READ_CHUNK_SIZE} bytes captured)")

        total_bytes = min((i + 1), READ_ITERATIONS) * READ_CHUNK_SIZE
        print(f"Done! Saved {total_bytes} bytes to {OUTPUT_FILE}")

        # Send 'S' command to STM32 to stop sampling
        ser.write(b'S')
        print("Sent 'S' command to stop STM32 sampling.")

except serial.SerialException as e:
    print(f"Serial error: {e}")
    sys.exit(1)
except KeyboardInterrupt:
    print("\nCapture interrupted by user.")
    sys.exit(0)