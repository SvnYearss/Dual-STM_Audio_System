# Python CLI & Data Visualization
**Feature Lead:** [Member Name]

### Core Responsibilities
Responsible for the front-end user experience on the PC. This module handles the Python Command Line Interface (CLI), serial data reception, and the generation of waveform plots.

### Task Evolution & Requirements
* **Task 1 (MVP)**:
  * Utilize the `pyserial` module to receive data from the Processing STM and save it to a `.txt` file.
  * Implement a hardcoded recording duration.
  * Use the `subprocess` module to trigger the compiled C converter.
* **Task 2 (UI & Modes)**:
  * Develop a clear, interactive CLI menu.
  * Support switching between **'Manual Recording Mode'** (user-defined duration) and **'Distance Trigger Mode'**.
  * Generate a **.png waveform plot** (Amplitude vs. Time) that automatically includes standard titles and axis labels.
* **Task 3 & 4 (Scaling)**:
  * Optimize visualization functions to render high-density data arrays (e.g., 44,000 data points per second) without memory overflow.

### Academic Integrity & Citations
* *Base UART reception script built upon the PySerial examples provided in Week 5.*