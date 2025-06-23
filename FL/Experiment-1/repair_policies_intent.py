

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
import openai
from openai import OpenAI
from google import generativeai as genai
import argparse

claude_client = anthropic.Anthropic(
    api_key="#your-anthropic-api-key#",
)
claude_model_name = "claude-3-5-sonnet-20241022"

#Global configurations
MAX_ATTEMPT = 3
DELAY       = 5

PROMPT = (
    "Generate a comprehensive and unambiguous natural language description of the provided AWS IAM policy. "
    "The description must meticulously detail every component of the policy so that another language model can "
    "perfectly reconstruct the original policy, at least semantically.\n\n"
    "{policy_content}\n\nDescription:"
)

SYSTEM_PROMPT = """
Reconstruct an AWS IAM policy in JSON format based on the provided natural language description. The generated policy must semantically match the description, including all specified effects, actions, resources, principals (if any), and conditions.
Output Format:
    Provide only the JSON policy. Do not include any explanatory text before or after the JSON block.
    Example response format:
    {
    "Version": "2012-10-17",
    "Statement": [
        {
        "Effect": "Allow",
        "Action": ["s3:GetObject"],
        "Resource": "arn:aws:s3:::example-bucket/*"
        }
    ]
    }
Ensure the generated policy matches the description and follows AWS IAM structure.
""".strip()



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


policy_folder         = "Folder with JSON policy files"               
quacky_path           = "Path to Quacky script"   
working_directory     = "Working dir for Quacky" 
generated_policy_path = "Where to save generated policy JSON"  

RESULT_DIR         = Path("your-result-directory")
if not RESULT_DIR.is_absolute():
    RESULT_DIR = Path(__file__).parent / RESULT_DIR
if not RESULT_DIR.exists():
    logging.info(f"Creating result directory: {RESULT_DIR}")
RESULT_DIR.mkdir(parents=True, exist_ok=True)
result_table_path  = None
progress_file_path = None 




#Claude

@retry(max_attempts=MAX_ATTEMPT, delay=DELAY)
def get_policy_description_claude(policy_content: str) -> str:
    """Use Claude to generate a short policy description using PROMPT."""
    try:
        normalized = policy_content.encode("utf-8").decode("utf-8")
    except UnicodeError:
        normalized = policy_content.encode("ascii", "ignore").decode("ascii")

    prompt_filled = PROMPT.format(policy_content=normalized)
    response = claude_client.messages.create(
        model=claude_model_name,
        max_tokens=400,
        system="",
        messages=[{"role": "user", "content": prompt_filled}]
    )
    if response and response.content:
        for block in response.content:
            if block.type == "text":
                return block.text.strip()
    raise ValueError("Unable to extract text from Claude response")

@retry(max_attempts=MAX_ATTEMPT, delay=DELAY)
def generate_new_policy_claude(description: str) -> str:
    """Use Claude to reconstruct JSON from description, using SYSTEM_PROMPT."""
    combined_prompt = SYSTEM_PROMPT + "\n\n" + description
    response = claude_client.messages.create(
        model=claude_model_name,
        max_tokens=800,
        system=combined_prompt,
        messages=[{"role": "user", "content": ""}]
    )

    text = ""
    if response and response.content:
        for block in response.content:
            if block.type == "text":
                text = block.text.strip()
                break

    if not text:
        raise ValueError("Unable to extract text from Claude response")

    # Strip markdown fences if present
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

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


def get_policy_description(policy_content: str) -> str:
    """Dispatch to the chosen model's description function."""
    if ACTIVE_MODEL == "claude":
        return get_policy_description_claude(policy_content)
    else:
        raise ValueError(f"Unknown model: {ACTIVE_MODEL}")
    

def generate_new_policy(description: str) -> str:
    """Dispatch to the chosen model's policy-generation function."""
    if ACTIVE_MODEL == "claude":
        return generate_new_policy_claude(description)
    else:
        raise ValueError(f"Unknown model: {ACTIVE_MODEL}")


# Quacky

def save_generated_policy(policy_content: str, file_path: str):
    """Save JSON policy to disk."""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    obj = json.loads(policy_content)
    with open(file_path, "w") as f:
        json.dump(obj, f, indent=2)
    logging.info(f"Generated policy saved to {file_path}")
    

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

@retry(max_attempts=MAX_ATTEMPT, delay=DELAY)
def process_policy(policy_path: str, size: int) -> dict:
    """End-to-end: read, describe, regenerate, compare, record."""
    start_time = time.time()
    original = read_policy_file(policy_path)

    desc = get_policy_description(original)
    new_pol = generate_new_policy(desc)
    logging.info("Generated Policy JSON:")
    logging.info(new_pol)
    save_generated_policy(new_pol, generated_policy_path)


    total_time = time.time() - start_time

    return {
        "model_name": POLICY_MODEL,
        "Original Policy": original,
        "Generated Policy": new_pol,
        "Policy Description": desc,
        "Size": size,
        "Total Processing Time (seconds)": total_time
    }

def read_policy_file(file_path: str) -> str:
    """Read JSON policy from disk."""
    with open(file_path, 'r') as file:
        return file.read()


# ─── Main Execution ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Process AWS IAM policies with various LLMs."
    )
    parser.add_argument(
        "--model",
        choices=["gpt_turbo", "deepseek", "gpt", "claude"],
        required=True,
        help="Which LLM to use for processing policies."
    )

    args = parser.parse_args()
    ACTIVE_MODEL = args.model

    # Map ACTIVE_MODEL → actual LLM name
  
    if ACTIVE_MODEL == "claude":
        POLICY_MODEL = claude_model_name
    else:
        raise ValueError(f"Unknown model: {ACTIVE_MODEL}")

    MODEL_SLUG         = slugify(POLICY_MODEL)
    result_table_path  = RESULT_DIR / f"{MODEL_SLUG}.csv"
    progress_file_path = RESULT_DIR / f"{MODEL_SLUG}.json"

    size = 500
    policy_files = sorted(
        [f for f in os.listdir(policy_folder) if f.endswith(".json")],
        key=lambda x: int(Path(x).stem)
    )
    total = len(policy_files)
    print(f"Found {total} policy files in '{policy_folder}'.")

    progress = get_progress()
    last_stem = progress.get("last_processed", 0)
    start_index = 0
    if last_stem:
        try:
            start_index = next(
                i for i, fname in enumerate(policy_files)
                if int(Path(fname).stem) == last_stem
            )
        except StopIteration:
            print(f"Warning: {last_stem}.json not found; starting at 0")

    if start_index >= total:
        print(f"All {total} policies processed. Nothing to do.")
        sys.exit(0)

    print(f"Resuming from policy number {policy_files[start_index]} (index {start_index})")

    required_columns = [
        "Policy Number", "model_name", "Original Policy", "Generated Policy",
        "Policy Description", "Size", "Final Analysis", "Total Processing Time (seconds)"
    ]
    if not os.path.exists(result_table_path) or os.stat(result_table_path).st_size == 0:
        pd.DataFrame(columns=required_columns).to_csv(result_table_path, index=False)
    else:
        df_existing = pd.read_csv(
            result_table_path, quoting=QUOTE_NONE, sep=",", low_memory=False
        )
        for col in set(required_columns) - set(df_existing.columns):
            df_existing[col] = ""
        df_existing.to_csv(result_table_path, index=False)

    processed = 0
    for i in tqdm(range(start_index, total), desc="Processing policies"):
        fname = policy_files[i]
        policy_path = os.path.join(policy_folder, fname)
        stem = int(Path(fname).stem)
        logging.info(f"\nProcessing policy: {fname}")

        try:
            entry = process_policy(policy_path, size)
            entry["Policy Number"] = stem
            pd.DataFrame([entry]).to_csv(
                result_table_path,
                mode="a",
                header=False,
                index=False
            )
            update_progress(stem)
            processed += 1
        except Exception as e:
            logging.error(f"Failed to process {fname}: {e}")
            continue

    logging.info("\nProcessing complete. Final results table saved to: " + str(result_table_path))
    next_policy = (
        policy_files[start_index + processed]
        if processed + start_index < total else "done"
    )
    print(f"Processed {processed} policies. Next run will start from policy number {next_policy}")