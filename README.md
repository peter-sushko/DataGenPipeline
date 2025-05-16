# Prompt Augmentation Pipeline

This repository contains a pipeline for generating and executing web automation instructions based on different personas. The system uses GPT-4 to generate and augment instructions, then executes them using Playwright.

## Overview

The pipeline consists of two main components:

1. **Pipeline Instruction Generator** (`pipeline_instruction.py`)
   - Generates initial and augmented instructions for different personas
   - Uses GPT-4 to create contextually relevant instructions
   - Supports two phases of instruction generation

2. **Pipeline Trajectory Generator** (`pipeline_trajectory_generation.py`)
   - Executes the generated instructions using Playwright
   - Creates detailed trajectories of the automation process
   - Saves screenshots and execution logs for each instruction

## Setup

1. Install required dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Set up environment variables in `.env`:

   ```env
   CHROME_PROFILE_PATH=/path/to/chrome/profile
   CHROME_EXECUTABLE_PATH=/path/to/chrome/executable
   OPENAI_API_KEY=your_openai_api_key
   ```

## Step-by-Step Usage Flow

Step 1: Configure Parameters  
Edit `config.py` to define global settings:

```python
NUM_PERSONAS = 4                  # Number of personas to process
PHASE1_NUM_INSTRUCTIONS = 5       # Number of instructions per persona in Phase 1
PHASE2_NUM_INSTRUCTIONS = 5       # Number of instructions per persona in Phase 2
RESULTS_DIR = "results"           # Folder to store outputs
```

Step 2: Generate Phase 1 Instructions  
Run the following script to generate Phase 1 instructions:

```bash
python pipeline_instruction.py
```

This script will:
- Loop through `NUM_PERSONAS` from the PersonaHub dataset
- Generate `PHASE1_NUM_INSTRUCTIONS` per persona
- Save the output to: `results/instructions_phase1.json`

Step 3: Generate Phase 1 Trajectories  
Open `pipeline_trajectory_generation.py` and configure:

```python
PHASE = 1
START_IDX = 0           # Starting instruction index
END_IDX = 5             # Ending instruction index (exclusive)
MODE = 0                # 0: Automatic execution, 1: Interactive mode
```

Then run:

```bash
python pipeline_trajectory_generation.py
```

This will:
- Load `instructions_phase1.json`
- Execute each instruction using Playwright
- Save browser trajectories, screenshots, and logs into uniquely named folders (UUID-based) inside `results/`

Step 4: Generate Phase 2 Instructions  
Update the phase to `PHASE = 2` in `config.py`, then rerun:

```bash
python pipeline_instruction.py
```

Output will be saved to: `results/instructions_phase2.json`

Step 5: Generate Phase 2 Trajectories  
Repeat the trajectory generation step for Phase 2:
- Update `PHASE = 2` in `pipeline_trajectory_generation.py`
- Set new values for `START_IDX` and `END_IDX`
- Run the script again:

```bash
python pipeline_trajectory_generation.py
```

This will:
- Read instructions from `instructions_phase2.json`
- Generate second-phase trajectories conditioned on modified web states

## Output Artifacts

Each instruction will generate:
- A `.json` file with logs and metadata
- Screenshots (initial + final state)
- A step-by-step interaction trace (clicks, types, scrolls, etc.)

## Summary

This pipeline allows you to:
- Create scalable, persona-grounded natural instructions
- Generate real executable trajectories through Playwright
- Iterate and augment your dataset with Phase 1 → Phase 2 logic
