#!/usr/bin/env python3
"""
iterative_policy_repair.py

This script iteratively repairs AWS IAM policies using Claude and validates them with SMT solver.
It attempts up to 5 iterations per policy until 100% accuracy is achieved.

Features:
- Baseline validation (original policy accuracy)
- Iterative repair with accuracy feedback
- SMT solver validation integration
- Comprehensive tracking of all iterations
- Results saved to CSV for analysis
- Progress tracking with resume capability

Usage:
    python3 iterative_policy_repair.py
"""

import os
import sys
import time
import json
import logging
import re
import subprocess
import tempfile
import shutil
from functools import wraps
from datetime import datetime
from pathlib import Path
import pandas as pd
from tqdm import tqdm
import anthropic


POLICY_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-1/original_policy"
REQUIREMENTS_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-1/requests/request-80"
OUTPUT_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-1/results/result-80"
LOG_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-1/logs/log-80"
TEMP_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-1/temp_validation/val-80"
QUACKY_SRC_DIR = "/home/bhall2/Documents/fixmypo`licy/quacky/src"
SMT_VALIDATOR_SCRIPT = "/home/bhall2/Documents/fixmypolicy/quacky/src/validate_requests.py"



# Global configurations
MAX_ITERATIONS = 5
MAX_ATTEMPT = 3
DELAY = 5
TARGET_ACCURACY = 100.0

# Configure logging
def setup_logging(log_dir: str = LOG_DIR):
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f'iterative_repair_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
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

# Simple policy repair prompt without feedback
def get_policy_repair_prompt(problematic_policy, requirements):
    prompt = f"""
You are an AWS IAM security expert. Your task is to repair a problematic AWS IAM policy using best security practices so that the requests will be properly authorized. Do not copy the requests into the policy unless needed.

PROBLEMATIC POLICY:
{problematic_policy}

SECURITY REQUIREMENTS:
{requirements}:
CRITICAL: Return ONLY valid JSON. No explanations, no markdown, no extra text. Start with {{ and end with }}. The JSON must be properly formatted with correct commas, brackets, and quotes.
Output format:
{{"Version": "2012-10-17", "Statement": [ ... ]}}

Repaired Policy:"""
    
    return prompt

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

class IterativeProgressTracker:
    def __init__(self, progress_file: str = os.path.join(OUTPUT_DIR, "iterative_progress.json")):
        self.progress_file = progress_file
        self.progress = self._load_progress()
    
    def _load_progress(self):
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {
            "last_processed": -1, 
            "completed": [], 
            "failed": [],
            "policy_iterations": {}  # Track iterations per policy
        }
    
    def save_progress(self):
        os.makedirs(os.path.dirname(self.progress_file), exist_ok=True)
        with open(self.progress_file, 'w') as f:
            json.dump(self.progress, f, indent=2)
    
    def mark_completed(self, idx, baseline_accuracy, final_accuracy, iterations_used):
        self.progress["last_processed"] = idx
        if idx not in self.progress["completed"]:
            self.progress["completed"].append(idx)
        if idx in self.progress["failed"]:
            self.progress["failed"].remove(idx)
        
        self.progress["policy_iterations"][str(idx)] = {
            "status": "completed",
            "baseline_accuracy": baseline_accuracy,
            "final_accuracy": final_accuracy,
            "iterations_used": iterations_used
        }
        self.save_progress()
    
    def mark_failed(self, idx, baseline_accuracy, final_accuracy, iterations_used):
        if idx not in self.progress["failed"]:
            self.progress["failed"].append(idx)
        
        self.progress["policy_iterations"][str(idx)] = {
            "status": "failed",
            "baseline_accuracy": baseline_accuracy,
            "final_accuracy": final_accuracy,
            "iterations_used": iterations_used
        }
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
        "  - Principle of least privilege",
        "  - Specific ARNs where provided",
        "  - Ensure actions allowed/denied as specified",
    ])
    
    return "\n".join(lines)

def extract_and_validate_json(response_text: str) -> dict:
    """Extract and validate JSON from Claude's response with improved error handling."""
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
    prompt = get_policy_repair_prompt(policy_json, req_text)
    
    resp = claude_client.messages.create(
        model=claude_model_name,
        max_tokens=9000,
        temperature=0,
        system="You are an AWS IAM security expert who repairs policies to meet specific security requirements. Do not hard-code the requests into the policy. Generate only valid JSON policies without any explanatory text.",
        messages=[{"role": "user", "content": prompt}]
    )
    
    # Extract response text
    response_text = ""
    for block in getattr(resp, 'content', []):
        if hasattr(block, 'type') and block.type == 'text':
            response_text += block.text
    
    if not response_text:
        raise ValueError("Empty response from Claude")
    
    logging.debug(f"Raw Claude response: {response_text}")
    return extract_and_validate_json(response_text)

def run_smt_validator(policy_file: str, requests_file: str) -> dict:
    """Run the SMT validator and return parsed results."""
    try:
        # Change to the Quacky source directory
        original_dir = os.getcwd()
        os.chdir(QUACKY_SRC_DIR)
        
        # Create output directory if it doesn't exist
        quacky_output_dir = os.path.join(OUTPUT_DIR, "Quacky_output")
        os.makedirs(quacky_output_dir, exist_ok=True)
        
        # Create unique output file name
        timestamp = int(time.time())
        pid = os.getpid()
        output_file_path = os.path.join(quacky_output_dir, f"temp_validation_{pid}_{timestamp}.txt")
        
        # Run the validator with your exact command structure
        cmd = [
            'python3', 'validate_requests.py',
            '-p1', policy_file,
            '--requests', requests_file,
            '-s'
        ]
        
        logging.debug(f"Running SMT validator: cd {QUACKY_SRC_DIR} && {' '.join(cmd)} > {output_file_path}")
        
        # Run the command and redirect output to file
        with open(output_file_path, 'w') as output_file:
            result = subprocess.run(cmd, stdout=output_file, stderr=subprocess.PIPE, text=True, timeout=300)
        
        # Change back to original directory
        os.chdir(original_dir)
        
        if result.returncode != 0:
            logging.error(f"SMT validator failed: {result.stderr}")
            # Clean up temp file
            if os.path.exists(output_file_path):
                os.unlink(output_file_path)
            raise Exception(f"SMT validator failed: {result.stderr}")
        
        # Read the output file to parse results
        with open(output_file_path, 'r') as f:
            output_content = f.read()
        
        logging.debug(f"Validator output saved to: {output_file_path}")
        logging.debug(f"Raw validator output (first 1000 chars): {output_content[:1000]}")
        
        # Parse the output to extract accuracy information
        output_lines = output_content.split('\n')
        
        # Look for accuracy information in the output
        accuracy = 0.0
        total_requests = 0
        correct_count = 0
        incorrect_count = 0
        misclassified_allow_to_deny = 0
        misclassified_deny_to_allow = 0
        
        # Parse the specific format from your validator
        in_analysis_section = False
        found_analysis_section = False
        
        for i, line in enumerate(output_lines):
            line = line.strip()
            
            # Check if we're in the analysis section
            if "INDIVIDUAL REQUEST ANALYSIS" in line:
                in_analysis_section = True
                found_analysis_section = True
                logging.debug(f"Found analysis section at line {i}: {line}")
                continue
            elif line.startswith("=") and in_analysis_section and len(line) > 10:
                # End of analysis section (long line of equals)
                if any(phrase in ''.join(output_lines[i:i+5]) for phrase in ["Results saved", "saved to HOME"]):
                    logging.debug(f"End of analysis section at line {i}")
                    break
            
            if in_analysis_section:
                logging.debug(f"Parsing analysis line {i}: {line}")
                if line.startswith("Total Individual Requests:"):
                    total_match = re.search(r'(\d+)', line)
                    if total_match:
                        total_requests = int(total_match.group(1))
                        logging.debug(f"Found total requests: {total_requests}")
                elif line.startswith("Correct Classifications:"):
                    correct_match = re.search(r'(\d+)', line)
                    if correct_match:
                        correct_count = int(correct_match.group(1))
                        logging.debug(f"Found correct count: {correct_count}")
                elif line.startswith("Incorrect Classifications:"):
                    incorrect_match = re.search(r'(\d+)', line)
                    if incorrect_match:
                        incorrect_count = int(incorrect_match.group(1))
                        logging.debug(f"Found incorrect count: {incorrect_count}")
                elif line.startswith("Overall Accuracy:"):
                    accuracy_match = re.search(r'(\d+\.?\d*)%', line)
                    if accuracy_match:
                        accuracy = float(accuracy_match.group(1))
                        logging.debug(f"Found accuracy: {accuracy}%")
                elif line.startswith("Expected Allow -> Got Deny:"):
                    allow_deny_match = re.search(r'(\d+)', line)
                    if allow_deny_match:
                        misclassified_allow_to_deny = int(allow_deny_match.group(1))
                        logging.debug(f"Found allow->deny: {misclassified_allow_to_deny}")
                elif line.startswith("Expected Deny -> Got Allow:"):
                    deny_allow_match = re.search(r'(\d+)', line)
                    if deny_allow_match:
                        misclassified_deny_to_allow = int(deny_allow_match.group(1))
                        logging.debug(f"Found deny->allow: {misclassified_deny_to_allow}")
        
        if not found_analysis_section:
            logging.warning("Could not find 'INDIVIDUAL REQUEST ANALYSIS' section in output")
            logging.debug("Searching for any accuracy information...")
            # Fallback: search entire output for accuracy
            for line in output_lines:
                if "Overall Accuracy:" in line or "Accuracy:" in line:
                    accuracy_match = re.search(r'(\d+\.?\d*)%', line)
                    if accuracy_match:
                        accuracy = float(accuracy_match.group(1))
                        logging.debug(f"Found fallback accuracy: {accuracy}%")
                        break
        
        # Clean up temporary file (disabled for debugging)
        # if os.path.exists(output_file_path):
        #     os.unlink(output_file_path)
        
        # Keep the file for debugging and log its location
        logging.info(f"Validator output file kept for debugging: {output_file_path}")
        
        # Validate that we got meaningful results
        if total_requests == 0:
            logging.warning("No requests found in validator output - check parsing logic")
            logging.warning(f"Output file location: {output_file_path}")
            logging.debug(f"Raw output preview: {output_content[:500]}...")
            # Also save the full output to a debug file
            debug_file = output_file_path.replace('.txt', '_debug.txt')
            with open(debug_file, 'w') as f:
                f.write("=== FULL VALIDATOR OUTPUT ===\n")
                f.write(output_content)
            logging.warning(f"Full output saved to: {debug_file}")
        
        logging.info(f"Validation completed - Accuracy: {accuracy}%, Total: {total_requests}, Correct: {correct_count}, Incorrect: {incorrect_count}")
        logging.debug(f"Misclassified - Allow→Deny: {misclassified_allow_to_deny}, Deny→Allow: {misclassified_deny_to_allow}")
        
        return {
            'accuracy': accuracy,
            'total_requests': total_requests,
            'correct': correct_count,
            'incorrect': incorrect_count,
            'misclassified_allow_to_deny': misclassified_allow_to_deny,
            'misclassified_deny_to_allow': misclassified_deny_to_allow,
            'raw_output': output_content,
            'output_file': output_file_path
        }
        
    except subprocess.TimeoutExpired:
        # Change back to original directory in case of timeout
        try:
            os.chdir(original_dir)
        except:
            pass
        logging.error("SMT validator timed out")
        raise Exception("SMT validator timed out")
    except Exception as e:
        # Change back to original directory in case of error
        try:
            os.chdir(original_dir)
        except:
            pass
        logging.error(f"Error running SMT validator: {e}")
        raise

def validate_baseline_policy(idx: int, policy_file: str, req_file: str) -> dict:
    """Validate the original policy without any modifications to get baseline accuracy."""
    logging.info(f"Validating baseline (original) policy for index {idx}...")
    
    try:
        # Run SMT validator on original policy
        baseline_results = run_smt_validator(policy_file, req_file)
        baseline_accuracy = baseline_results['accuracy']
        
        logging.info(f"Policy {idx} - Baseline accuracy: {baseline_accuracy:.1f}%")
        print(f"Policy {idx} - Baseline accuracy: {baseline_accuracy:.1f}%")
        
        return {
            'policy_idx': idx,
            'iteration': 0,  # 0 represents baseline
            'accuracy': baseline_accuracy,
            'total_requests': baseline_results['total_requests'],
            'correct': baseline_results['correct'],
            'incorrect': baseline_results['incorrect'],
            'misclassified_allow_to_deny': baseline_results['misclassified_allow_to_deny'],
            'misclassified_deny_to_allow': baseline_results['misclassified_deny_to_allow'],
            'policy_file': policy_file,
            'is_baseline': True
        }
        
    except Exception as e:
        logging.error(f"Error validating baseline policy {idx}: {e}")
        return {
            'policy_idx': idx,
            'iteration': 0,
            'accuracy': 0.0,
            'error': str(e),
            'is_baseline': True
        }

def process_policy_iteratively(idx: int) -> dict:
    """Process a single policy with iterative repair and validation."""
    policy_file = os.path.join(POLICY_DIR, f"{idx}.json")
    req_file = os.path.join(REQUIREMENTS_DIR, f"{idx}.json")
    
    if not os.path.exists(policy_file) or not os.path.exists(req_file):
        raise FileNotFoundError(f"Missing files for index {idx}")
    
    # Load initial policy and requests
    original_policy = load_json_file(policy_file)
    requests = load_json_file(req_file)
    
    logging.info(f"Starting iterative repair for policy {idx}...")
    print(f"\n{'='*50}")
    print(f"Processing Policy {idx}")
    print(f"{'='*50}")
    
    # Step 1: Validate baseline (original policy)
    baseline_result = validate_baseline_policy(idx, policy_file, req_file)
    baseline_accuracy = baseline_result.get('accuracy', 0.0)
    
    # Track all iterations (including baseline)
    iteration_results = [baseline_result]
    accuracy_progression = [baseline_accuracy]  # Track accuracy over iterations
    
    current_policy = original_policy.copy()
    final_accuracy = baseline_accuracy
    
    # Check if baseline already meets target
    if baseline_accuracy >= TARGET_ACCURACY:
        logging.info(f"Policy {idx} already meets target accuracy at baseline!")
        print(f"Policy {idx} already meets target accuracy at baseline!")
        
        return {
            'index': idx,
            'status': 'success',
            'baseline_accuracy': baseline_accuracy,
            'final_accuracy': baseline_accuracy,
            'iterations_used': 0,
            'iteration_results': iteration_results,
            'accuracy_progression': accuracy_progression,
            'final_policy_file': policy_file  # Original policy is already perfect
        }
    
    # Step 2: Iterative repair
    for iteration in range(1, MAX_ITERATIONS + 1):
        logging.info(f"Policy {idx} - Iteration {iteration}/{MAX_ITERATIONS}")
        print(f"  Iteration {iteration}/{MAX_ITERATIONS}...")
        
        try:
            # Repair policy with Claude (same prompt every time)
            logging.info(f"Repairing policy with Claude (iteration {iteration})...")
            repaired_policy = repair_policy_with_claude(current_policy, requests)
            
            # Save temporary repaired policy for validation
            temp_policy_file = os.path.join(TEMP_DIR, f"policy_{idx}_iter_{iteration}.json")
            os.makedirs(TEMP_DIR, exist_ok=True)
            save_json_file(repaired_policy, temp_policy_file)
            
            # Validate with SMT solver
            logging.info(f"Validating with SMT solver (iteration {iteration})...")
            validation_results = run_smt_validator(temp_policy_file, req_file)
            
            accuracy = validation_results['accuracy']
            logging.info(f"Iteration {iteration} accuracy: {accuracy:.1f}%")
            print(f"    Accuracy: {accuracy:.1f}%")
            
            # Record this iteration
            iteration_record = {
                'policy_idx': idx,
                'iteration': iteration,
                'accuracy': accuracy,
                'total_requests': validation_results['total_requests'],
                'correct': validation_results['correct'],
                'incorrect': validation_results['incorrect'],
                'misclassified_allow_to_deny': validation_results['misclassified_allow_to_deny'],
                'misclassified_deny_to_allow': validation_results['misclassified_deny_to_allow'],
                'policy_file': temp_policy_file,
                'is_baseline': False
            }
            iteration_results.append(iteration_record)
            accuracy_progression.append(accuracy)
            
            final_accuracy = accuracy
            
            # Check if we achieved target accuracy
            if accuracy >= TARGET_ACCURACY:
                logging.info(f"Target accuracy achieved for policy {idx} in {iteration} iterations!")
                print(f"    ✓ Target accuracy achieved in {iteration} iterations!")
                
                # Save final repaired policy
                final_output_file = os.path.join(OUTPUT_DIR, f"repaired_{idx}_final.json")
                save_json_file(repaired_policy, final_output_file)
                
                return {
                    'index': idx,
                    'status': 'success',
                    'baseline_accuracy': baseline_accuracy,
                    'final_accuracy': accuracy,
                    'iterations_used': iteration,
                    'iteration_results': iteration_results,
                    'accuracy_progression': accuracy_progression,
                    'final_policy_file': final_output_file
                }
            
            # For next iteration, use the ORIGINAL policy again (not the repaired one)
            # This ensures we start fresh each time with the same prompt
            current_policy = original_policy.copy()
            
        except Exception as e:
            logging.error(f"Error in iteration {iteration} for policy {idx}: {e}")
            print(f"    ✗ Error in iteration {iteration}: {str(e)[:100]}...")
            iteration_record = {
                'policy_idx': idx,
                'iteration': iteration,
                'accuracy': 0.0,
                'error': str(e),
                'is_baseline': False
            }
            iteration_results.append(iteration_record)
            accuracy_progression.append(0.0)
    
    # If we reach here, we didn't achieve target accuracy
    logging.warning(f"Failed to achieve target accuracy for policy {idx} after {MAX_ITERATIONS} iterations. Final accuracy: {final_accuracy:.1f}%")
    print(f"    ✗ Failed to achieve target accuracy. Best: {final_accuracy:.1f}%")
    
    # Save best attempt
    if iteration_results:
        best_iteration = max([r for r in iteration_results if not r.get('is_baseline', False)], 
                           key=lambda x: x.get('accuracy', 0), default=None)
        if best_iteration and 'policy_file' in best_iteration and os.path.exists(best_iteration['policy_file']):
            final_output_file = os.path.join(OUTPUT_DIR, f"repaired_{idx}_best.json")
            shutil.copy2(best_iteration['policy_file'], final_output_file)
        else:
            # Save original policy as fallback
            final_output_file = os.path.join(OUTPUT_DIR, f"repaired_{idx}_original.json")
            save_json_file(original_policy, final_output_file)
    else:
        final_output_file = os.path.join(OUTPUT_DIR, f"repaired_{idx}_original.json")
        save_json_file(original_policy, final_output_file)
    
    return {
        'index': idx,
        'status': 'failed',
        'baseline_accuracy': baseline_accuracy,
        'final_accuracy': final_accuracy,
        'iterations_used': MAX_ITERATIONS,
        'iteration_results': iteration_results,
        'accuracy_progression': accuracy_progression,
        'final_policy_file': final_output_file
    }

def main():
    log_file = setup_logging()
    logging.info("Starting iterative policy repair system")
    
    # Ensure required directories exist
    for directory in [POLICY_DIR, REQUIREMENTS_DIR]:
        if not os.path.isdir(directory):
            logging.error(f"Directory '{directory}' not found.")
            print(f"Directory '{directory}' not found. Exiting.")
            sys.exit(1)
    
    # Check if SMT validator script exists
    if not os.path.exists(SMT_VALIDATOR_SCRIPT):
        logging.error(f"SMT validator script '{SMT_VALIDATOR_SCRIPT}' not found.")
        print(f"SMT validator script '{SMT_VALIDATOR_SCRIPT}' not found. Exiting.")
        sys.exit(1)
    
    # Create output directories
    for directory in [OUTPUT_DIR, TEMP_DIR]:
        os.makedirs(directory, exist_ok=True)
    
    # Initialize progress tracker
    tracker = IterativeProgressTracker()
    total = 10
    to_process = [i for i in range(total) if not tracker.is_done(i)]
    logging.info(f"Policies to process: {to_process}")
    
    all_results = []
    all_iteration_data = []
    
    print(f"\n{'='*60}")
    print("ITERATIVE POLICY REPAIR WITH BASELINE VALIDATION")
    print(f"{'='*60}")
    print(f"Target accuracy: {TARGET_ACCURACY}%")
    print(f"Max iterations per policy: {MAX_ITERATIONS}")
    print(f"Policies to process: {len(to_process)}")
    print(f"{'='*60}")
    
    # Process each policy
    for idx in tqdm(to_process, desc="Processing policies iteratively"):
        try:
            result = process_policy_iteratively(idx)
            
            # Track completion/failure
            if result['status'] == 'success':
                tracker.mark_completed(idx, result['baseline_accuracy'], result['final_accuracy'], result['iterations_used'])
            else:
                tracker.mark_failed(idx, result['baseline_accuracy'], result['final_accuracy'], result['iterations_used'])
            
            all_results.append(result)
            
            # Collect iteration data for detailed analysis
            for iter_data in result['iteration_results']:
                all_iteration_data.append(iter_data)
            
            # Print progress summary
            improvement = result['final_accuracy'] - result['baseline_accuracy']
            if result['status'] == 'success':
                print(f"  ✓ Policy {idx}: {result['baseline_accuracy']:.1f}% → {result['final_accuracy']:.1f}% (+{improvement:.1f}%) in {result['iterations_used']} iterations")
            else:
                print(f"  ✗ Policy {idx}: {result['baseline_accuracy']:.1f}% → {result['final_accuracy']:.1f}% (+{improvement:.1f}%) - Target not reached")
            
        except Exception as e:
            logging.error(f"Policy {idx} failed completely: {e}")
            tracker.mark_failed(idx, 0.0, 0.0, 0)
            all_results.append({
                'index': idx,
                'status': 'error',
                'baseline_accuracy': 0.0,
                'final_accuracy': 0.0,
                'iterations_used': 0,
                'error': str(e)
            })
            print(f"  ✗ Policy {idx}: Complete failure - {str(e)[:50]}...")
    
    # Save comprehensive results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Summary results with baseline tracking
    if all_results:
        # Enhanced summary with baseline and improvement tracking
        summary_data = []
        for result in all_results:
            summary_record = {
                'policy_index': result['index'],
                'status': result['status'],
                'baseline_accuracy': result.get('baseline_accuracy', 0.0),
                'final_accuracy': result.get('final_accuracy', 0.0),
                'accuracy_improvement': result.get('final_accuracy', 0.0) - result.get('baseline_accuracy', 0.0),
                'iterations_used': result.get('iterations_used', 0),
                'target_achieved': result.get('final_accuracy', 0.0) >= TARGET_ACCURACY,
                'error': result.get('error', ''),
                'accuracy_progression': result.get('accuracy_progression', [])
            }
            summary_data.append(summary_record)
        
        df_summary = pd.DataFrame(summary_data)
        summary_csv = os.path.join(OUTPUT_DIR, f"iterative_repair_summary_{timestamp}.csv")
        df_summary.to_csv(summary_csv, index=False)
        logging.info(f"Summary results saved to {summary_csv}")
    
    # Detailed iteration results with baseline marker
    if all_iteration_data:
        df_iterations = pd.DataFrame(all_iteration_data)
        iterations_csv = os.path.join(OUTPUT_DIR, f"iterative_repair_details_{timestamp}.csv")
        df_iterations.to_csv(iterations_csv, index=False)
        logging.info(f"Detailed iteration results saved to {iterations_csv}")
    
    # Calculate comprehensive statistics
    successful = len([r for r in all_results if r.get('status') == 'success'])
    failed = len([r for r in all_results if r.get('status') in ['failed', 'error']])
    
    baseline_accuracies = [r.get('baseline_accuracy', 0) for r in all_results if 'baseline_accuracy' in r]
    final_accuracies = [r.get('final_accuracy', 0) for r in all_results if 'final_accuracy' in r]
    improvements = [r.get('final_accuracy', 0) - r.get('baseline_accuracy', 0) for r in all_results if 'baseline_accuracy' in r and 'final_accuracy' in r]
    
    avg_baseline = sum(baseline_accuracies) / len(baseline_accuracies) if baseline_accuracies else 0
    avg_final = sum(final_accuracies) / len(final_accuracies) if final_accuracies else 0
    avg_improvement = sum(improvements) / len(improvements) if improvements else 0
    
    total_iterations = sum(r.get('iterations_used', 0) for r in all_results)
    policies_improved = len([imp for imp in improvements if imp > 0])
    policies_degraded = len([imp for imp in improvements if imp < 0])
    policies_unchanged = len([imp for imp in improvements if imp == 0])
    
    # Print comprehensive final summary
    print(f"\n{'='*70}")
    print("ITERATIVE REPAIR - COMPREHENSIVE FINAL SUMMARY")
    print(f"{'='*70}")
    print(f"Total policies processed: {len(all_results)}")
    print(f"Successfully repaired (100% accuracy): {successful}")
    print(f"Failed to reach 100% accuracy: {failed}")
    print(f"")
    print(f"ACCURACY STATISTICS:")
    print(f"  Average baseline accuracy: {avg_baseline:.1f}%")
    print(f"  Average final accuracy: {avg_final:.1f}%")
    print(f"  Average improvement: {avg_improvement:.1f}%")
    print(f"")
    print(f"IMPROVEMENT BREAKDOWN:")
    print(f"  Policies improved: {policies_improved}")
    print(f"  Policies degraded: {policies_degraded}")
    print(f"  Policies unchanged: {policies_unchanged}")
    print(f"")
    print(f"ITERATION STATISTICS:")
    print(f"  Total iterations used: {total_iterations}")
    print(f"  Average iterations per policy: {total_iterations/len(all_results):.1f}" if all_results else "0")
    print(f"  Policies successful at baseline: {len([r for r in all_results if r.get('baseline_accuracy', 0) >= TARGET_ACCURACY])}")
    
    # Show detailed success/failure breakdown
    success_policies = [r for r in all_results if r.get('status') == 'success']
    if success_policies:
        print(f"\nSUCCESSFUL POLICIES:")
        for policy in success_policies:
            baseline = policy.get('baseline_accuracy', 0)
            final = policy.get('final_accuracy', 0)
            iters = policy.get('iterations_used', 0)
            improvement = final - baseline
            if iters == 0:
                print(f"  Policy {policy['index']}: {baseline:.1f}% (already perfect at baseline)")
            else:
                print(f"  Policy {policy['index']}: {baseline:.1f}% → {final:.1f}% (+{improvement:.1f}%) in {iters} iterations")
    
    failed_policies = [r for r in all_results if r.get('status') in ['failed', 'error']]
    if failed_policies:
        print(f"\nFAILED POLICIES:")
        for policy in failed_policies:
            baseline = policy.get('baseline_accuracy', 0)
            final = policy.get('final_accuracy', 0)
            improvement = final - baseline
            if policy.get('status') == 'error':
                print(f"  Policy {policy['index']}: Error - {policy.get('error', 'Unknown error')}")
            else:
                print(f"  Policy {policy['index']}: {baseline:.1f}% → {final:.1f}% (+{improvement:.1f}%) - Target not reached")
    
    # Show baseline vs final comparison
    baseline_perfect = len([r for r in all_results if r.get('baseline_accuracy', 0) >= TARGET_ACCURACY])
    final_perfect = len([r for r in all_results if r.get('final_accuracy', 0) >= TARGET_ACCURACY])
    
    print(f"\nBASELINE VS FINAL COMPARISON:")
    print(f"  Policies at target accuracy at baseline: {baseline_perfect}")
    print(f"  Policies at target accuracy after repair: {final_perfect}")
    print(f"  Net policies improved to target: {final_perfect - baseline_perfect}")
    
    print(f"{'='*70}")
    
    # Log the final summary as well
    logging.info(f"\n{'='*70}")
    logging.info("ITERATIVE REPAIR - COMPREHENSIVE FINAL SUMMARY")
    logging.info(f"{'='*70}")
    logging.info(f"Total policies processed: {len(all_results)}")
    logging.info(f"Successfully repaired (100% accuracy): {successful}")
    logging.info(f"Failed to reach 100% accuracy: {failed}")
    logging.info(f"Average baseline accuracy: {avg_baseline:.1f}%")
    logging.info(f"Average final accuracy: {avg_final:.1f}%")
    logging.info(f"Average improvement: {avg_improvement:.1f}%")
    logging.info(f"Total iterations used: {total_iterations}")
    logging.info(f"Average iterations per policy: {total_iterations/len(all_results):.1f}" if all_results else "0")
    logging.info(f"Policies improved: {policies_improved}, Degraded: {policies_degraded}, Unchanged: {policies_unchanged}")
    logging.info(f"Baseline perfect: {baseline_perfect}, Final perfect: {final_perfect}")
    logging.info(f"{'='*70}")
    
    # Cleanup temporary files
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
        logging.info("Cleaned up temporary files")

if __name__ == "__main__":
    main()