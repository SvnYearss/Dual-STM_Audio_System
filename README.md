# ECE2071 Project S1 2026 - Dual-STM Audio System

Welcome to the Dual-STM Audio System project repository. This project is developed by a 5-person team, with each member responsible for a specific subsystem.

## 📁 Repository Structure

The repository is modularized based on team responsibilities to prevent merge conflicts and maintain a clean codebase.

- **`01_Sampling_Data_Acquisition/`**: [Owner 1] Sampling STM Project. Responsible for ADC configuration and data acquisition.
- **`02_Signal_Processing_Sensors/`**: [Owner 2] Processing STM algorithms and sensor logic.
- **`03_PC_File_Conversion/`**: [Owner 3] PC-side backend C code for binary to WAV conversion.
- **`04_Python_CLI_Visualization/`**: [Owner 4] PC-side frontend CLI and Python waveform plotting.
- **`05_System_Comm_Protocols/`**: [Owner 5] Cross-system communication protocols (UART/SPI) and packet formatting.
- **`Docs/`**: Stores block diagrams, raw project specifications (in `Docs/raw/`), and progress records.

*(See `SCHEMA.md` for a more detailed technical tree diagram).*

## 🌿 Version Control (Branching Strategy)

We use **branches** as our primary version control mechanism. To keep the project organized and avoid interrupting each other's work, please follow this branching workflow:

### How to use this repository:

1. **Clone the repository:**
   ```bash
   git clone <repository_url>
   cd Dual-STM_Audio_System
   ```

2. **Create a branch for your module:**
   When starting your work, create a dedicated branch corresponding to your subsystem:
   ```bash
   git checkout main
   git pull origin main
   
   # Examples of branch names per owner:
   git checkout -b feature/01-sampling       
   git checkout -b feature/02-processing     
   git checkout -b feature/03-pc-backend     
   git checkout -b feature/04-python-cli     
   git checkout -b feature/05-protocols     
   ```

3. **Work within your dedicated folder:**
   To minimize git merge conflicts, please restrict your code changes to your assigned directory (e.g., Owner 1 should only modify code inside `01_Sampling_Data_Acquisition/`).

4. **Commit and Push your changes:**
   ```bash
   git add .
   git commit -m "Brief description of the update"
   git push -u origin <your-branch-name>
   ```

5. **Merge to Main:**
   Once your subsystem implementation is tested and functional, create a Pull Request (or Merge Request) into the `main` branch. Ensure your code is reviewed before merging.

## 🚀 Getting Started

Before running or making changes to a specific submodule, navigate into its folder and consult its respective `README.md` file for dedicated setup instructions, dependencies, and execution commands.
