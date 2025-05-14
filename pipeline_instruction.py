import random
import os
from dotenv import load_dotenv
load_dotenv()

import json
from datasets import load_dataset
from tqdm import tqdm
from generate_instruction import generate_instructions
from prompt_augmentation import generate_augmented_instructions
import openai
from playwright.sync_api import sync_playwright

# ========== CONFIGURABLE PARAMETERS ==========
from config import (
    NUM_PERSONAS,
    PHASE1_NUM_INSTRUCTIONS,
    PHASE2_NUM_INSTRUCTIONS,
    RESULTS_DIR,
    URL
)

chrome_profile_path = os.getenv("CHROME_PROFILE_PATH")
chrome_executable_path = os.getenv("CHROME_EXECUTABLE_PATH")
PERSONAHUB_DATA_PATH = "persona.jsonl"  # Path to PersonaHub data file
SCREENSHOT_PATH = "screenshot.png"
PHASE = 1

def write_documentation(persona, url, instructions, augmented_instructions, results_dir=RESULTS_DIR, filename=f"instructions_phase{PHASE}.json"):
    import json

    # Ensure the results directory exists
    os.makedirs(results_dir, exist_ok=True)
    file_path = os.path.join(results_dir, filename)

    # Load existing data if file exists, else start with empty list
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = []
    else:
        data = []

    # Append new entry
    data.append({
        "persona": persona,
        "url": url,
        "instructions": instructions,
        "augmented_instructions": augmented_instructions
    })

    # Write back to file
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def main():
    # Ensure results directory exists
    os.makedirs(RESULTS_DIR, exist_ok=True)

    dataset = load_dataset("proj-persona/PersonaHub", data_files=PERSONAHUB_DATA_PATH)['train']
    shuffled = dataset.shuffle(seed=random.randint(0, 9999))  # Use a random seed each run
    personas = shuffled[:NUM_PERSONAS]['persona']
    num_instructions = PHASE2_NUM_INSTRUCTIONS if PHASE == 2 else PHASE1_NUM_INSTRUCTIONS

    print(personas)

    for persona in tqdm(personas, desc="Processing personas"):
        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=chrome_profile_path,
                executable_path=chrome_executable_path,
                headless=False,
                args=["--disable-blink-features=AutomationControlled"]
            )
            page = browser.new_page()
            page.goto(URL)

                
            # Take screenshot
            screenshot_path = SCREENSHOT_PATH
            page.screenshot(path=screenshot_path)
                
            # Generate instructions and augment them
            instructions = generate_instructions(
                persona, PHASE, num_instructions=num_instructions, screenshot_path=screenshot_path
            )

            print(instructions)
                
            augmented_instructions = generate_augmented_instructions(
                instructions, screenshot_path=screenshot_path
            )

            print(augmented_instructions)

            write_documentation(persona, URL, instructions, augmented_instructions)
                
            browser.close()

if __name__ == "__main__":
    main()
