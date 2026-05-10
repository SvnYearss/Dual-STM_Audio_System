# Python CLI and Data Visualization

This folder contains the PC-side control interface, data receiver, file generator, and visualization tools for the final Dual-STM audio system.

## Main Files

- `main_cli.py`: Standard command-line interface and core processing pipeline.
- `UI.py`: Rich terminal interface that reuses the core functions from `main_cli.py`.

## Final Data Flow

```text
User
  -> Python CLI mode selection
  -> serial commands to Processing STM32
  -> serial audio bytes from Processing STM32
  -> raw binary persistence
  -> optional PC-side cleanup
  -> TXT, CSV, PNG, and WAV outputs
```

The final version targets 44100 Hz output and 12-bit samples, matching the Task 4 audio path.

## Key Implementation

### Python CLI as the control layer

Why Python is used:

- The specification requires a Python script to communicate with the Processing STM32.
- Python is fast to develop for CLI interaction, file handling, plotting, and launching the C converter.
- It can use `pyserial`, `numpy`, and `matplotlib` to handle the PC-side tasks with little boilerplate.

How it is implemented:

- `main()` prints a menu with Manual Recording Mode, Distance Trigger Mode, and Quit.
- `serial.Serial(PORT, BAUD, timeout=...)` opens the PC serial link.
- `send_command_and_wait_for_ack()` sends STM commands and waits for acknowledgement strings.

Default serial settings:

```text
PORT = "COM5"
BAUD = 921600
NOMINAL_FS = 44100
OUTPUT_FS = 44100
SAMPLE_WIDTH_BYTES = 2
BIT_DEPTH = 12
TEAM_ID = "T12"
```

### 12-bit sample decoding

Why this format is used:

- The final STM output sends one sample as two bytes.
- Only the lower 12 bits are valid audio data.
- Masking on the PC keeps the decoder aligned with the embedded data format.

How it is implemented:

- `decode_samples()` uses `np.frombuffer(raw_data, dtype="<u2")`.
- It masks samples with `0x0FFF`.
- `encode_samples()` repacks processed samples as little-endian 16-bit words for the C converter.

### Manual Recording Mode

Why this mode exists:

- The specification requires a manual mode where the user can choose how long to record.
- It is useful for controlled tests because the capture time is known.
- It also replaces the early Task 1 hardcoded duration in the final version.

How it is implemented:

- `manual_recording_mode()` asks the user for duration in seconds.
- It asks which output formats to generate.
- It opens the serial port and waits for the user to press Enter.
- `record_for_duration()` sends `M`, records until the deadline, then sends `S`.
- Received bytes are passed to `process_outputs()`.

### Distance Trigger Mode

Why this mode exists:

- The specification requires the STM system to start and stop automatically based on proximity.
- The PC should stay in the mode and allow repeated triggers.
- The distance threshold must be configurable so the trigger range is not fixed at 10 cm.

How it is implemented:

- `distance_trigger_mode()` asks for output formats.
- `get_distance_threshold()` asks for a trigger distance.
- Valid range is 2 to 200 cm.
- Empty input uses the default 10 cm.
- `configure_distance_threshold()` sends:

```text
R + one-byte distance_cm
```

- It waits for:

```text
ACK:R:<distance_cm>
```

- Python then sends `D` and waits for `ACK:D`.
- The CLI waits for bytes from the Processing STM32. The STM32 decides when recording starts and stops based on the ultrasonic sensor.
- The loop continues until `Ctrl+C`.

### Output format selection

Why selectable outputs are used:

- The specification requires several output formats.
- Users may not need every format for every recording.
- Generating only requested formats makes testing faster.

How it is implemented:

- `get_output_preferences()` asks the user about WAV, PNG, and CSV.
- TXT is generated every time as a simple readable data record.
- `process_outputs()` routes to the correct generation functions.

### TXT output

Why TXT is used:

- Task 1 requires the Python script to save received samples to a file.
- TXT is simple to inspect manually and useful for debugging.

How it is implemented:

- `generate_txt()` writes sample rate, bit depth, and one amplitude value per line.
- `process_outputs()` always calls `generate_txt()`.

### CSV output

Why CSV is used:

- The specification asks for processed audio data in CSV format.
- CSV can be opened in spreadsheets or loaded into analysis tools.
- The first row must include sample rate so the signal can be reconstructed later.

How it is implemented:

- `generate_csv()` writes:

```text
Sample Rate:,44100
Bit Depth:,12
Amplitude_12bit
...
```

- The sample values are written with `np.savetxt()`.

### PNG waveform output

Why PNG is used:

- The specification requires a waveform plot that is immediately interpretable.
- A labelled amplitude-vs-time plot helps verify capture duration, clipping, silence, and trigger behavior.

How it is implemented:

- `generate_png()` builds a time axis with `np.arange(len(samples)) / sample_rate`.
- It plots samples with `matplotlib`.
- It adds title, x-axis label, y-axis label, grid, and tight layout.

### WAV output through C converter

Why Python launches C:

- The specification requires Python to compile and run a C program for WAV conversion.
- Python controls the workflow, while C handles the binary WAV format.

How it is implemented:

- `compile_and_run_c_converter()` writes `recording.bin`.
- It runs `gcc` on `03_PC_File_Conversion/file_conversion.c`.
- It runs the generated executable with the sample rate.
- It renames `output_audio.wav` to the final output name.

### File naming

Why this naming scheme is used:

- The specification requires file names to include team ID and sample rate.
- Including bit depth and mode prevents confusion between manual and distance-triggered recordings.

How it is implemented:

- `output_filename()` builds names from `TEAM_ID`, sample rate, `BIT_DEPTH`, mode name, and extension.

Example:

```text
T12_44100Hz_12bit_Manual_Mode.wav
T12_44100Hz_12bit_Distance_Trigger_1.csv
```

### PC-side audio cleanup

Why these filters are used:

- The embedded system already performs real-time filtering, but PC-side processing can improve final output quality without risking STM timing.
- These filters are not used to replace the embedded requirements; they improve the final saved files.

How it is implemented:

- `deglitch_samples()` removes large sample spikes.
- `_one_pole_highpass()` reduces DC and low-frequency rumble.
- `_zero_phase_lowpass()` limits high-frequency noise.
- `_spectral_denoise()` estimates a noise profile from quiet frames.
- `_soft_noise_gate()` lowers quiet-section noise.
- `_speech_clarity_eq()` adjusts speech clarity bands.
- `_apply_edge_fade()` reduces start/end clicks.
- `filter_background_noise()` combines the enabled filters.

## Rich UI

Why `UI.py` exists:

- The standard CLI is simple and reliable.
- The Rich UI provides a clearer live display for demonstrations.
- It reuses `main_cli.py` functions so the data path remains consistent.

How it is implemented:

- `UI.py` imports `main_cli as audio`.
- It calls `audio.configure_distance_threshold()`, `audio.process_outputs()`, and other shared helpers.
- It adds panels for capture status, telemetry, logs, and output summaries.

## Requirement-by-requirement Justification

| Project specification requirement | Why this design satisfies it | Code-level implementation |
|---|---|---|
| Task 1: Python script reads serial output from the Processing STM32 | Python is the PC control layer and uses `pyserial` to receive the stream. | `serial.Serial(PORT, BAUD, ...)` and read loops in `record_for_duration()` and `distance_trigger_mode()`. |
| Task 1: Python saves received audio samples to file | Raw and text outputs preserve the captured data for later inspection. | `record_for_duration()` writes `recording_raw.bin`; `generate_txt()` writes a readable sample file. |
| Task 1: recording time is hardcoded | This was superseded by Task 2. The final version intentionally uses user-defined duration because the final specification requires Manual Mode control. | `manual_recording_mode()` asks for `duration`; the old hardcoded behavior is not retained. |
| Task 1: Python compiles and runs a C program for WAV conversion | The final WAV path follows the required Python-plus-C workflow. | `compile_and_run_c_converter()` uses `subprocess.run()` for `gcc` and the converter executable. |
| Task 1: output should be recognisably the input audio | The CLI saves the stream and invokes the WAV converter; PC-side filters can improve audibility. | `process_outputs()` decodes, filters, writes TXT, and optionally generates WAV. |
| Task 2: CLI has a clear menu structure | Users can choose Manual Mode, Distance Trigger Mode, or Quit. | `main()` prints choices `1`, `2`, and `q`. |
| Task 2: Manual Mode allows user-specified recording time | The duration is entered at runtime, so no code change is needed to test different capture lengths. | `manual_recording_mode()` reads `duration = float(input(...))`. |
| Task 2: Distance Trigger Mode is available | The CLI can switch the Processing STM32 into sensor-controlled recording. | `distance_trigger_mode()` sends `D` and waits for `ACK:D`. |
| Task 2: trigger range is configurable | The user enters the threshold before Distance Trigger Mode starts. | `get_distance_threshold()` validates input; `configure_distance_threshold()` sends `R + distance_cm`. |
| Task 2: output WAV, PNG, and CSV formats | The user can select each output format before recording. | `get_output_preferences()` returns selected options; `process_outputs()` generates requested files. |
| Task 2: WAV is created by compiling and running C | Python does not hand-write WAV output; it delegates to the C converter as required. | `compile_and_run_c_converter()`. |
| Task 2: PNG includes title and axis labels | The plot is ready to interpret without manually adding labels. | `generate_png()` sets title, x label, y label, grid, and layout. |
| Task 2: CSV first row indicates sample rate | The sample rate is written into the file so the signal can be reconstructed. | `generate_csv()` writes `Sample Rate:,<rate>` as the first row. |
| Task 2: filenames include team ID and sample rate | The naming convention makes outputs self-describing. | `output_filename()` includes `TEAM_ID` and `<sample_rate>Hz`. |
| Task 3: audio quality is improved | PC-side filters supplement the Processing STM32 outlier rejection and moving average. | `deglitch_samples()` and `filter_background_noise()` are called before output generation. |
| Task 3: 22 ksps / 8-bit intermediate output | This final version supersedes the intermediate mode with Task 4 quality. It keeps 44.1 ksps / 12-bit output instead. | `OUTPUT_FS = 44100`; `BIT_DEPTH = 12`; samples are masked with `0x0FFF`. |
| Task 4: final output file sample rate is 44 ksps or higher | The PC output uses 44100 Hz metadata and filenames. | `OUTPUT_FS = NOMINAL_FS`; `NOMINAL_FS = 44100`. |
| Task 4: final output file bit depth is 12-bit | Python decodes and labels the data as 12-bit, and the C converter writes 12 valid bits. | `BIT_DEPTH = 12`; `decode_samples()` masks with `0x0FFF`; WAV converter uses 12 valid bits. |
| Task 4: PC baud rate no higher than 921600 | The PC serial connection uses the allowed maximum baud rate to support the final audio stream. | `BAUD = 921600`. |

## Running the CLI

Standard CLI:

```powershell
python 04_Python_CLI_Visualization/main_cli.py
```

Rich UI:

```powershell
python 04_Python_CLI_Visualization/UI.py
```

Required packages:

```powershell
pip install pyserial numpy matplotlib
```

Additional package for `UI.py`:

```powershell
pip install rich
```

The C converter requires `gcc` to be available on the system path when WAV output is selected.

## Verification Evidence to Collect

1. Flash both STM32 boards with the final firmware.
2. Run `main_cli.py`.
3. In Manual Mode, record a short sample and generate TXT, WAV, CSV, and PNG.
4. Confirm filenames include `T12`, `44100Hz`, and `12bit`.
5. Open the WAV file and confirm it is playable.
6. Open the CSV and confirm the first row contains sample rate.
7. Open the PNG and confirm title and axis labels are present.
8. In Distance Trigger Mode, test several thresholds such as 5 cm, 10 cm, and 20 cm.
9. Confirm the CLI prints `Distance trigger threshold set to <cm>cm`.
10. Confirm object movement starts and stops capture automatically.
