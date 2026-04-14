import serial
import time

# Helper function: Python's version of the XOR Checksum
def calculate_checksum(data_string):
    checksum = 0
    # ord(char) converts a character to its ASCII number so we can do the math
    for char in data_string:
        checksum ^= ord(char) 
    return checksum

# Remember to change COM3 to your actual port!
ser = serial.Serial(port='COM4', baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=2)
print("Connected to:", ser.name)

while (1):
    message = input("Enter starting token (e.g., C): ")
    
    # We must add the \n so the STM32 interrupt knows the word is finished
    ser.write((message + "\n").encode())
    print("Token sent! Waiting for the ring...")

    # Wait until STM sends back result
    while (1):
        if ser.in_waiting > 0:
            # We use readline() to grab the entire long string at once
            data = ser.readline().decode('ascii', errors='ignore').strip()
            
            if data:
                print("\n" + "="*30)
                print("TOKEN RETURNED FROM RING!")
                print(f"Raw Data String : {data}")
                
                # Check if the data contains our '#' checksum delimiter
                if '#' in data:
                    # rsplit splits the string from the right side, separating the text from the hex
                    payload, received_hex = data.rsplit('#', 1)
                    
                    print(f"Extracted Text  : {payload}")
                    print(f"Extracted Checksum: {received_hex}")
                    
                    # Calculate what the checksum *should* be
                    expected_checksum = calculate_checksum(payload)
                    
                    # Convert our calculated math number into a 2-digit Hex string (e.g., "4F")
                    expected_hex = f"{expected_checksum:02X}" 
                    
                    # The Final Viva Verification
                    if expected_hex == received_hex:
                        print(f"Status          : ✅ INTEGRITY PASSED! (Matches {expected_hex})")
                    else:
                        print(f"Status          : ❌ CORRUPTION DETECTED! (Expected {expected_hex})")
                else:
                    print("Status          : ⚠️ No checksum delimiter '#' found.")
                
                print("="*30 + "\n")
                break # Break out of the waiting loop to ask for the next token
        
        # A tiny delay to prevent the terminal from freezing
        time.sleep(0.1)