# Sampling & Data Acquisition
**Feature Lead:** [Member Name]

### Core Responsibilities
Responsible for the firmware development of the **Sampling STM32**. This module handles the initial analog-to-digital conversion (ADC) of the audio signal and ensures precise sampling intervals using hardware timers.

### Task Evolution & Requirements
* **Task 1 (MVP)**:
  * Configure ADC to capture audio at a minimum sampling rate of **5 ksps** with an **8-bit** resolution.
  * Implement hardware Timer Interrupts to precisely trigger ADC conversions.
* **Task 3 (Audio Improvements)**:
  * Upgrade the ADC sampling rate to **≥ 44 ksps**.
  * Increase the sampling resolution to **10-bit**.
* **Task 4 (Advanced HD Challenge)**:
  * Maintain a high-fidelity sampling rate of **44 ksps @ 12-bit** across the entire data pipeline without downsampling.

### Academic Integrity & Citations
* *ADC peripheral configuration inspired by the Week 6 Lab Activity.*
* *Timer interrupt architecture adapted from the Week 4 Lab Activity.*