# PC File Conversion and Persistence

This folder contains the C converter used by the Python CLI to turn captured raw audio samples into a playable WAV file.

## Main File

- `file_conversion.c`: Converts `recording.bin` into `output_audio.wav`.

## Final Data Flow

```text
Python CLI
  -> writes recording.bin
  -> compiles file_conversion.c with gcc
  -> runs converter executable
  -> converter writes output_audio.wav
  -> Python renames WAV with team ID, sample rate, bit depth, and mode
```

## Key Implementation

### C converter

Why C is used:

- The project specification explicitly requires the Python script to compile and run a C program to create the WAV file.
- C is well suited to binary file parsing and fixed-layout header writing.
- Keeping this logic in C separates the file format conversion from the Python user interface.

How it is implemented:

- `main_cli.py` calls `gcc` through `subprocess.run()`.
- The compiled executable reads `recording.bin`.
- The converter writes `output_audio.wav`.

### Raw input format

Why this format is used:

- The Processing STM32 sends each 12-bit sample packed into two bytes.
- Using 16-bit little-endian words keeps the PC parsing simple.
- The upper 4 bits are ignored, so the format is robust to unused upper bits.

How it is implemented:

- `read_le16()` reconstructs a 16-bit word from two bytes.
- `raw_12bit = read_le16(raw_bytes) & 0x0FFFU` extracts the valid sample.
- `sample_count = raw_size / 2U` derives the number of samples.

### WAV extensible header

Why `WAVE_FORMAT_EXTENSIBLE` is used:

- Normal PCM WAV files usually describe storage bits, not necessarily valid ADC bits.
- The final system stores audio in a 16-bit PCM container for compatibility.
- `WAVE_FORMAT_EXTENSIBLE` allows the file to state that only 12 bits are valid audio data.

How it is implemented:

- `header.audio_format = 0xFFFE`.
- `header.bits_per_sample = 16U`.
- `header.valid_bits_per_sample = 12U`.
- `header.channels = 1U`.
- `header.sample_rate = sample_rate`.

### Signed PCM conversion

Why conversion is needed:

- ADC samples are unsigned values from 0 to 4095.
- WAV playback expects audio centered around zero.
- Directly writing unsigned ADC values would produce a large DC offset and poor playback.

How it is implemented:

- The converter calculates `dc_center` by averaging all samples.
- It finds the maximum absolute centered value.
- It calculates a bounded gain value.
- It writes each sample as signed 16-bit PCM using `clamp_i16()`.

### Sample rate handling

Why a runtime argument is used:

- The final system normally uses 44100 Hz.
- Passing the rate from Python keeps the converter reusable if the system rate is changed later.
- The WAV metadata must match the sample rate used to interpret time.

How it is implemented:

- Default is `44100`.
- If an argument is provided, `strtoul(argv[1], NULL, 10)` overrides it.
- Python passes the configured output rate when running the converter.

## Requirement-by-requirement Justification

| Project specification requirement | Why this design satisfies it | Code-level implementation |
|---|---|---|
| Task 1: Python script compiles and runs a C program | The WAV generation path is intentionally implemented as a compiled C program, matching the specification. | `main_cli.py` uses `subprocess.run()` to compile `file_conversion.c` and run the executable. |
| Task 1: C program converts audio samples into WAV | The converter reads raw sample bytes and writes a WAV header plus PCM data. | `file_conversion.c` reads `recording.bin`, fills `WavExtensibleHeader`, and writes `output_audio.wav`. |
| Task 1: output should be recognisably the input audio | DC centering and gain scaling make the captured waveform playable through normal audio software. | The converter calculates `dc_center`, `gain`, and writes signed 16-bit PCM samples. |
| Task 2: WAV is one of the selectable output formats | Python only runs the converter when the user selects WAV, so WAV is integrated into the CLI output menu. | `process_outputs()` calls `compile_and_run_c_converter()` when `"WAV"` is selected. |
| Task 2: files should be appropriately named with team ID and sample rate | The converter writes a temporary WAV name; Python renames it using the shared naming convention. | Python renames `output_audio.wav` to names such as `T12_44100Hz_12bit_Manual_Mode.wav`. |
| Task 4: final audio file should be 44 ksps or higher | The converter defaults to 44100 Hz and accepts the sample rate supplied by Python. | `uint32_t sample_rate = 44100`; command-line argument can override it. |
| Task 4: final audio file should be 12-bit | The input parser masks 12-bit samples, and the WAV header records 12 valid bits. | `raw_12bit = ... & 0x0FFFU`; `header.valid_bits_per_sample = 12U`. |
| Task 4: final file should remain playable | A 16-bit PCM container is used because it is broadly supported by audio players, while metadata preserves the 12-bit validity. | `bits_per_sample = 16U`; `valid_bits_per_sample = 12U`; PCM GUID is written. |

## Manual Test

If `recording.bin` already exists in the repository root:

```powershell
gcc 03_PC_File_Conversion/file_conversion.c -o converter.exe
./converter.exe 44100
```

This writes:

```text
output_audio.wav
```

## Verification Evidence to Collect

1. Run the Python CLI and request WAV output.
2. Confirm that `gcc` successfully compiles the converter.
3. Confirm that `output_audio.wav` is produced and renamed by Python.
4. Open the WAV file in a normal audio player.
5. Check WAV metadata for 44100 Hz and 12 valid bits.
6. Compare the audio content against the sound played into the input.
