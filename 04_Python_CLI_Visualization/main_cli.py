import os
import subprocess
import sys
import time

import matplotlib.pyplot as plt
import numpy as np
import serial


PORT = "COM5"
BAUD = 921600
NOMINAL_FS = 44100
OUTPUT_FS = NOMINAL_FS
SAMPLE_WIDTH_BYTES = 2
BIT_DEPTH = 12
TEAM_ID = "T12"
OUTLIER_THRESHOLD = 600
FILTER_ENABLED = True
HIGHPASS_CUTOFF_HZ = 70.0
LOWPASS_CUTOFF_HZ = 15000.0
MAINS_HUM_HZ = 50.0
MAINS_NOTCH_HARMONICS = 0
NOTCH_Q = 35.0
SPECTRAL_DENOISE_ENABLED = True
SPECTRAL_DENOISE_STRENGTH = 0.75
SPECTRAL_DENOISE_FLOOR = 0.45
NOISE_PROFILE_QUIET_FRAMES = 0.20
STFT_WINDOW_SIZE = 1024
STFT_HOP_SIZE = 256
NOISE_GATE_ENABLED = True
NOISE_GATE_THRESHOLD_MULT = 1.8
NOISE_GATE_FLOOR = 0.45
NOISE_GATE_FRAME_MS = 20.0
CLARITY_EQ_ENABLED = True
PRESENCE_LOW_HZ = 1800.0
PRESENCE_HIGH_HZ = 6500.0
PRESENCE_BOOST = 0.1
MUD_LOW_HZ = 180.0
MUD_HIGH_HZ = 500.0
MUD_CUT = 0.12
EDGE_FADE_MS = 20.0
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
CONVERTER_SOURCE = os.path.join(REPO_ROOT, "03_PC_File_Conversion", "file_conversion.c")
CONVERTER_BINARY = os.path.join(REPO_ROOT, "converter.exe" if sys.platform == "win32" else "converter")
CONVERTER_EXE = CONVERTER_BINARY
RECORDING_BIN = os.path.join(REPO_ROOT, "recording.bin")
RAW_RECORDING_BIN = os.path.join(REPO_ROOT, "recording_raw.bin")
INTERMEDIATE_WAV = os.path.join(REPO_ROOT, "output_audio.wav")


def output_filename(mode_name, sample_rate, extension):
    safe_mode = "".join(c if c.isalnum() else "_" for c in mode_name).strip("_")
    return f"{TEAM_ID}_{sample_rate}Hz_{BIT_DEPTH}bit_{safe_mode}.{extension}"


def output_path(mode_name, sample_rate, extension):
    return os.path.join(REPO_ROOT, output_filename(mode_name, sample_rate, extension))


def decode_samples(raw_data):
    usable_len = len(raw_data) - (len(raw_data) % SAMPLE_WIDTH_BYTES)
    if usable_len <= 0:
        return np.array([], dtype=np.uint16)
    return np.frombuffer(raw_data[:usable_len], dtype="<u2") & 0x0FFF


def encode_samples(samples):
    return (np.asarray(samples, dtype=np.uint16) & 0x0FFF).astype("<u2").tobytes()


def deglitch_samples(samples, threshold=OUTLIER_THRESHOLD):
    if len(samples) == 0:
        return samples, 0

    cleaned = np.empty(len(samples), dtype=np.uint16)
    initial_center = int(np.median(samples[:min(64, len(samples))]))
    history = [initial_center] * 3
    hist_index = 0
    last_filtered = initial_center
    rejected = 0

    for i, raw_sample in enumerate(samples):
        sample = int(raw_sample) & 0x0FFF
        mean = sum(history) // 3
        if i >= 3 and abs(sample - mean) > threshold:
            sample = last_filtered
            rejected += 1

        history[hist_index] = sample
        hist_index = (hist_index + 1) % len(history)
        last_filtered = sum(history) // 3
        cleaned[i] = last_filtered

    return cleaned, rejected


def _one_pole_highpass(signal, sample_rate, cutoff_hz):
    if cutoff_hz <= 0 or len(signal) == 0:
        return signal

    dt = 1.0 / sample_rate
    rc = 1.0 / (2.0 * np.pi * cutoff_hz)
    alpha = rc / (rc + dt)
    filtered = np.empty_like(signal)
    filtered[0] = 0.0
    for i in range(1, len(signal)):
        filtered[i] = alpha * (filtered[i - 1] + signal[i] - signal[i - 1])
    return filtered


def _one_pole_lowpass(signal, sample_rate, cutoff_hz):
    if cutoff_hz <= 0 or cutoff_hz >= (sample_rate / 2.0) or len(signal) == 0:
        return signal

    dt = 1.0 / sample_rate
    rc = 1.0 / (2.0 * np.pi * cutoff_hz)
    alpha = dt / (rc + dt)
    filtered = np.empty_like(signal)
    filtered[0] = signal[0]
    for i in range(1, len(signal)):
        filtered[i] = filtered[i - 1] + alpha * (signal[i] - filtered[i - 1])
    return filtered


def _zero_phase_lowpass(signal, sample_rate, cutoff_hz, passes=2):
    filtered = signal
    for _ in range(passes):
        filtered = _one_pole_lowpass(filtered, sample_rate, cutoff_hz)
        filtered = _one_pole_lowpass(filtered[::-1], sample_rate, cutoff_hz)[::-1]
    return filtered


def _biquad_notch(signal, sample_rate, notch_hz, q):
    if notch_hz <= 0 or notch_hz >= (sample_rate / 2.0):
        return signal

    w0 = 2.0 * np.pi * notch_hz / sample_rate
    alpha = np.sin(w0) / (2.0 * q)
    cos_w0 = np.cos(w0)

    b0 = 1.0
    b1 = -2.0 * cos_w0
    b2 = 1.0
    a0 = 1.0 + alpha
    a1 = -2.0 * cos_w0
    a2 = 1.0 - alpha

    b0 /= a0
    b1 /= a0
    b2 /= a0
    a1 /= a0
    a2 /= a0

    filtered = np.empty_like(signal)
    x1 = x2 = y1 = y2 = 0.0
    for i, x0 in enumerate(signal):
        y0 = b0 * x0 + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        filtered[i] = y0
        x2 = x1
        x1 = x0
        y2 = y1
        y1 = y0
    return filtered


def _spectral_denoise(signal, sample_rate):
    if not SPECTRAL_DENOISE_ENABLED or len(signal) < STFT_WINDOW_SIZE:
        return signal

    window_size = STFT_WINDOW_SIZE
    hop_size = STFT_HOP_SIZE
    window = np.hanning(window_size)
    padded_len = int(np.ceil((len(signal) - window_size) / hop_size)) * hop_size + window_size
    padded_len = max(padded_len, window_size)
    padded = np.pad(signal, (0, padded_len - len(signal)))

    starts = range(0, padded_len - window_size + 1, hop_size)
    spectra = []
    energies = []
    for start in starts:
        frame = padded[start:start + window_size] * window
        spectrum = np.fft.rfft(frame)
        spectra.append(spectrum)
        energies.append(float(np.mean(frame * frame)))

    spectra = np.asarray(spectra)
    magnitudes = np.abs(spectra)
    energies = np.asarray(energies)
    quiet_count = max(3, int(len(energies) * NOISE_PROFILE_QUIET_FRAMES))
    quiet_indices = np.argsort(energies)[:quiet_count]
    noise_magnitude = np.median(magnitudes[quiet_indices], axis=0)

    output = np.zeros(padded_len)
    weight = np.zeros(padded_len)
    eps = 1e-9
    for frame_index, start in enumerate(range(0, padded_len - window_size + 1, hop_size)):
        spectrum = spectra[frame_index]
        magnitude = magnitudes[frame_index]
        gain = 1.0 - SPECTRAL_DENOISE_STRENGTH * (noise_magnitude / (magnitude + eps))
        gain = np.clip(gain, SPECTRAL_DENOISE_FLOOR, 1.0)
        gain = np.convolve(gain, np.ones(5) / 5.0, mode="same")

        cleaned = np.fft.irfft(spectrum * gain, n=window_size)
        output[start:start + window_size] += cleaned * window
        weight[start:start + window_size] += window * window

    valid = weight > eps
    output[valid] /= weight[valid]
    return output[:len(signal)]


def _soft_noise_gate(signal, sample_rate):
    if not NOISE_GATE_ENABLED or len(signal) == 0:
        return signal

    frame_size = max(16, int(sample_rate * NOISE_GATE_FRAME_MS / 1000.0))
    hop_size = max(8, frame_size // 2)
    starts = list(range(0, max(1, len(signal) - frame_size + 1), hop_size))
    if not starts or starts[-1] != max(0, len(signal) - frame_size):
        starts.append(max(0, len(signal) - frame_size))

    rms_values = []
    centers = []
    for start in starts:
        frame = signal[start:start + frame_size]
        if len(frame) == 0:
            continue
        rms_values.append(float(np.sqrt(np.mean(frame * frame))))
        centers.append(start + len(frame) // 2)

    if not rms_values:
        return signal

    rms_values = np.asarray(rms_values)
    centers = np.asarray(centers)
    noise_rms = max(1e-6, float(np.percentile(rms_values, 20)))
    threshold = noise_rms * NOISE_GATE_THRESHOLD_MULT
    open_level = threshold * 2.5

    gains = (rms_values - threshold) / max(1e-6, open_level - threshold)
    gains = np.clip(gains, 0.0, 1.0)
    gains = NOISE_GATE_FLOOR + (1.0 - NOISE_GATE_FLOOR) * gains

    sample_positions = np.arange(len(signal))
    interpolated = np.interp(sample_positions, centers, gains, left=gains[0], right=gains[-1])
    smooth_len = max(3, int(sample_rate * 0.01))
    smooth_window = np.ones(smooth_len) / smooth_len
    interpolated = np.convolve(interpolated, smooth_window, mode="same")
    return signal * interpolated


def _bandpass(signal, sample_rate, low_hz, high_hz):
    low_removed = signal - _zero_phase_lowpass(signal, sample_rate, low_hz, passes=1)
    return _zero_phase_lowpass(low_removed, sample_rate, high_hz, passes=1)


def _speech_clarity_eq(signal, sample_rate):
    if not CLARITY_EQ_ENABLED or len(signal) == 0:
        return signal

    mud = _bandpass(signal, sample_rate, MUD_LOW_HZ, MUD_HIGH_HZ)
    presence = _bandpass(signal, sample_rate, PRESENCE_LOW_HZ, PRESENCE_HIGH_HZ)
    return signal - (MUD_CUT * mud) + (PRESENCE_BOOST * presence)


def _apply_edge_fade(signal, sample_rate):
    fade_len = int(sample_rate * EDGE_FADE_MS / 1000.0)
    if fade_len <= 1 or len(signal) < (fade_len * 2):
        return signal

    faded = signal.copy()
    ramp = np.linspace(0.0, 1.0, fade_len)
    faded[:fade_len] *= ramp
    faded[-fade_len:] *= ramp[::-1]
    return faded


def filter_background_noise(samples, sample_rate):
    if not FILTER_ENABLED or len(samples) == 0:
        return samples

    center = float(np.median(samples))
    signal = samples.astype(np.float64) - center
    signal = _one_pole_highpass(signal, sample_rate, HIGHPASS_CUTOFF_HZ)

    for harmonic in range(1, MAINS_NOTCH_HARMONICS + 1):
        signal = _biquad_notch(signal, sample_rate, MAINS_HUM_HZ * harmonic, NOTCH_Q)

    signal = _spectral_denoise(signal, sample_rate)
    signal = _soft_noise_gate(signal, sample_rate)
    signal = _speech_clarity_eq(signal, sample_rate)
    signal = _zero_phase_lowpass(signal, sample_rate, LOWPASS_CUTOFF_HZ, passes=1)
    signal = _apply_edge_fade(signal, sample_rate)
    filtered = np.clip(np.rint(signal + center), 0, 4095).astype(np.uint16)
    return filtered


def measured_sample_rate(sample_count, elapsed_seconds):
    if elapsed_seconds <= 0 or sample_count <= 0:
        return NOMINAL_FS
    return max(1, int(round(sample_count / elapsed_seconds)))


def compile_and_run_c_converter(raw_data, mode_name, sample_rate):
    with open(RECORDING_BIN, "wb") as f:
        f.write(raw_data[: len(raw_data) - (len(raw_data) % SAMPLE_WIDTH_BYTES)])

    print("  Compiling C converter...")
    compile_result = subprocess.run(
        ["gcc", CONVERTER_SOURCE, "-o", CONVERTER_BINARY],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if compile_result.returncode != 0:
        raise RuntimeError(compile_result.stderr.strip() or "C converter compilation failed")

    print("  Running C converter...")
    run_result = subprocess.run(
        [CONVERTER_EXE, str(sample_rate)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if run_result.stdout:
        print(run_result.stdout.strip())
    if run_result.returncode != 0:
        raise RuntimeError(run_result.stderr.strip() or "C converter failed")

    wav_name = output_path(mode_name, sample_rate, "wav")
    if os.path.exists(INTERMEDIATE_WAV):
        os.replace(INTERMEDIATE_WAV, wav_name)
    print(f"  -> Generated {os.path.basename(wav_name)}")


def generate_txt(samples, mode_name, sample_rate):
    txt_name = output_path(mode_name, sample_rate, "txt")
    with open(txt_name, "w") as f:
        f.write(f"Sample Rate: {sample_rate}\n")
        f.write(f"Bit Depth: {BIT_DEPTH}\n")
        f.write("Amplitude_12bit\n")
        np.savetxt(f, samples, fmt="%d")
    print(f"  -> Generated {os.path.basename(txt_name)}")


def generate_csv(samples, mode_name, sample_rate):
    csv_name = output_path(mode_name, sample_rate, "csv")
    with open(csv_name, "w") as f:
        f.write(f"Sample Rate:,{sample_rate}\n")
        f.write(f"Bit Depth:,{BIT_DEPTH}\n")
        f.write("Amplitude_12bit\n")
        np.savetxt(f, samples, delimiter=",", fmt="%d")
    print(f"  -> Generated {os.path.basename(csv_name)}")


def generate_png(samples, mode_name, sample_rate):
    png_name = output_path(mode_name, sample_rate, "png")
    time_axis = np.arange(len(samples)) / sample_rate

    plt.figure(figsize=(10, 4))
    plt.plot(time_axis, samples, color="blue", linewidth=0.5)
    plt.title(f"Audio Waveform ({mode_name})")
    plt.xlabel("Time (seconds)")
    plt.ylabel("Amplitude (12-bit ADC)")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(png_name)
    plt.close()
    print(f"  -> Generated {os.path.basename(png_name)}")


def process_outputs(raw_data, options, mode_name, measured_rate):
    with open(RAW_RECORDING_BIN, "wb") as f:
        f.write(raw_data[: len(raw_data) - (len(raw_data) % SAMPLE_WIDTH_BYTES)])

    raw_samples = decode_samples(raw_data)
    sample_rate = OUTPUT_FS
    print("\nProcessing outputs...")
    print(f"Measured capture-rate estimate: {measured_rate} Hz")
    print(f"Writing outputs at calibrated sample rate: {sample_rate} Hz")
    print(f"Decoded samples: {len(raw_samples)} at {BIT_DEPTH}-bit resolution")

    if len(raw_samples) == 0:
        print("No audio samples were received. Check the STM command link, SPI link, and PC UART wiring.")
        return

    samples, rejected = deglitch_samples(raw_samples)
    if rejected:
        print(f"Deglitched {rejected} spike samples before output generation.")

    filtered_samples = filter_background_noise(samples, sample_rate)
    if FILTER_ENABLED:
        print(
            "Applied noise filter "
            f"(HP {HIGHPASS_CUTOFF_HZ:.0f} Hz, LP {LOWPASS_CUTOFF_HZ:.0f} Hz, "
            f"{MAINS_HUM_HZ:.0f} Hz notch x{MAINS_NOTCH_HARMONICS}, "
            f"spectral denoise {'on' if SPECTRAL_DENOISE_ENABLED else 'off'})."
        )
        samples = filtered_samples

    generate_txt(samples, mode_name, sample_rate)

    if "WAV" in options:
        compile_and_run_c_converter(encode_samples(samples), mode_name, sample_rate)
    if "CSV" in options:
        generate_csv(samples, mode_name, sample_rate)
    if "PNG" in options:
        generate_png(samples, mode_name, sample_rate)

    print("Outputs generated successfully!")


def get_output_preferences():
    print("\nSelect Output Formats (y/n for each):")
    want_wav = input("  1. Generate .WAV file? (y/n): ").strip().lower() == "y"
    want_png = input("  2. Generate .PNG waveform plot? (y/n): ").strip().lower() == "y"
    want_csv = input("  3. Generate .CSV data file? (y/n): ").strip().lower() == "y"

    options = []
    if want_wav:
        options.append("WAV")
    if want_png:
        options.append("PNG")
    if want_csv:
        options.append("CSV")
    return options


def send_command_and_wait_for_ack(ser, command, timeout=0.35):
    expected = b"ACK:" + command + b"\n"
    deadline = time.monotonic() + timeout
    seen = bytearray()

    ser.write(command)
    ser.flush()

    while time.monotonic() < deadline:
        chunk = ser.read(1)
        if not chunk:
            continue
        seen.extend(chunk)
        if expected in seen:
            return True, bytes(seen)
        if len(seen) > 64:
            del seen[:-64]

    return False, bytes(seen)


def record_for_duration(ser, duration):
    chunks = []
    ser.reset_input_buffer()
    time.sleep(0.05)
    got_ack, seen = send_command_and_wait_for_ack(ser, b"M")
    if got_ack:
        print("Processing STM acknowledged manual start.")
    else:
        print("Warning: no ACK:M from Processing STM. Continuing capture anyway.")
        if seen:
            print(f"Received before audio capture: {seen!r}")
    ser.reset_input_buffer()

    start_time = time.monotonic()
    deadline = start_time + duration

    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        target_bytes = int(NOMINAL_FS * SAMPLE_WIDTH_BYTES * min(0.05, max(0.001, remaining)))
        chunk = ser.read(max(SAMPLE_WIDTH_BYTES, min(8192, target_bytes)))
        if chunk:
            chunks.append(chunk)

    elapsed = time.monotonic() - start_time
    ser.write(b"S")
    ser.flush()

    raw_data = b"".join(chunks)
    with open(RAW_RECORDING_BIN, "wb") as f:
        f.write(raw_data[: len(raw_data) - (len(raw_data) % SAMPLE_WIDTH_BYTES)])
    sample_count = len(raw_data) // SAMPLE_WIDTH_BYTES
    return raw_data, measured_sample_rate(sample_count, elapsed), elapsed


def manual_recording_mode():
    print("\n--- Manual Recording Mode ---")
    try:
        duration = float(input("Enter recording duration in seconds: "))
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

        process_outputs(raw_data, options, "Manual Mode", sample_rate)
    except Exception as exc:
        print(f"Serial/processing error: {exc}")


def distance_trigger_mode():
    print("\n--- Distance Trigger Mode ---")
    options = get_output_preferences()
    print("\n[Distance Mode] Recording starts while the ultrasonic sensor is within 10cm.")
    print("Press Ctrl+C to exit mode.\n")

    try:
        with serial.Serial(PORT, BAUD, timeout=0.05) as ser:
            ser.reset_input_buffer()
            got_ack, seen = send_command_and_wait_for_ack(ser, b"D")
            if got_ack:
                print("Processing STM acknowledged distance mode.")
            else:
                print("Warning: no ACK:D from Processing STM. Check COM port, baud rate, and flashed firmware.")
                if seen:
                    print(f"Received before distance capture: {seen!r}")
            trigger_num = 0

            while True:
                print("[Distance Mode] Waiting for proximity trigger...")
                first = ser.read(SAMPLE_WIDTH_BYTES)
                if len(first) < SAMPLE_WIDTH_BYTES:
                    continue

                trigger_num += 1
                print(f"\n[!] Trigger #{trigger_num} detected! Recording started...")
                chunks = [first]
                recording_start = time.monotonic()
                last_data_time = recording_start

                while True:
                    chunk = ser.read(8192)
                    if chunk:
                        chunks.append(chunk)
                        last_data_time = time.monotonic()
                    else:
                        print("[!] Object left. Recording stopped.")
                        break

                raw_data = b"".join(chunks)
                elapsed = max(0.001, last_data_time - recording_start)
                sample_rate = measured_sample_rate(len(raw_data) // SAMPLE_WIDTH_BYTES, elapsed)
                print(f"Captured {len(raw_data)} bytes in {elapsed:.2f}s.")
                process_outputs(raw_data, options, f"Distance Trigger {trigger_num}", sample_rate)
                print()

    except KeyboardInterrupt:
        print("\nExiting Distance Trigger Mode.")
        try:
            with serial.Serial(PORT, BAUD, timeout=1) as ser:
                ser.write(b"S")
        except Exception:
            pass
    except Exception as exc:
        print(f"Serial/processing error: {exc}")


if __name__ == "__main__":
    print("Welcome to the Dual-Board Audio Processing System CLI!")

    while True:
        print("\n" + "=" * 30)
        print("--- Main Menu ---")
        print("1: Manual Recording Mode")
        print("2: Distance Trigger Mode")
        print("q: Quit Program")

        choice = input("Please enter your choice: ").strip().lower()
        if choice == "1":
            manual_recording_mode()
        elif choice == "2":
            distance_trigger_mode()
        elif choice == "q":
            try:
                with serial.Serial(PORT, BAUD, timeout=1) as ser:
                    ser.write(b"S")
            except Exception:
                pass
            print("Exiting program. Goodbye!")
            break
        else:
            print("Invalid input, please try again.")
