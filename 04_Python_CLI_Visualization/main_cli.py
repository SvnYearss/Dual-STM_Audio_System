import serial
import subprocess
import numpy as np
import matplotlib.pyplot as plt
import sys
import os
import time

# --- Configuration Parameters ---
PORT = 'COM5'
BAUD = 921600
NOMINAL_FS = 22038  # Processing STM output rate after 44.077 ksps -> 2:1 downsample
TEAM_ID = 'T12'

def output_filename(mode_name, extension, sample_rate):
    safe_mode = ''.join(c if c.isalnum() else '_' for c in mode_name).strip('_')
    return f"{TEAM_ID}_{sample_rate}Hz_{safe_mode}.{extension}"

def measured_sample_rate(byte_count, elapsed_seconds):
    if elapsed_seconds <= 0 or byte_count <= 0:
        return NOMINAL_FS
    return max(1, int(round(byte_count / elapsed_seconds)))

def compile_and_run_c_converter(raw_data, mode_name, sample_rate):
    """Saves binary data and calls the C converter to create a WAV file."""
    with open("raw_ADC_values.data", "wb") as f:
        f.write(raw_data)
        
    print("  Compiling C converter...")
    subprocess.run(["gcc", "01_Sampling_Data_Acquisition/STM_Sampling/file_conversion.c", "-o", "converter"])
    print("  Running C converter...")
    # On Windows, the executable might be .exe
    exe_name = "converter.exe" if sys.platform == "win32" else "./converter"
    subprocess.run([exe_name, str(sample_rate)])
    wav_name = output_filename(mode_name, "wav", sample_rate)
    if os.path.exists("output.wav"):
        os.replace("output.wav", wav_name)
    print(f"  -> Generated {wav_name}")

def generate_csv(data_array, mode_name, sample_rate):
    """Generates a CSV file with the first row indicating the sample rate."""
    csv_name = output_filename(mode_name, "csv", sample_rate)
    # The requirement specifically asks for the first row to indicate the sample rate
    with open(csv_name, "w") as f:
        f.write(f"Sample Rate:,{sample_rate}\n")
        f.write("Amplitude\n")
        np.savetxt(f, data_array, delimiter=",", fmt='%d')
    print(f"  -> Generated {csv_name}")

def generate_png(data_array, mode_name, sample_rate):
    """Generates a plot of amplitude vs time with proper labels."""
    png_name = output_filename(mode_name, "png", sample_rate)
    time_axis = np.arange(len(data_array)) / sample_rate
    
    plt.figure(figsize=(10, 4))
    plt.plot(time_axis, data_array, color='blue', linewidth=0.5)
    plt.title(f"Audio Waveform ({mode_name})")
    plt.xlabel("Time (seconds)")
    plt.ylabel("Amplitude (8-bit PCM)")
    plt.grid(True)
    plt.savefig(png_name)
    plt.close()
    print(f"  -> Generated {png_name}")

def process_outputs(raw_data, options, mode_name, sample_rate):
    """Processes the raw serial bytes into the formats requested by the user."""
    print("\nProcessing outputs...")
    print(f"Measured sample rate: {sample_rate} Hz")
    
    if 'WAV' in options:
        compile_and_run_c_converter(raw_data, mode_name, sample_rate)
        
    if 'CSV' in options or 'PNG' in options:
        data_array = np.frombuffer(raw_data, dtype=np.uint8)
        
        if 'CSV' in options:
            generate_csv(data_array, mode_name, sample_rate)
            
        if 'PNG' in options:
            generate_png(data_array, mode_name, sample_rate)
    
    print("Outputs generated successfully!")

def get_output_preferences():
    """Prompts the user to select which outputs they want."""
    print("\nSelect Output Formats (y/n for each):")
    want_wav = input("  1. Generate .WAV file? (y/n): ").strip().lower() == 'y'
    want_png = input("  2. Generate .PNG waveform plot? (y/n): ").strip().lower() == 'y'
    want_csv = input("  3. Generate .CSV data file? (y/n): ").strip().lower() == 'y'
    
    options = []
    if want_wav: options.append('WAV')
    if want_png: options.append('PNG')
    if want_csv: options.append('CSV')
    return options

def record_for_duration(ser, duration):
    """Record by elapsed time, then use the actual byte rate for playback."""
    chunks = []
    ser.reset_input_buffer()
    ser.write(b'M')

    start_time = time.monotonic()
    deadline = start_time + duration

    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        read_size = max(1, min(4096, int(NOMINAL_FS * min(0.05, remaining))))
        chunk = ser.read(read_size)
        if chunk:
            chunks.append(chunk)

    elapsed = time.monotonic() - start_time
    ser.write(b'S')

    raw_data = b''.join(chunks)
    return raw_data, measured_sample_rate(len(raw_data), elapsed), elapsed

def manual_recording_mode():
    print("\n--- Manual Recording Mode ---")
    try:
        duration_str = input("Enter recording duration in seconds: ")
        duration = float(duration_str)
    except ValueError:
        print("Invalid duration. Returning to menu.")
        return
        
    options = get_output_preferences()
    
    try:
        with serial.Serial(PORT, BAUD, timeout=0.02) as ser:
            input("\nPress Enter to START recording...")
            print(f"Recording for {duration} seconds...")
            raw_data, sample_rate, elapsed = record_for_duration(ser, duration)
            print(f"Recording complete! Captured {len(raw_data)} bytes in {elapsed:.2f}s.")
            
        if options:
            process_outputs(raw_data, options, "Manual Mode", sample_rate)
    except Exception as e:
        print(f"Serial Error: {e}")

def distance_trigger_mode():
    print("\n--- Distance Trigger Mode ---")
    options = get_output_preferences()
    try:
        threshold_raw = input("Trigger distance in cm [default 10]: ").strip()
        threshold_cm = int(threshold_raw) if threshold_raw else 10
        threshold_cm = max(1, min(255, threshold_cm))
    except ValueError:
        threshold_cm = 10
    
    print(f"\n[Distance Mode] The system will auto-record when an object is within {threshold_cm}cm.")
    print("Press Ctrl+C to exit mode.\n")
    
    ser = None
    try:
        import time
        ser = serial.Serial(PORT, BAUD, timeout=1)
        ser.reset_input_buffer()
        # Ensure clean state before entering distance mode
        ser.write(b'S')
        time.sleep(0.3)
        ser.reset_input_buffer()
        ser.write(bytes([ord('C'), threshold_cm]))
        time.sleep(0.1)
        ser.write(b'D')  # Put Processing STM into Distance Trigger mode
        
        trigger_num = 0
        
        while True:
            print("[Distance Mode] Waiting for proximity trigger...")
            
            # Wait for first byte (= sensor triggered, ADC data flowing)
            trigger_byte = ser.read(1)
            
            if trigger_byte:
                trigger_num += 1
                print(f"\n[!] Trigger #{trigger_num} detected! Recording started...")
                recording_start = time.monotonic()
                last_data_time = recording_start
                raw_data = trigger_byte
                
                # Keep reading until timeout (= object left, data stopped)
                while True:
                    chunk = ser.read(8000)
                    if chunk:
                        raw_data += chunk
                        last_data_time = time.monotonic()
                    else:
                        print("[!] Object left. Recording stopped.")
                        break
                
                elapsed = max(0.001, last_data_time - recording_start)
                sample_rate = measured_sample_rate(len(raw_data), elapsed)
                print(f"Captured {len(raw_data)} bytes of audio in {elapsed:.2f}s.")
                if options and len(raw_data) > 0:
                    process_outputs(raw_data, options, f"Distance Trigger #{trigger_num}", sample_rate)
                
                print()
                    
    except KeyboardInterrupt:
        print("\nExiting Distance Trigger Mode.")
    except Exception as e:
        print(f"Serial Error: {e}")
    finally:
        if ser and ser.is_open:
            try:
                ser.write(b'S')
            except:
                pass
            ser.close()

# --- CLI Main Program Architecture ---
if __name__ == "__main__":
    print("Welcome to the Dual-Board Audio Processing System CLI!")
    
    while True:
        print("\n" + "="*30)
        print("--- Main Menu ---")
        print("1: Manual Recording Mode")
        print("2: Distance Trigger Mode")
        print("q: Quit Program")
        
        choice = input("Please enter your choice: ").strip().lower()
        
        if choice == '1':
            manual_recording_mode()
        elif choice == '2':
            distance_trigger_mode()
        elif choice == 'q':
            print("Exiting program. Goodbye!")
            # Send S to ensure system is cleanly stopped
            try:
                with serial.Serial(PORT, BAUD, timeout=1) as ser:
                    ser.write(b'S')
            except:
                pass
            break
        else:
            print("Invalid input, please try again.")
