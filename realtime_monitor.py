import serial
import struct
import sys
import time

PORT = 'COM5'
BAUD = 921600
SAMPLE_BYTES = 2        # 12-bit LE samples, 2 bytes each
CHUNK_SAMPLES = 400     # read 400 samples at a time (~10 FPS at 44.1 kHz)
CHUNK_SIZE = CHUNK_SAMPLES * SAMPLE_BYTES
BAR_WIDTH = 60


def bar_graph(value, max_val=4095):
    """Draw a text bar for a 12-bit ADC value (0-4095)."""
    length = int((value / max_val) * BAR_WIDTH)
    length = max(0, min(BAR_WIDTH, length))
    return '█' * length + '-' * (BAR_WIDTH - length)


try:
    with serial.Serial(PORT, BAUD, timeout=1) as ser:
        print(f"Connected to {PORT}.")

        # Flush any stale data & ensure STM is stopped before restarting
        ser.write(b'S')
        ser.flush()
        time.sleep(0.1)
        ser.reset_input_buffer()

        print("Sending 'M' to start STM32 sampling...")
        ser.write(b'M')
        ser.flush()

        print("Listening to real-time 12-bit ADC values (Press Ctrl+C to stop)...\n")

        while True:
            data = ser.read(CHUNK_SIZE)

            if len(data) >= SAMPLE_BYTES:
                # Trim to even number of bytes
                usable = len(data) - (len(data) % SAMPLE_BYTES)
                # Parse all 16-bit LE values, mask to 12-bit
                samples = struct.unpack(f'<{usable // SAMPLE_BYTES}H', data[:usable])
                samples_12bit = [s & 0x0FFF for s in samples]

                # Use the average of the chunk for a smoother display
                avg = sum(samples_12bit) // len(samples_12bit)
                latest = samples_12bit[-1]

                bar = bar_graph(avg)
                sys.stdout.write(f"\r12-bit ADC  avg: {avg:4d}  last: {latest:4d}  ({len(samples_12bit):4d} smp) |{bar}|")
                sys.stdout.flush()

except KeyboardInterrupt:
    print("\n\nUser interrupted. Stopping...")
    try:
        with serial.Serial(PORT, BAUD, timeout=1) as ser:
            ser.write(b'S')
        print("Sent 'S' to stop STM32. Exited successfully.")
    except Exception:
        pass
except Exception as e:
    print(f"\nError: {e}")
