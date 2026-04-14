# PC File Conversion & Persistence
**Feature Lead:** [Member Name]

### Core Responsibilities
Responsible for the back-end data processing on the PC side. This involves writing a compiled C program to interpret raw binary serial data and format it into standard, usable file types.

### Task Evolution & Requirements
* **Task 1 (MVP)**:
  * Develop a C program to convert raw serial bytes into a playable **.WAV file**.
  * Properly construct the 44-byte WAV header based on the incoming sample rate and bit depth.
* **Task 2 (UI & Modes)**:
  * Expand output capabilities to generate **.csv files** containing the processed audio data.
  * Ensure the first row of the CSV explicitly indicates the audio sample rate.
  * Implement automated file naming conventions (must include Team ID and sample rate).
* **Task 4 (Advanced HD Challenge)**:
  * Refactor the C program to accurately parse and compile **12-bit depth** audio streams at 44 ksps.

### Academic Integrity & Citations
* *WAV file header structure constructed using concepts introduced in the Week 6 Lab Manual.*