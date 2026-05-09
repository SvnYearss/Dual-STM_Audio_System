# System Communication Protocols
**Feature Lead:** [Member Name]

### Core Responsibilities
Responsible for designing, optimizing, and maintaining the communication pipelines (Board-to-Board and Board-to-PC). This is critical for preventing data bottlenecks and packet loss.

### Task Evolution & Requirements
* **Milestone (Week 6)**:
  * Establish a Token Ring UART network.
  * **HD Requirement**: Implement an XOR bitwise **Checksum** for data error detection.
  * **HD Requirement**: Engineer a **Dynamic Head STM** architecture where any board can become the master node without reprogramming.
* **Task 1 & 2**:
  * Ensure stable UART transmission of data and state-control commands (Trigger signals).
* **Task 3 & 4 (Advanced HD Challenge)**:
  * **Architectural Overhaul**: Replace the inter-board UART with high-speed **SPI (Serial Peripheral Interface)** to support 44 ksps data loads.
  * Implement **DMA (Direct Memory Access)** to offload data transfer tasks from the CPU.
  * Push the Board-to-PC UART baud rate to its maximum stable limit (up to **921600 bps**).

### Current Task 3 Interface Contract
* Inter-board audio/control link uses **SPI1, 16-bit frames**.
* Sampling STM is the SPI master and clocks one 10-bit ADC sample per timer tick.
* Processing STM is the SPI slave and returns the current command word (`'M'` start, `'S'` stop) during each SPI frame.
* Pin map for both STM32L432KC boards:
  * `PB3` = `SPI1_SCK`
  * `PB4` = `SPI1_MISO` from Processing STM to Sampling STM
  * `PB5` = `SPI1_MOSI` from Sampling STM to Processing STM
  * Common `GND` is required.
* Processing STM sends the PC stream over `USART2` at `921600` baud after outlier rejection, moving average filtering, 2:1 downsampling, and 10-bit to 8-bit rescaling.
* PC-to-Processing commands remain on `USART2`: `'M'` manual start, `'S'` stop, `'D'` distance mode, `'T'` distance test, and `'C'` followed by one byte for the distance threshold in centimetres.
* Because `PB5` is now SPI MOSI, the Processing STM HC-SR04 trigger pin is `PA4`; echo remains on `PA5/TIM2_CH1`.

### Academic Integrity & Citations
* *SPI and Low-Layer (LL) driver implementations adapted from the Week 7 Lab Activity.*
* *XOR Checksum logic derived from the ECE2071 Milestone Full Requirements specification.*
