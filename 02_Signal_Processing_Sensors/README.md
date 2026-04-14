# Signal Processing & Sensor Control
**Feature Lead:** [Member Name]

### Core Responsibilities
Responsible for the **Processing STM32** logic. This includes digital signal processing (DSP) algorithms to clean the audio data and the integration of the proximity sensor to control recording states.

### Task Evolution & Requirements
* **Task 1 (MVP)**:
  * Implement a **Moving Average Filter** (window length ≥ 3) to smooth the incoming raw audio data.
* **Task 2 (UI & Modes)**:
  * Integrate the **HC-SR04 Ultrasonic Sensor**.
  * Implement 'Distance Trigger Mode': Automatically start recording when an object is within the default 10cm range, and stop when it leaves.
  * Develop robust debounce logic to handle momentary sensor spikes/bouncing.
* **Task 3 (Audio Improvements)**:
  * Develop a **Simple Outlier Rejection** algorithm to discard anomalous data points before averaging.
  * Implement a down-scaling algorithm to **rescale 10-bit data into 8-bit** format for efficient UART transmission.

### Academic Integrity & Citations
* *HC-SR04 input capture and trigger logic referenced from the Week 5 Lab Activity.*
* *DSP requirements based on the ECE2071 Project Specification guidelines.*