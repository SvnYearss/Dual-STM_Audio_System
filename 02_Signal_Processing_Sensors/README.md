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

## Code Reading Guide

This section explains how to read the Processing STM32 firmware as a study guide. The important idea is that this board is both a realtime audio processor and the system coordinator.

### 1. Start with the key constants

The main behaviour is controlled by a small set of definitions near the top of `Core/Src/main.c`:

```c
#define AUDIO_SAMPLE_MASK      0x0FFFU
#define OUTLIER_THRESHOLD_12B  600
#define MOVING_AVERAGE_WINDOW  3U
#define HCSR04_DEFAULT_TRIGGER_CM  10U
#define HCSR04_MIN_TRIGGER_CM      2U
#define HCSR04_MAX_TRIGGER_CM      200U
#define HCSR04_DEBOUNCE_COUNT  3U
```

How to understand these values:

- `AUDIO_SAMPLE_MASK` preserves the lower 12 bits from each 16-bit SPI word.
- `OUTLIER_THRESHOLD_12B` defines how far a sample may jump before it is treated as a spike.
- `MOVING_AVERAGE_WINDOW` is set to 3 because the specification requires at least a 3-sample moving average.
- The HC-SR04 constants define the default, minimum, maximum, and debounce count for Distance Trigger Mode.

### 2. Understand the audio filter state

The moving average filter uses a small circular history:

```c
uint16_t sample_history[MOVING_AVERAGE_WINDOW] = {0};
uint8_t buffer_index = 0;
uint16_t last_valid_sample = 0;
uint32_t sample_count = 0;
```

This is intentionally small. At 44.1 ksps, every sample must be processed quickly, so the firmware avoids dynamic memory, long loops, and floating-point audio filtering.

### 3. Read `ProcessAudioSample()` as the audio pipeline

This function is the centre of the Processing STM32 audio logic:

```c
static uint16_t ProcessAudioSample(uint16_t sample)
{
    sample &= AUDIO_SAMPLE_MASK;

    if (sample_count == 0U)
    {
        for (uint8_t i = 0; i < MOVING_AVERAGE_WINDOW; i++)
        {
            sample_history[i] = sample;
        }
        last_valid_sample = sample;
        sample_count = 1U;
        return sample;
    }
```

The first line masks the sample to 12 bits. The first-sample branch initializes the history window so the first few outputs do not average against zeros.

After the history has enough samples, the function calculates the local mean and rejects abnormal spikes:

```c
uint16_t mean = last_valid_sample;

if (sample_count >= MOVING_AVERAGE_WINDOW)
{
    uint32_t sum = 0U;
    for (uint8_t i = 0; i < MOVING_AVERAGE_WINDOW; i++)
    {
        sum += sample_history[i];
    }
    mean = (uint16_t)(sum / MOVING_AVERAGE_WINDOW);
    int diff = (int)sample - (int)mean;
    if (abs(diff) > OUTLIER_THRESHOLD_12B)
    {
        accepted = mean;
    }
}
```

Then it writes the accepted value into the circular history and returns the filtered average:

```c
sample_history[buffer_index] = accepted;
buffer_index++;
if (buffer_index >= MOVING_AVERAGE_WINDOW)
{
    buffer_index = 0U;
}

uint32_t filtered_sum = 0U;
for (uint8_t i = 0; i < MOVING_AVERAGE_WINDOW; i++)
{
    filtered_sum += sample_history[i];
}
last_valid_sample = (uint16_t)(filtered_sum / MOVING_AVERAGE_WINDOW) & AUDIO_SAMPLE_MASK;
return last_valid_sample;
```

Why this structure is useful for learning:

- Masking happens first because every later stage assumes a valid 12-bit sample.
- Outlier rejection happens before the moving average so spikes do not pollute the history.
- The moving average is integer-only, which is suitable for realtime embedded code.
- `last_valid_sample` is used as a safe fallback if a spike is detected.

### 4. Follow SPI receive callbacks into UART output

The Processing STM32 receives the same 200-sample block size used by the Sampling STM32. Each callback processes half of the block:

```c
void HAL_SPI_RxHalfCpltCallback(SPI_HandleTypeDef *hspi)
{
    if(hspi->Instance == SPI1)
    {
        if (tx_queue_full()) {
            return;
        }
        uint8_t *buf = tx_pool[tx_wr];
        for(int i = 0; i < 100; i++)
        {
            uint16_t avg = ProcessAudioSample(spi_rx_buffer[i]);
            buf[i * 2]     = (uint8_t)(avg & 0xFF);
            buf[i * 2 + 1] = (uint8_t)((avg >> 8) & 0x0F);
        }
        tx_enqueue();
    }
}
```

The full-complete callback does the same for the second half:

```c
uint16_t avg = ProcessAudioSample(spi_rx_buffer[i + 100]);
buf[i * 2]     = (uint8_t)(avg & 0xFF);
buf[i * 2 + 1] = (uint8_t)((avg >> 8) & 0x0F);
```

This shows the final output format clearly:

- Each filtered sample becomes two UART bytes.
- The first byte stores bits `0..7`.
- The second byte stores bits `8..11`.
- The upper 4 bits of the second byte are kept clear.

### 5. Understand the UART DMA queue

UART at 921600 bit/s is close to the required throughput, so the code avoids blocking transmit calls. A 4-slot pool buffers outgoing UART blocks:

```c
static void tx_enqueue(void)
{
    uint8_t next_wr = (tx_wr + 1U) % TX_BUF_COUNT;
    if (tx_queue_full()) {
        return;
    }

    tx_wr = next_wr;
    tx_cnt++;

    if (!tx_busy) {
        tx_busy = 1U;
        HAL_UART_Transmit_DMA(&huart2, tx_pool[tx_rd], TX_BUF_SIZE);
        tx_rd = (tx_rd + 1U) % TX_BUF_COUNT;
        tx_cnt--;
    }
}
```

When a DMA transmit finishes, the completion callback starts the next queued block:

```c
void HAL_UART_TxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART2) {
        if (tx_cnt > 0U) {
            HAL_UART_Transmit_DMA(&huart2, tx_pool[tx_rd], TX_BUF_SIZE);
            tx_rd = (tx_rd + 1U) % TX_BUF_COUNT;
            tx_cnt--;
        } else {
            tx_busy = 0U;
        }
    }
}
```

This is the main reason SPI callbacks can finish quickly. They fill a buffer and enqueue it, while DMA handles the slower UART transfer in the background.

### 6. Read the PC command parser

The PC talks to the Processing STM32 over `USART2`. The command parser handles three kinds of commands:

```c
if (expecting_distance_threshold != 0U)
{
    /* next byte is the new distance threshold */
}
else if(pc_rx_byte == 'M' || pc_rx_byte == 'S')
{
    system_state = pc_rx_byte;
    ForwardSamplingCommand(pc_rx_byte);
}
else if (pc_rx_byte == 'D')
{
    system_state = 'D';
    SendPcStatus("ACK:D\n");
}
else if (pc_rx_byte == 'R')
{
    expecting_distance_threshold = 1U;
}
```

How to study this:

- `M` and `S` are forwarded to the Sampling STM32 immediately.
- `D` changes the Processing STM32 into sensor-controlled mode.
- `R` does not contain the threshold by itself. It means the next received byte is the threshold.

The threshold byte is clamped before it is accepted:

```c
if (pc_rx_byte < HCSR04_MIN_TRIGGER_CM)
{
    hcsr04_trigger_cm = HCSR04_MIN_TRIGGER_CM;
}
else if (pc_rx_byte > HCSR04_MAX_TRIGGER_CM)
{
    hcsr04_trigger_cm = HCSR04_MAX_TRIGGER_CM;
}
else
{
    hcsr04_trigger_cm = pc_rx_byte;
}

snprintf(status_msg, sizeof(status_msg), "ACK:R:%u\n", hcsr04_trigger_cm);
SendPcStatus(status_msg);
```

This is why the Python CLI can confirm the exact threshold that the STM32 accepted.

### 7. Study the distance-trigger state machine

The distance logic converts measured distance into start/stop commands:

```c
static void UpdateDistanceTrigger(float distance_cm)
{
    if (distance_cm > 0.0f && distance_cm <= (float)hcsr04_trigger_cm)
    {
        trigger_count++;
        release_count = 0;
        if ((trigger_count >= HCSR04_DEBOUNCE_COUNT) && (distance_recording_active == 0U))
        {
            uint8_t cmd = 'M';
            distance_recording_active = 1U;
            ForwardSamplingCommand(cmd);
        }
    }
    else if (distance_cm > (float)hcsr04_trigger_cm)
    {
        release_count++;
        trigger_count = 0;
        if ((release_count >= HCSR04_DEBOUNCE_COUNT) && (distance_recording_active != 0U))
        {
            uint8_t cmd = 'S';
            distance_recording_active = 0U;
            ForwardSamplingCommand(cmd);
        }
    }
}
```

The two counters are the debounce mechanism:

- `trigger_count` must reach 3 before recording starts.
- `release_count` must reach 3 before recording stops.
- This prevents one unstable HC-SR04 reading from toggling recording state.

### 8. Connect the HC-SR04 reading to the state machine

`HCSR04_Read()` sends a 10 microsecond trigger pulse:

```c
void HCSR04_Read(void)
{
    Is_First_Captured = 0;
    __HAL_TIM_SET_CAPTUREPOLARITY(&htim2, TIM_CHANNEL_1, TIM_INPUTCHANNELPOLARITY_RISING);
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_4, GPIO_PIN_SET);
    delay_uS(10);
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_4, GPIO_PIN_RESET);
    __HAL_TIM_ENABLE_IT(&htim2, TIM_IT_CC1);
}
```

The timer input-capture callback measures the echo pulse width. When a valid distance is computed, Distance Trigger Mode calls `UpdateDistanceTrigger(distance)`.

### 9. What to change when studying the code

| Goal | Change here | What to watch |
|---|---|---|
| Make outlier rejection stricter or looser | `OUTLIER_THRESHOLD_12B` | Too low can flatten real transients; too high may let spikes pass. |
| Change moving average strength | `MOVING_AVERAGE_WINDOW` and `sample_history[]` logic | Larger windows add latency and can blur audio. |
| Change trigger range limits | `HCSR04_MIN_TRIGGER_CM` and `HCSR04_MAX_TRIGGER_CM` | Python validation should match firmware limits. |
| Change trigger stability | `HCSR04_DEBOUNCE_COUNT` | Higher values reduce false triggers but react more slowly. |
| Change PC baud rate | `huart2.Init.BaudRate` and Python `BAUD` | 44.1 ksps x 2 bytes/sample needs about 882000 serial bits/s with 8-N-1 framing. |
| Change output sample format | UART packing in SPI callbacks and Python `decode_samples()` | Both sides must agree on byte order and bit depth. |

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
