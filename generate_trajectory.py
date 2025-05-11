from dataclasses import dataclass
from openai import OpenAI
import json
import base64
import os
from dotenv import load_dotenv
import json
from openai import OpenAI
from PIL import Image
from io import BytesIO
import requests

from prompts import (
    PLAYWRIGHT_CODE_SYSTEM_MSG,
    PLAYWRIGHT_CODE_SYSTEM_MSG_DELETION,
    PLAYWRIGHT_CODE_SYSTEM_MSG_FAILED
)

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

def log_token_usage(resp):
    """Prints a detailed breakdown of token usage from OpenAI response."""
    if hasattr(resp, "usage"):
        input_tokens = getattr(resp.usage, "prompt_tokens", None)
        output_tokens = getattr(resp.usage, "completion_tokens", None)
        total_tokens = getattr(resp.usage, "total_tokens", None)
        print("\n📊 Token Usage Report:")
        print(f"📝 Input (Prompt) tokens: {input_tokens}")
        print(f"💬 Output (Completion) tokens: {output_tokens}")
        print(f"🔢 Total tokens charged: {total_tokens}")
    else:
        print("⚠️ Token usage info not available from API response.")

def resize_image_url(url: str, max_width=512) -> str:
    """Download image from URL, resize it, and return base64 string."""
    response = requests.get(url)
    img = Image.open(BytesIO(response.content))
    
    if img.width > max_width:
        aspect_ratio = img.height / img.width
        new_height = int(max_width * aspect_ratio)
        img = img.resize((max_width, new_height), Image.LANCZOS)
    
    buffer = BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")

def clean_code_response(raw_content):
    """Clean the raw response to extract just the Python code."""
    if not raw_content:
        return None
        
    raw_content = raw_content.strip()
    
    # Remove code block markers
    code_block_markers = [
        "```python",
        "```",
        "⁠ python",
        "⁠  python",
        "python",
        "⁠  ",
        "⁠ "
    ]
    
    for marker in code_block_markers:
        if raw_content.startswith(marker):
            raw_content = raw_content[len(marker):].strip()
            break
    
    # Remove ending markers
    if raw_content.endswith("```"):
        raw_content = raw_content[:-3].strip()
    if raw_content.endswith("⁠  "):
        raw_content = raw_content[:-3].strip()
    
    # Remove any remaining whitespace
    raw_content = raw_content.strip()
    
    # Remove any remaining backticks
    raw_content = raw_content.replace("`", "")
    
    # Debug print
    print("Cleaned code:", raw_content)
    
    return raw_content

def clean_json_response(raw_content):
    raw_content = raw_content.strip()
    if raw_content.startswith("  ⁠json"):
        raw_content = raw_content[len("⁠  json"):].strip()
    if raw_content.endswith("  ⁠"):
        raw_content = raw_content[:-3].strip()
    return raw_content

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@dataclass
class TaskStep:
    action: str
    target: dict
    value: str = None

task_summarizer = []

def is_calendar_event(node):
    """
    Detect calendar events and tasks based on known structure:
    - role is 'button'
    - name contains 'calendar:' and time info like 'am', 'pm', or 'all day'
    """
    name = node.get("name", "").lower()
    return (
        node.get("role") == "button" and
        "calendar:" in name and
        ("am" in name or "pm" in name or "all day" in name)
    )

def prune_ax_tree(node):
    """
    Recursively prune the accessibility tree to:
    - Keep only relevant roles and properties
    - Remove event/task buttons from calendar gridcells
    """

    # Roles we care about
    actionable_roles = {
        "button", "link", "textbox", "checkbox", "radio",
        "combobox", "tab", "switch", "menuitem", "listitem", "option"
    }

    # Properties to keep
    keep_attrs = {"role", "name", "checked", "pressed", "expanded", "haspopup", "children"}

    # Base case: no children
    if "children" not in node:
        return {k: v for k, v in node.items() if k in keep_attrs} if node.get("role") in actionable_roles else None

    # Recursively prune children
    pruned_children = []
    for child in node["children"]:
        if is_calendar_event(child):
            continue  # ❌ Remove scheduled calendar events/tasks
        pruned = prune_ax_tree(child)
        if pruned:
            pruned_children.append(pruned)

    # Keep this node if it's actionable or has valid children
    if node.get("role") in actionable_roles or pruned_children:
        pruned_node = {k: v for k, v in node.items() if k in keep_attrs and k != "children"}
        if pruned_children:
            pruned_node["children"] = pruned_children
        return pruned_node
    return None


def chat_ai_playwright_code(accessibility_tree=None, previous_steps=None, taskGoal=None, image_path=None, last_failed_code=None, is_deletion_task=False):
    """Get Playwright code directly from GPT to execute the next step."""
    # Base system message
    if last_failed_code:
        if is_deletion_task:
            base_system_message = PLAYWRIGHT_CODE_SYSTEM_MSG_FAILED + "\n\n" + PLAYWRIGHT_CODE_SYSTEM_MSG_DELETION
            print("\n🤖 Using FAILED DELETION task prompt")
        else:
            base_system_message = PLAYWRIGHT_CODE_SYSTEM_MSG_FAILED
            print("\n🤖 Using FAILED ATTEMPT prompt")
    elif is_deletion_task:
        base_system_message = PLAYWRIGHT_CODE_SYSTEM_MSG_DELETION
        print("\n🤖 Using DELETION task prompt")
    else:
        base_system_message = PLAYWRIGHT_CODE_SYSTEM_MSG
        print("\n🤖 Using STANDARD task prompt")

    # # Append failed code note
    # if last_failed_code:
    #     base_system_message += f"\n\n Last attempt failed with this code:\n{last_failed_code}\nPlease provide a different solution and do NOT use this same code again."

    if accessibility_tree is not None and previous_steps is not None and image_path:
        try:
            # Resize and encode image
            with Image.open(image_path) as img:
                if img.width > 512:
                    aspect_ratio = img.height / img.width
                    new_height = int(512 * aspect_ratio)
                    img = img.resize((512, new_height), Image.LANCZOS)
                
                buffer = BytesIO()
                img.save(buffer, format="PNG", optimize=True)
                resized_image = base64.b64encode(buffer.getvalue()).decode("utf-8")

            # Add last failed attempt information to the prompt if available
            # failed_attempt_info = ""
            # if last_failed_code:
            #     failed_attempt_info = f"\n\nLast attempt failed with this code: {last_failed_code}\nPlease provide a different solution that DOESN'T USE THIS FAILED code."
            # print(base_system_message + failed_attempt_info)
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": base_system_message 
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"Task goal: {taskGoal}\nPrevious steps: {json.dumps(previous_steps, indent=2)}\n\nAccessibility tree: {json.dumps(accessibility_tree, indent=2)}"
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{resized_image}"
                                }
                            }
                        ]
                    }
                ]
            )
            log_token_usage(response)
            raw_content = clean_code_response(response.choices[0].message.content)
            print("Raw Playwright code:", raw_content)
            
            if raw_content.strip() == "null":
                print("✅ Task goal appears to be complete. No further action needed.")
                return None
                
            return raw_content.strip()
            
        except Exception as e:
            print(f"❌ Error in GPT call: {str(e)}")
    else:
        print("⚠️ Error: Missing accessibility tree, previous steps, or image path")