from playwright.sync_api import sync_playwright
import json
import os
from datetime import datetime
import json
import uuid
import pprint

from generate_trajectory import chat_ai_playwright_code

# ========== CONFIGURABLE PARAMETERS ==========
PHASE = 1
START_IDX = 4
END_IDX = 5
MAX_RETRIES = 9

# Execution Modes:
# 0 - Automatic Mode: Processes all instructions without manual intervention
# 1 - Interactive Mode: Requires Enter press after each instruction for manual review
MODE = 0

from config import  RESULTS_DIR

def generate_trajectory_loop(user_data_dir, chrome_path, phase, start_idx, end_idx):
    # Load the appropriate phase file
    phase_file = os.path.join(RESULTS_DIR, f"instructions_phase{phase}.json")
    
    try:
        with open(phase_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: Could not find {phase_file}")
        return
    except json.JSONDecodeError:
        print(f"❌ Error: {phase_file} is not valid JSON")
        return

    # Flatten all instructions into a single list with persona info
    all_instructions = []
    for persona_data in data:
        persona = persona_data['persona']
        instructions = persona_data[f'phase{phase}_augmented_instructions']
        original_instructions = persona_data[f'phase{phase}_instructions']
        
        for orig_instr, aug_instr in zip(original_instructions, instructions):
            all_instructions.append({
                'persona': persona,
                'original_instruction': orig_instr,
                'augmented_instruction': aug_instr
            })

    # Start browser once for all instructions
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            executable_path=chrome_path,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        try:
            # Process only the specified range of instructions
            for idx, instruction_data in enumerate(all_instructions[start_idx:end_idx], start=start_idx):
                persona = instruction_data['persona']
                original_instruction = instruction_data['original_instruction']
                augmented_instruction = instruction_data['augmented_instruction']
                
                # Generate new UUID for each instruction
                run_uuid = str(uuid.uuid4())
                instruction_dir = os.path.join(RESULTS_DIR, run_uuid)
                os.makedirs(instruction_dir, exist_ok=True)
                
                print(f"\n🔄 Processing instruction {idx + 1}")
                print(f"👤 Persona: {persona}")
                print(f"📝 Original Instruction: {original_instruction}")
                print(f"🔄 Augmented Instruction: {augmented_instruction}")
                print(f"Run UUID: {run_uuid} | Files will be saved in: {instruction_dir}")
                
                # Create a new page for each instruction
                page = browser.new_page()
                page.goto("https://www.google.com/calendar/")
                task_summarizer = []  # This will now store dictionaries instead of just code
                max_retries = MAX_RETRIES
                
                try:
                    page.wait_for_selector('[aria-label*="Google Account"]', timeout=300000)
                    print("✅ Logged in successfully!")

                    while True:
                        # Take screenshot with UUID-based path
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        screenshot_path = os.path.join(instruction_dir, f"step_{timestamp}.png")
                        page.screenshot(path=screenshot_path)

                        # Get accessibility tree
                        tree = page.accessibility.snapshot()
                        
                        # Check if this is a deletion task
                        is_deletion_task = 'delete' in augmented_instruction.lower()
                        if is_deletion_task:
                            print("\n🔍 Deletion task detected in instruction:", augmented_instruction)

                        # Get Playwright code from GPT
                        playwright_code = chat_ai_playwright_code(
                            accessibility_tree=tree,
                            previous_steps=task_summarizer,
                            taskGoal=augmented_instruction,
                            image_path=screenshot_path,
                            is_deletion_task=is_deletion_task
                        )

                        if playwright_code is None:
                            print("Task completed!")
                            # Save task summarizer in UUID directory
                            summary_path = os.path.join(instruction_dir, f"task_summarizer.txt")
                            with open(summary_path, "w", encoding="utf-8") as f:
                                f.write(f"Persona: {persona}\n")
                                f.write(f"Original Instruction: {original_instruction}\n")
                                f.write(f"Augmented Instruction: {augmented_instruction}\n")
                                f.write("\nTask Steps:\n")
                                for step in task_summarizer:
                                    f.write("\n=== Step ===\n")
                                    f.write(f"Playwright Code: {step['code']}\n")
                                    f.write(f"Accessibility Tree: {pprint.pformat(step['axtree'], indent=2, width=120)}\n")
                            print(f"Task summarizer saved to {summary_path}")
                            break

                        # Rest of the execution code...
                        print(f"🤖 Executing Playwright code: {playwright_code}")
                        
                        retry_count = 0
                        last_failed_code = None
                        while retry_count < max_retries:
                            try:
                                exec(playwright_code)
                                # Store both code and accessibility tree
                                task_summarizer.append({
                                    'code': playwright_code,
                                    'axtree': tree
                                })
                                break
                            except Exception as e:
                                retry_count += 1
                                last_failed_code = playwright_code
                                
                                if retry_count < max_retries:
                                    print(f"⚠️ Attempt {retry_count} failed: {str(e)}")
                                    print("🔄 Retrying with new GPT-generated code...")
                                    
                                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                    screenshot_path = os.path.join(instruction_dir, f"retry_{timestamp}.png")
                                    page.screenshot(path=screenshot_path)
                                    tree = page.accessibility.snapshot()

                                    playwright_code = chat_ai_playwright_code(
                                        accessibility_tree=tree,
                                        previous_steps=task_summarizer,
                                        taskGoal=augmented_instruction,
                                        image_path=screenshot_path,
                                        last_failed_code=last_failed_code,
                                        is_deletion_task=is_deletion_task
                                    )
                                    
                                    if playwright_code is None:
                                        print("Task completed!")
                                        break
                                        
                                    print(f"🤖 New attempt with code: {playwright_code}")
                                    try:
                                        exec(playwright_code)
                                        # Store both code and accessibility tree for retry
                                        task_summarizer.append({
                                            'code': playwright_code,
                                            'axtree': tree
                                        })
                                        break
                                    except Exception as e:
                                        print(f"⚠️ New attempt also failed: {str(e)}")
                                else:
                                    print(f"❌ All {max_retries} attempts failed. Moving to next instruction.")
                                    # Delete the instruction directory since the data is incomplete
                                    try:
                                        import shutil
                                        shutil.rmtree(instruction_dir)
                                        print(f"🗑️ Deleted incomplete instruction directory: {instruction_dir}")
                                    except Exception as e:
                                        print(f"⚠️ Failed to delete directory {instruction_dir}: {str(e)}")
                                    # Break out of the while True loop to move to next instruction
                                    break

                        # Only wait if we haven't hit max retries
                        if retry_count < max_retries:
                            page.wait_for_timeout(2000)

                except Exception as e:
                    print(f"❌ Error: {str(e)}")
                    # Delete the instruction directory if there's an error
                    try:
                        import shutil
                        shutil.rmtree(instruction_dir)
                        print(f"🗑️ Deleted incomplete instruction directory: {instruction_dir}")
                    except Exception as del_e:
                        print(f"⚠️ Failed to delete directory {instruction_dir}: {str(del_e)}")
                finally:
                    # Close the page but keep the browser open
                    page.close()
                    # Only prompt for Enter in Interactive Mode
                    if MODE == 1:
                        input("🔚 Press Enter to continue to next instruction...")

        except Exception as e:
            print(f"❌ Error: {str(e)}")
        finally:
            # Always prompt before closing browser
            input("🔚 Press Enter to close browser...")
            browser.close()

def main():
    chrome_profile_path = os.getenv("CHROME_PROFILE_PATH")
    chrome_executable_path = os.getenv("CHROME_EXECUTABLE_PATH")
    
    # Example usage:
    # phase: 1 or 2
    # start_idx: starting index of instructions to process
    # end_idx: ending index of instructions to process
    generate_trajectory_loop(chrome_profile_path, chrome_executable_path, PHASE, START_IDX, END_IDX)

if __name__ == "__main__":
    main()