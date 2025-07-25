# import os
# import sys
# import time
# import json
# import logging
# import re
# import subprocess
# import tempfile
# import shutil
# from functools import wraps
# from datetime import datetime
# from pathlib import Path
# import pandas as pd
# from tqdm import tqdm
# import anthropic

# POLICY_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-2/original_policy"
# REQUIREMENTS_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-2/requests/request-30"
# OUTPUT_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-2/results/result-30"
# LOG_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-2/logs/log-30"
# TEMP_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-2/temp_validation/val-30"
# QUACKY_SRC_DIR = "/home/bhall2/Documents/fixmypolicy/quacky/src"
# SMT_VALIDATOR_SCRIPT = "/home/bhall2/Documents/fixmypolicy/quacky/src/validate_requests.py"
# #!/usr/bin/env python3
# """
# iterative_policy_repair_exp2.py

# EXPERIMENT 2: Enhanced iterative policy repair with failed examples feedback

# This script automatically processes multiple AWS IAM policies with their 
# corresponding requirement files using Claude to repair them. Unlike Experiment 1,
# this version analyzes failed validation results and provides specific examples
# of misclassified requests to guide the LLM in subsequent iterations.

# Features:
# - Iterative repair with failed examples feedback
# - SMT solver validation integration
# - Failed request extraction and analysis
# - Comprehensive tracking of all iterations
# - Results saved to CSV for analysis
# - Progress tracking with resume capability

# Usage:
#     python3 iterative_policy_repair_exp2.py
# """
# # Global configurations
# MAX_ITERATIONS = 5
# MAX_ATTEMPT = 3
# DELAY = 5
# TARGET_ACCURACY = 100.0

# # Configure logging
# def setup_logging(log_dir: str = LOG_DIR):
#     os.makedirs(log_dir, exist_ok=True)
#     log_file = os.path.join(log_dir, f'iterative_repair_exp2_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
#     logging.basicConfig(
#         level=logging.INFO,
#         format='%(asctime)s - %(levelname)s - %(message)s',
#         handlers=[
#             logging.FileHandler(log_file),
#             logging.StreamHandler()
#         ]
#     )
#     return log_file

# # API Client Initialization
# claude_client = anthropic.Anthropic(
#     api_key="REDACTED_API_KEY",
# )
# claude_model_name = "claude-sonnet-4-20250514"
# def get_policy_repair_prompt(problematic_policy, requirements, iteration=1, failed_examples=None):
#     base_prompt = f"""
# You are an AWS IAM security expert working on a RESEARCH PROJECT. Your task is to repair a problematic AWS IAM policy to satisfy specific test requirements that include intentionally challenging edge cases.

# RESEARCH CONTEXT:
# - This is a test scenario with intentionally unusual cross-service request combinations
# - Some requests are designed to be misclassified to test policy repair capabilities
# - Your job is to create a policy that satisfies the SMT solver for these exact test combinations
# - Ignore normal AWS service logic constraints - treat all action+resource combinations as potentially valid

# SMT SOLVER VALIDATION:
# - SMT solver returns SAT = ALLOW the request (policy permits access)
# - SMT solver returns UNSAT = DENY the request (policy blocks access)
# - The solver checks exact literal matches: Action+Resource+Principal+Condition
# - No fuzzy matching or AWS service logic - only exact string/pattern matching

# CURRENT PROBLEMATIC POLICY:
# {problematic_policy}

# TEST REQUIREMENTS TO SATISFY:
# {requirements}

# ITERATION: {iteration}/{MAX_ITERATIONS}
# """
    
#     if failed_examples and iteration > 1:
#         allow_failures = [ex for ex in failed_examples if ex['expected'] == 'allow']
#         deny_failures = [ex for ex in failed_examples if ex['expected'] == 'deny']
        
#         base_prompt += f"""
# ANALYSIS OF PREVIOUS ITERATION FAILURES:
# Previous policy failed {len(failed_examples)} test cases. SMT solver analysis:

# """
        
#         if allow_failures:
#             base_prompt += f"""
# CRITICAL: {len(allow_failures)} ALLOW test cases returned UNSAT (denied) instead of SAT (allowed)
# These test cases REQUIRE explicit Allow statements in the policy:

# """
#             for i, example in enumerate(allow_failures, 1):
#                 # Clean up the values
#                 principal_val = example.get('principal') if example.get('principal') not in [None, 'None', 'N/A'] else None
#                 condition_val = example.get('condition') if example.get('condition') not in [None, 'None', 'N/A'] else None
                
#                 base_prompt += f"""
# FAILED ALLOW TEST {i}:
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Request ID: {example.get('request_id', 'unknown')}
# Action: {example['action']}
# Resource: {example['resource']}
# Principal: {principal_val if principal_val else 'Not specified'}
# Condition: {condition_val if condition_val else 'Not specified'}
# SMT Problem: Solver returned UNSAT - no Allow statement matches this combination
# REQUIRED FIX: Add explicit Allow statement matching these exact parameters
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# EXACT ALLOW STATEMENT NEEDED:
# {{
#   "Sid": "Research_Allow_{i}_{example.get('request_id', 'test')}",
#   "Effect": "Allow",
#   "Action": "{example['action']}",
#   "Resource": "{example['resource']}"{"," if principal_val or condition_val else ""}
#   {"" if not principal_val else f'"Principal": {{"AWS": "{principal_val}"}}'}{("," if principal_val and condition_val else "") if condition_val else ""}
#   {"" if not condition_val else f'"Condition": {condition_val}'}
# }}

# """
        
#         if deny_failures:
#             base_prompt += f"""
# {len(deny_failures)} DENY test cases returned SAT (allowed) instead of UNSAT (denied):

# """
#             for i, example in enumerate(deny_failures, 1):
#                 base_prompt += f"""
# FAILED DENY TEST {i}:
# - Action: {example['action']} on Resource: {example['resource']}
# - Principal: {example.get('principal', 'Not specified')}
# - Condition: {example.get('condition', 'Not specified')}
# - Problem: SMT solver found Allow statement that matches - need to block this
# - Fix: Add explicit Deny statement or remove conflicting Allow
# """
    
#     base_prompt += """

# RESEARCH POLICY REPAIR STRATEGY:
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 1. CROSS-SERVICE COMBINATIONS: Treat unusual combinations as valid test cases
#    - athena:GetQueryExecution on S3 resources → Create Allow statement
#    - glue:GetTable on Athena resources → Create Allow statement  
#    - s3:GetObject on Glue resources → Create Allow statement
#    - Any service action on any resource type → Match exactly as requested

# 2. EXACT MATCHING REQUIREMENTS:
#    - Action names: Match exactly (case-sensitive)
#    - Resource ARNs: Match exactly (account IDs, regions, resource names)
#    - Principal ARNs: Match exactly if specified
#    - Condition keys/values: Match exactly if specified

# 3. CONDITION HANDLING:
#    - If test requires aws:RequestedRegion=us-west-2, use exactly that
#    - If test requires aws:SecureTransport=true, use exactly that
#    - Don't modify conditions to "make sense" - use test requirements exactly

# 4. PRINCIPAL HANDLING:
#    - Cross-account access (555666777888 vs 123456789012) → Allow exactly as specified
#    - Role vs User access → Match exactly as specified

# POLICY STRUCTURE FOR RESEARCH TESTS:
# {
#   "Version": "2012-10-17",
#   "Statement": [
#     {
#       "Sid": "Research_Allow_CrossService_1",
#       "Effect": "Allow",
#       "Action": "athena:GetQueryExecution",
#       "Resource": "arn:aws:s3:::bkt_logs/logs/app.log",
#       "Principal": {"AWS": "arn:aws:iam::123456789012:role/service-role"},
#       "Condition": {"Bool": {"aws:SecureTransport": "true"}}
#     },
#     {
#       "Sid": "Research_Allow_CrossService_2", 
#       "Effect": "Allow",
#       "Action": "glue:GetTable",
#       "Resource": "arn:aws:glue:us-east-1:123456789012:catalog",
#       "Principal": {"AWS": "arn:aws:iam::123456789012:role/service-role"},
#       "Condition": {"StringEquals": {"aws:RequestedRegion": "us-west-2"}}
#     }
#   ]
# }

# CRITICAL INSTRUCTIONS:
# - Generate explicit Allow statements for each failed Allow test case
# - Use exact Action+Resource+Principal+Condition combinations from failed examples
# - Don't try to "fix" or "improve" the test requirements - implement them exactly
# - For research purposes, all combinations are considered valid
# - Preserve existing Deny logic for test cases that should be denied

# RETURN ONLY VALID JSON POLICY - NO EXPLANATIONS OR COMMENTS:
# """
    
#     return base_prompt

# # Retry decorator
# def retry(max_attempts=MAX_ATTEMPT, delay=DELAY):
#     def decorator(func):
#         @wraps(func)
#         def wrapper(*args, **kwargs):
#             attempts = 0
#             while attempts < max_attempts:
#                 try:
#                     return func(*args, **kwargs)
#                 except Exception as e:
#                     attempts += 1
#                     if attempts == max_attempts:
#                         raise
#                     logging.warning(f"Attempt {attempts} failed: {e}. Retrying in {delay} seconds...")
#                     time.sleep(delay)
#         return wrapper
#     return decorator

# class IterativeProgressTracker:
#     def __init__(self, progress_file: str = os.path.join(OUTPUT_DIR, "iterative_progress_exp2.json")):
#         self.progress_file = progress_file
#         self.progress = self._load_progress()
    
#     def _load_progress(self):
#         if os.path.exists(self.progress_file):
#             try:
#                 with open(self.progress_file, 'r') as f:
#                     return json.load(f)
#             except:
#                 pass
#         return {
#             "last_processed": -1, 
#             "completed": [], 
#             "failed": [],
#             "policy_iterations": {}  # Track iterations per policy
#         }
    
#     def save_progress(self):
#         os.makedirs(os.path.dirname(self.progress_file), exist_ok=True)
#         with open(self.progress_file, 'w') as f:
#             json.dump(self.progress, f, indent=2)
    
#     def mark_completed(self, idx, final_accuracy, iterations_used, iteration_accuracies):
#         self.progress["last_processed"] = idx
#         if idx not in self.progress["completed"]:
#             self.progress["completed"].append(idx)
#         if idx in self.progress["failed"]:
#             self.progress["failed"].remove(idx)
        
#         self.progress["policy_iterations"][str(idx)] = {
#             "status": "completed",
#             "final_accuracy": final_accuracy,
#             "iterations_used": iterations_used,
#             "iteration_accuracies": iteration_accuracies  # Track all accuracies
#         }
#         self.save_progress()
    
#     def mark_failed(self, idx, final_accuracy, iterations_used, iteration_accuracies):
#         if idx not in self.progress["failed"]:
#             self.progress["failed"].append(idx)
        
#         self.progress["policy_iterations"][str(idx)] = {
#             "status": "failed",
#             "final_accuracy": final_accuracy,
#             "iterations_used": iterations_used,
#             "iteration_accuracies": iteration_accuracies  # Track all accuracies
#         }
#         self.save_progress()
    
#     def get_next(self):
#         return self.progress.get("last_processed", -1) + 1
    
#     def is_done(self, idx):
#         return idx in self.progress.get("completed", [])

# def load_json_file(path: str) -> dict:
#     with open(path, 'r', encoding='utf-8') as f:
#         return json.load(f)

# def save_json_file(data: dict, path: str):
#     os.makedirs(os.path.dirname(path), exist_ok=True)
#     with open(path, 'w', encoding='utf-8') as f:
#         json.dump(data, f, indent=2)

# def format_requirements(requests: dict) -> str:
#     if "Requests" not in requests:
#         raise ValueError("Invalid request format: missing 'Requests' key")
    
#     allow = []
#     deny = []
    
#     for req in requests["Requests"]:
#         if req.get("Effect", "").lower() == "allow":
#             allow.append(req)
#         else:
#             deny.append(req)
    
#     lines = []
#     if allow:
#         lines.append("MUST ALLOW:")
#         for i, r in enumerate(allow, 1):
#             lines.append(f"  {i}. ID: {r.get('id')} Actions: {r.get('Action')} Resources: {r.get('Resource')}")
    
#     if deny:
#         lines.append("MUST DENY:")
#         for i, r in enumerate(deny, 1):
#             lines.append(f"  {i}. ID: {r.get('id')} Actions: {r.get('Action')} Resources: {r.get('Resource')}")
    
#     lines.append("ADDITIONAL REQUIREMENTS:")
#     lines.extend([
#         "  - Version must be '2012-10-17'",
#         "  - Explicit Sid values",
#         "  - Principle of least privilege",
#         "  - Specific ARNs where provided",
#         "  - Ensure actions allowed/denied as specified",
#     ])
    
#     return "\n".join(lines)

# def extract_and_validate_json(response_text: str) -> dict:
#     """Extract and validate JSON from Claude's response with improved error handling."""
#     text = response_text.strip()
    
#     # Remove markdown formatting
#     if text.startswith("```json"):
#         text = text[7:]
#     elif text.startswith("```"):
#         text = text[3:]
    
#     if text.endswith("```"):
#         text = text[:-3]
    
#     text = text.strip()
    
#     # Find JSON boundaries
#     start_idx = text.find("{")
#     end_idx = text.rfind("}")
    
#     if start_idx == -1 or end_idx == -1:
#         raise ValueError(f"No JSON object found in response. Text: {text[:200]}...")
    
#     json_text = text[start_idx:end_idx+1]
#     logging.debug(f"Extracted JSON: {json_text}")
    
#     try:
#         parsed_json = json.loads(json_text)
        
#         # Validate required fields
#         if not isinstance(parsed_json, dict):
#             raise ValueError("Response is not a JSON object")
        
#         if "Version" not in parsed_json:
#             raise ValueError("Missing 'Version' field in policy")
        
#         if "Statement" not in parsed_json:
#             raise ValueError("Missing 'Statement' field in policy")
        
#         if not isinstance(parsed_json["Statement"], list):
#             raise ValueError("'Statement' field must be an array")
        
#         return parsed_json
        
#     except json.JSONDecodeError as e:
#         # Try to fix common JSON issues
#         logging.warning(f"JSON decode error: {e}. Attempting to fix...")
        
#         # Fix trailing commas
#         fixed_json = re.sub(r',(\s*[}\]])', r'\1', json_text)
        
#         # Fix missing quotes around keys
#         fixed_json = re.sub(r'(\w+):', r'"\1":', fixed_json)
        
#         try:
#             parsed_json = json.loads(fixed_json)
#             logging.info("Successfully fixed JSON syntax issues")
#             return parsed_json
#         except json.JSONDecodeError as e2:
#             raise ValueError(f"Failed to parse JSON even after fixes. Original error: {e}. Fixed JSON: {fixed_json}")

# @retry()
# def repair_policy_with_claude(policy: dict, requests: dict, iteration: int = 1, failed_examples: list = None) -> dict:
#     policy_json = json.dumps(policy, indent=2)
#     req_text = format_requirements(requests)
#     prompt = get_policy_repair_prompt(policy_json, req_text, iteration, failed_examples)
    
#     resp = claude_client.messages.create(
#         model=claude_model_name,
#         max_tokens=8000,  # Increased for longer prompts with examples
#         temperature=0,
#         system="You are an AWS IAM security expert who repairs policies to meet specific security requirements. When provided with failed examples, pay special attention to fixing those specific issues. Generate only valid JSON policies without any explanatory text.",
#         messages=[{"role": "user", "content": prompt}]
#     )
    
#     # Extract response text
#     response_text = ""
#     for block in getattr(resp, 'content', []):
#         if hasattr(block, 'type') and block.type == 'text':
#             response_text += block.text
    
#     if not response_text:
#         raise ValueError("Empty response from Claude")
    
#     logging.debug(f"Raw Claude response: {response_text}")
#     return extract_and_validate_json(response_text)

# def extract_failed_examples(output_content: str) -> list:
#     """Extract failed examples from validator output preserving exact test case details."""
#     failed_examples = []
#     lines = output_content.split('\n')
    
#     current_request = None
    
#     for line in lines:
#         line = line.strip()
        
#         # Look for individual request validations
#         if "Validating individual request:" in line:
#             # Extract request info: allow_0110392c_combo_1
#             match = re.search(r'Validating individual request: (\w+)_combo_\d+', line)
#             if match:
#                 current_request = {"id": match.group(1)}
        
#         # Extract action, resource, principal, condition from the detailed line
#         elif line.startswith("Action:") and current_request:
#             # Parse: Action: athena:GetQueryExecution, Resource: arn:aws:s3:::bkt_logs/logs/app.log, Principal: arn:aws:iam::123456789012:role/service-role, Condition: {'Bool': {'aws:SecureTransport': 'true'}}
#             parts = line.split(", ")
#             for part in parts:
#                 if part.startswith("Action:"):
#                     current_request["action"] = part.split(": ", 1)[1].strip()
#                 elif part.startswith("Resource:"):
#                     current_request["resource"] = part.split(": ", 1)[1].strip()
#                 elif part.startswith("Principal:"):
#                     principal_val = part.split(": ", 1)[1].strip()
#                     current_request["principal"] = principal_val if principal_val != "None" else None
#                 elif part.startswith("Condition:"):
#                     condition_val = part.split(": ", 1)[1].strip()
#                     # Try to preserve the condition as a string that can be parsed as JSON
#                     if condition_val != "None":
#                         try:
#                             # Convert Python dict string to JSON
#                             condition_json = condition_val.replace("'", '"')
#                             # Validate it's proper JSON
#                             import json
#                             json.loads(condition_json)
#                             current_request["condition"] = condition_json
#                         except:
#                             current_request["condition"] = condition_val
#                     else:
#                         current_request["condition"] = None
        
#         # Look for incorrect classifications
#         elif "INCORRECT:" in line and current_request:
#             # Parse: INCORRECT: Expected=allow, Got=deny
#             match = re.search(r'Expected=(\w+), Got=(\w+)', line)
#             if match:
#                 expected = match.group(1)
#                 actual = match.group(2)
                
#                 failed_example = {
#                     "request_id": current_request.get("id", "unknown"),
#                     "action": current_request.get("action", "unknown"),
#                     "resource": current_request.get("resource", "unknown"),
#                     "principal": current_request.get("principal"),
#                     "condition": current_request.get("condition"),
#                     "expected": expected,
#                     "actual": actual
#                 }
                
#                 failed_examples.append(failed_example)
#                 logging.debug(f"Extracted research test failure: {failed_example}")
        
#         # Reset current request when we see CORRECT or start new request
#         elif "CORRECT:" in line or "Processing request object:" in line:
#             current_request = None
    
#     logging.info(f"Extracted {len(failed_examples)} failed research test cases from validator output")
#     return failed_examples

# def run_smt_validator(policy_file: str, requests_file: str) -> dict:
#     """Run the SMT validator and return parsed results."""
#     try:
#         # Change to the Quacky source directory
#         original_dir = os.getcwd()
#         os.chdir(QUACKY_SRC_DIR)
        
#         # Create output directory if it doesn't exist
#         quacky_output_dir = os.path.join(OUTPUT_DIR, "Quacky_output")
#         os.makedirs(quacky_output_dir, exist_ok=True)
        
#         # Create unique output file name
#         timestamp = int(time.time())
#         pid = os.getpid()
#         output_file_path = os.path.join(quacky_output_dir, f"temp_validation_{pid}_{timestamp}.txt")
        
#         # Run the validator with your exact command structure
#         cmd = [
#             'python3', 'validate_requests.py',
#             '-p1', policy_file,
#             '--requests', requests_file,
#             '-s'
#         ]
        
#         logging.debug(f"Running SMT validator: cd {QUACKY_SRC_DIR} && {' '.join(cmd)} > {output_file_path}")
        
#         # Run the command and redirect output to file
#         with open(output_file_path, 'w') as output_file:
#             result = subprocess.run(cmd, stdout=output_file, stderr=subprocess.PIPE, text=True, timeout=300)
        
#         # Change back to original directory
#         os.chdir(original_dir)
        
#         if result.returncode != 0:
#             logging.error(f"SMT validator failed: {result.stderr}")
#             # Clean up temp file
#             if os.path.exists(output_file_path):
#                 os.unlink(output_file_path)
#             raise Exception(f"SMT validator failed: {result.stderr}")
        
#         # Read the output file to parse results
#         with open(output_file_path, 'r') as f:
#             output_content = f.read()
        
#         logging.debug(f"Validator output saved to: {output_file_path}")
#         logging.debug(f"Raw validator output (first 1000 chars): {output_content[:1000]}")
        
#         # Parse the output to extract accuracy information
#         output_lines = output_content.split('\n')
        
#         # Look for accuracy information in the output
#         accuracy = 0.0
#         total_requests = 0
#         correct_count = 0
#         incorrect_count = 0
#         misclassified_allow_to_deny = 0
#         misclassified_deny_to_allow = 0
        
#         # Parse the specific format from your validator
#         in_analysis_section = False
#         found_analysis_section = False
        
#         for i, line in enumerate(output_lines):
#             line = line.strip()
            
#             # Check if we're in the analysis section
#             if "INDIVIDUAL REQUEST ANALYSIS" in line:
#                 in_analysis_section = True
#                 found_analysis_section = True
#                 logging.debug(f"Found analysis section at line {i}: {line}")
#                 continue
#             elif line.startswith("=") and in_analysis_section and len(line) > 10:
#                 # End of analysis section (long line of equals)
#                 if any(phrase in ''.join(output_lines[i:i+5]) for phrase in ["Results saved", "saved to HOME"]):
#                     logging.debug(f"End of analysis section at line {i}")
#                     break
            
#             if in_analysis_section:
#                 logging.debug(f"Parsing analysis line {i}: {line}")
#                 if line.startswith("Total Individual Requests:"):
#                     total_match = re.search(r'(\d+)', line)
#                     if total_match:
#                         total_requests = int(total_match.group(1))
#                         logging.debug(f"Found total requests: {total_requests}")
#                 elif line.startswith("Correct Classifications:"):
#                     correct_match = re.search(r'(\d+)', line)
#                     if correct_match:
#                         correct_count = int(correct_match.group(1))
#                         logging.debug(f"Found correct count: {correct_count}")
#                 elif line.startswith("Incorrect Classifications:"):
#                     incorrect_match = re.search(r'(\d+)', line)
#                     if incorrect_match:
#                         incorrect_count = int(incorrect_match.group(1))
#                         logging.debug(f"Found incorrect count: {incorrect_count}")
#                 elif line.startswith("Overall Accuracy:"):
#                     accuracy_match = re.search(r'(\d+\.?\d*)%', line)
#                     if accuracy_match:
#                         accuracy = float(accuracy_match.group(1))
#                         logging.debug(f"Found accuracy: {accuracy}%")
#                 elif line.startswith("Expected Allow -> Got Deny:"):
#                     allow_deny_match = re.search(r'(\d+)', line)
#                     if allow_deny_match:
#                         misclassified_allow_to_deny = int(allow_deny_match.group(1))
#                         logging.debug(f"Found allow->deny: {misclassified_allow_to_deny}")
#                 elif line.startswith("Expected Deny -> Got Allow:"):
#                     deny_allow_match = re.search(r'(\d+)', line)
#                     if deny_allow_match:
#                         misclassified_deny_to_allow = int(deny_allow_match.group(1))
#                         logging.debug(f"Found deny->allow: {misclassified_deny_to_allow}")
        
#         if not found_analysis_section:
#             logging.warning("Could not find 'INDIVIDUAL REQUEST ANALYSIS' section in output")
#             logging.debug("Searching for any accuracy information...")
#             # Fallback: search entire output for accuracy
#             for line in output_lines:
#                 if "Overall Accuracy:" in line or "Accuracy:" in line:
#                     accuracy_match = re.search(r'(\d+\.?\d*)%', line)
#                     if accuracy_match:
#                         accuracy = float(accuracy_match.group(1))
#                         logging.debug(f"Found fallback accuracy: {accuracy}%")
#                         break
        
#         # Extract failed examples for feedback
#         failed_examples = extract_failed_examples(output_content)
        
#         # Keep the file for debugging and log its location
#         logging.info(f"Validator output file kept for debugging: {output_file_path}")
        
#         # Validate that we got meaningful results
#         if total_requests == 0:
#             logging.warning("No requests found in validator output - check parsing logic")
#             logging.warning(f"Output file location: {output_file_path}")
#             logging.debug(f"Raw output preview: {output_content[:500]}...")
#             # Also save the full output to a debug file
#             debug_file = output_file_path.replace('.txt', '_debug.txt')
#             with open(debug_file, 'w') as f:
#                 f.write("=== FULL VALIDATOR OUTPUT ===\n")
#                 f.write(output_content)
#             logging.warning(f"Full output saved to: {debug_file}")
        
#         logging.info(f"Validation completed - Accuracy: {accuracy}%, Total: {total_requests}, Correct: {correct_count}, Incorrect: {incorrect_count}")
#         logging.debug(f"Misclassified - Allow→Deny: {misclassified_allow_to_deny}, Deny→Allow: {misclassified_deny_to_allow}")
#         logging.info(f"Found {len(failed_examples)} failed examples for feedback")
        
#         return {
#             'accuracy': accuracy,
#             'total_requests': total_requests,
#             'correct': correct_count,
#             'incorrect': incorrect_count,
#             'misclassified_allow_to_deny': misclassified_allow_to_deny,
#             'misclassified_deny_to_allow': misclassified_deny_to_allow,
#             'failed_examples': failed_examples,
#             'raw_output': output_content,
#             'output_file': output_file_path
#         }
        
#     except subprocess.TimeoutExpired:
#         # Change back to original directory in case of timeout
#         try:
#             os.chdir(original_dir)
#         except:
#             pass
#         logging.error("SMT validator timed out")
#         raise Exception("SMT validator timed out")
#     except Exception as e:
#         # Change back to original directory in case of error
#         try:
#             os.chdir(original_dir)
#         except:
#             pass
#         logging.error(f"Error running SMT validator: {e}")
#         raise

# def process_policy_iteratively(idx: int) -> dict:
#     """Process a single policy with iterative repair and validation."""
#     policy_file = os.path.join(POLICY_DIR, f"{idx}.json")
#     req_file = os.path.join(REQUIREMENTS_DIR, f"{idx}.json")
    
#     if not os.path.exists(policy_file) or not os.path.exists(req_file):
#         raise FileNotFoundError(f"Missing files for index {idx}")
    
#     # Load initial policy and requests
#     original_policy = load_json_file(policy_file)
#     requests = load_json_file(req_file)
    
#     logging.info(f"Starting iterative repair for policy {idx}...")
    
#     # ==========================================
#     # BASELINE VALIDATION - Test Original Policy
#     # ==========================================
#     logging.info(f"=" * 60)
#     logging.info(f"BASELINE  - Testing Original Policy {idx}")
#     logging.info(f"=" * 60)
    
#     # Save original policy for baseline testing
#     baseline_policy_file = os.path.join(TEMP_DIR, f"policy_{idx}_original_baseline.json")
#     os.makedirs(TEMP_DIR, exist_ok=True)
#     save_json_file(original_policy, baseline_policy_file)
    
#     try:
#         # Run baseline validation
#         logging.info(f"Running baseline validation on original policy {idx}...")
#         baseline_results = run_smt_validator(baseline_policy_file, req_file)
        
#         baseline_accuracy = baseline_results['accuracy']
#         baseline_failed_examples = baseline_results.get('failed_examples', [])
        
#         # Log baseline results
#         logging.info(f"BASELINE RESULTS for Policy {idx}:")
#         logging.info(f"  Original Accuracy: {baseline_accuracy:.1f}%")
#         logging.info(f"  Total Requests: {baseline_results['total_requests']}")
#         logging.info(f"  Correct: {baseline_results['correct']}")
#         logging.info(f"  Incorrect: {baseline_results['incorrect']}")
#         logging.info(f"  Allow→Deny Failures: {baseline_results['misclassified_allow_to_deny']}")
#         logging.info(f"  Deny→Allow Failures: {baseline_results['misclassified_deny_to_allow']}")
#         logging.info(f"  Failed Examples Count: {len(baseline_failed_examples)}")
        
#         # Print baseline results to console as well
#         print(f"\n{'='*60}")
#         print(f"BASELINE VALIDATION - Policy {idx}")
#         print(f"{'='*60}")
#         print(f"Original Policy Accuracy: {baseline_accuracy:.1f}%")
#         print(f"Total Requests: {baseline_results['total_requests']}")
#         print(f"Correct Classifications: {baseline_results['correct']}")
#         print(f"Incorrect Classifications: {baseline_results['incorrect']}")
#         print(f"Allow→Deny Failures: {baseline_results['misclassified_allow_to_deny']}")
#         print(f"Deny→Allow Failures: {baseline_results['misclassified_deny_to_allow']}")
#         print(f"Failed Examples: {len(baseline_failed_examples)}")
        
#         # Log specific failed examples for debugging
#         if baseline_failed_examples:
#             logging.info(f"BASELINE FAILED EXAMPLES for Policy {idx}:")
#             print(f"\nBASELINE FAILED EXAMPLES:")
#             for i, example in enumerate(baseline_failed_examples, 1):
#                 failure_msg = f"  {i}. {example['request_id']}: {example['action']} on {example['resource']} (Expected: {example['expected']}, Got: {example['actual']})"
#                 logging.info(failure_msg)
#                 print(failure_msg)
        
#         print(f"{'='*60}\n")
        
#         # Check if original policy already meets target
#         if baseline_accuracy >= TARGET_ACCURACY:
#             logging.info(f"Policy {idx} already meets target accuracy ({baseline_accuracy:.1f}%) - no repair needed!")
#             print(f"Policy {idx} already meets target accuracy ({baseline_accuracy:.1f}%) - no repair needed!")
            
#             # Save original as final since it already works
#             final_output_file = os.path.join(OUTPUT_DIR, f"repaired_{idx}_already_perfect.json")
#             save_json_file(original_policy, final_output_file)
            
#             return {
#                 'index': idx,
#                 'status': 'already_perfect',
#                 'baseline_accuracy': baseline_accuracy,
#                 'final_accuracy': baseline_accuracy,
#                 'iterations_used': 0,
#                 'iteration_accuracies': [baseline_accuracy],
#                 'iteration_results': [{
#                     'policy_idx': idx,
#                     'iteration': 0,  # Baseline
#                     'accuracy': baseline_accuracy,
#                     'total_requests': baseline_results['total_requests'],
#                     'correct': baseline_results['correct'],
#                     'incorrect': baseline_results['incorrect'],
#                     'misclassified_allow_to_deny': baseline_results['misclassified_allow_to_deny'],
#                     'misclassified_deny_to_allow': baseline_results['misclassified_deny_to_allow'],
#                     'failed_examples_count': len(baseline_failed_examples),
#                     'failed_examples': baseline_failed_examples,
#                     'policy_file': baseline_policy_file,
#                     'type': 'baseline'
#                 }],
#                 'baseline_results': baseline_results,
#                 'final_policy_file': final_output_file
#             }
        
#     except Exception as e:
#         logging.error(f"Baseline validation failed for policy {idx}: {e}")
#         print(f"Baseline validation failed for policy {idx}: {e}")
#         baseline_accuracy = 0.0
#         baseline_failed_examples = []
#         baseline_results = {
#             'accuracy': 0.0,
#             'total_requests': 0,
#             'correct': 0,
#             'incorrect': 0,
#             'misclassified_allow_to_deny': 0,
#             'misclassified_deny_to_allow': 0,
#             'failed_examples': [],
#             'error': str(e)
#         }
    
#     # ==========================================
#     # ITERATIVE REPAIR PROCESS
#     # ==========================================
#     logging.info(f"STARTING ITERATIVE REPAIR for Policy {idx} (Baseline: {baseline_accuracy:.1f}%)")
#     print(f"STARTING ITERATIVE REPAIR for Policy {idx} (Baseline: {baseline_accuracy:.1f}%)")
    
#     # Track all iterations (including baseline as iteration 0)
#     iteration_results = []
    
#     # Add baseline as iteration 0
#     baseline_iteration = {
#         'policy_idx': idx,
#         'iteration': 0,  # Baseline
#         'accuracy': baseline_accuracy,
#         'total_requests': baseline_results.get('total_requests', 0),
#         'correct': baseline_results.get('correct', 0),
#         'incorrect': baseline_results.get('incorrect', 0),
#         'misclassified_allow_to_deny': baseline_results.get('misclassified_allow_to_deny', 0),
#         'misclassified_deny_to_allow': baseline_results.get('misclassified_deny_to_allow', 0),
#         'failed_examples_count': len(baseline_failed_examples),
#         'failed_examples': baseline_failed_examples,
#         'policy_file': baseline_policy_file,
#         'type': 'baseline'
#     }
#     iteration_results.append(baseline_iteration)
    
#     current_policy = original_policy.copy()
#     failed_examples = baseline_failed_examples  # Start with baseline failures
#     final_accuracy = baseline_accuracy
#     iteration_accuracies = [baseline_accuracy]  # Track accuracy for each iteration (starting with baseline)
    
#     for iteration in range(1, MAX_ITERATIONS + 1):
#         logging.info(f"Policy {idx} - Iteration {iteration}/{MAX_ITERATIONS} (Previous: {final_accuracy:.1f}%)")
#         print(f"Policy {idx} - Iteration {iteration}/{MAX_ITERATIONS} (Previous: {final_accuracy:.1f}%)")
        
#         try:
#             # Repair policy with Claude (with failed examples feedback)
#             logging.info(f"Repairing policy with Claude (iteration {iteration})...")
#             if failed_examples:
#                 logging.info(f"Providing {len(failed_examples)} failed examples as guidance")
#                 print(f"  Using {len(failed_examples)} failed examples as guidance")
            
#             repaired_policy = repair_policy_with_claude(
#                 current_policy, requests, iteration, failed_examples
#             )
            
#             # Save temporary repaired policy for validation
#             temp_policy_file = os.path.join(TEMP_DIR, f"policy_{idx}_iter_{iteration}.json")
#             save_json_file(repaired_policy, temp_policy_file)
            
#             # Validate with SMT solver
#             logging.info(f"Validating with SMT solver (iteration {iteration})...")
#             validation_results = run_smt_validator(temp_policy_file, req_file)
            
#             accuracy = validation_results['accuracy']
#             current_failed_examples = validation_results.get('failed_examples', [])
            
#             # Track this iteration's accuracy
#             iteration_accuracies.append(accuracy)
            
#             # Calculate improvement from baseline
#             improvement = accuracy - baseline_accuracy
            
#             logging.info(f"Iteration {iteration} Results:")
#             logging.info(f"  Accuracy: {accuracy:.1f}% (Baseline: {baseline_accuracy:.1f}%, Improvement: {improvement:+.1f}%)")
#             logging.info(f"  Failed Examples: {len(current_failed_examples)}")
            
#             print(f"  Iteration {iteration} Accuracy: {accuracy:.1f}% (Improvement: {improvement:+.1f}%)")
#             print(f"  Failed Examples: {len(current_failed_examples)}")
            
#             # Record this iteration
#             iteration_record = {
#                 'policy_idx': idx,
#                 'iteration': iteration,
#                 'accuracy': accuracy,
#                 'baseline_accuracy': baseline_accuracy,
#                 'improvement_from_baseline': improvement,
#                 'total_requests': validation_results['total_requests'],
#                 'correct': validation_results['correct'],
#                 'incorrect': validation_results['incorrect'],
#                 'misclassified_allow_to_deny': validation_results['misclassified_allow_to_deny'],
#                 'misclassified_deny_to_allow': validation_results['misclassified_deny_to_allow'],
#                 'failed_examples_count': len(current_failed_examples),
#                 'failed_examples': current_failed_examples,
#                 'policy_file': temp_policy_file,
#                 'type': 'repair_iteration'
#             }
#             iteration_results.append(iteration_record)
            
#             final_accuracy = accuracy
            
#             # Check if we achieved target accuracy
#             if accuracy >= TARGET_ACCURACY:
#                 logging.info(f"Target accuracy achieved for policy {idx} in {iteration} iterations!")
#                 logging.info(f"Final accuracy: {accuracy:.1f}% (Improvement from baseline: {improvement:+.1f}%)")
                
#                 print(f"✅ Target accuracy achieved for policy {idx} in {iteration} iterations!")
#                 print(f"   Final: {accuracy:.1f}% | Baseline: {baseline_accuracy:.1f}% | Improvement: {improvement:+.1f}%")
                
#                 # Save final repaired policy
#                 final_output_file = os.path.join(OUTPUT_DIR, f"repaired_{idx}_final.json")
#                 save_json_file(repaired_policy, final_output_file)
                
#                 return {
#                     'index': idx,
#                     'status': 'success',
#                     'baseline_accuracy': baseline_accuracy,
#                     'final_accuracy': accuracy,
#                     'improvement_from_baseline': improvement,
#                     'iterations_used': iteration,
#                     'iteration_accuracies': iteration_accuracies,
#                     'iteration_results': iteration_results,
#                     'baseline_results': baseline_results,
#                     'final_policy_file': final_output_file
#                 }
            
#             # Update for next iteration - use the repaired policy and failed examples as feedback
#             current_policy = repaired_policy.copy()
#             failed_examples = current_failed_examples if current_failed_examples else None
            
#         except Exception as e:
#             logging.error(f"Error in iteration {iteration} for policy {idx}: {e}")
#             print(f"❌ Error in iteration {iteration}: {e}")
#             iteration_record = {
#                 'policy_idx': idx,
#                 'iteration': iteration,
#                 'accuracy': 0.0,
#                 'baseline_accuracy': baseline_accuracy,
#                 'improvement_from_baseline': -baseline_accuracy,
#                 'failed_examples_count': 0,
#                 'error': str(e),
#                 'type': 'error'
#             }
#             iteration_results.append(iteration_record)
    
#     # If we reach here, we didn't achieve target accuracy
#     improvement = final_accuracy - baseline_accuracy
#     logging.warning(f"Failed to achieve target accuracy for policy {idx} after {MAX_ITERATIONS} iterations.")
#     logging.warning(f"Final accuracy: {final_accuracy:.1f}% (Baseline: {baseline_accuracy:.1f}%, Improvement: {improvement:+.1f}%)")
    
#     print(f"❌ Failed to achieve target accuracy for policy {idx}")
#     print(f"   Final: {final_accuracy:.1f}% | Baseline: {baseline_accuracy:.1f}% | Improvement: {improvement:+.1f}%")
    
#     # Save best attempt
#     if iteration_results:
#         best_iteration = max([r for r in iteration_results if r.get('type') != 'baseline'], 
#                            key=lambda x: x.get('accuracy', 0), default=baseline_iteration)
#         if 'policy_file' in best_iteration and os.path.exists(best_iteration['policy_file']):
#             final_output_file = os.path.join(OUTPUT_DIR, f"repaired_{idx}_best.json")
#             shutil.copy2(best_iteration['policy_file'], final_output_file)
#         else:
#             # Save original policy as fallback
#             final_output_file = os.path.join(OUTPUT_DIR, f"repaired_{idx}_original.json")
#             save_json_file(original_policy, final_output_file)
#     else:
#         final_output_file = os.path.join(OUTPUT_DIR, f"repaired_{idx}_original.json")
#         save_json_file(original_policy, final_output_file)
    
#     return {
#         'index': idx,
#         'status': 'failed',
#         'baseline_accuracy': baseline_accuracy,
#         'final_accuracy': final_accuracy,
#         'improvement_from_baseline': improvement,
#         'iterations_used': MAX_ITERATIONS,
#         'iteration_accuracies': iteration_accuracies,
#         'iteration_results': iteration_results,
#         'baseline_results': baseline_results,
#         'final_policy_file': final_output_file
#     }


# # Enhanced main function to handle baseline results in summary
# def main():
#     log_file = setup_logging()
#     logging.info("Starting iterative policy repair system - EXPERIMENT 2 (with failed examples feedback)")
    
#     # Ensure required directories exist
#     for directory in [POLICY_DIR, REQUIREMENTS_DIR]:
#         if not os.path.isdir(directory):
#             logging.error(f"Directory '{directory}' not found.")
#             print(f"Directory '{directory}' not found. Exiting.")
#             sys.exit(1)
    
#     # Check if SMT validator script exists
#     if not os.path.exists(SMT_VALIDATOR_SCRIPT):
#         logging.error(f"SMT validator script '{SMT_VALIDATOR_SCRIPT}' not found.")
#         print(f"SMT validator script '{SMT_VALIDATOR_SCRIPT}' not found. Exiting.")
#         sys.exit(1)
    
#     # Create output directories
#     for directory in [OUTPUT_DIR, TEMP_DIR, os.path.join(OUTPUT_DIR, "Quacky_output")]:
#         os.makedirs(directory, exist_ok=True)
    
#     # Initialize progress tracker
#     tracker = IterativeProgressTracker()
#     total = 10
#     to_process = [i for i in range(total) if not tracker.is_done(i)]
#     logging.info(f"Policies to process: {to_process}")
    
#     all_results = []
#     all_iteration_data = []
    
#     # Process each policy
#     for idx in tqdm(to_process, desc="Processing policies iteratively (Experiment 2)"):
#         try:
#             result = process_policy_iteratively(idx)
            
#             # Track completion/failure
#             if result['status'] in ['success', 'already_perfect']:
#                 tracker.mark_completed(idx, result['final_accuracy'], result['iterations_used'], result['iteration_accuracies'])
#             else:
#                 tracker.mark_failed(idx, result['final_accuracy'], result['iterations_used'], result.get('iteration_accuracies', []))
            
#             all_results.append(result)
            
#             # Collect iteration data for detailed analysis
#             for iter_data in result['iteration_results']:
#                 all_iteration_data.append(iter_data)
            
#         except Exception as e:
#             logging.error(f"Policy {idx} failed completely: {e}")
#             tracker.mark_failed(idx, 0.0, 0, [])
#             all_results.append({
#                 'index': idx,
#                 'status': 'error',
#                 'baseline_accuracy': 0.0,
#                 'final_accuracy': 0.0,
#                 'improvement_from_baseline': 0.0,
#                 'iterations_used': 0,
#                 'iteration_accuracies': [],
#                 'error': str(e)
#             })
    
#     # Save comprehensive results
#     timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
#     # Summary results (enhanced with baseline info)
#     if all_results:
#         df_summary = pd.DataFrame(all_results)
#         summary_csv = os.path.join(OUTPUT_DIR, f"iterative_repair_exp2_summary_{timestamp}.csv")
#         df_summary.to_csv(summary_csv, index=False)
#         logging.info(f"Summary results saved to {summary_csv}")
    
#     # Detailed iteration results
#     if all_iteration_data:
#         df_iterations = pd.DataFrame(all_iteration_data)
#         iterations_csv = os.path.join(OUTPUT_DIR, f"iterative_repair_exp2_details_{timestamp}.csv")
#         df_iterations.to_csv(iterations_csv, index=False)
#         logging.info(f"Detailed iteration results saved to {iterations_csv}")
    
#     # Save failed examples analysis
#     failed_examples_analysis = []
#     for result in all_results:
#         if 'iteration_results' in result:
#             for iter_result in result['iteration_results']:
#                 if 'failed_examples' in iter_result and iter_result['failed_examples']:
#                     for example in iter_result['failed_examples']:
#                         failed_examples_analysis.append({
#                             'policy_idx': iter_result['policy_idx'],
#                             'iteration': iter_result['iteration'],
#                             'iteration_type': iter_result.get('type', 'unknown'),
#                             'request_id': example['request_id'],
#                             'action': example['action'],
#                             'resource': example['resource'],
#                             'expected': example['expected'],
#                             'actual': example['actual']
#                         })
    
#     if failed_examples_analysis:
#         df_failed = pd.DataFrame(failed_examples_analysis)
#         failed_csv = os.path.join(OUTPUT_DIR, f"iterative_repair_exp2_failed_examples_{timestamp}.csv")
#         df_failed.to_csv(failed_csv, index=False)
#         logging.info(f"Failed examples analysis saved to {failed_csv}")
    
#     # Enhanced final summary with baseline analysis
#     successful = len([r for r in all_results if r.get('status') in ['success', 'already_perfect']])
#     already_perfect = len([r for r in all_results if r.get('status') == 'already_perfect'])
#     improved = len([r for r in all_results if r.get('status') == 'success'])
#     failed = len([r for r in all_results if r.get('status') in ['failed', 'error']])
    
#     avg_baseline = sum(r.get('baseline_accuracy', 0) for r in all_results) / len(all_results) if all_results else 0
#     avg_final = sum(r.get('final_accuracy', 0) for r in all_results) / len(all_results) if all_results else 0
#     avg_improvement = avg_final - avg_baseline
    
#     total_iterations = sum(r.get('iterations_used', 0) for r in all_results)
    
#     # Calculate feedback effectiveness
#     policies_with_feedback = 0
#     feedback_improvements = 0
    
#     for result in all_results:
#         if 'iteration_results' in result and len(result['iteration_results']) > 2:  # Baseline + at least 2 repair iterations
#             iterations = [r for r in result['iteration_results'] if r.get('type') != 'baseline']
#             if len(iterations) > 1:
#                 policies_with_feedback += 1
                
#                 # Check if accuracy improved after feedback
#                 first_accuracy = iterations[0].get('accuracy', 0)
#                 best_later_accuracy = max(iter_result.get('accuracy', 0) for iter_result in iterations[1:])
                
#                 if best_later_accuracy > first_accuracy:
#                     feedback_improvements += 1
    
#     # Log the enhanced final summary
#     logging.info("=" * 60)
#     logging.info("ITERATIVE REPAIR SYSTEM - EXPERIMENT 2 FINAL SUMMARY")
#     logging.info("=" * 60)
#     logging.info(f"Total policies processed: {len(all_results)}")
#     logging.info(f"Already perfect (no repair needed): {already_perfect}")
#     logging.info(f"Successfully improved to 100%: {improved}")
#     logging.info(f"Failed to reach 100%: {failed}")
#     logging.info(f"Average baseline accuracy: {avg_baseline:.1f}%")
#     logging.info(f"Average final accuracy: {avg_final:.1f}%")
#     logging.info(f"Average improvement: {avg_improvement:+.1f}%")
#     logging.info(f"Total repair iterations used: {total_iterations}")
#     logging.info(f"Average iterations per policy: {total_iterations/len(all_results):.1f}" if all_results else "0")
#     logging.info("EXPERIMENT 2 - FAILED EXAMPLES FEEDBACK ANALYSIS:")
#     logging.info(f"Policies with multiple iterations: {policies_with_feedback}")
#     logging.info(f"Policies that improved with feedback: {feedback_improvements}")
#     logging.info(f"Feedback effectiveness rate: {(feedback_improvements/policies_with_feedback*100):.1f}%" if policies_with_feedback > 0 else "0%")
#     logging.info(f"Total failed examples captured: {len(failed_examples_analysis)}")
    
#     # Print enhanced final summary to console
#     print(f"\n{'='*60}")
#     print("ITERATIVE REPAIR SYSTEM - EXPERIMENT 2 FINAL SUMMARY")
#     print(f"{'='*60}")
#     print(f"Total policies processed: {len(all_results)}")
#     print(f"Already perfect (no repair needed): {already_perfect}")
#     print(f"Successfully improved to 100%: {improved}")
#     print(f"Failed to reach 100%: {failed}")
#     print(f"Average baseline accuracy: {avg_baseline:.1f}%")
#     print(f"Average final accuracy: {avg_final:.1f}%")
#     print(f"Average improvement: {avg_improvement:+.1f}%")
#     print(f"Total repair iterations: {total_iterations}")
#     print(f"Average iterations per policy: {total_iterations/len(all_results):.1f}" if all_results else "0")
    
#     # Rest of the summary logging and printing code remains the same...
#     # [Previous summary code continues here]
    
#     # Cleanup temporary files
#     if os.path.exists(TEMP_DIR):
#         logging.info(f"Temporary files kept for analysis in: {TEMP_DIR}")

# def main():
#     log_file = setup_logging()
#     logging.info("Starting iterative policy repair system - EXPERIMENT 2 (with failed examples feedback)")
    
#     # Ensure required directories exist
#     for directory in [POLICY_DIR, REQUIREMENTS_DIR]:
#         if not os.path.isdir(directory):
#             logging.error(f"Directory '{directory}' not found.")
#             print(f"Directory '{directory}' not found. Exiting.")
#             sys.exit(1)
    
#     # Check if SMT validator script exists
#     if not os.path.exists(SMT_VALIDATOR_SCRIPT):
#         logging.error(f"SMT validator script '{SMT_VALIDATOR_SCRIPT}' not found.")
#         print(f"SMT validator script '{SMT_VALIDATOR_SCRIPT}' not found. Exiting.")
#         sys.exit(1)
    
#     # Create output directories
#     for directory in [OUTPUT_DIR, TEMP_DIR, os.path.join(OUTPUT_DIR, "Quacky_output")]:
#         os.makedirs(directory, exist_ok=True)
    
#     # Initialize progress tracker
#     tracker = IterativeProgressTracker()
#     total = 10
#     to_process = [i for i in range(total) if not tracker.is_done(i)]
#     logging.info(f"Policies to process: {to_process}")
    
#     all_results = []
#     all_iteration_data = []
    
#     # Process each policy
#     for idx in tqdm(to_process, desc="Processing policies iteratively (Experiment 2)"):
#         try:
#             result = process_policy_iteratively(idx)
            
#             # Track completion/failure
#             if result['status'] == 'success':
#                 tracker.mark_completed(idx, result['final_accuracy'], result['iterations_used'], result['iteration_accuracies'])
#             else:
#                 tracker.mark_failed(idx, result['final_accuracy'], result['iterations_used'], result.get('iteration_accuracies', []))
            
#             all_results.append(result)
            
#             # Collect iteration data for detailed analysis
#             for iter_data in result['iteration_results']:
#                 all_iteration_data.append(iter_data)
            
#         except Exception as e:
#             logging.error(f"Policy {idx} failed completely: {e}")
#             tracker.mark_failed(idx, 0.0, 0, [])
#             all_results.append({
#                 'index': idx,
#                 'status': 'error',
#                 'final_accuracy': 0.0,
#                 'iterations_used': 0,
#                 'iteration_accuracies': [],
#                 'error': str(e)
#             })
    
#     # Save comprehensive results
#     timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
#     # Summary results
#     if all_results:
#         df_summary = pd.DataFrame(all_results)
#         summary_csv = os.path.join(OUTPUT_DIR, f"iterative_repair_exp2_summary_{timestamp}.csv")
#         df_summary.to_csv(summary_csv, index=False)
#         logging.info(f"Summary results saved to {summary_csv}")
    
#     # Detailed iteration results
#     if all_iteration_data:
#         df_iterations = pd.DataFrame(all_iteration_data)
#         iterations_csv = os.path.join(OUTPUT_DIR, f"iterative_repair_exp2_details_{timestamp}.csv")
#         df_iterations.to_csv(iterations_csv, index=False)
#         logging.info(f"Detailed iteration results saved to {iterations_csv}")
    
#     # Save failed examples analysis
#     failed_examples_analysis = []
#     for result in all_results:
#         if 'iteration_results' in result:
#             for iter_result in result['iteration_results']:
#                 if 'failed_examples' in iter_result and iter_result['failed_examples']:
#                     for example in iter_result['failed_examples']:
#                         failed_examples_analysis.append({
#                             'policy_idx': iter_result['policy_idx'],
#                             'iteration': iter_result['iteration'],
#                             'request_id': example['request_id'],
#                             'action': example['action'],
#                             'resource': example['resource'],
#                             'expected': example['expected'],
#                             'actual': example['actual']
#                         })
    
#     if failed_examples_analysis:
#         df_failed = pd.DataFrame(failed_examples_analysis)
#         failed_csv = os.path.join(OUTPUT_DIR, f"iterative_repair_exp2_failed_examples_{timestamp}.csv")
#         df_failed.to_csv(failed_csv, index=False)
#         logging.info(f"Failed examples analysis saved to {failed_csv}")
    
#     # Print final summary
#     successful = len([r for r in all_results if r.get('status') == 'success'])
#     failed = len([r for r in all_results if r.get('status') in ['failed', 'error']])
#     avg_accuracy = sum(r.get('final_accuracy', 0) for r in all_results) / len(all_results) if all_results else 0
#     total_iterations = sum(r.get('iterations_used', 0) for r in all_results)
    
#     # Calculate feedback effectiveness
#     policies_with_feedback = 0
#     feedback_improvements = 0
    
#     for result in all_results:
#         if 'iteration_results' in result and len(result['iteration_results']) > 1:
#             iterations = result['iteration_results']
#             policies_with_feedback += 1
            
#             # Check if accuracy improved after feedback
#             first_accuracy = iterations[0].get('accuracy', 0)
#             best_later_accuracy = max(iter_result.get('accuracy', 0) for iter_result in iterations[1:])
            
#             if best_later_accuracy > first_accuracy:
#                 feedback_improvements += 1
    
#     # Log the final summary to the log file
#     logging.info("=" * 60)
#     logging.info("ITERATIVE REPAIR SYSTEM - EXPERIMENT 2 FINAL SUMMARY")
#     logging.info("=" * 60)
#     logging.info(f"Total policies processed: {len(all_results)}")
#     logging.info(f"Successfully repaired (100% accuracy): {successful}")
#     logging.info(f"Failed to reach 100% accuracy: {failed}")
#     logging.info(f"Average final accuracy: {avg_accuracy:.1f}%")
#     logging.info(f"Total iterations used: {total_iterations}")
#     logging.info(f"Average iterations per policy: {total_iterations/len(all_results):.1f}" if all_results else "0")
#     logging.info("EXPERIMENT 2 - FAILED EXAMPLES FEEDBACK ANALYSIS:")
#     logging.info(f"Policies with multiple iterations: {policies_with_feedback}")
#     logging.info(f"Policies that improved with feedback: {feedback_improvements}")
#     logging.info(f"Feedback effectiveness rate: {(feedback_improvements/policies_with_feedback*100):.1f}%" if policies_with_feedback > 0 else "0%")
#     logging.info(f"Total failed examples captured: {len(failed_examples_analysis)}")
    
#     # Log successful policies details
#     success_policies = [r for r in all_results if r.get('status') == 'success']
#     if success_policies:
#         logging.info("Successful policies:")
#         for policy in success_policies:
#             iteration_accs = policy.get('iteration_accuracies', [])
#             acc_str = " -> ".join([f"{acc:.1f}%" for acc in iteration_accs]) if iteration_accs else "N/A"
#             logging.info(f"  Policy {policy['index']}: {policy['iterations_used']} iterations ({acc_str})")
    
#     # Log failed policies details
#     failed_policies = [r for r in all_results if r.get('status') in ['failed', 'error']]
#     if failed_policies:
#         logging.info("Failed policies:")
#         for policy in failed_policies:
#             if policy.get('final_accuracy', 0) > 0:
#                 iteration_accs = policy.get('iteration_accuracies', [])
#                 acc_str = " -> ".join([f"{acc:.1f}%" for acc in iteration_accs]) if iteration_accs else "N/A"
#                 logging.info(f"  Policy {policy['index']}: {policy.get('final_accuracy', 0):.1f}% (best attempt, {acc_str})")
#             else:
#                 logging.info(f"  Policy {policy['index']}: Error - {policy.get('error', 'Unknown error')}")
    
#     logging.info("=" * 60)
#     logging.info("Results files:")
#     logging.info(f"  - Summary: iterative_repair_exp2_summary_{timestamp}.csv")
#     logging.info(f"  - Detailed iterations: iterative_repair_exp2_details_{timestamp}.csv")
#     logging.info(f"  - Failed examples: iterative_repair_exp2_failed_examples_{timestamp}.csv")
#     logging.info("=" * 60)
    
#     # Print final summary to console
#     print(f"\n{'='*60}")
#     print("ITERATIVE REPAIR SYSTEM - EXPERIMENT 2 FINAL SUMMARY")
#     print(f"{'='*60}")
#     print(f"Total policies processed: {len(all_results)}")
#     print(f"Successfully repaired (100% accuracy): {successful}")
#     print(f"Failed to reach 100% accuracy: {failed}")
#     print(f"Average final accuracy: {avg_accuracy:.1f}%")
#     print(f"Total iterations used: {total_iterations}")
#     print(f"Average iterations per policy: {total_iterations/len(all_results):.1f}" if all_results else "0")
    
#     # Experiment 2 specific metrics
#     print(f"\nEXPERIMENT 2 - FAILED EXAMPLES FEEDBACK ANALYSIS:")
#     print(f"Policies with multiple iterations: {policies_with_feedback}")
#     print(f"Policies that improved with feedback: {feedback_improvements}")
#     print(f"Feedback effectiveness rate: {(feedback_improvements/policies_with_feedback*100):.1f}%" if policies_with_feedback > 0 else "0%")
#     print(f"Total failed examples captured: {len(failed_examples_analysis)}")
    
#     # Show success details
#     success_policies = [r for r in all_results if r.get('status') == 'success']
#     if success_policies:
#         print(f"\nSuccessful policies:")
#         for policy in success_policies:
#             iteration_accs = policy.get('iteration_accuracies', [])
#             acc_str = " -> ".join([f"{acc:.1f}%" for acc in iteration_accs]) if iteration_accs else "N/A"
#             print(f"  Policy {policy['index']}: {policy['iterations_used']} iterations ({acc_str})")
    
#     # Show failure details
#     failed_policies = [r for r in all_results if r.get('status') in ['failed', 'error']]
#     if failed_policies:
#         print(f"\nFailed policies:")
#         for policy in failed_policies:
#             if policy.get('final_accuracy', 0) > 0:
#                 iteration_accs = policy.get('iteration_accuracies', [])
#                 acc_str = " -> ".join([f"{acc:.1f}%" for acc in iteration_accs]) if iteration_accs else "N/A"
#                 print(f"  Policy {policy['index']}: {policy.get('final_accuracy', 0):.1f}% (best attempt, {acc_str})")
#             else:
#                 print(f"  Policy {policy['index']}: Error - {policy.get('error', 'Unknown error')}")
    
#     print(f"{'='*60}")
#     print("Results files:")
#     print(f"  - Summary: iterative_repair_exp2_summary_{timestamp}.csv")
#     print(f"  - Detailed iterations: iterative_repair_exp2_details_{timestamp}.csv")
#     print(f"  - Failed examples: iterative_repair_exp2_failed_examples_{timestamp}.csv")
#     print(f"{'='*60}")
    
#     # Cleanup temporary files
#     if os.path.exists(TEMP_DIR):
#         # shutil.rmtree(TEMP_DIR)  # Keep for debugging in Experiment 2
#         logging.info(f"Temporary files kept for analysis in: {TEMP_DIR}")

# if __name__ == "__main__":
#     main()
#!/usr/bin/env python3
"""
iterative_policy_repair_exp2.py

EXPERIMENT 2: Enhanced iterative policy repair with failed examples feedback

This script first performs baseline validation on original AWS IAM policies,
then automatically processes multiple AWS IAM policies with their 
corresponding requirement files using Claude to repair them. Unlike Experiment 1,
this version analyzes failed validation results and provides specific examples
of misclassified requests to guide the LLM in subsequent iterations.

Features:
- Baseline validation of original policies
- Iterative repair with failed examples feedback
- SMT solver validation integration
- Failed request extraction and analysis
- Comprehensive tracking of all iterations
- Results saved to CSV for analysis
- Progress tracking with resume capability

Usage:
    python3 iterative_policy_repair_exp2.py
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

POLICY_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-2/original_policy"
REQUIREMENTS_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-2/requests/request-100"
OUTPUT_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-2/results/result-100"
LOG_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-2/logs/log-100"
TEMP_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-2/temp_validation/val-100"
QUACKY_SRC_DIR = "/home/bhall2/Documents/fixmypolicy/quacky/src"
SMT_VALIDATOR_SCRIPT = "/home/bhall2/Documents/fixmypolicy/quacky/src/validate_requests.py"

# Global configurations
MAX_ITERATIONS = 5
MAX_ATTEMPT = 3
DELAY = 5
TARGET_ACCURACY = 100.0

# Configure logging
def setup_logging(log_dir: str = LOG_DIR):
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f'iterative_repair_exp2_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
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
claude_model_name = "claude-3-7-sonnet-20250219"

def get_policy_repair_prompt(problematic_policy, requirements, iteration=1, failed_examples=None):
    base_prompt = f"""
You are an AWS IAM security expert. Your task is to repair a problematic AWS IAM policy based on specific security requirements. Do not hardcode the request in the policies.

PROBLEMATIC POLICY:
{problematic_policy}

REQUIREMENTS:
{requirements}

ITERATION: {iteration}/{MAX_ITERATIONS}
"""
    
    if failed_examples and iteration > 1:
        base_prompt += f"""
FAILED EXAMPLES FROM PREVIOUS ITERATION:
The previous policy repair attempt had {len(failed_examples)} misclassified requests. 
Please pay special attention to these specific failures:

"""
        for i, example in enumerate(failed_examples, 1):
            base_prompt += f"""
Failure {i}:
- Action: {example['action']}
- Resource: {example['resource']}
- Expected: {example['expected']} (but got {example['actual']})
- Problem: This request should be {example['expected'].upper()} but was {example['actual'].upper()}
"""
        
        base_prompt += f"""
SPECIFIC GUIDANCE:
- Pay attention to wildcard patterns and resource ARN matching
"""
    base_prompt += """

CRITICAL: Return ONLY valid JSON. No explanations, no markdown, no extra text. Start with { and end with }. The JSON must be properly formatted with correct commas, brackets, and quotes.

Repaired Policy:"""
    
    return base_prompt

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
    def __init__(self, progress_file: str = os.path.join(OUTPUT_DIR, "iterative_progress_exp2.json")):
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
            "policy_iterations": {},  # Track iterations per policy
            "baseline_completed": [],  # Track baseline validation completion
            "baseline_accuracies": {}  # NEW: Track baseline accuracies explicitly
        }
    
    def save_progress(self):
        os.makedirs(os.path.dirname(self.progress_file), exist_ok=True)
        with open(self.progress_file, 'w') as f:
            json.dump(self.progress, f, indent=2)
    
    def mark_baseline_completed(self, idx, baseline_accuracy=None):
        """Mark baseline validation as completed and optionally store the accuracy"""
        if idx not in self.progress["baseline_completed"]:
            self.progress["baseline_completed"].append(idx)
        
        # Store baseline accuracy if provided
        if baseline_accuracy is not None:
            self.progress["baseline_accuracies"][str(idx)] = baseline_accuracy
            
        self.save_progress()
    
    def get_baseline_accuracy(self, idx):
        """Get the stored baseline accuracy for a policy"""
        return self.progress["baseline_accuracies"].get(str(idx), 0.0)
    
    def is_baseline_done(self, idx):
        return idx in self.progress.get("baseline_completed", [])
    
    def mark_completed(self, idx, baseline_accuracy, final_accuracy, iterations_used, iteration_accuracies):
        """Mark policy as completed with explicit baseline tracking"""
        self.progress["last_processed"] = idx
        if idx not in self.progress["completed"]:
            self.progress["completed"].append(idx)
        if idx in self.progress["failed"]:
            self.progress["failed"].remove(idx)
        
        # Store baseline accuracy
        self.progress["baseline_accuracies"][str(idx)] = baseline_accuracy
        
        self.progress["policy_iterations"][str(idx)] = {
            "status": "completed",
            "baseline_accuracy": baseline_accuracy,  # NEW: Explicit baseline
            "final_accuracy": final_accuracy,
            "improvement": final_accuracy - baseline_accuracy,  # NEW: Calculate improvement
            "iterations_used": iterations_used,
            "iteration_accuracies": iteration_accuracies  # Track all accuracies
        }
        self.save_progress()
    
    def mark_failed(self, idx, baseline_accuracy, final_accuracy, iterations_used, iteration_accuracies):
        """Mark policy as failed with explicit baseline tracking"""
        if idx not in self.progress["failed"]:
            self.progress["failed"].append(idx)
        
        # Store baseline accuracy
        self.progress["baseline_accuracies"][str(idx)] = baseline_accuracy
        
        self.progress["policy_iterations"][str(idx)] = {
            "status": "failed",
            "baseline_accuracy": baseline_accuracy,  # NEW: Explicit baseline
            "final_accuracy": final_accuracy,
            "improvement": final_accuracy - baseline_accuracy,  # NEW: Calculate improvement
            "iterations_used": iterations_used,
            "iteration_accuracies": iteration_accuracies  # Track all accuracies
        }
        self.save_progress()
    
    def get_next(self):
        return self.progress.get("last_processed", -1) + 1
    
    def is_done(self, idx):
        return idx in self.progress.get("completed", [])
    
    def get_summary_stats(self):
        """Get summary statistics including baseline performance"""
        baseline_accuracies = []
        final_accuracies = []
        improvements = []
        
        for policy_data in self.progress["policy_iterations"].values():
            if "baseline_accuracy" in policy_data:
                baseline_accuracies.append(policy_data["baseline_accuracy"])
                final_accuracies.append(policy_data["final_accuracy"])
                improvements.append(policy_data.get("improvement", 0))
        
        if not baseline_accuracies:
            return {
                "total_policies": 0,
                "avg_baseline": 0,
                "avg_final": 0,
                "avg_improvement": 0,
                "baseline_perfect": 0,
                "final_perfect": 0
            }
        
        return {
            "total_policies": len(baseline_accuracies),
            "avg_baseline": sum(baseline_accuracies) / len(baseline_accuracies),
            "avg_final": sum(final_accuracies) / len(final_accuracies),
            "avg_improvement": sum(improvements) / len(improvements),
            "baseline_perfect": len([acc for acc in baseline_accuracies if acc >= TARGET_ACCURACY]),
            "final_perfect": len([acc for acc in final_accuracies if acc >= TARGET_ACCURACY])
        }

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
def repair_policy_with_claude(policy: dict, requests: dict, iteration: int = 1, failed_examples: list = None) -> dict:
    policy_json = json.dumps(policy, indent=2)
    req_text = format_requirements(requests)
    prompt = get_policy_repair_prompt(policy_json, req_text, iteration, failed_examples)
    
    resp = claude_client.messages.create(
        model=claude_model_name,
        max_tokens=9000,  # Increased for longer prompts with examples
        temperature=0,
        system="You are an AWS IAM security expert who repairs policies to meet the request specifications using best security practices. Do not hardcode the request into the policy. Generate only valid JSON policies without any explanatory text.",
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

def extract_failed_examples(output_content: str) -> list:
    """Extract failed examples from validator output preserving exact test case details."""
    failed_examples = []
    lines = output_content.split('\n')
    
    current_request = None
    
    for line in lines:
        line = line.strip()
        
        # Look for individual request validations
        if "Validating individual request:" in line:
            # Extract request info: allow_0110392c_combo_1
            match = re.search(r'Validating individual request: (\w+)_combo_\d+', line)
            if match:
                current_request = {"id": match.group(1)}
        
        # Extract action, resource, principal, condition from the detailed line
        elif line.startswith("Action:") and current_request:
            # Parse: Action: athena:GetQueryExecution, Resource: arn:aws:s3:::bkt_logs/logs/app.log, Principal: arn:aws:iam::123456789012:role/service-role, Condition: {'Bool': {'aws:SecureTransport': 'true'}}
            parts = line.split(", ")
            for part in parts:
                if part.startswith("Action:"):
                    current_request["action"] = part.split(": ", 1)[1].strip()
                elif part.startswith("Resource:"):
                    current_request["resource"] = part.split(": ", 1)[1].strip()
                elif part.startswith("Principal:"):
                    principal_val = part.split(": ", 1)[1].strip()
                    current_request["principal"] = principal_val if principal_val != "None" else None
                elif part.startswith("Condition:"):
                    condition_val = part.split(": ", 1)[1].strip()
                    # Try to preserve the condition as a string that can be parsed as JSON
                    if condition_val != "None":
                        try:
                            # Convert Python dict string to JSON
                            condition_json = condition_val.replace("'", '"')
                            # Validate it's proper JSON
                            import json
                            json.loads(condition_json)
                            current_request["condition"] = condition_json
                        except:
                            current_request["condition"] = condition_val
                    else:
                        current_request["condition"] = None
        
        # Look for incorrect classifications
        elif "INCORRECT:" in line and current_request:
            # Parse: INCORRECT: Expected=allow, Got=deny
            match = re.search(r'Expected=(\w+), Got=(\w+)', line)
            if match:
                expected = match.group(1)
                actual = match.group(2)
                
                failed_example = {
                    "request_id": current_request.get("id", "unknown"),
                    "action": current_request.get("action", "unknown"),
                    "resource": current_request.get("resource", "unknown"),
                    "principal": current_request.get("principal"),
                    "condition": current_request.get("condition"),
                    "expected": expected,
                    "actual": actual
                }
                
                failed_examples.append(failed_example)
                logging.debug(f"Extracted research test failure: {failed_example}")
        
        # Reset current request when we see CORRECT or start new request
        elif "CORRECT:" in line or "Processing request object:" in line:
            current_request = None
    
    logging.info(f"Extracted {len(failed_examples)} failed research test cases from validator output")
    return failed_examples

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
        
        # Extract failed examples for feedback
        failed_examples = extract_failed_examples(output_content)
        
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
        logging.info(f"Found {len(failed_examples)} failed examples for feedback")
        
        return {
            'accuracy': accuracy,
            'total_requests': total_requests,
            'correct': correct_count,
            'incorrect': incorrect_count,
            'misclassified_allow_to_deny': misclassified_allow_to_deny,
            'misclassified_deny_to_allow': misclassified_deny_to_allow,
            'failed_examples': failed_examples,
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

def run_baseline_validation(idx: int) -> dict:
    """Run baseline validation on the original policy."""
    policy_file = os.path.join(POLICY_DIR, f"{idx}.json")
    req_file = os.path.join(REQUIREMENTS_DIR, f"{idx}.json")
    
    if not os.path.exists(policy_file) or not os.path.exists(req_file):
        raise FileNotFoundError(f"Missing files for index {idx}")
    
    logging.info(f"Running baseline validation for policy {idx}...")
    
    try:
        # Run SMT validator on original policy
        validation_results = run_smt_validator(policy_file, req_file)
        
        baseline_result = {
            'policy_idx': idx,
            'validation_type': 'baseline',
            'accuracy': validation_results['accuracy'],
            'total_requests': validation_results['total_requests'],
            'correct': validation_results['correct'],
            'incorrect': validation_results['incorrect'],
            'misclassified_allow_to_deny': validation_results['misclassified_allow_to_deny'],
            'misclassified_deny_to_allow': validation_results['misclassified_deny_to_allow'],
            'failed_examples_count': len(validation_results.get('failed_examples', [])),
            'failed_examples': validation_results.get('failed_examples', []),
            'output_file': validation_results['output_file']
        }
        
        logging.info(f"Baseline validation for policy {idx}: {validation_results['accuracy']:.1f}% accuracy")
        
        return baseline_result
        
    except Exception as e:
        logging.error(f"Baseline validation failed for policy {idx}: {e}")
        return {
            'policy_idx': idx,
            'validation_type': 'baseline',
            'accuracy': 0.0,
            'failed_examples_count': 0,
            'failed_examples': [],
            'error': str(e)
        }

def process_policy_iteratively(idx: int, baseline_accuracy: float = 0.0, baseline_failed_examples: list = None) -> dict:
    """Process a single policy with iterative repair and validation."""
    policy_file = os.path.join(POLICY_DIR, f"{idx}.json")
    req_file = os.path.join(REQUIREMENTS_DIR, f"{idx}.json")
    
    if not os.path.exists(policy_file) or not os.path.exists(req_file):
        raise FileNotFoundError(f"Missing files for index {idx}")
    
    # Load initial policy and requests
    original_policy = load_json_file(policy_file)
    requests = load_json_file(req_file)
    
    logging.info(f"Starting iterative repair for policy {idx} (baseline: {baseline_accuracy:.1f}%)...")
    
    # If baseline is already 100%, no need to repair
    if baseline_accuracy >= TARGET_ACCURACY:
        logging.info(f"Policy {idx} already achieves target accuracy ({baseline_accuracy:.1f}%). Skipping repair.")
        # Still save the original policy as the "repaired" version
        final_output_file = os.path.join(OUTPUT_DIR, f"repaired_{idx}_already_perfect.json")
        save_json_file(original_policy, final_output_file)
        
        return {
            'index': idx,
            'status': 'already_perfect',
            'baseline_accuracy': baseline_accuracy,
            'final_accuracy': baseline_accuracy,
            'improvement_from_baseline': 0.0,
            'iterations_used': 0,
            'iteration_accuracies': [baseline_accuracy],
            'iteration_results': [],
            'final_policy_file': final_output_file
        }
    
    # Track all iterations
    iteration_results = []
    current_policy = original_policy.copy()
    failed_examples = baseline_failed_examples or []  # Start with baseline failures
    final_accuracy = baseline_accuracy
    iteration_accuracies = [baseline_accuracy]  # Track accuracy for each iteration (starting with baseline)
    
    for iteration in range(1, MAX_ITERATIONS + 1):
        logging.info(f"Policy {idx} - Iteration {iteration}/{MAX_ITERATIONS} (Previous: {final_accuracy:.1f}%)")
        
        try:
            # Repair policy with Claude (with failed examples feedback)
            logging.info(f"Repairing policy with Claude (iteration {iteration})...")
            if failed_examples:
                logging.info(f"Providing {len(failed_examples)} failed examples as guidance")
            
            repaired_policy = repair_policy_with_claude(
                current_policy, requests, iteration, failed_examples
            )
            
            # Save temporary repaired policy for validation
            temp_policy_file = os.path.join(TEMP_DIR, f"policy_{idx}_iter_{iteration}.json")
            os.makedirs(TEMP_DIR, exist_ok=True)
            save_json_file(repaired_policy, temp_policy_file)
            
            # Validate with SMT solver
            logging.info(f"Validating with SMT solver (iteration {iteration})...")
            validation_results = run_smt_validator(temp_policy_file, req_file)
            
            accuracy = validation_results['accuracy']
            current_failed_examples = validation_results.get('failed_examples', [])
            
            # Track this iteration's accuracy
            iteration_accuracies.append(accuracy)
            
            # Calculate improvement from baseline
            improvement = accuracy - baseline_accuracy
            
            logging.info(f"Iteration {iteration} Results:")
            logging.info(f"  Accuracy: {accuracy:.1f}% (Baseline: {baseline_accuracy:.1f}%, Improvement: {improvement:+.1f}%)")
            logging.info(f"  Failed Examples: {len(current_failed_examples)}")
            
            # Record this iteration
            iteration_record = {
                'policy_idx': idx,
                'iteration': iteration,
                'validation_type': 'repair',
                'accuracy': accuracy,
                'baseline_accuracy': baseline_accuracy,
                'improvement_from_baseline': improvement,
                'total_requests': validation_results['total_requests'],
                'correct': validation_results['correct'],
                'incorrect': validation_results['incorrect'],
                'misclassified_allow_to_deny': validation_results['misclassified_allow_to_deny'],
                'misclassified_deny_to_allow': validation_results['misclassified_deny_to_allow'],
                'failed_examples_count': len(current_failed_examples),
                'failed_examples': current_failed_examples,
                'policy_file': temp_policy_file
            }
            iteration_results.append(iteration_record)
            
            final_accuracy = accuracy
            
            # Check if we achieved target accuracy
            if accuracy >= TARGET_ACCURACY:
                logging.info(f"Target accuracy achieved for policy {idx} in {iteration} iterations!")
                logging.info(f"Final accuracy: {accuracy:.1f}% (Improvement from baseline: {improvement:+.1f}%)")
                
                # Save final repaired policy
                final_output_file = os.path.join(OUTPUT_DIR, f"repaired_{idx}_final.json")
                save_json_file(repaired_policy, final_output_file)
                
                return {
                    'index': idx,
                    'status': 'success',
                    'baseline_accuracy': baseline_accuracy,
                    'final_accuracy': accuracy,
                    'improvement_from_baseline': improvement,
                    'iterations_used': iteration,
                    'iteration_accuracies': iteration_accuracies,
                    'iteration_results': iteration_results,
                    'final_policy_file': final_output_file
                }
            
            # Update for next iteration - use the repaired policy and failed examples as feedback
            current_policy = repaired_policy.copy()
            failed_examples = current_failed_examples if current_failed_examples else None
            
        except Exception as e:
            logging.error(f"Error in iteration {iteration} for policy {idx}: {e}")
            iteration_record = {
                'policy_idx': idx,
                'iteration': iteration,
                'validation_type': 'repair',
                'accuracy': 0.0,
                'baseline_accuracy': baseline_accuracy,
                'improvement_from_baseline': -baseline_accuracy,
                'failed_examples_count': 0,
                'error': str(e)
            }
            iteration_results.append(iteration_record)
    
    # If we reach here, we didn't achieve target accuracy
    improvement = final_accuracy - baseline_accuracy
    logging.warning(f"Failed to achieve target accuracy for policy {idx} after {MAX_ITERATIONS} iterations.")
    logging.warning(f"Final accuracy: {final_accuracy:.1f}% (Baseline: {baseline_accuracy:.1f}%, Improvement: {improvement:+.1f}%)")
    
    # Save best attempt
    if iteration_results:
        best_iteration = max(iteration_results, key=lambda x: x.get('accuracy', 0))
        if 'policy_file' in best_iteration and os.path.exists(best_iteration['policy_file']):
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
        'improvement_from_baseline': improvement,
        'iterations_used': MAX_ITERATIONS,
        'iteration_accuracies': iteration_accuracies,
        'iteration_results': iteration_results,
        'final_policy_file': final_output_file
    }

def main():
    log_file = setup_logging()
    logging.info("Starting iterative policy repair system - EXPERIMENT 2 (with failed examples feedback and baseline validation)")
    
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
    for directory in [OUTPUT_DIR, TEMP_DIR, os.path.join(OUTPUT_DIR, "Quacky_output")]:
        os.makedirs(directory, exist_ok=True)
    
    # Initialize progress tracker
    tracker = IterativeProgressTracker()
    total = 10
    
    # Step 1: Run baseline validation for all policies
    print("=" * 60)
    print("STEP 1: BASELINE VALIDATION")
    print("=" * 60)
    
    baseline_results = []
    baseline_to_process = [i for i in range(total) if not tracker.is_baseline_done(i)]
    
    if baseline_to_process:
        logging.info(f"Running baseline validation for policies: {baseline_to_process}")
        
        for idx in tqdm(baseline_to_process, desc="Baseline validation"):
            try:
                baseline_result = run_baseline_validation(idx)
                baseline_results.append(baseline_result)
                
                # Store baseline accuracy in tracker
                baseline_accuracy = baseline_result.get('accuracy', 0.0)
                tracker.mark_baseline_completed(idx, baseline_accuracy)
                
                # Log baseline result
                if 'error' not in baseline_result:
                    logging.info(f"Policy {idx} baseline: {baseline_accuracy:.1f}% accuracy, {baseline_result['failed_examples_count']} failed examples")
                else:
                    logging.error(f"Policy {idx} baseline failed: {baseline_result['error']}")
                    
            except Exception as e:
                logging.error(f"Baseline validation failed for policy {idx}: {e}")
                baseline_results.append({
                    'policy_idx': idx,
                    'validation_type': 'baseline',
                    'accuracy': 0.0,
                    'failed_examples_count': 0,
                    'failed_examples': [],
                    'error': str(e)
                })
                tracker.mark_baseline_completed(idx, 0.0)  # Mark as done with 0% accuracy
    else:
        logging.info("All baseline validations already completed. Loading existing results...")
        # Load baseline accuracies from tracker
        for i in range(total):
            baseline_accuracy = tracker.get_baseline_accuracy(i)
            baseline_results.append({
                'policy_idx': i,
                'validation_type': 'baseline',
                'accuracy': baseline_accuracy,
                'failed_examples_count': 0,
                'failed_examples': []
            })
    
    # Save baseline results
    if baseline_results:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        baseline_csv = os.path.join(OUTPUT_DIR, f"baseline_results_exp2_{timestamp}.csv")
        baseline_df = pd.DataFrame(baseline_results)
        baseline_df.to_csv(baseline_csv, index=False)
        logging.info(f"Baseline results saved to {baseline_csv}")
        
        # Also save as latest baseline
        latest_baseline_csv = os.path.join(OUTPUT_DIR, "baseline_results_exp2.csv")
        baseline_df.to_csv(latest_baseline_csv, index=False)
    
    # Print baseline summary
    print(f"\n{'='*60}")
    print("BASELINE VALIDATION SUMMARY")
    print(f"{'='*60}")
    successful_baselines = [r for r in baseline_results if r.get('accuracy', 0) > 0 and 'error' not in r]
    failed_baselines = [r for r in baseline_results if 'error' in r]
    perfect_baselines = [r for r in baseline_results if r.get('accuracy', 0) >= TARGET_ACCURACY]
    
    if successful_baselines:
        avg_baseline_accuracy = sum(r['accuracy'] for r in successful_baselines) / len(successful_baselines)
        total_failed_examples = sum(r.get('failed_examples_count', 0) for r in successful_baselines)
        print(f"Successfully validated policies: {len(successful_baselines)}")
        print(f"Failed baseline validations: {len(failed_baselines)}")
        print(f"Average baseline accuracy: {avg_baseline_accuracy:.1f}%")
        print(f"Total failed examples (baseline): {total_failed_examples}")
        print(f"Policies already at target accuracy: {len(perfect_baselines)}")
        
        if perfect_baselines:
            perfect_indices = [r['policy_idx'] for r in perfect_baselines]
            print(f"Perfect baseline policies: {perfect_indices}")
    
    print(f"{'='*60}")
    
    # Step 2: Iterative repair for policies that need improvement
    print("\nSTEP 2: Iterative Repair")
    print("=" * 60)
    
    # Create baseline accuracy and failed examples lookup
    baseline_accuracy_map = {r['policy_idx']: r.get('accuracy', 0.0) for r in baseline_results}
    baseline_failed_examples_map = {r['policy_idx']: r.get('failed_examples', []) for r in baseline_results}
    
    to_process = [i for i in range(total) if not tracker.is_done(i)]
    logging.info(f"Policies to process for repair: {to_process}")
    
    all_results = []
    all_iteration_data = baseline_results.copy()  # Start with baseline data
    
    # Process each policy
    for idx in tqdm(to_process, desc="Processing policies iteratively (Experiment 2)"):
        try:
            baseline_acc = baseline_accuracy_map.get(idx, 0.0)
            baseline_failed = baseline_failed_examples_map.get(idx, [])
            result = process_policy_iteratively(idx, baseline_acc, baseline_failed)
            
            # Track completion/failure with explicit baseline
            if result['status'] in ['success', 'already_perfect']:
                tracker.mark_completed(
                    idx, 
                    result['baseline_accuracy'], 
                    result['final_accuracy'], 
                    result['iterations_used'], 
                    result['iteration_accuracies']
                )
            else:
                tracker.mark_failed(
                    idx, 
                    result['baseline_accuracy'], 
                    result['final_accuracy'], 
                    result['iterations_used'], 
                    result.get('iteration_accuracies', [])
                )
            
            all_results.append(result)
            
            # Collect iteration data for detailed analysis
            for iter_data in result['iteration_results']:
                all_iteration_data.append(iter_data)
            
        except Exception as e:
            logging.error(f"Policy {idx} failed completely: {e}")
            baseline_acc = baseline_accuracy_map.get(idx, 0.0)
            tracker.mark_failed(idx, baseline_acc, 0.0, 0, [])
            all_results.append({
                'index': idx,
                'status': 'error',
                'baseline_accuracy': baseline_acc,
                'final_accuracy': 0.0,
                'improvement_from_baseline': 0.0,
                'iterations_used': 0,
                'iteration_accuracies': [],
                'error': str(e)
            })
    
    # Save comprehensive results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Summary results (enhanced with baseline info)
    if all_results:
        df_summary = pd.DataFrame(all_results)
        summary_csv = os.path.join(OUTPUT_DIR, f"iterative_repair_exp2_summary_{timestamp}.csv")
        df_summary.to_csv(summary_csv, index=False)
        logging.info(f"Summary results saved to {summary_csv}")
    
    # Detailed iteration results (includes baseline + all repair iterations)
    if all_iteration_data:
        df_iterations = pd.DataFrame(all_iteration_data)
        iterations_csv = os.path.join(OUTPUT_DIR, f"iterative_repair_exp2_details_{timestamp}.csv")
        df_iterations.to_csv(iterations_csv, index=False)
        logging.info(f"Detailed iteration results saved to {iterations_csv}")
    
    # Save failed examples analysis
    failed_examples_analysis = []
    for result in all_results:
        if 'iteration_results' in result:
            for iter_result in result['iteration_results']:
                if 'failed_examples' in iter_result and iter_result['failed_examples']:
                    for example in iter_result['failed_examples']:
                        failed_examples_analysis.append({
                            'policy_idx': iter_result['policy_idx'],
                            'iteration': iter_result['iteration'],
                            'iteration_type': iter_result.get('validation_type', 'unknown'),
                            'request_id': example['request_id'],
                            'action': example['action'],
                            'resource': example['resource'],
                            'expected': example['expected'],
                            'actual': example['actual']
                        })
    
    # Also include baseline failed examples
    for baseline_result in baseline_results:
        if 'failed_examples' in baseline_result and baseline_result['failed_examples']:
            for example in baseline_result['failed_examples']:
                failed_examples_analysis.append({
                    'policy_idx': baseline_result['policy_idx'],
                    'iteration': 0,  # Baseline
                    'iteration_type': 'baseline',
                    'request_id': example['request_id'],
                    'action': example['action'],
                    'resource': example['resource'],
                    'expected': example['expected'],
                    'actual': example['actual']
                })
    
    if failed_examples_analysis:
        df_failed = pd.DataFrame(failed_examples_analysis)
        failed_csv = os.path.join(OUTPUT_DIR, f"iterative_repair_exp2_failed_examples_{timestamp}.csv")
        df_failed.to_csv(failed_csv, index=False)
        logging.info(f"Failed examples analysis saved to {failed_csv}")
    
    # Enhanced final summary with baseline analysis
    successful = len([r for r in all_results if r.get('status') in ['success', 'already_perfect']])
    already_perfect = len([r for r in all_results if r.get('status') == 'already_perfect'])
    improved = len([r for r in all_results if r.get('status') == 'success'])
    failed = len([r for r in all_results if r.get('status') in ['failed', 'error']])
    
    if all_results:
        avg_baseline = sum(r.get('baseline_accuracy', 0) for r in all_results) / len(all_results)
        avg_final = sum(r.get('final_accuracy', 0) for r in all_results) / len(all_results)
        avg_improvement = avg_final - avg_baseline
        total_iterations = sum(r.get('iterations_used', 0) for r in all_results)
        
        # Calculate improvement
        baseline_perfect = len([r for r in all_results if r.get('baseline_accuracy', 0) >= TARGET_ACCURACY])
        final_perfect = len([r for r in all_results if r.get('final_accuracy', 0) >= TARGET_ACCURACY])
        improvement_count = final_perfect - baseline_perfect
    else:
        avg_baseline = avg_final = avg_improvement = total_iterations = improvement_count = 0
        baseline_perfect = final_perfect = 0
    
    # Calculate feedback effectiveness
    policies_with_feedback = 0
    feedback_improvements = 0
    
    for result in all_results:
        if 'iteration_results' in result and len(result['iteration_results']) > 1:
            iterations = result['iteration_results']
            policies_with_feedback += 1
            
            # Check if accuracy improved after feedback
            baseline_acc = result.get('baseline_accuracy', 0)
            best_later_accuracy = max(iter_result.get('accuracy', 0) for iter_result in iterations)
            
            if best_later_accuracy > baseline_acc:
                feedback_improvements += 1
    
    # Get enhanced summary stats from tracker
    tracker_stats = tracker.get_summary_stats()
    
    # Log the enhanced final summary
    logging.info("=" * 60)
    logging.info(f"Total policies processed: {len(all_results)}")
    logging.info(f"")
    logging.info(f"baseline performance:")
    logging.info(f"  Average baseline accuracy: {avg_baseline:.1f}%")
    logging.info(f"  Policies at target (baseline): {baseline_perfect}")
    logging.info(f"")
    logging.info(f"Final performance:")
    logging.info(f"  Successfully repaired to 100%: {improved}")
    logging.info(f"  Already perfect (no repair needed): {already_perfect}")
    logging.info(f"  Failed to reach 100%: {failed}")
    logging.info(f"  Average final accuracy: {avg_final:.1f}%")
    logging.info(f"  Policies at target (final): {final_perfect}")
    logging.info(f"")
    logging.info(f"Improvement:")
    logging.info(f"  Net improvement: +{improvement_count} policies reaching 100%")
    logging.info(f"  Accuracy improvement: {avg_improvement:.1f} percentage points")
    logging.info(f"  Total iterations used: {total_iterations}")
    logging.info(f"  Average iterations per policy: {total_iterations/len(all_results):.1f}" if all_results else "0")
    logging.info(f"")
    logging.info(f"PROGRESS TRACKER SUMMARY:")
    logging.info(f"  Tracked policies: {tracker_stats['total_policies']}")
    logging.info(f"  Tracker avg baseline: {tracker_stats['avg_baseline']:.1f}%")
    logging.info(f"  Tracker avg final: {tracker_stats['avg_final']:.1f}%")
    logging.info(f"  Tracker avg improvement: {tracker_stats['avg_improvement']:.1f}%")
    logging.info("=" * 60)
    
    # Print enhanced final summary to console
    print(f"\n{'='*60}")
    print("ITERATIVE REPAIR SYSTEM - EXPERIMENT 2 FINAL SUMMARY")
    print(f"{'='*60}")
    print(f"Total policies processed: {len(all_results)}")
    print(f"")
    print(f"BASELINE PERFORMANCE:")
    print(f"  Average baseline accuracy: {avg_baseline:.1f}%")
    print(f"  Policies at target (baseline): {baseline_perfect}")
    print(f"")
    print(f"FINAL PERFORMANCE:")
    print(f"  Successfully repaired to 100%: {improved}")
    print(f"  Already perfect (no repair needed): {already_perfect}")
    print(f"  Failed to reach 100%: {failed}")
    print(f"  Average final accuracy: {avg_final:.1f}%")
    print(f"  Policies at target (final): {final_perfect}")
    print(f"")
    print(f"IMPROVEMENT:")
    print(f"  Net improvement: +{improvement_count} policies reaching 100%")
    print(f"  Accuracy improvement: {avg_improvement:.1f} percentage points")
    print(f"  Total iterations used: {total_iterations}")
    print(f"  Average iterations per policy: {total_iterations/len(all_results):.1f}" if all_results else "0")
    
    # Experiment 2 specific metrics
    print(f"\nEXPERIMENT 2 - FAILED EXAMPLES FEEDBACK ANALYSIS:")
    print(f"  Policies with multiple iterations: {policies_with_feedback}")
    print(f"  Policies that improved with feedback: {feedback_improvements}")
    print(f"  Feedback effectiveness rate: {(feedback_improvements/policies_with_feedback*100):.1f}%" if policies_with_feedback > 0 else "0%")
    print(f"  Total failed examples captured: {len(failed_examples_analysis)}")
    
    # Show baseline accuracies from tracker
    print(f"\nBASELINE ACCURACIES FROM TRACKER:")
    for i in range(total):
        baseline_acc = tracker.get_baseline_accuracy(i)
        print(f"  Policy {i}: {baseline_acc:.1f}%")
    
    # Show detailed policy-by-policy results
    print(f"\nDETAILED RESULTS:")
    for result in all_results:
        idx = result['index']
        baseline = result.get('baseline_accuracy', 0)
        final = result.get('final_accuracy', 0)
        status = result.get('status', 'unknown')
        iterations = result.get('iterations_used', 0)
        improvement = result.get('improvement_from_baseline', 0)
        
        if status == 'already_perfect':
            print(f"  Policy {idx}: {baseline:.1f}% → {final:.1f}% (already perfect)")
        elif status == 'success':
            print(f"  Policy {idx}: {baseline:.1f}% → {final:.1f}% (SUCCESS in {iterations} iterations, +{improvement:.1f}%)")
        elif status == 'failed':
            print(f"  Policy {idx}: {baseline:.1f}% → {final:.1f}% (failed after {iterations} iterations, +{improvement:.1f}%)")
        else:
            print(f"  Policy {idx}: {baseline:.1f}% → {final:.1f}% (ERROR: {result.get('error', 'unknown')})")
    
    print(f"{'='*60}")
    print("Results files:")
    print(f"  - Baseline: baseline_results_exp2_{timestamp}.csv")
    print(f"  - Summary: iterative_repair_exp2_summary_{timestamp}.csv")
    print(f"  - Detailed iterations: iterative_repair_exp2_details_{timestamp}.csv")
    print(f"  - Failed examples: iterative_repair_exp2_failed_examples_{timestamp}.csv")
    print(f"  - Progress tracker: {tracker.progress_file}")
    print(f"{'='*60}")
    
    # Cleanup temporary files
    if os.path.exists(TEMP_DIR):
        logging.info(f"Temporary files kept for analysis in: {TEMP_DIR}")

if __name__ == "__main__":
    main()