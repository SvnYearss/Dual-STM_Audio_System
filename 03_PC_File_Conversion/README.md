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

## Code Reading Guide

This section explains how to read `file_conversion.c` as a learning guide. The converter is small, but it contains several important ideas: binary parsing, WAV header construction, 12-bit-to-16-bit audio conversion, and runtime metadata.

### 1. Understand the input contract

The converter expects `recording.bin` in the repository root. Python writes this file before compiling and running the converter.

Each sample is stored as a little-endian 16-bit word, but only the lower 12 bits are valid:

```c
static uint16_t read_le16(const uint8_t bytes[2])
{
    return (uint16_t)bytes[0] | ((uint16_t)bytes[1] << 8);
}
```

Later, every raw word is masked:

```c
uint16_t raw_12bit = read_le16(raw_bytes) & 0x0FFFU;
```

How to understand this:

- The Processing STM32 sends two bytes per sample.
- Python stores those bytes directly in `recording.bin`.
- The C converter reconstructs the 16-bit container and discards the unused upper 4 bits.
- This keeps the converter aligned with the final 12-bit project requirement.

### 2. Follow the sample-rate argument

The converter defaults to 44100 Hz but allows Python to pass another rate:

```c
uint32_t sample_rate = 44100;
if (argc >= 2) {
    uint32_t requested_rate = (uint32_t)strtoul(argv[1], NULL, 10);
    if (requested_rate > 0U) {
        sample_rate = requested_rate;
    }
}
```

This makes the C converter reusable. If the project sample rate changes, the converter does not need to be recompiled with a hardcoded constant.

### 3. Read the raw file size and sample count

The converter calculates how many samples are present by dividing file size by two:

```c
fseek(raw_file, 0, SEEK_END);
long raw_size_long = ftell(raw_file);
fseek(raw_file, 0, SEEK_SET);

uint32_t raw_size = (uint32_t)raw_size_long;
uint32_t sample_count = raw_size / 2U;
uint32_t data_size = sample_count * 2U;
```

Why this matters:

- `recording.bin` contains 2 bytes per sample.
- `data_size` is also 2 bytes per output sample because the WAV file uses a 16-bit PCM container.
- If the raw byte count is odd, the final incomplete byte is ignored by the integer division.

### 4. Understand DC centering

ADC samples are unsigned, usually centred near mid-scale. WAV playback expects signed samples around zero, so the converter first estimates the actual DC centre:

```c
double dc_center = 2048.0;

if (sample_count > 0U) {
    uint64_t sample_sum = 0U;
    uint8_t raw_bytes[2];
    while (fread(raw_bytes, 1, 2, raw_file) == 2) {
        sample_sum += (uint64_t)(read_le16(raw_bytes) & 0x0FFFU);
    }
    dc_center = (double)sample_sum / (double)sample_count;
```

Why this is useful:

- Ideal 12-bit unsigned audio is centred around `2048`.
- Real ADC circuits may sit slightly above or below that value.
- Calculating the centre from the recording removes DC offset and makes playback clearer.

### 5. Understand gain scaling

After finding the centre, the converter finds the largest centred amplitude:

```c
double max_abs = 1.0;
while (fread(raw_bytes, 1, 2, raw_file) == 2) {
    double centered = (double)(read_le16(raw_bytes) & 0x0FFFU) - dc_center;
    double abs_centered = centered < 0.0 ? -centered : centered;
    if (abs_centered > max_abs) {
        max_abs = abs_centered;
    }
}

gain = 28000.0 / max_abs;
if (gain < 4.0) {
    gain = 4.0;
} else if (gain > 64.0) {
    gain = 64.0;
}
```

How to interpret this:

- `28000.0` leaves headroom below the signed 16-bit maximum of `32767`.
- The lower bound avoids extremely quiet output if the measured signal is large.
- The upper bound avoids amplifying noise too aggressively when the recording is nearly silent.

### 6. Study the WAV header structure

The file uses a packed `WavExtensibleHeader` so the bytes written by C match the WAV file layout:

```c
#pragma pack(push, 1)
typedef struct {
    char riff[4];
    uint32_t riff_size;
    char wave[4];
    char fmt_id[4];
    uint32_t fmt_size;
    uint16_t audio_format;
    uint16_t channels;
    uint32_t sample_rate;
    uint32_t byte_rate;
    uint16_t block_align;
    uint16_t bits_per_sample;
    uint16_t cb_size;
    uint16_t valid_bits_per_sample;
    uint32_t channel_mask;
    uint8_t subformat[16];
    char data_id[4];
    uint32_t data_size;
} WavExtensibleHeader;
#pragma pack(pop)
```

The important fields are filled like this:

```c
header.audio_format = 0xFFFE; /* WAVE_FORMAT_EXTENSIBLE */
header.channels = 1U;
header.sample_rate = sample_rate;
header.bits_per_sample = 16U;       /* storage container */
header.valid_bits_per_sample = 12U; /* actual ADC/audio resolution */
header.block_align = 2U;
header.byte_rate = sample_rate * header.block_align;
```

Why this design is used:

- Most audio players understand 16-bit PCM storage.
- The project still needs to document that only 12 bits are valid audio.
- `WAVE_FORMAT_EXTENSIBLE` allows both requirements to be represented: 16-bit storage and 12 valid bits.

### 7. Follow the final sample write loop

After the header is written, the converter writes each audio sample:

```c
fwrite(&header, sizeof(header), 1, wav_file);

uint8_t raw_bytes[2];
while (fread(raw_bytes, 1, 2, raw_file) == 2) {
    uint16_t raw_12bit = read_le16(raw_bytes) & 0x0FFFU;
    int16_t signed_16bit = clamp_i16(((double)raw_12bit - dc_center) * gain);
    fwrite(&signed_16bit, sizeof(signed_16bit), 1, wav_file);
}
```

This is the conversion in one line:

```text
12-bit unsigned ADC sample -> remove DC centre -> apply gain -> signed 16-bit PCM sample
```

The clamp function protects against overflow:

```c
static int16_t clamp_i16(double value)
{
    if (value > 32767.0) {
        return 32767;
    }
    if (value < -32768.0) {
        return -32768;
    }
    return (int16_t)value;
}
```

### 8. What to change when studying the code

| Goal | Change here | What to watch |
|---|---|---|
| Change default WAV rate | `uint32_t sample_rate = 44100` | Python normally passes the rate, so keep both sides consistent. |
| Change valid bit depth | `header.valid_bits_per_sample` and `0x0FFFU` mask | Processing STM32 and Python decoding must match the same bit depth. |
| Change output loudness | `gain = 28000.0 / max_abs` and gain bounds | Too much gain can clip; too little gain can sound quiet. |
| Change channel count | `header.channels`, `block_align`, `byte_rate`, and write loop | The input stream is mono, so stereo requires duplicating or separately capturing channels. |
| Use a different raw filename | `fopen("recording.bin", "rb")` | Python `compile_and_run_c_converter()` must write the same filename. |

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
