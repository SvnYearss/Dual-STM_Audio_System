"""
HC-SR04 Distance Sensor Diagnostic — Processing STM32 architecture.
The sensor is now on the Processing STM32, which sends DIST: lines
directly to the PC via USART2 (ST-Link VCP).
"""
import serial
import time

PORT = 'COM5'
BAUD = 230400
TIMEOUT = 2

print(f"=== HC-SR04 Distance Pipeline Diagnostic ===")
print(f"Port: {PORT}, Baud: {BAUD}")
print(f"Architecture: PC <-> Processing STM (HC-SR04) <-> Sampling STM (ADC)\n")

try:
    ser = serial.Serial(PORT, BAUD, timeout=TIMEOUT)
    print("[OK] Serial port opened")

    # Reset state
    ser.reset_input_buffer()
    ser.write(b'S')
    time.sleep(0.5)
    ser.reset_input_buffer()

    # Quick Manual Mode sanity check (tests full pipeline: Sampling -> Processing -> PC)
    print("--- Testing Manual Mode (full pipeline) ---")
    ser.write(b'M')
    time.sleep(1.0)
    n = ser.in_waiting
    if n > 100:
        print(f"[OK] Manual Mode: {n} bytes received (ADC data through Processing STM)")
    else:
        print(f"[WARN] Manual Mode: only {n} bytes — check Sampling STM connection")

    # Stop
    ser.write(b'S')
    time.sleep(0.5)
    ser.reset_input_buffer()

    # Enter Distance Test Mode
    print("\n--- Entering Distance Test Mode ('T') ---")
    print("Expected: DIST:XX.XX lines from Processing STM")
    print("Move your hand near the HC-SR04 sensor...\n")
    ser.write(b'T')
    time.sleep(0.2)

    # Listen for 15 seconds
    start = time.time()
    buf = b''
    dist_count = 0
    while time.time() - start < 15:
        waiting = ser.in_waiting
        if waiting > 0:
            chunk = ser.read(waiting)
            buf += chunk
            # Process complete lines
            while b'\n' in buf:
                line, buf = buf.split(b'\n', 1)
                line = line.strip()
                if line:
                    try:
                        text = line.decode('utf-8', errors='replace')
                        if text.startswith('DIST:'):
                            dist_count += 1
                            print(f"  [{dist_count:3d}] {text}")
                        else:
                            print(f"  [info] {text}")
                    except:
                        print(f"  [raw] {line.hex()}")
        time.sleep(0.02)

    # Print remaining buffer
    if buf.strip():
        print(f"  [partial] {buf.hex()} = {buf.decode('utf-8', errors='replace')}")

    # Stop
    ser.write(b'S')
    ser.close()

    print(f"\n--- Summary ---")
    print(f"Total DIST readings: {dist_count}")
    if dist_count > 0:
        print("[OK] Distance sensor pipeline is WORKING!")
    else:
        print("[FAIL] No DIST readings received.")
        print("  Check: HC-SR04 wired to Processing STM (TRIG=PB5, ECHO=PA5)?")
        print("  Check: Processing STM firmware flashed correctly?")

    print("\n[DONE] Diagnostic complete.")

except serial.SerialException as e:
    print(f"[ERROR] Serial: {e}")
except KeyboardInterrupt:
    print("\n[INTERRUPTED]")
    try:
        ser.write(b'S')
        ser.close()
    except:
        pass
