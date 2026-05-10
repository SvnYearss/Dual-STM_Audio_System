# Signal Processing and Sensor Control

This folder contains the final firmware for the Processing STM32. The Processing STM32 is the coordinator between the Sampling STM32 and the PC. It receives the audio stream over SPI, applies real-time filtering, forwards 12-bit samples to the PC, and controls Distance Trigger Mode using the HC-SR04 ultrasonic sensor.

The final version implements the Task 4 path directly: about 44.1 ksps and 12-bit samples throughout. The earlier Task 3 22 ksps / 8-bit PC stream is not kept as an active mode because the final version supersedes it with higher quality.

## Main Files

- `STM_Processing/`: STM32CubeIDE project for the Processing STM32.
- `STM_Processing/Core/Src/main.c`: Main firmware implementation.
- `STM_Processing/STM_Processing.ioc`: CubeMX peripheral configuration.

## Final Data Flow

```text
Sampling STM32
  -> SPI1 slave receive DMA
  -> 12-bit sample mask
  -> outlier rejection
  -> 3-sample moving average
  -> UART TX DMA queue
  -> PC at 921600 bit/s
```

Command flow:

```text
PC
  -> USART2 commands
  -> Processing STM32
  -> USART1 start/stop forwarding
  -> Sampling STM32
```

Distance trigger flow:

```text
PC configures threshold
  -> Processing STM32 measures HC-SR04 distance
  -> Processing STM32 sends M or S to Sampling STM32
```

## Key Implementation

### SPI receive from Sampling STM32

Why SPI is used:

- Task 4 requires a higher data rate than the early MVP.
- A 44.1 ksps, 12-bit stream is easier to move reliably over SPI than over low-speed UART.
- The Sampling STM32 acts as SPI master, and the Processing STM32 acts as SPI slave.

Why DMA is used:

- The Processing STM32 must receive audio continuously while also handling UART, filtering, and ultrasonic timing.
- DMA avoids one interrupt per byte or per sample.
- Half-buffer processing gives the firmware predictable chunks of 100 samples.

How it is implemented:

- `SPI1` is configured as a 16-bit slave receiver.
- `HAL_SPI_Receive_DMA(&hspi1, (uint8_t*)spi_rx_buffer, 200)` starts continuous reception.
- `HAL_SPI_RxHalfCpltCallback()` processes samples `0..99`.
- `HAL_SPI_RxCpltCallback()` processes samples `100..199`.

### 12-bit sample handling

Why this design is used:

- Task 4 requires 12-bit resolution throughout.
- The SPI frame is 16 bits for alignment and peripheral compatibility, but only 12 bits are valid audio data.
- Masking each sample makes the data format explicit and prevents upper bits from contaminating the audio value.

How it is implemented:

- `AUDIO_SAMPLE_MASK` is defined as `0x0FFFU`.
- `ProcessAudioSample()` applies `sample &= AUDIO_SAMPLE_MASK`.
- UART output stores each processed sample in two bytes:

```c
buf[i * 2]     = (uint8_t)(avg & 0xFF);
buf[i * 2 + 1] = (uint8_t)((avg >> 8) & 0x0F);
```

### Outlier rejection

Why this technique is used:

- The specification asks for a simple outlier rejection algorithm.
- Short spikes can come from ADC noise, sensor switching noise, or transfer glitches.
- Replacing a spike with the local mean is computationally cheap enough for an STM32 and avoids expensive DSP.

How it is implemented:

- `OUTLIER_THRESHOLD_12B` is set to `600`.
- `ProcessAudioSample()` calculates the mean of the history window.
- If `abs(sample - mean) > OUTLIER_THRESHOLD_12B`, the sample is replaced with the mean.
- The accepted value is then used by the moving average filter.

### Moving average filter

Why this technique is used:

- Task 1 requires a moving average filter with a window of at least 3 samples.
- A 3-sample window is small enough to run in real time at 44.1 ksps.
- It smooths isolated sample variation without adding too much latency or muffling.

How it is implemented:

- `MOVING_AVERAGE_WINDOW` is defined as `3U`.
- `sample_history[]` stores the accepted samples.
- `ProcessAudioSample()` averages the three history values.
- The result is stored in `last_valid_sample` and forwarded to the PC.

### UART output to PC

Why 921600 baud is used:

- Task 4 requires an industry-standard baud rate no higher than 921600 bit/s.
- The final stream uses 44,100 samples/s and 2 bytes/sample.
- With standard 8-N-1 UART framing, each byte uses about 10 serial bits.
- Required line rate is approximately:

```text
44,100 samples/s * 2 bytes/sample * 10 bits/byte = 882,000 bit/s
```

- 921600 bit/s is therefore the lowest common high baud rate that can carry the final stream with a small margin.

Why UART DMA and a queue are used:

- The baud rate is close to the required throughput.
- Blocking UART calls would risk losing incoming SPI samples.
- The 4-slot circular queue decouples SPI receive callbacks from UART transmit completion.

How it is implemented:

- `USART2` is configured at `921600`.
- `DMA1_Channel7` is used for USART2 TX.
- `tx_pool`, `tx_wr`, `tx_rd`, `tx_cnt`, and `tx_busy` implement the circular queue.
- `tx_enqueue()` starts `HAL_UART_Transmit_DMA()` if UART is idle.
- `HAL_UART_TxCpltCallback()` advances the queue.

### Manual recording commands

Why simple command bytes are used:

- The Processing STM32 only needs a small command set.
- Single-byte commands reduce parsing overhead and make serial debugging simple.
- The same commands can be forwarded directly to the Sampling STM32.

How it is implemented:

- PC sends `M` to start manual capture.
- PC sends `S` to stop capture.
- `HAL_UART_RxCpltCallback()` receives commands on `USART2`.
- `ForwardSamplingCommand()` forwards `M` or `S` to the Sampling STM32 over `USART1`.
- The PC receives `ACK:M` or `ACK:S`.

### Distance Trigger Mode

Why HC-SR04 is used:

- The specification requires a proximity trigger.
- HC-SR04 gives a simple distance measurement using trigger and echo timing.
- It can be handled with timer input capture on the Processing STM32.

Why debounce is used:

- Ultrasonic readings can briefly spike or drop.
- Without debounce, recording could start and stop too rapidly.
- Consecutive trigger/release counts make the mode more reliable.

How it is implemented:

- PC sends `D`.
- Firmware starts the distance trigger timer logic.
- `HCSR04_Read()` sends the ultrasonic trigger pulse.
- `HAL_TIM_IC_CaptureCallback()` measures echo pulse width.
- `UpdateDistanceTrigger()` compares measured distance against the configured threshold.
- `trigger_count` and `release_count` debounce the decision.
- In range: forward `M` to Sampling STM32.
- Out of range: forward `S` to Sampling STM32.

### Configurable trigger distance

Why this command design is used:

- The specification requires the proximity range to be configurable.
- A one-byte centimeter value is enough for the supported 2 to 200 cm range.
- Binary configuration avoids a multi-character parser inside the UART interrupt path.

How it is implemented:

- Default distance: `HCSR04_DEFAULT_TRIGGER_CM = 10U`.
- Minimum distance: `HCSR04_MIN_TRIGGER_CM = 2U`.
- Maximum distance: `HCSR04_MAX_TRIGGER_CM = 200U`.
- PC sends:

```text
R + one-byte distance_cm
```

- The next received byte after `R` is interpreted as the new threshold.
- The value is clamped to the valid range.
- Firmware replies:

```text
ACK:R:<distance_cm>
```

## Requirement-by-requirement Justification

| Project specification requirement | Why this design satisfies it | Code-level implementation |
|---|---|---|
| Task 1: Processing STM performs a moving average filter with at least 3 samples | A 3-sample average is the minimum required filter and is light enough to run at 44.1 ksps. | `MOVING_AVERAGE_WINDOW = 3U`; `ProcessAudioSample()` averages `sample_history[]`. |
| Task 2: STM can operate in Distance Trigger Mode | The Processing STM32 owns the HC-SR04 sensor and can start/stop Sampling STM32 without PC timing decisions. | `D` command in `HAL_UART_RxCpltCallback()` enables distance mode and starts trigger timing. |
| Task 2: trigger range is configurable | The PC can send a threshold before entering Distance Trigger Mode, so the range is no longer hardcoded. | `R + distance_cm` command updates `hcsr04_trigger_cm`; firmware replies `ACK:R:<cm>`. |
| Task 2: default distance can be 10 cm | The default is kept at 10 cm because the specification suggests 10 cm as a default. | `HCSR04_DEFAULT_TRIGGER_CM = 10U`; `hcsr04_trigger_cm` is initialized to that value. |
| Task 2: recording starts when object is in range | The Processing STM32 compares measured distance to the configured threshold and forwards start command. | `UpdateDistanceTrigger()` sends `M` through `ForwardSamplingCommand()`. |
| Task 2: recording stops after the object leaves | The release path waits for repeated out-of-range readings before forwarding stop. | `release_count` reaches `HCSR04_DEBOUNCE_COUNT`, then `S` is forwarded. |
| Task 2: account for ultrasonic bouncing | Debounce counters avoid reacting to one bad distance reading. | `trigger_count`, `release_count`, and `HCSR04_DEBOUNCE_COUNT`. |
| Task 3: Processing STM removes outliers | Large deviations from the local mean are replaced before averaging. | `OUTLIER_THRESHOLD_12B` and the `abs(diff)` check in `ProcessAudioSample()`. |
| Task 3: Processing STM sends output data to PC | Processed audio is streamed continuously to the PC. | `USART2` TX DMA and `tx_enqueue()`. |
| Task 3: 10-bit to 8-bit and 22 ksps PC stream | This intermediate requirement is superseded by the final Task 4 design. The system keeps 12-bit samples and the full 44.1 ksps stream. | The output path sends two bytes per sample and masks to 12 bits rather than shifting down to 8 bits. |
| Task 4: 44 ksps throughout | The Processing STM32 is designed to consume and forward the Sampling STM32's 44.1 ksps stream without intentional downsampling. | SPI RX DMA processes both half-buffer and full-buffer callbacks; UART uses 921600 baud with DMA. |
| Task 4: 12-bit throughout | Samples remain 12-bit from SPI input through filtering and UART output. | `AUDIO_SAMPLE_MASK = 0x0FFFU`; output packs lower 12 bits into two bytes. |
| Task 4: PC baud rate no higher than 921600 | 921600 is the maximum allowed and is required for 44.1 ksps at 2 bytes/sample over UART. | `huart2.Init.BaudRate = 921600`. |
| Task 4 recommended technology: SPI and DMA | SPI provides board-to-board throughput; DMA prevents blocking while audio is streamed. | `HAL_SPI_Receive_DMA()` and `HAL_UART_Transmit_DMA()`. |

## Verification Evidence to Collect

1. Build and flash `STM_Processing`.
2. Confirm `ACK:M`, `ACK:S`, `ACK:D`, and `ACK:R:<cm>` are received by the PC.
3. Use multiple thresholds, for example 5 cm, 10 cm, and 20 cm, and confirm trigger behavior changes.
4. Use a logic analyzer to confirm SPI input remains continuous while UART output is active.
5. Confirm UART output is at 921600 bit/s.
6. Check the generated PC output to confirm samples remain in the 0 to 4095 range before WAV conversion.
