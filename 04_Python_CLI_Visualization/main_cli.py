import serial
import subprocess
import numpy as np
import matplotlib.pyplot as plt

# --- Configuration Parameters ---
PORT = '/dev/cu.usbmodemXXXXX' # Remember to replace with your Mac port
BAUD = 230400
FS = 6400
DURATION = 5

def record_audio(mode_name, command_byte):
    """Core function for recording, generating binary file, converting to WAV, and saving CSV and PNG"""
    bytes_to_read = FS * DURATION * 1
    
    # 1. Record Audio
    with serial.Serial(PORT, BAUD, timeout=10) as ser:

        ser.write(command_byte)
        print(f"\n[{mode_name}] Recording for {DURATION} seconds...")
        raw_data = ser.read(bytes_to_read)
        print(f"[{mode_name}] Recording complete!")

    # 2. Save binary file for C program
    with open("recording.bin", "wb") as f:
        f.write(raw_data)

    # 3. Call C program to generate .wav
    subprocess.run(["./converter"]) 
    print("Generated output_audio.wav")

    # ==========================================
    # Task 2 New feature: Numpy Data Processing and Visualization
    # ==========================================
    
    # Convert byte string to Numpy array (8-bit unsigned integer)
    data_array = np.frombuffer(raw_data, dtype=np.uint8)

    # 4. Generate .csv file (Numpy one-liner instead of a for loop!)
    np.savetxt("audio_data.csv", data_array, delimiter=",", fmt='%d')
    print("Generated audio_data.csv")

    # 5. Generate .png waveform
    plt.figure(figsize=(10, 4))
    plt.plot(data_array, color='blue', linewidth=0.5)
    plt.title(f"Audio Waveform ({mode_name})")
    plt.xlabel("Sample Index")
    plt.ylabel("Amplitude (8-bit)")
    plt.grid(True)
    plt.savefig("waveform.png")
    plt.close() # Remember to close the figure to release memory
    print("Generated waveform.png")


# --- CLI Main Program Architecture ---
if __name__ == "__main__":
    print("Welcome to the Dual-Board Audio Processing System CLI!")
    
    while True: # Equivalent to while(1)
        print("\n--- Main Menu ---")
        print("1: Manual Recording Mode")
        print("2: Distance Trigger Mode (TBD)")
        print("q: Quit Program")
        
        choice = input("Please enter your choice: ")
        
        if choice == '1':
            print("\nYou selected Manual Recording.")
            input("Press Enter to start recording...") # Blocking wait for user confirmation
            record_audio("Manual Mode", b'M')
            
        elif choice == '2':
            print("\nYou selected Distance Trigger Mode.")
            record_audio("Distance Trigger Mode", b'D')
            
        elif choice.lower() == 'q':
            print("Exiting program. Goodbye!")
            break # Break the infinite loop, end program
            
        else:
            print("Invalid input, please try again.")