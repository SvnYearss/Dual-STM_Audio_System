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

### Academic Integrity & Citations
* *SPI and Low-Layer (LL) driver implementations adapted from the Week 7 Lab Activity.*
* *XOR Checksum logic derived from the ECE2071 Milestone Full Requirements specification.*