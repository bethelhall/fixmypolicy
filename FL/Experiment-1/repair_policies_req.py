#!/usr/bin/env python3
"""
policy_repair_batch.py

This script automatically processes multiple AWS IAM policies (0.json to 9.json) with their 
corresponding requirement files (0.json to 9.json) using Claude to repair them based on 
"must allow" and "must deny" requirements.

Features:
- Batch processing of policies 0-9
- Progress tracking with resume capability
- Comprehensive logging
- Results saved to CSV for analysis
- Improved JSON parsing with better error handling

Usage:
    python3 policy_repair_batch.py  # Uses hardcoded directories
"""

import os
import sys
import time
import json
import logging
import re
from functools import wraps
from datetime import datetime
from pathlib import Path
import pandas as pd
from tqdm import tqdm
import anthropic

# === Hardcoded directories ===
POLICY_DIR = "original_policy"
REQUIREMENTS_DIR = "requests"
OUTPUT_DIR = "Results"
LOG_DIR = "logs"
# =============================

# Configure logging¡
def setup_logging(log_dir: str = LOG_DIR):
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f'policy_repair_batch_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return log_file

# API Client Initialization
claude_client = anthropic.Anthropic(
    api_key="REDACTED_API_KEY",
)
claude_model_name = "claude-sonnet-4-20250514"

# Global configurations
MAX_ATTEMPT = 3
DELAY = 5

# Improved policy repair prompt with stricter JSON requirements
POLICY_REPAIR_PROMPT = """
You are an AWS IAM security expert. Your task is to repair a problematic AWS IAM policy based on specific security requirements.

PROBLEMATIC POLICY:
{problematic_policy}

SECURITY REQUIREMENTS:
{requirements}

Your task:
1. Analyze the problematic policy against the security requirements
2. Identify what's wrong or missing in the current policy
3. Generate a repaired policy that meets ALL the security requirements
4. Ensure the policy follows AWS IAM best practices (principle of least privilege, proper resource specification, etc.)

CRITICAL: Return ONLY valid JSON. No explanations, no markdown, no extra text. Start with {{ and end with }}. The JSON must be properly formatted with correct commas, brackets, and quotes.

The policy must include:
- "Version": "2012-10-17"
- "Statement": [array of statement objects]
- Each statement must have "Sid", "Effect", "Action", and "Resource" fields

Repaired Policy:"""

# Retry decorator
def retry(max_attempts=MAX_ATTEMPT, delay=DELAY):
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
                        raise
                    logging.warning(f"Attempt {attempts} failed: {e}. Retrying in {delay} seconds...")
                    time.sleep(delay)
        return wrapper
    return decorator

class ProgressTracker:
    def __init__(self, progress_file: str = os.path.join(OUTPUT_DIR, "progress.json")):
        self.progress_file = progress_file
        self.progress = self._load_progress()
    
    def _load_progress(self):
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {"last_processed": -1, "completed": [], "failed": []}
    
    def save_progress(self):
        os.makedirs(os.path.dirname(self.progress_file), exist_ok=True)
        with open(self.progress_file, 'w') as f:
            json.dump(self.progress, f, indent=2)
    
    def mark_completed(self, idx):
        self.progress["last_processed"] = idx
        if idx not in self.progress["completed"]:
            self.progress["completed"].append(idx)
        if idx in self.progress["failed"]:
            self.progress["failed"].remove(idx)
        self.save_progress()
    
    def mark_failed(self, idx):
        if idx not in self.progress["failed"]:
            self.progress["failed"].append(idx)
        self.save_progress()
    
    def get_next(self):
        return self.progress.get("last_processed", -1) + 1
    
    def is_done(self, idx):
        return idx in self.progress.get("completed", [])


def load_json_file(path: str) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json_file(data: dict, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def format_requirements(requests: dict) -> str:
    if "Requests" not in requests:
        raise ValueError("Invalid request format: missing 'Requests' key")
    
    allow = []
    deny = []
    
    for req in requests["Requests"]:
        if req.get("Effect", "").lower() == "allow":
            allow.append(req)
        else:
            deny.append(req)
    
    lines = []
    if allow:
        lines.append("MUST ALLOW:")
        for i, r in enumerate(allow, 1):
            lines.append(f"  {i}. ID: {r.get('id')} Actions: {r.get('Action')} Resources: {r.get('Resource')}")
    
    if deny:
        lines.append("MUST DENY:")
        for i, r in enumerate(deny, 1):
            lines.append(f"  {i}. ID: {r.get('id')} Actions: {r.get('Action')} Resources: {r.get('Resource')}")
    
    lines.append("ADDITIONAL REQUIREMENTS:")
    lines.extend([
        "  - Version must be '2012-10-17'",
        "  - Explicit Sid values",
        "  - Principle of least privilege",
        "  - Specific ARNs where provided",
        "  - Ensure actions allowed/denied as specified",
    ])
    
    return "\n".join(lines)

def extract_and_validate_json(response_text: str) -> dict:
    """
    Extract and validate JSON from Claude's response with improved error handling.
    """
    # Remove markdown code blocks
    text = response_text.strip()
    
    # Remove markdown formatting
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    
    if text.endswith("```"):
        text = text[:-3]
    
    text = text.strip()
    
    # Find JSON boundaries
    start_idx = text.find("{")
    end_idx = text.rfind("}")
    
    if start_idx == -1 or end_idx == -1:
        raise ValueError(f"No JSON object found in response. Text: {text[:200]}...")
    
    json_text = text[start_idx:end_idx+1]
    
    # Log the extracted JSON for debugging
    logging.debug(f"Extracted JSON: {json_text}")
    
    try:
        parsed_json = json.loads(json_text)
        
        # Validate required fields
        if not isinstance(parsed_json, dict):
            raise ValueError("Response is not a JSON object")
        
        if "Version" not in parsed_json:
            raise ValueError("Missing 'Version' field in policy")
        
        if "Statement" not in parsed_json:
            raise ValueError("Missing 'Statement' field in policy")
        
        if not isinstance(parsed_json["Statement"], list):
            raise ValueError("'Statement' field must be an array")
        
        return parsed_json
        
    except json.JSONDecodeError as e:
        # Try to fix common JSON issues
        logging.warning(f"JSON decode error: {e}. Attempting to fix...")
        
        # Fix trailing commas
        fixed_json = re.sub(r',(\s*[}\]])', r'\1', json_text)
        
        # Fix missing quotes around keys
        fixed_json = re.sub(r'(\w+):', r'"\1":', fixed_json)
        
        # Try parsing again
        try:
            parsed_json = json.loads(fixed_json)
            logging.info("Successfully fixed JSON syntax issues")
            return parsed_json
        except json.JSONDecodeError as e2:
            raise ValueError(f"Failed to parse JSON even after fixes. Original error: {e}. Fixed JSON: {fixed_json}")

@retry()
def repair_policy_with_claude(policy: dict, requests: dict) -> dict:
    policy_json = json.dumps(policy, indent=2)
    req_text = format_requirements(requests)
    prompt = POLICY_REPAIR_PROMPT.format(problematic_policy=policy_json, requirements=req_text)
    
    resp = claude_client.messages.create(
        model=claude_model_name,
        max_tokens=1000,  # Increased token limit
        temperature=0,    # More deterministic output
        system="You are an AWS IAM security expert who repairs policies to meet specific security requirements. Generate only valid JSON policies without any explanatory text.",
        messages=[{"role": "user", "content": prompt}]
    )
    
    # Extract response text
    response_text = ""
    for block in getattr(resp, 'content', []):
        if hasattr(block, 'type') and block.type == 'text':
            response_text += block.text
    
    if not response_text:
        raise ValueError("Empty response from Claude")
    
    # Log raw response for debugging
    logging.debug(f"Raw Claude response: {response_text}")
    
    return extract_and_validate_json(response_text)

def process_single(idx: int) -> dict:
    policy_file = os.path.join(POLICY_DIR, f"{idx}.json")
    req_file = os.path.join(REQUIREMENTS_DIR, f"{idx}.json")
    out_file = os.path.join(OUTPUT_DIR, f"repaired_{idx}.json")
    
    if not os.path.exists(policy_file) or not os.path.exists(req_file):
        raise FileNotFoundError(f"Missing files for index {idx}")
    
    policy = load_json_file(policy_file)
    requests = load_json_file(req_file)
    
    logging.info(f"Processing policy {idx}...")
    repaired = repair_policy_with_claude(policy, requests)
    
    save_json_file(repaired, out_file)
    logging.info(f"Successfully repaired policy {idx}")
    
    return {"index": idx, "output": out_file, "status": "success"}


def main():
    log_file = setup_logging()
    logging.info("Starting batch policy repair")

    # Ensure policy and requirements directories exist
    if not os.path.isdir(POLICY_DIR):
        logging.error(f"Policy directory '{POLICY_DIR}' not found.")
        print(f"Policy directory '{POLICY_DIR}' not found. Exiting.")
        sys.exit(1)
    
    if not os.path.isdir(REQUIREMENTS_DIR):
        logging.error(f"Requirements directory '{REQUIREMENTS_DIR}' not found.")
        print(f"Requirements directory '{REQUIREMENTS_DIR}' not found. Exiting.")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    tracker = ProgressTracker()
    total = 10
    to_proc = [i for i in range(total) if not tracker.is_done(i)]
    logging.info(f"Policies to process: {to_proc}")

    results = []
    failed_policies = []
    
    for idx in tqdm(to_proc, desc="Repairing policies"):
        try:
            res = process_single(idx)
            tracker.mark_completed(idx)
            results.append(res)
            
        except Exception as e:
            logging.error(f"Index {idx} failed: {e}")
            tracker.mark_failed(idx)
            failed_policies.append({"index": idx, "error": str(e), "status": "failed"})
            results.append({"index": idx, "output": None, "status": "failed", "error": str(e)})

    # Save results
    if results:
        df = pd.DataFrame(results)
        out_csv = os.path.join(OUTPUT_DIR, f"repair_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        df.to_csv(out_csv, index=False)
        logging.info(f"Results saved to {out_csv}")

    # Print summary
    successful = len([r for r in results if r.get("status") == "success"])
    failed = len([r for r in results if r.get("status") == "failed"])
    
    print(f"\nBatch processing complete!")
    print(f"Successfully processed: {successful}")
    print(f"Failed: {failed}")
    
    if failed_policies:
        print(f"\nFailed policies:")
        for fp in failed_policies:
            print(f"  Policy {fp['index']}: {fp['error']}")

if __name__ == "__main__":
    main()