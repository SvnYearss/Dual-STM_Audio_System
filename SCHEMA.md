ECE2071-Audio-System/ (Repository Root)
├── .gitignore               # Ignore compiled garbage files (Debug/, .o, .pycache, etc.) 
├── README.md                # Overall project outline, including 5-person task table and running guide [cite: 328]
│
├── 01_Sampling_Data_Acquisition/  # [Owner 1]: Sampling STM Project
│   ├── Sampling_STM_Project/      # CubeIDE complete project folder (.ioc, etc.) [cite: 84, 201]
│   └── README.md                  # Document: Upgrade path of ADC sampling rate from 5k to 44k [cite: 124, 237]
│
├── 02_Signal_Processing_Sensors/  # [Owner 2]: Processing STM algorithms and sensors
│   ├── Processing_STM_Project/    # CubeIDE complete project folder [cite: 85, 202]
│   └── README.md                  # Document: Filters, outlier rejection, and ultrasonic logic instructions [cite: 125, 182, 240]
│
├── 03_PC_File_Conversion/         # [Owner 3]: PC-side backend processing
│   ├── src_c/                     # C source code: core logic for binary to WAV conversion [cite: 103, 117]
│   ├── bin/                       # Compiled executable file path
│   └── README.md                  # Document: WAV file header structure and CSV export format specifications [cite: 104, 190]
│
├── 04_Python_CLI_Visualization/   # [Owner 4]: PC-side frontend and interaction
│   ├── main_cli.py                # Python main program: CLI menu logic [cite: 99, 175]
│   ├── plotting/                  # Specifically for storing waveform plotting scripts [cite: 188]
│   └── README.md                  # Document: Menu structure design and visualization parameter instructions [cite: 176, 177, 178]
│
├── 05_System_Comm_Protocols/      # [Owner 5]: Cross-system communication protocols
│   ├── protocols_lib/             # Store custom packet formats and checksum algorithms [cite: 492]
│   └── README.md                  # Document: UART/SPI interface contract, baud rate tuning, and DMA configuration 
│
└── Docs/                          # Store Block Diagrams and project progress records [cite: 42, 325]