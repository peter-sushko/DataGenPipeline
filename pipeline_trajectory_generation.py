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
START_IDX = 0
END_IDX = 2
MAX_RETRIES = 9
ACTION_TIMEOUT = 30000  # 30 seconds timeout for actions
# Execution Modes:
# 0 - Automatic Mode: Processes all instructions without manual intervention
# 1 - Interactive Mode: Requires Enter press after each instruction for manual review
MODE = 0

from config import RESULTS_DIR

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
        url = persona_data['url']  # Get URL from persona data
        instructions = persona_data['augmented_instructions']
        original_instructions = persona_data['instructions']
        
        for orig_instr, aug_instr in zip(original_instructions, instructions):
            all_instructions.append({
                'persona': persona,
                'url': url,  # Include URL in instruction data
                'original_instruction': orig_instr,
                'augmented_instruction': aug_instr
            })

    # Check if the specified range is empty
    if start_idx >= len(all_instructions) or end_idx <= start_idx or end_idx > len(all_instructions):
        print(f"❌ Error: Invalid instruction range. Total instructions: {len(all_instructions)}, Requested range: {start_idx} to {end_idx}")
        return

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
                should_continue = True
                persona = instruction_data['persona']
                url = instruction_data['url']  # Get URL for this instruction
                original_instruction = instruction_data['original_instruction']
                augmented_instruction = instruction_data['augmented_instruction']
                
                # Generate new UUID for each instruction
                run_uuid = str(uuid.uuid4())
                instruction_dir = os.path.join(RESULTS_DIR, run_uuid)
                os.makedirs(instruction_dir, exist_ok=True)
                print(f"////////////////////////////////////////////////////////////")
                print(f"\n🔄 Processing instruction {idx + 1}")
                print(f"👤 Persona: {persona}")
                print(f"🌐 Starting URL: {url}")
                print(f"📝 Original Instruction: {original_instruction}")
                print(f"🔄 Augmented Instruction: {augmented_instruction}")
                print(f"Run UUID: {run_uuid} | Files will be saved in: {instruction_dir}")
                print(f"////////////////////////////////////////////////////////////")
                # Create a new page for each instruction
                page = browser.new_page()
                page.set_default_timeout(ACTION_TIMEOUT)  # Set default timeout for all actions
                page.goto(url)  # Use URL from instruction data
                execution_history = []  # For passing to chat_ai_playwright_code
                task_summarizer = []  # For documentation
                max_retries = MAX_RETRIES
                
                try:
                    # Wait for login to complete
                    page.wait_for_selector('[aria-label*="Google Account"]', timeout=300000)
                    print("✅ Logged in successfully!")
                    while should_continue:
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
                        gpt_response = chat_ai_playwright_code(
                            accessibility_tree=tree,
                            previous_steps=execution_history,  # Use execution_history instead
                            taskGoal=augmented_instruction,
                            image_path=screenshot_path,
                            is_deletion_task=is_deletion_task,
                            failed_codes= None
                        )

                        if "summary_instruction" in gpt_response:
                            print("Task completed!")
                            # Save task summarizer in UUID directory
                            summary_path = os.path.join(instruction_dir, f"task_summarizer.json")
                            
                            # Create a structured JSON object
                            summary_data = {
                                "persona": persona,
                                "original_instruction": original_instruction,
                                "augmented_instruction": augmented_instruction,
                                "url": url,
                                "final_instruction": gpt_response['summary_instruction'],
                                "task_steps": [
                                    {
                                        "step": step['step'],
                                        "code": step['code'],
                                        "accessibility_tree": step['axtree']
                                    } for step in task_summarizer
                                ]
                            }
                            
                            # Write JSON file with proper formatting
                            with open(summary_path, "w", encoding="utf-8") as f:
                                json.dump(summary_data, f, indent=2, ensure_ascii=False)
                            print(f"Task summarizer saved to {summary_path}")
                            should_continue = False
                            break

                        # Rest of the execution code...
                        description = gpt_response["description"]
                        code = gpt_response["code"]
                        
                        retry_count = 0
                        failed_codes = []
                        while retry_count < max_retries and should_continue:
                            try:
                                print(f"🤖 Executing Description: {description}")
                                print(f"🤖 Executing Playwright code: {code}")
                                exec(code)
                                # Store in both arrays
                                execution_history.append({
                                    'step': description,
                                    'code': code
                                })
                                task_summarizer.append({
                                    'step': description,
                                    'code': code,
                                    'axtree': tree
                                })
                                break
                            except Exception as e:
                                retry_count += 1
                                failed_codes.append(code)
                                print(f"Failed codes: {failed_codes}")
                                
                                if retry_count < max_retries:
                                    print(f"⚠️ Attempt {retry_count} failed: {str(e)}")
                                    print("🔄 Retrying with new GPT-generated code...")
                                    
                                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                    screenshot_path = os.path.join(instruction_dir, f"retry_{timestamp}.png")
                                    page.screenshot(path=screenshot_path)
                                    tree = page.accessibility.snapshot()

                                    gpt_response = chat_ai_playwright_code(
                                        accessibility_tree=tree,
                                        previous_steps=execution_history,  # Use execution_history
                                        taskGoal=augmented_instruction,
                                        image_path=screenshot_path,
                                        failed_codes=failed_codes,
                                        is_deletion_task=is_deletion_task
                                    )
                                    
                                    if "summary_instruction" in gpt_response:
                                        print("Task completed!")
                                        should_continue = False
                                        break
                                    new_description = gpt_response["description"]
                                    new_code = gpt_response["code"]
                                    print(f"🤖 New Attempt Description: {new_description}")
                                    print(f"🤖 New attempt with code: {new_code}")    
                                    # Update the code variable with the new code
                                    code = new_code
                                    description = new_description
                                    try:
                                        exec(new_code)
                                        # Store in both arrays
                                        execution_history.append({
                                            'step': new_description,
                                            'code': new_code
                                        })
                                        task_summarizer.append({
                                            'step': new_description,
                                            'code': new_code,
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
                                    should_continue = False
                                    break  # Break out of the while True loop to move to next instruction

                        # Only wait if we haven't hit max retries
                        if retry_count < max_retries and should_continue:
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
                    should_continue = False
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