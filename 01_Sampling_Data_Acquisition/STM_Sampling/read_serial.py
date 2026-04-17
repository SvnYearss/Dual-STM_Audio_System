import serial
ser = serial.Serial(port = "COM5", baudrate = 230400, bytesize = 8, parity = "N", stopbits = 1, timeout = 5)
print(ser.name)
file_1 = open("raw_ADC_values.data", "wb")
for i in range(100):
    x = ser.read(500)
    file_1.write(x)
file_1.close()
ser.close