# Sampling and Data Acquisition

This folder contains the final firmware for the Sampling STM32. The Sampling STM32 is responsible for acquiring the analog audio signal with the ADC and streaming the full-resolution samples to the Processing STM32.

The final version implements the Task 4 design directly: about 44.1 ksps and 12-bit samples throughout. Earlier lower-rate or lower-resolution versions are not kept as active modes because the final version supersedes them.

## Main Files

- `STM_Sampling/`: STM32CubeIDE project for the Sampling STM32.
- `STM_Sampling/Core/Src/main.c`: Main firmware implementation.
- `STM_Sampling/Project_Week_6.ioc`: CubeMX peripheral configuration.

## Final Data Flow

```text
Analog audio input
  -> ADC1, 12-bit conversion
  -> ADC DMA circular buffer
  -> TIM6 paced sampling trigger
  -> SPI1 master transmission using DMA
  -> Processing STM32
```

The Sampling STM32 only starts sampling when the Processing STM32 tells it to start. This lets both Manual Recording Mode and Distance Trigger Mode reuse the same acquisition firmware.

## Key Implementation

### Timer-triggered ADC

The ADC is not sampled from a software loop. Instead, `TIM6` generates a hardware trigger and `ADC1` converts one sample on each trigger.

Why this technology is used:

- A software loop would depend on interrupt load and branch timing.
- A timer trigger gives a stable sample interval, which is important for audio playback.
- It directly supports the specification requirement for a sustained sample rate.

How it is implemented:

- `MX_TIM6_Init()` configures `TIM6`.
- `htim6.Init.Prescaler = 5`.
- `htim6.Init.Period = 120`.
- `sMasterConfig.MasterOutputTrigger = TIM_TRGO_UPDATE`.
- `MX_ADC1_Init()` sets `hadc1.Init.ExternalTrigConv = ADC_EXTERNALTRIG_T6_TRGO`.
- `Audio_Start()` starts both ADC DMA and `TIM6`.

Sample rate calculation:

```text
Timer clock = 32,000,000 Hz
Sample rate = 32,000,000 / ((5 + 1) * (120 + 1))
            = 44,077 samples/second
```

This is effectively the 44.1 ksps final sampling path.

### 12-bit ADC resolution

Why this technology is used:

- Task 4 requires 12-bit resolution throughout.
- Keeping 12-bit samples at the source avoids throwing away audio detail before processing.
- It also automatically exceeds the earlier Task 1 and Task 3 bit-depth requirements.

How it is implemented:

- `MX_ADC1_Init()` sets `hadc1.Init.Resolution = ADC_RESOLUTION_12B`.
- Samples are stored in `uint16_t adc_buffer[200]`.
- The valid audio value is in the lower 12 bits of each 16-bit word.

### ADC DMA buffering

Why this technology is used:

- At 44.1 ksps, the CPU should not manually copy every ADC result.
- DMA prevents missed samples while the CPU handles command logic and SPI transfer setup.
- A circular buffer allows continuous acquisition without stopping between blocks.

How it is implemented:

- `HAL_ADC_Start_DMA(&hadc1, (uint32_t*)adc_buffer, 200)` starts ADC DMA.
- The buffer has 200 samples.
- `HAL_ADC_ConvHalfCpltCallback()` runs when the first 100 samples are ready.
- `HAL_ADC_ConvCpltCallback()` runs when the second 100 samples are ready.

### SPI transmission to Processing STM32

Why SPI is used:

- Task 4 recommends investigating SPI for the higher audio throughput.
- SPI is better suited than UART for board-to-board streaming at this data rate.
- The Sampling STM32 controls the clock as SPI master, making the stream deterministic.

Why SPI DMA is used:

- It lets each half-buffer transmit while ADC sampling continues.
- It avoids blocking the CPU during 100-sample transfers.
- It keeps the 12-bit stream moving with low overhead.

How it is implemented:

- `SPI1` is configured as master.
- `hspi1.Init.DataSize = SPI_DATASIZE_16BIT`.
- On ADC DMA half-complete:

```c
HAL_SPI_Transmit_DMA(&hspi1, (uint8_t*)&adc_buffer[0], 100);
```

- On ADC DMA complete:

```c
HAL_SPI_Transmit_DMA(&hspi1, (uint8_t*)&adc_buffer[100], 100);
```

Each SPI frame is 16 bits, but the actual audio data is the lower 12 bits.

### Start and stop commands

Why command control is used:

- Manual Mode and Distance Trigger Mode both need to start and stop capture.
- The Processing STM32 is the coordinator because it receives commands from the PC and owns the ultrasonic trigger logic.
- A simple command byte keeps the firmware robust and easy to debug.

How it is implemented:

- `USART1` receives commands from the Processing STM32.
- `M` calls `Audio_Start()`.
- `S` calls `Audio_Stop()`.
- `Audio_Start()` starts ADC DMA and `TIM6`.
- `Audio_Stop()` stops `TIM6` and ADC DMA.

## Requirement-by-requirement Justification

| Project specification requirement | Why this design satisfies it | Code-level implementation |
|---|---|---|
| Task 1: audio samples captured by the Sampling STM should contain at least 8 bits | The final design captures 12-bit samples, so it exceeds the minimum 8-bit requirement. Keeping more bits improves quality and supports the final Task 4 target. | `MX_ADC1_Init()` sets `ADC_RESOLUTION_12B`; samples are stored in `uint16_t adc_buffer[200]`. |
| Task 1: sample rate should be at least 5 ksps | The final timer configuration gives about 44.1 ksps, far above 5 ksps. A hardware timer is used so the rate is stable enough for audio. | `MX_TIM6_Init()` uses prescaler 5 and period 120; `ADC1` is triggered by `TIM6 TRGO`. |
| Task 1: system should contain a Sampling STM32 | This folder is the dedicated Sampling STM32 firmware project. It performs the acquisition role in the two-STM architecture. | `STM_Sampling/` is an independent STM32CubeIDE project with its own `main.c`, `.ioc`, startup, and HAL configuration. |
| Task 3: Sampling STM samples at a minimum of 44k samples/second | The timer-triggered ADC runs at about 44,077 samples/second. This meets the 44 ksps requirement. | `TIM6` timing plus `ADC_EXTERNALTRIG_T6_TRGO` define the sample cadence. |
| Task 3: Sampling STM transmits at least 10 bits/sample | The final firmware transmits 12-bit samples, which is higher than the Task 3 10-bit requirement. | `ADC_RESOLUTION_12B` and 16-bit SPI frames preserve the lower 12 bits. |
| Task 4: system should operate at 44 ksps throughout | The Sampling stage produces the 44.1 ksps source stream used by the rest of the pipeline. This module does not downsample. | ADC DMA callbacks transmit every half-buffer over SPI immediately. |
| Task 4: system should operate at 12-bit resolution throughout | The Sampling stage is where bit depth begins, so it preserves 12-bit resolution from the ADC onward. | ADC values are stored as 16-bit words with valid lower 12 bits and sent over 16-bit SPI. |
| Task 4 recommended technology: SPI and DMA | SPI provides enough board-to-board throughput, and DMA keeps acquisition non-blocking. | ADC DMA fills `adc_buffer`; SPI TX DMA sends each half-buffer. |

## Verification Evidence to Collect

Use these checks during demonstration or report preparation:

1. Build `STM_Sampling` in STM32CubeIDE.
2. Flash the Sampling STM32.
3. Start Manual Mode from the Python CLI.
4. Use a logic analyzer or oscilloscope to confirm continuous SPI activity after the `M` command.
5. Measure the timer/sample cadence and confirm it is about 44.1 ksps.
6. Confirm that transmitted sample words contain changing lower-12-bit ADC data.
