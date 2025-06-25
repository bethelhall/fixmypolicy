"""
policy_repair_claude.py

This script uses Claude to repair AWS IAM policies by:
  1. Reading problematic policy files from a fixed folder.
  2. Using Claude to:
       a. Understand the policy's intent (what it's supposed to do)
       b. Identify where/why it's failing
       c. Generate a repaired policy
  3. Reading the corresponding ground truth healthy policy from a different directory
  4. Running Quacky to compare the repaired vs. ground truth policies
  5. Logging and saving the analysis results to CSV and tracking progress

Usage:
  python3 policy_repair_claude.py
"""



import os
import sys
import time
import json
import logging
import subprocess
import re
from pathlib import Path
from functools import wraps
import pandas as pd
from tqdm import tqdm
from csv import QUOTE_NONE
import anthropic

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('policy_repair.log'),
        logging.StreamHandler()
    ]
)

# API Client Initialization
claude_client = anthropic.Anthropic(
    api_key="REDACTED_API_KEY",
)
claude_model_name = "claude-sonnet-4-20250514"

# Global configurations
MAX_ATTEMPT = 3
DELAY = 5

# Hardcoded intent - REMOVE THIS WHEN USING JSON FILE
# CURRENT_INTENT = "trying to restrict access to Sagemaker notebook using SSO identity's UserID."

def load_intents_from_file(file_path: str) -> dict:
    """Load intents from either JSON or text file."""
    try:
        file_path = os.path.abspath(file_path)
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Intent file not found: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Try to parse as JSON first
        if file_path.endswith('.json'):
            try:
                intents = json.loads(content)
                # Convert string keys to integers for consistency
                result = {int(k): v for k, v in intents.items()}
                logging.info(f"Loaded {len(result)} intents from JSON file: {file_path}")
                return result
            except json.JSONDecodeError as e:
                logging.error(f"Invalid JSON in {file_path}: {e}")
                return {}
        
        # Parse as text file (original format)
        intents = {}
        lines = content.strip().split('\n')
        current_intent_num = None
        current_intent_text = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Check if line starts with a number followed by a period
            if re.match(r'^\d+\.', line):
                # Save previous intent if exists
                if current_intent_num is not None and current_intent_text:
                    intents[current_intent_num] = ' '.join(current_intent_text).strip()
                
                # Start new intent
                parts = line.split('.', 1)
                current_intent_num = int(parts[0])
                current_intent_text = [parts[1].strip()] if len(parts) > 1 and parts[1].strip() else []
            else:
                # Continue current intent text
                if current_intent_num is not None:
                    current_intent_text.append(line)
        
        # Save the last intent
        if current_intent_num is not None and current_intent_text:
            intents[current_intent_num] = ' '.join(current_intent_text).strip()
        
        logging.info(f"Loaded {len(intents)} intents from text file: {file_path}")
        return intents
        
    except Exception as e:
        logging.error(f"Error loading intents from {file_path}: {e}")
        return {}

def get_intent_for_policy(policy_filename: str, intents: dict) -> str:
    """Get intent for a policy file."""
    stem = Path(policy_filename).stem
    try:
        policy_num = int(stem)
        return intents.get(policy_num, f"Policy {policy_num} - Intent not specified")
    except ValueError:
        return f"Policy {policy_filename} - Intent not specified"

# Single prompt for intent-based policy repair
POLICY_REPAIR_PROMPT = """
You are given a problematic AWS IAM policy and its intended purpose. Your task is to repair the policy to achieve the stated intent.

INTENT: {intent}

PROBLEMATIC POLICY:
{original_policy}

Generate a repaired AWS IAM policy that:
1. Achieves the intended purpose stated above
2. Fixes any syntax errors, misconfigurations, or security issues
3. Follows AWS IAM best practices (principle of least privilege, proper resource specification, etc.)
4. Is valid JSON that can be directly used in AWS IAM

Generate ONLY the repaired JSON policy without any explanatory text.

Repaired Policy:"""

def retry(max_attempts=MAX_ATTEMPT, delay=DELAY):
    """Decorator to retry a function on exception up to max_attempts."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempts = 0
            while attempts < max_attempts:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    attempts += 1
                    if attempts == max_attempts:
                        raise e
                    logging.warning(f"Attempt {attempts} failed: {e}. Retrying in {delay} seconds...")
                    time.sleep(delay)
        return wrapper
    return decorator

def slugify(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", text).strip().lower()

# Path configurations - UPDATE THESE TO YOUR ABSOLUTE PATHS
problematic_policy_folder = os.path.abspath("/home/bhall2/Documents/fixmypolicy/FL/Experiment-3/Data/problematic_policy")
ground_truth_folder = os.path.abspath("/home/bhall2/Documents/fixmypolicy/FL/Experiment-3/Data/ground_truth")
intent_file_path = os.path.abspath("/home/bhall2/Documents/fixmypolicy/FL/Experiment-3/Data/intent.txt")  # Text file containing policy intents
quacky_path = os.path.abspath("/home/bhall2/Documents/fixmypolicy/quacky/src/quacky.py")
working_directory = os.path.abspath("/home/bhall2/Documents/fixmypolicy/FL/Experiment-3")
repaired_policy_temp_path = os.path.abspath("/home/bhall2/Documents/fixmypolicy/FL/Experiment-3/Data/repaired_policy/repaired_policy.json")

RESULT_DIR = Path(os.path.abspath("/home/bhall2/Documents/fixmypolicy/FL/Experiment-3/Data/Result"))
if not RESULT_DIR.exists():
    logging.info(f"Creating result directory: {RESULT_DIR}")
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

MODEL_SLUG = slugify(claude_model_name)
result_table_path = RESULT_DIR / f"{MODEL_SLUG}_repair_results.csv"
progress_file_path = RESULT_DIR / f"{MODEL_SLUG}_repair_progress.json"

@retry(max_attempts=MAX_ATTEMPT, delay=DELAY)
def generate_repaired_policy(original_policy: str, intent: str) -> str:
    """Use Claude to generate a repaired policy based on the intent."""
    prompt_filled = POLICY_REPAIR_PROMPT.format(
        intent=intent,
        original_policy=original_policy
    )
    
    response = claude_client.messages.create(
        model=claude_model_name,
        max_tokens=600,
        system="You are an AWS IAM security expert who repairs problematic policies to achieve their intended purpose. Generate only valid JSON policies without explanatory text.",
        messages=[{"role": "user", "content": prompt_filled}]
    )

    text = ""
    if response and response.content:
        for block in response.content:
            if block.type == "text":
                text = block.text.strip()
                break

    if not text:
        raise ValueError("Unable to extract repaired policy from Claude response")

    # Strip markdown fences if present
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    # Extract JSON
    if text.startswith("{") and text.endswith("}"):
        json_part = text
    else:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            logging.error(f"Full Claude response: {text}")
            raise ValueError(f"No JSON found in Claude response: {text[:200]}...")
        json_part = text[start : end + 1].strip()

    try:
        json.loads(json_part)
        return json_part
    except json.JSONDecodeError as e:
        logging.error(f"JSON parsing failed: {e}")
        logging.error(f"Extracted JSON: {json_part}")
        raise ValueError(f"Invalid JSON from Claude: {e}")

def save_repaired_policy(policy_content: str, file_path: str):
    """Save repaired JSON policy to disk."""
    file_path = os.path.abspath(file_path)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    obj = json.loads(policy_content)
    with open(file_path, "w") as f:
        json.dump(obj, f, indent=2)
    logging.info(f"Repaired policy saved to {file_path}")

@retry(max_attempts=MAX_ATTEMPT, delay=DELAY)
def run_final_analysis(repaired_policy_path: str, ground_truth_path: str) -> str:
    """Run Quacky analysis comparing repaired policy to ground truth."""
    # ensure Quacky runs from its own src dir so it finds re2smt/pcre.lark
    quacky_dir = os.path.dirname(os.path.abspath(quacky_path))
    command = [
        "python3", quacky_path,
        "-p1", os.path.abspath(repaired_policy_path),
        "-p2", os.path.abspath(ground_truth_path),
        "-b", "100"
    ]
    result = subprocess.run(
        command,
        cwd=quacky_dir,
        capture_output=True,
        text=True
    )
    logging.info("Quacky Analysis Output (Repaired vs Ground Truth):")
    logging.info(result.stdout)
    if result.stderr:
        logging.error(f"Quacky stderr: {result.stderr}")
    return result.stdout


def get_progress() -> dict:
    """Load last_processed from progress file."""
    if os.path.exists(progress_file_path):
        with open(progress_file_path, 'r') as f:
            return json.load(f)
    return {"last_processed": 0}

def update_progress(last_processed: int):
    """Write last_processed to progress file."""
    with open(progress_file_path, 'w') as f:
        json.dump({"last_processed": last_processed}, f)

def read_policy_file(file_path: str) -> str:
    """Read JSON policy from disk."""
    with open(file_path, 'r') as file:
        return file.read()

def find_ground_truth_policy(policy_filename: str) -> str:
    """Find the corresponding ground truth policy file."""
    # Assuming ground truth files have the same name as problematic ones
    ground_truth_path = os.path.abspath(os.path.join(ground_truth_folder, policy_filename))
    if os.path.exists(ground_truth_path):
        return ground_truth_path
    
    # Alternative: try with different extensions or prefixes
    base_name = Path(policy_filename).stem
    for ext in ['.json', '_fixed.json', '_healthy.json']:
        alt_path = os.path.abspath(os.path.join(ground_truth_folder, f"{base_name}{ext}"))
        if os.path.exists(alt_path):
            return alt_path
    
    # List available files for debugging
    if os.path.exists(ground_truth_folder):
        available_files = [f for f in os.listdir(ground_truth_folder) if f.endswith('.json')]
        logging.info(f"Available ground truth files: {available_files}")
    
    raise FileNotFoundError(f"Ground truth policy not found for {policy_filename} in {ground_truth_folder}")

@retry(max_attempts=MAX_ATTEMPT, delay=DELAY)
def process_policy_repair(problematic_policy_path: str, policy_filename: str, intent: str) -> dict:
    """End-to-end policy repair process: repair, compare with ground truth."""
    start_time = time.time()
    
    # Read problematic policy
    problematic_policy = read_policy_file(problematic_policy_path)
    logging.info(f"Processing problematic policy: {policy_filename}")
    logging.info(f"Intent: {intent}")
    
    # Generate repaired policy
    logging.info("Generating repaired policy...")
    repaired_policy = generate_repaired_policy(problematic_policy, intent)
    logging.info("Repaired Policy JSON:")
    logging.info(repaired_policy)
    
    # Save repaired policy to temporary file for Quacky analysis
    save_repaired_policy(repaired_policy, repaired_policy_temp_path)
    
    # Find and read ground truth policy
    ground_truth_path = find_ground_truth_policy(policy_filename)
    ground_truth_policy = read_policy_file(ground_truth_path)
    logging.info(f"Found ground truth policy: {ground_truth_path}")
    
    # Run Quacky analysis comparing repaired policy to ground truth
    final_analysis = run_final_analysis(repaired_policy_temp_path, ground_truth_path)
    total_time = time.time() - start_time
    
    return {
        "policy_filename": policy_filename,
        "model_name": claude_model_name,
        "intent": intent,
        "problematic_policy": problematic_policy,
        "repaired_policy": repaired_policy,
        "ground_truth_policy": ground_truth_policy,
        "ground_truth_path": ground_truth_path,
        "quacky_analysis": final_analysis,
        "total_processing_time_seconds": total_time
    }

# ─── Main Execution ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Policy Repair Script Configuration:")
    print("=" * 80)
    print(f"Problematic policies folder: {problematic_policy_folder}")
    print(f"Ground truth policies folder: {ground_truth_folder}")
    print(f"Intent file: {intent_file_path}")
    print(f"Quacky script path: {quacky_path}")
    print(f"Working directory: {working_directory}")
    print(f"Results directory: {RESULT_DIR}")
    print("=" * 80)
    
    # Load intents from file (supports both JSON and text formats)
    logging.info("Loading policy intents from file...")
    intents = load_intents_from_file(intent_file_path)
    if not intents:
        print(f"ERROR: No intents loaded from {intent_file_path}")
        print("Please check that the file exists and contains properly formatted intents.")
        print("Expected format for text files: '3. intent text here...'")
        print("Or use a JSON file with {\"3\": \"intent text\", ...} format")
        sys.exit(1)
    
    print(f"Loaded intents for policies: {sorted(intents.keys())}")
    print()
    
    # Validate all paths exist
    paths_to_check = [
        ("Problematic policy folder", problematic_policy_folder),
        ("Ground truth folder", ground_truth_folder),
        ("Intent file", intent_file_path),
        ("Quacky script", quacky_path),
        ("Working directory", working_directory)
    ]
    
    for name, path in paths_to_check:
        if not os.path.exists(path):
            print(f"ERROR: {name} not found at: {path}")
            sys.exit(1)
        else:
            print(f"✓ {name} found: {path}")
    
    print()
    
    # Get list of problematic policy files
    policy_files = sorted(
        [f for f in os.listdir(problematic_policy_folder) if f.endswith(".json")],
        key=lambda x: int(Path(x).stem) if Path(x).stem.isdigit() else x
    )
    total = len(policy_files)
    print(f"Found {total} problematic policy files in '{problematic_policy_folder}'.")
    
    if total == 0:
        print("No JSON policy files found. Please check the problematic_policy_folder path.")
        sys.exit(1)
    
    # Filter to only process policies that have intents defined
    available_policy_numbers = set()
    policies_with_intents = []
    
    for fname in policy_files:
        stem = Path(fname).stem
        if stem.isdigit():
            policy_num = int(stem)
            if policy_num in intents:
                policies_with_intents.append(fname)
                available_policy_numbers.add(policy_num)
            else:
                print(f"Warning: No intent found for policy {policy_num} ({fname})")
        else:
            print(f"Warning: Skipping non-numeric policy file: {fname}")
    
    print(f"Processing {len(policies_with_intents)} policies with defined intents: {sorted(available_policy_numbers)}")
    
    if not policies_with_intents:
        print("No policies found with matching intents. Check that:")
        print("- Policy files are named like '3.json', '4.json', etc.")
        print("- Intent file contains matching policy numbers")
        sys.exit(1)
    
    # Handle progress tracking
    progress = get_progress()
    last_processed = progress.get("last_processed", 0)
    start_index = 0
    
    if last_processed:
        try:
            # Find the index of the last processed file
            for i, fname in enumerate(policy_files):
                stem = Path(fname).stem
                if (stem.isdigit() and int(stem) == last_processed) or stem == str(last_processed):
                    start_index = i + 1
                    break
        except:
            print(f"Warning: Could not find last processed file; starting from beginning")
    
    if start_index >= total:
        print(f"All {total} policies processed. Nothing to do.")
        sys.exit(0)
    
    print(f"Starting from policy index {start_index} ({policy_files[start_index] if start_index < total else 'N/A'})")
    
    # Initialize CSV file with headers
    required_columns = [
        "policy_filename", "model_name", "intent", "problematic_policy", 
        "repaired_policy", "ground_truth_policy", "ground_truth_path", 
        "quacky_analysis", "total_processing_time_seconds"
    ]
    
    if not os.path.exists(result_table_path) or os.stat(result_table_path).st_size == 0:
        pd.DataFrame(columns=required_columns).to_csv(result_table_path, index=False)
    else:
        # Ensure all required columns exist
        df_existing = pd.read_csv(result_table_path, quoting=QUOTE_NONE, sep=",", low_memory=False)
        for col in set(required_columns) - set(df_existing.columns):
            df_existing[col] = ""
        df_existing.to_csv(result_table_path, index=False)
    
    processed = 0
    failed = 0
    
    for i in tqdm(range(start_index, total), desc="Repairing policies"):
        fname = policies_with_intents[i]
        problematic_policy_path = os.path.abspath(os.path.join(problematic_policy_folder, fname))
        stem = Path(fname).stem
        
        logging.info(f"\n{'='*60}")
        logging.info(f"Processing policy repair: {fname}")
        logging.info(f"{'='*60}")
        
        try:
            # Get intent for this policy
            intent = get_intent_for_policy(fname, intents)
            logging.info(f"Intent for {fname}: {intent}")
            
            entry = process_policy_repair(problematic_policy_path, fname, intent)
            
            # Save results to CSV
            pd.DataFrame([entry]).to_csv(
                result_table_path,
                mode="a",
                header=False,
                index=False
            )
            
            # Update progress
            if stem.isdigit():
                update_progress(int(stem))
            else:
                update_progress(i)
            
            processed += 1
            logging.info(f"Successfully processed {fname}")
            
        except Exception as e:
            failed += 1
            logging.error(f"Failed to process {fname}: {e}")
            logging.error(f"Exception details:", exc_info=True)
            continue
    
    logging.info(f"\n{'='*60}")
    logging.info("POLICY REPAIR PROCESSING COMPLETE")
    logging.info(f"{'='*60}")
    logging.info(f"Total processed: {processed}")
    logging.info(f"Total failed: {failed}")
    logging.info(f"Results saved to: {result_table_path}")
    
    next_policy = (
        policies_with_intents[start_index + processed]
        if processed + start_index < total else "All complete"
    )
    print(f"Processed {processed} policies, {failed} failed. Next run will start from: {next_policy}")