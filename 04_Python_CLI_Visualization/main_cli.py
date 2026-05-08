import serial
import subprocess
import numpy as np
import matplotlib.pyplot as plt
import sys

# --- Configuration Parameters ---
PORT = 'COM5'
BAUD = 230400
FS = 8000  # Sampling rate from the STM32 configuration

def compile_and_run_c_converter(raw_data):
    """Saves binary data and calls the C converter to create a WAV file."""
    with open("raw_ADC_values.data", "wb") as f:
        f.write(raw_data)
        
    print("  Compiling C converter...")
    subprocess.run(["gcc", "01_Sampling_Data_Acquisition/STM_Sampling/file_conversion.c", "-o", "converter"])
    print("  Running C converter...")
    # On Windows, the executable might be .exe
    exe_name = "converter.exe" if sys.platform == "win32" else "./converter"
    subprocess.run([exe_name])
    print("  -> Generated output.wav")

def generate_csv(data_array):
    """Generates a CSV file with the first row indicating the sample rate."""
    # The requirement specifically asks for the first row to indicate the sample rate
    with open("audio_data.csv", "w") as f:
        f.write(f"Sample Rate:,{FS}\n")
        f.write("Amplitude\n")
        np.savetxt(f, data_array, delimiter=",", fmt='%d')
    print("  -> Generated audio_data.csv")

def generate_png(data_array, mode_name):
    """Generates a plot of amplitude vs time with proper labels."""
    time_axis = np.arange(len(data_array)) / FS
    
    plt.figure(figsize=(10, 4))
    plt.plot(time_axis, data_array, color='blue', linewidth=0.5)
    plt.title(f"Audio Waveform ({mode_name})")
    plt.xlabel("Time (seconds)")
    plt.ylabel("Amplitude (8-bit PCM)")
    plt.grid(True)
    plt.savefig("waveform.png")
    plt.close()
    print("  -> Generated waveform.png")

def process_outputs(raw_data, options, mode_name):
    """Processes the raw serial bytes into the formats requested by the user."""
    print("\nProcessing outputs...")
    
    if 'WAV' in options:
        compile_and_run_c_converter(raw_data)
        
    if 'CSV' in options or 'PNG' in options:
        data_array = np.frombuffer(raw_data, dtype=np.uint8)
        
        if 'CSV' in options:
            generate_csv(data_array)
            
        if 'PNG' in options:
            generate_png(data_array, mode_name)
    
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
            ser.write(b'M')
            print(f"Recording for {duration} seconds...")
            raw_data = ser.read(bytes_to_read)
            ser.write(b'S')
            print("Recording complete!")
            
        if options:
            process_outputs(raw_data, options, "Manual Mode")
    except Exception as e:
        print(f"Serial Error: {e}")

def distance_trigger_mode():
    print("\n--- Distance Trigger Mode ---")
    options = get_output_preferences()
    
    print("\n[Distance Mode] Waiting for proximity trigger (Press Ctrl+C to exit mode)...")
    
    try:
        with serial.Serial(PORT, BAUD, timeout=1) as ser:
            ser.write(b'D') # Put STM32 into Distance mode
            
            while True:
                # Read 1 byte to detect if STM32 started sending data
                trigger_byte = ser.read(1)
                
                if trigger_byte:
                    print("\n[!] Trigger detected! Recording started...")
                    raw_data = trigger_byte
                    
                    # Keep reading chunks until STM32 stops sending (timeout)
                    while True:
                        chunk = ser.read(8000)
                        if chunk:
                            raw_data += chunk
                        else:
                            # Timeout hit, meaning object left and STM32 stopped sampling
                            print("[!] Object left. Recording stopped.")
                            break
                    
                    print(f"Captured {len(raw_data)} bytes of audio.")
                    if options and len(raw_data) > 0:
                        process_outputs(raw_data, options, "Distance Mode")
                    
                    print("\n[Distance Mode] Waiting for next trigger (Press Ctrl+C to exit)...")
                    
    except KeyboardInterrupt:
        print("\nExiting Distance Trigger Mode.")
        # Send S just in case
        try:
            with serial.Serial(PORT, BAUD, timeout=1) as ser:
                ser.write(b'S')
        except:
            pass
    except Exception as e:
        print(f"Serial Error: {e}")

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