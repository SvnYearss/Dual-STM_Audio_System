import serial
import sys
import time

PORT = 'COM5'
BAUD = 921600

def map_value(value, min_val=0, max_val=255, bar_width=60):
    """Maps a value from 0-255 to a bar width."""
    return int((value / max_val) * bar_width)

try:
    with serial.Serial(PORT, BAUD, timeout=1) as ser:
        print(f"Connected to {PORT}.")
        print("Sending 'M' to start STM32 sampling...")
        ser.write(b'M')
        
        print("Listening to real-time ADC values (Press Ctrl+C to stop)...\n")
        
        while True:
            # Read a chunk of data (800 bytes = 0.1 seconds at 8kHz)
            # This prevents terminal flooding and gives a smooth 10 FPS visual update
            data = ser.read(800)
            
            if data:
                # Pick the first byte of the chunk to visualize
                val = data[0]
                # Multiply by 16 to reconstruct the original 12-bit ADC value (approx 0 - 4095)
                val_12bit = val * 16
                
                # Draw a text-based bar graph
                bar_length = map_value(val)
                bar = '█' * bar_length + '-' * (60 - bar_length)
                
                # Print dynamically on the same line
                sys.stdout.write(f"\r12-bit ADC: {val_12bit:4d} (8-bit: {val:3d}) |{bar}|")
                sys.stdout.flush()

except KeyboardInterrupt:
    print("\n\nUser interrupted. Stopping...")
    # Open a brief new connection to send the stop signal, just in case
    try:
        with serial.Serial(PORT, BAUD, timeout=1) as ser:
            ser.write(b'S')
        print("Sent 'S' to stop STM32. Exited successfully.")
    except Exception:
        pass
except Exception as e:
    print(f"\nError: {e}")
