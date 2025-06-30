# # #!/usr/bin/env python3
# # """
# # iterative_policy_repair.py

# # This script first performs baseline validation on original AWS IAM policies,
# # then iteratively repairs them using Claude and validates with SMT solver.
# # It attempts up to 5 iterations per policy until 100% accuracy is achieved.

# # Features:
# # - Baseline validation of original policies
# # - Iterative repair with accuracy feedback
# # - SMT solver validation integration
# # - Comprehensive tracking of all iterations
# # - Results saved to CSV for analysis
# # - Progress tracking with resume capability

# # Usage:
# #     python3 iterative_policy_repair.py
# # """

# # import os
# # import sys
# # import time
# # import json
# # import logging
# # import re
# # import subprocess
# # import tempfile
# # import shutil
# # from functools import wraps
# # from datetime import datetime
# # from pathlib import Path
# # import pandas as pd
# # from tqdm import tqdm
# # import anthropic


# # POLICY_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-1/original_policy"
# # REQUIREMENTS_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-1/requests/request-80"
# # OUTPUT_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-1/results/result-80"
# # LOG_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-1/logs/log-80"
# # TEMP_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-1/temp_validation/val-80"
# # QUACKY_SRC_DIR = "/home/bhall2/Documents/fixmypolicy/quacky/src"
# # SMT_VALIDATOR_SCRIPT = "/home/bhall2/Documents/fixmypolicy/quacky/src/validate_requests.py"


# # # Global configurations
# # MAX_ITERATIONS = 5
# # MAX_ATTEMPT = 3
# # DELAY = 5
# # TARGET_ACCURACY = 100.0

# # # Configure logging
# # def setup_logging(log_dir: str = LOG_DIR):
# #     os.makedirs(log_dir, exist_ok=True)
# #     log_file = os.path.join(log_dir, f'iterative_repair_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
# #     logging.basicConfig(
# #         level=logging.INFO,
# #         format='%(asctime)s - %(levelname)s - %(message)s',
# #         handlers=[
# #             logging.FileHandler(log_file),
# #             logging.StreamHandler()
# #         ]
# #     )
# #     return log_file

# # # API Client Initialization
# # claude_client = anthropic.Anthropic(
# #     api_key="REDACTED_API_KEY",
# # )
# # claude_model_name = "claude-sonnet-4-20250514"

# # # Simple policy repair prompt without feedback
# # def get_policy_repair_prompt(problematic_policy, requirements):
# #     prompt = f"""
# # You are an AWS IAM security expert. Your task is to repair a problematic AWS IAM policy based on specific security requirements.

# # PROBLEMATIC POLICY:
# # {problematic_policy}

# # SECURITY REQUIREMENTS:
# # {requirements}

# # Your task:
# # 1. Analyze the problematic policy against the security requirements
# # 2. Identify what's wrong or missing in the current policy
# # 3. Generate a repaired policy that meets ALL the security requirements
# # 4. Ensure the policy follows AWS IAM best practices (principle of least privilege, proper resource specification, etc.)

# # CRITICAL: Return ONLY valid JSON. No explanations, no markdown, no extra text. Start with {{ and end with }}. The JSON must be properly formatted with correct commas, brackets, and quotes.

# # The policy must include:
# # - "Version": "2012-10-17"
# # - "Statement": [array of statement objects]
# # - Each statement must have "Sid", "Effect", "Action", "Resource", "Condition" and "Principal" fields

# # Repaired Policy:"""
    
# #     return prompt

# # # Retry decorator
# # def retry(max_attempts=MAX_ATTEMPT, delay=DELAY):
# #     def decorator(func):
# #         @wraps(func)
# #         def wrapper(*args, **kwargs):
# #             attempts = 0
# #             while attempts < max_attempts:
# #                 try:
# #                     return func(*args, **kwargs)
# #                 except Exception as e:
# #                     attempts += 1
# #                     if attempts == max_attempts:
# #                         raise
# #                     logging.warning(f"Attempt {attempts} failed: {e}. Retrying in {delay} seconds...")
# #                     time.sleep(delay)
# #         return wrapper
# #     return decorator

# # class IterativeProgressTracker:
# #     def __init__(self, progress_file: str = os.path.join(OUTPUT_DIR, "iterative_progress.json")):
# #         self.progress_file = progress_file
# #         self.progress = self._load_progress()
    
# #     def _load_progress(self):
# #         if os.path.exists(self.progress_file):
# #             try:
# #                 with open(self.progress_file, 'r') as f:
# #                     return json.load(f)
# #             except:
# #                 pass
# #         return {
# #             "last_processed": -1, 
# #             "completed": [], 
# #             "failed": [],
# #             "policy_iterations": {},  # Track iterations per policy
# #             "baseline_completed": []  # Track baseline validation completion
# #         }
    
# #     def save_progress(self):
# #         os.makedirs(os.path.dirname(self.progress_file), exist_ok=True)
# #         with open(self.progress_file, 'w') as f:
# #             json.dump(self.progress, f, indent=2)
    
# #     def mark_baseline_completed(self, idx):
# #         if idx not in self.progress["baseline_completed"]:
# #             self.progress["baseline_completed"].append(idx)
# #         self.save_progress()
    
# #     def is_baseline_done(self, idx):
# #         return idx in self.progress.get("baseline_completed", [])
    
# #     def mark_completed(self, idx, final_accuracy, iterations_used):
# #         self.progress["last_processed"] = idx
# #         if idx not in self.progress["completed"]:
# #             self.progress["completed"].append(idx)
# #         if idx in self.progress["failed"]:
# #             self.progress["failed"].remove(idx)
        
# #         self.progress["policy_iterations"][str(idx)] = {
# #             "status": "completed",
# #             "final_accuracy": final_accuracy,
# #             "iterations_used": iterations_used
# #         }
# #         self.save_progress()
    
# #     def mark_failed(self, idx, final_accuracy, iterations_used):
# #         if idx not in self.progress["failed"]:
# #             self.progress["failed"].append(idx)
        
# #         self.progress["policy_iterations"][str(idx)] = {
# #             "status": "failed",
# #             "final_accuracy": final_accuracy,
# #             "iterations_used": iterations_used
# #         }
# #         self.save_progress()
    
# #     def get_next(self):
# #         return self.progress.get("last_processed", -1) + 1
    
# #     def is_done(self, idx):
# #         return idx in self.progress.get("completed", [])

# # def load_json_file(path: str) -> dict:
# #     with open(path, 'r', encoding='utf-8') as f:
# #         return json.load(f)

# # def save_json_file(data: dict, path: str):
# #     os.makedirs(os.path.dirname(path), exist_ok=True)
# #     with open(path, 'w', encoding='utf-8') as f:
# #         json.dump(data, f, indent=2)

# # def format_requirements(requests: dict) -> str:
# #     if "Requests" not in requests:
# #         raise ValueError("Invalid request format: missing 'Requests' key")
    
# #     allow = []
# #     deny = []
    
# #     for req in requests["Requests"]:
# #         if req.get("Effect", "").lower() == "allow":
# #             allow.append(req)
# #         else:
# #             deny.append(req)
    
# #     lines = []
# #     if allow:
# #         lines.append("MUST ALLOW:")
# #         for i, r in enumerate(allow, 1):
# #             lines.append(f"  {i}. ID: {r.get('id')} Actions: {r.get('Action')} Resources: {r.get('Resource')}")
    
# #     if deny:
# #         lines.append("MUST DENY:")
# #         for i, r in enumerate(deny, 1):
# #             lines.append(f"  {i}. ID: {r.get('id')} Actions: {r.get('Action')} Resources: {r.get('Resource')}")
    
# #     lines.append("ADDITIONAL REQUIREMENTS:")
# #     lines.extend([
# #         "  - Version must be '2012-10-17'",
# #         "  - Principle of least privilege",
# #         "  - Specific ARNs where provided",
# #         "  - Ensure actions allowed/denied as specified",
# #     ])
    
# #     return "\n".join(lines)

# # def extract_and_validate_json(response_text: str) -> dict:
# #     """Extract and validate JSON from Claude's response with improved error handling."""
# #     text = response_text.strip()
    
# #     # Remove markdown formatting
# #     if text.startswith("```json"):
# #         text = text[7:]
# #     elif text.startswith("```"):
# #         text = text[3:]
    
# #     if text.endswith("```"):
# #         text = text[:-3]
    
# #     text = text.strip()
    
# #     # Find JSON boundaries
# #     start_idx = text.find("{")
# #     end_idx = text.rfind("}")
    
# #     if start_idx == -1 or end_idx == -1:
# #         raise ValueError(f"No JSON object found in response. Text: {text[:200]}...")
    
# #     json_text = text[start_idx:end_idx+1]
# #     logging.debug(f"Extracted JSON: {json_text}")
    
# #     try:
# #         parsed_json = json.loads(json_text)
        
# #         # Validate required fields
# #         if not isinstance(parsed_json, dict):
# #             raise ValueError("Response is not a JSON object")
        
# #         if "Version" not in parsed_json:
# #             raise ValueError("Missing 'Version' field in policy")
        
# #         if "Statement" not in parsed_json:
# #             raise ValueError("Missing 'Statement' field in policy")
        
# #         if not isinstance(parsed_json["Statement"], list):
# #             raise ValueError("'Statement' field must be an array")
        
# #         return parsed_json
        
# #     except json.JSONDecodeError as e:
# #         # Try to fix common JSON issues
# #         logging.warning(f"JSON decode error: {e}. Attempting to fix...")
        
# #         # Fix trailing commas
# #         fixed_json = re.sub(r',(\s*[}\]])', r'\1', json_text)
        
# #         # Fix missing quotes around keys
# #         fixed_json = re.sub(r'(\w+):', r'"\1":', fixed_json)
        
# #         try:
# #             parsed_json = json.loads(fixed_json)
# #             logging.info("Successfully fixed JSON syntax issues")
# #             return parsed_json
# #         except json.JSONDecodeError as e2:
# #             raise ValueError(f"Failed to parse JSON even after fixes. Original error: {e}. Fixed JSON: {fixed_json}")

# # @retry()
# # def repair_policy_with_claude(policy: dict, requests: dict) -> dict:
# #     policy_json = json.dumps(policy, indent=2)
# #     req_text = format_requirements(requests)
# #     prompt = get_policy_repair_prompt(policy_json, req_text)
    
# #     resp = claude_client.messages.create(
# #         model=claude_model_name,
# #         max_tokens=4000,
# #         temperature=0,
# #         system="You are an AWS IAM security expert who repairs policies to meet specific security requirements. Generate only valid JSON policies without any explanatory text.",
# #         messages=[{"role": "user", "content": prompt}]
# #     )
    
# #     # Extract response text
# #     response_text = ""
# #     for block in getattr(resp, 'content', []):
# #         if hasattr(block, 'type') and block.type == 'text':
# #             response_text += block.text
    
# #     if not response_text:
# #         raise ValueError("Empty response from Claude")
    
# #     logging.debug(f"Raw Claude response: {response_text}")
# #     return extract_and_validate_json(response_text)

# # def run_smt_validator(policy_file: str, requests_file: str) -> dict:
# #     """Run the SMT validator and return parsed results."""
# #     try:
# #         # Change to the Quacky source directory
# #         original_dir = os.getcwd()
# #         os.chdir(QUACKY_SRC_DIR)
        
# #         # Create output directory if it doesn't exist
# #         quacky_output_dir = os.path.join(OUTPUT_DIR, "Quacky_output")
# #         os.makedirs(quacky_output_dir, exist_ok=True)
        
# #         # Create unique output file name
# #         timestamp = int(time.time())
# #         pid = os.getpid()
# #         output_file_path = os.path.join(quacky_output_dir, f"temp_validation_{pid}_{timestamp}.txt")
        
# #         # Run the validator with your exact command structure
# #         cmd = [
# #             'python3', 'validate_requests.py',
# #             '-p1', policy_file,
# #             '--requests', requests_file,
# #             '-s'
# #         ]
        
# #         logging.debug(f"Running SMT validator: cd {QUACKY_SRC_DIR} && {' '.join(cmd)} > {output_file_path}")
        
# #         # Run the command and redirect output to file
# #         with open(output_file_path, 'w') as output_file:
# #             result = subprocess.run(cmd, stdout=output_file, stderr=subprocess.PIPE, text=True, timeout=300)
        
# #         # Change back to original directory
# #         os.chdir(original_dir)
        
# #         if result.returncode != 0:
# #             logging.error(f"SMT validator failed: {result.stderr}")
# #             # Clean up temp file
# #             if os.path.exists(output_file_path):
# #                 os.unlink(output_file_path)
# #             raise Exception(f"SMT validator failed: {result.stderr}")
        
# #         # Read the output file to parse results
# #         with open(output_file_path, 'r') as f:
# #             output_content = f.read()
        
# #         logging.debug(f"Validator output saved to: {output_file_path}")
# #         logging.debug(f"Raw validator output (first 1000 chars): {output_content[:1000]}")
        
# #         # Parse the output to extract accuracy information
# #         output_lines = output_content.split('\n')
        
# #         # Look for accuracy information in the output
# #         accuracy = 0.0
# #         total_requests = 0
# #         correct_count = 0
# #         incorrect_count = 0
# #         misclassified_allow_to_deny = 0
# #         misclassified_deny_to_allow = 0
        
# #         # Parse the specific format from your validator
# #         in_analysis_section = False
# #         found_analysis_section = False
        
# #         for i, line in enumerate(output_lines):
# #             line = line.strip()
            
# #             # Check if we're in the analysis section
# #             if "INDIVIDUAL REQUEST ANALYSIS" in line:
# #                 in_analysis_section = True
# #                 found_analysis_section = True
# #                 logging.debug(f"Found analysis section at line {i}: {line}")
# #                 continue
# #             elif line.startswith("=") and in_analysis_section and len(line) > 10:
# #                 # End of analysis section (long line of equals)
# #                 if any(phrase in ''.join(output_lines[i:i+5]) for phrase in ["Results saved", "saved to HOME"]):
# #                     logging.debug(f"End of analysis section at line {i}")
# #                     break
            
# #             if in_analysis_section:
# #                 logging.debug(f"Parsing analysis line {i}: {line}")
# #                 if line.startswith("Total Individual Requests:"):
# #                     total_match = re.search(r'(\d+)', line)
# #                     if total_match:
# #                         total_requests = int(total_match.group(1))
# #                         logging.debug(f"Found total requests: {total_requests}")
# #                 elif line.startswith("Correct Classifications:"):
# #                     correct_match = re.search(r'(\d+)', line)
# #                     if correct_match:
# #                         correct_count = int(correct_match.group(1))
# #                         logging.debug(f"Found correct count: {correct_count}")
# #                 elif line.startswith("Incorrect Classifications:"):
# #                     incorrect_match = re.search(r'(\d+)', line)
# #                     if incorrect_match:
# #                         incorrect_count = int(incorrect_match.group(1))
# #                         logging.debug(f"Found incorrect count: {incorrect_count}")
# #                 elif line.startswith("Overall Accuracy:"):
# #                     accuracy_match = re.search(r'(\d+\.?\d*)%', line)
# #                     if accuracy_match:
# #                         accuracy = float(accuracy_match.group(1))
# #                         logging.debug(f"Found accuracy: {accuracy}%")
# #                 elif line.startswith("Expected Allow -> Got Deny:"):
# #                     allow_deny_match = re.search(r'(\d+)', line)
# #                     if allow_deny_match:
# #                         misclassified_allow_to_deny = int(allow_deny_match.group(1))
# #                         logging.debug(f"Found allow->deny: {misclassified_allow_to_deny}")
# #                 elif line.startswith("Expected Deny -> Got Allow:"):
# #                     deny_allow_match = re.search(r'(\d+)', line)
# #                     if deny_allow_match:
# #                         misclassified_deny_to_allow = int(deny_allow_match.group(1))
# #                         logging.debug(f"Found deny->allow: {misclassified_deny_to_allow}")
        
# #         if not found_analysis_section:
# #             logging.warning("Could not find 'INDIVIDUAL REQUEST ANALYSIS' section in output")
# #             logging.debug("Searching for any accuracy information...")
# #             # Fallback: search entire output for accuracy
# #             for line in output_lines:
# #                 if "Overall Accuracy:" in line or "Accuracy:" in line:
# #                     accuracy_match = re.search(r'(\d+\.?\d*)%', line)
# #                     if accuracy_match:
# #                         accuracy = float(accuracy_match.group(1))
# #                         logging.debug(f"Found fallback accuracy: {accuracy}%")
# #                         break
        
# #         # Clean up temporary file (disabled for debugging)
# #         # if os.path.exists(output_file_path):
# #         #     os.unlink(output_file_path)
        
# #         # Keep the file for debugging and log its location
# #         logging.info(f"Validator output file kept for debugging: {output_file_path}")
        
# #         # Validate that we got meaningful results
# #         if total_requests == 0:
# #             logging.warning("No requests found in validator output - check parsing logic")
# #             logging.warning(f"Output file location: {output_file_path}")
# #             logging.debug(f"Raw output preview: {output_content[:500]}...")
# #             # Also save the full output to a debug file
# #             debug_file = output_file_path.replace('.txt', '_debug.txt')
# #             with open(debug_file, 'w') as f:
# #                 f.write("=== FULL VALIDATOR OUTPUT ===\n")
# #                 f.write(output_content)
# #             logging.warning(f"Full output saved to: {debug_file}")
        
# #         logging.info(f"Validation completed - Accuracy: {accuracy}%, Total: {total_requests}, Correct: {correct_count}, Incorrect: {incorrect_count}")
# #         logging.debug(f"Misclassified - Allow→Deny: {misclassified_allow_to_deny}, Deny→Allow: {misclassified_deny_to_allow}")
        
# #         return {
# #             'accuracy': accuracy,
# #             'total_requests': total_requests,
# #             'correct': correct_count,
# #             'incorrect': incorrect_count,
# #             'misclassified_allow_to_deny': misclassified_allow_to_deny,
# #             'misclassified_deny_to_allow': misclassified_deny_to_allow,
# #             'raw_output': output_content,
# #             'output_file': output_file_path
# #         }
        
# #     except subprocess.TimeoutExpired:
# #         # Change back to original directory in case of timeout
# #         try:
# #             os.chdir(original_dir)
# #         except:
# #             pass
# #         logging.error("SMT validator timed out")
# #         raise Exception("SMT validator timed out")
# #     except Exception as e:
# #         # Change back to original directory in case of error
# #         try:
# #             os.chdir(original_dir)
# #         except:
# #             pass
# #         logging.error(f"Error running SMT validator: {e}")
# #         raise

# # def run_baseline_validation(idx: int) -> dict:
# #     """Run baseline validation on the original policy."""
# #     policy_file = os.path.join(POLICY_DIR, f"{idx}.json")
# #     req_file = os.path.join(REQUIREMENTS_DIR, f"{idx}.json")
    
# #     if not os.path.exists(policy_file) or not os.path.exists(req_file):
# #         raise FileNotFoundError(f"Missing files for index {idx}")
    
# #     logging.info(f"Running baseline validation for policy {idx}...")
    
# #     try:
# #         # Run SMT validator on original policy
# #         validation_results = run_smt_validator(policy_file, req_file)
        
# #         baseline_result = {
# #             'policy_idx': idx,
# #             'validation_type': 'baseline',
# #             'accuracy': validation_results['accuracy'],
# #             'total_requests': validation_results['total_requests'],
# #             'correct': validation_results['correct'],
# #             'incorrect': validation_results['incorrect'],
# #             'misclassified_allow_to_deny': validation_results['misclassified_allow_to_deny'],
# #             'misclassified_deny_to_allow': validation_results['misclassified_deny_to_allow'],
# #             'output_file': validation_results['output_file']
# #         }
        
# #         logging.info(f"Baseline validation for policy {idx}: {validation_results['accuracy']:.1f}% accuracy")
        
# #         return baseline_result
        
# #     except Exception as e:
# #         logging.error(f"Baseline validation failed for policy {idx}: {e}")
# #         return {
# #             'policy_idx': idx,
# #             'validation_type': 'baseline',
# #             'accuracy': 0.0,
# #             'error': str(e)
# #         }

# # def process_policy_iteratively(idx: int, baseline_accuracy: float = 0.0) -> dict:
# #     """Process a single policy with iterative repair and validation."""
# #     policy_file = os.path.join(POLICY_DIR, f"{idx}.json")
# #     req_file = os.path.join(REQUIREMENTS_DIR, f"{idx}.json")
    
# #     if not os.path.exists(policy_file) or not os.path.exists(req_file):
# #         raise FileNotFoundError(f"Missing files for index {idx}")
    
# #     # Load initial policy and requests
# #     original_policy = load_json_file(policy_file)
# #     requests = load_json_file(req_file)
    
# #     logging.info(f"Starting iterative repair for policy {idx} (baseline: {baseline_accuracy:.1f}%)...")
    
# #     # If baseline is already 100%, no need to repair
# #     if baseline_accuracy >= TARGET_ACCURACY:
# #         logging.info(f"Policy {idx} already achieves target accuracy ({baseline_accuracy:.1f}%). Skipping repair.")
# #         # Still save the original policy as the "repaired" version
# #         final_output_file = os.path.join(OUTPUT_DIR, f"repaired_{idx}_already_perfect.json")
# #         save_json_file(original_policy, final_output_file)
        
# #         return {
# #             'index': idx,
# #             'status': 'already_perfect',
# #             'baseline_accuracy': baseline_accuracy,
# #             'final_accuracy': baseline_accuracy,
# #             'iterations_used': 0,
# #             'iteration_results': [],
# #             'final_policy_file': final_output_file
# #         }
    
# #     # Track all iterations
# #     iteration_results = []
# #     current_policy = original_policy.copy()
# #     final_accuracy = baseline_accuracy
    
# #     for iteration in range(1, MAX_ITERATIONS + 1):
# #         logging.info(f"Policy {idx} - Iteration {iteration}/{MAX_ITERATIONS}")
        
# #         try:
# #             # Repair policy with Claude (same prompt every time)
# #             logging.info(f"Repairing policy with Claude (iteration {iteration})...")
# #             repaired_policy = repair_policy_with_claude(current_policy, requests)
            
# #             # Save temporary repaired policy for validation
# #             temp_policy_file = os.path.join(TEMP_DIR, f"policy_{idx}_iter_{iteration}.json")
# #             os.makedirs(TEMP_DIR, exist_ok=True)
# #             save_json_file(repaired_policy, temp_policy_file)
            
# #             # Validate with SMT solver
# #             logging.info(f"Validating with SMT solver (iteration {iteration})...")
# #             validation_results = run_smt_validator(temp_policy_file, req_file)
            
# #             accuracy = validation_results['accuracy']
# #             logging.info(f"Iteration {iteration} accuracy: {accuracy:.1f}%")
            
# #             # Record this iteration
# #             iteration_record = {
# #                 'policy_idx': idx,
# #                 'iteration': iteration,
# #                 'validation_type': 'repair',
# #                 'accuracy': accuracy,
# #                 'total_requests': validation_results['total_requests'],
# #                 'correct': validation_results['correct'],
# #                 'incorrect': validation_results['incorrect'],
# #                 'misclassified_allow_to_deny': validation_results['misclassified_allow_to_deny'],
# #                 'misclassified_deny_to_allow': validation_results['misclassified_deny_to_allow'],
# #                 'policy_file': temp_policy_file
# #             }
# #             iteration_results.append(iteration_record)
            
# #             final_accuracy = accuracy
            
# #             # Check if we achieved target accuracy
# #             if accuracy >= TARGET_ACCURACY:
# #                 logging.info(f"Target accuracy achieved for policy {idx} in {iteration} iterations!")
                
# #                 # Save final repaired policy
# #                 final_output_file = os.path.join(OUTPUT_DIR, f"repaired_{idx}_final.json")
# #                 save_json_file(repaired_policy, final_output_file)
                
# #                 return {
# #                     'index': idx,
# #                     'status': 'success',
# #                     'baseline_accuracy': baseline_accuracy,
# #                     'final_accuracy': accuracy,
# #                     'iterations_used': iteration,
# #                     'iteration_results': iteration_results,
# #                     'final_policy_file': final_output_file
# #                 }
            
# #             # For next iteration, use the ORIGINAL policy again (not the repaired one)
# #             # This ensures we start fresh each time with the same prompt
# #             current_policy = original_policy.copy()
            
# #         except Exception as e:
# #             logging.error(f"Error in iteration {iteration} for policy {idx}: {e}")
# #             iteration_record = {
# #                 'policy_idx': idx,
# #                 'iteration': iteration,
# #                 'validation_type': 'repair',
# #                 'accuracy': 0.0,
# #                 'error': str(e)
# #             }
# #             iteration_results.append(iteration_record)
    
# #     # If we reach here, we didn't achieve target accuracy
# #     logging.warning(f"Failed to achieve target accuracy for policy {idx} after {MAX_ITERATIONS} iterations. Final accuracy: {final_accuracy:.1f}%")
    
# #     # Save best attempt
# #     if iteration_results:
# #         best_iteration = max(iteration_results, key=lambda x: x.get('accuracy', 0))
# #         if 'policy_file' in best_iteration and os.path.exists(best_iteration['policy_file']):
# #             final_output_file = os.path.join(OUTPUT_DIR, f"repaired_{idx}_best.json")
# #             shutil.copy2(best_iteration['policy_file'], final_output_file)
# #         else:
# #             # Save original policy as fallback
# #             final_output_file = os.path.join(OUTPUT_DIR, f"repaired_{idx}_original.json")
# #             save_json_file(original_policy, final_output_file)
# #     else:
# #         final_output_file = os.path.join(OUTPUT_DIR, f"repaired_{idx}_original.json")
# #         save_json_file(original_policy, final_output_file)
    
# #     return {
# #         'index': idx,
# #         'status': 'failed',
# #         'baseline_accuracy': baseline_accuracy,
# #         'final_accuracy': final_accuracy,
# #         'iterations_used': MAX_ITERATIONS,
# #         'iteration_results': iteration_results,
# #         'final_policy_file': final_output_file
# #     }

# # def main():
# #     log_file = setup_logging()
# #     logging.info("Starting iterative policy repair system with baseline validation")
    
# #     # Ensure required directories exist
# #     for directory in [POLICY_DIR, REQUIREMENTS_DIR]:
# #         if not os.path.isdir(directory):
# #             logging.error(f"Directory '{directory}' not found.")
# #             print(f"Directory '{directory}' not found. Exiting.")
# #             sys.exit(1)
    
# #     # Check if SMT validator script exists
# #     if not os.path.exists(SMT_VALIDATOR_SCRIPT):
# #         logging.error(f"SMT validator script '{SMT_VALIDATOR_SCRIPT}' not found.")
# #         print(f"SMT validator script '{SMT_VALIDATOR_SCRIPT}' not found. Exiting.")
# #         sys.exit(1)
    
# #     # Create output directories
# #     for directory in [OUTPUT_DIR, TEMP_DIR]:
# #         os.makedirs(directory, exist_ok=True)
    
# #     # Initialize progress tracker
# #     tracker = IterativeProgressTracker()
# #     total = 10
    
# #     # Step 1: Run baseline validation for all policies
# #     print("=" * 60)
# #     print("STEP 1: BASELINE VALIDATION")
# #     print("=" * 60)
    
# #     baseline_results = []
# #     baseline_to_process = [i for i in range(total) if not tracker.is_baseline_done(i)]
    
# #     if baseline_to_process:
# #         logging.info(f"Running baseline validation for policies: {baseline_to_process}")
        
# #         for idx in tqdm(baseline_to_process, desc="Baseline validation"):
# #             try:
# #                 baseline_result = run_baseline_validation(idx)
# #                 baseline_results.append(baseline_result)
# #                 tracker.mark_baseline_completed(idx)
                
# #                 # Log baseline result
# #                 if 'error' not in baseline_result:
# #                     logging.info(f"Policy {idx} baseline: {baseline_result['accuracy']:.1f}% accuracy")
# #                 else:
# #                     logging.error(f"Policy {idx} baseline failed: {baseline_result['error']}")
                    
# #             except Exception as e:
# #                 logging.error(f"Baseline validation failed for policy {idx}: {e}")
# #                 baseline_results.append({
# #                     'policy_idx': idx,
# #                     'validation_type': 'baseline',
# #                     'accuracy': 0.0,
# #                     'error': str(e)
# #                 })
# #                 tracker.mark_baseline_completed(idx)  # Mark as done even if failed
# #     else:
# #         logging.info("All baseline validations already completed. Loading existing results...")
# #         # Load existing baseline results if available
# #         existing_baseline_file = os.path.join(OUTPUT_DIR, "baseline_results.csv")
# #         if os.path.exists(existing_baseline_file):
# #             baseline_df = pd.read_csv(existing_baseline_file)
# #             baseline_results = baseline_df.to_dict('records')
# #         else:
# #             # If no existing file, create empty baseline results with 0% accuracy
# #             baseline_results = [{'policy_idx': i, 'validation_type': 'baseline', 'accuracy': 0.0} for i in range(total)]
    
# #     # Save baseline results
# #     if baseline_results:
# #         timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
# #         baseline_csv = os.path.join(OUTPUT_DIR, f"baseline_results_{timestamp}.csv")
# #         baseline_df = pd.DataFrame(baseline_results)
# #         baseline_df.to_csv(baseline_csv, index=False)
# #         logging.info(f"Baseline results saved to {baseline_csv}")
        
# #         # Also save as latest baseline
# #         latest_baseline_csv = os.path.join(OUTPUT_DIR, "baseline_results.csv")
# #         baseline_df.to_csv(latest_baseline_csv, index=False)
    
# #     # Print baseline summary
# #     print(f"\n{'='*60}")
# #     print("BASELINE VALIDATION SUMMARY")
# #     print(f"{'='*60}")
# #     successful_baselines = [r for r in baseline_results if r.get('accuracy', 0) > 0 and 'error' not in r]
# #     failed_baselines = [r for r in baseline_results if 'error' in r]
# #     perfect_baselines = [r for r in baseline_results if r.get('accuracy', 0) >= TARGET_ACCURACY]
    
# #     if successful_baselines:
# #         avg_baseline_accuracy = sum(r['accuracy'] for r in successful_baselines) / len(successful_baselines)
# #         print(f"Successfully validated policies: {len(successful_baselines)}")
# #         print(f"Failed baseline validations: {len(failed_baselines)}")
# #         print(f"Average baseline accuracy: {avg_baseline_accuracy:.1f}%")
# #         print(f"Policies already at target accuracy: {len(perfect_baselines)}")
        
# #         if perfect_baselines:
# #             perfect_indices = [r['policy_idx'] for r in perfect_baselines]
# #             print(f"Perfect baseline policies: {perfect_indices}")
    
# #     print(f"{'='*60}")
    
# #     # Step 2: Iterative repair for policies that need improvement
# #     print("\nSTEP 2: ITERATIVE REPAIR")
# #     print("=" * 60)
    
# #     # Create baseline accuracy lookup
# #     baseline_accuracy_map = {r['policy_idx']: r.get('accuracy', 0.0) for r in baseline_results}
    
# #     to_process = [i for i in range(total) if not tracker.is_done(i)]
# #     logging.info(f"Policies to process for repair: {to_process}")
    
# #     all_results = []
# #     all_iteration_data = baseline_results.copy()  # Start with baseline data
    
# #     # Process each policy
# #     for idx in tqdm(to_process, desc="Processing policies iteratively"):
# #         try:
# #             baseline_acc = baseline_accuracy_map.get(idx, 0.0)
# #             result = process_policy_iteratively(idx, baseline_acc)
            
# #             # Track completion/failure
# #             if result['status'] in ['success', 'already_perfect']:
# #                 tracker.mark_completed(idx, result['final_accuracy'], result['iterations_used'])
# #             else:
# #                 tracker.mark_failed(idx, result['final_accuracy'], result['iterations_used'])
            
# #             all_results.append(result)
            
# #             # Collect iteration data for detailed analysis
# #             for iter_data in result['iteration_results']:
# #                 all_iteration_data.append(iter_data)
            
# #         except Exception as e:
# #             logging.error(f"Policy {idx} failed completely: {e}")
# #             tracker.mark_failed(idx, 0.0, 0)
# #             baseline_acc = baseline_accuracy_map.get(idx, 0.0)
# #             all_results.append({
# #                 'index': idx,
# #                 'status': 'error',
# #                 'baseline_accuracy': baseline_acc,
# #                 'final_accuracy': 0.0,
# #                 'iterations_used': 0,
# #                 'error': str(e)
# #             })
    
# #     # Save comprehensive results
# #     timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
# #     # Summary results
# #     if all_results:
# #         df_summary = pd.DataFrame(all_results)
# #         summary_csv = os.path.join(OUTPUT_DIR, f"iterative_repair_summary_{timestamp}.csv")
# #         df_summary.to_csv(summary_csv, index=False)
# #         logging.info(f"Summary results saved to {summary_csv}")
    
# #     # Detailed iteration results (includes baseline + all repair iterations)
# #     if all_iteration_data:
# #         df_iterations = pd.DataFrame(all_iteration_data)
# #         iterations_csv = os.path.join(OUTPUT_DIR, f"iterative_repair_details_{timestamp}.csv")
# #         df_iterations.to_csv(iterations_csv, index=False)
# #         logging.info(f"Detailed iteration results saved to {iterations_csv}")
    
# #     # Print final summary
# #     successful = len([r for r in all_results if r.get('status') in ['success', 'already_perfect']])
# #     failed = len([r for r in all_results if r.get('status') in ['failed', 'error']])
# #     already_perfect = len([r for r in all_results if r.get('status') == 'already_perfect'])
    
# #     if all_results:
# #         avg_baseline = sum(r.get('baseline_accuracy', 0) for r in all_results) / len(all_results)
# #         avg_final = sum(r.get('final_accuracy', 0) for r in all_results) / len(all_results)
# #         total_iterations = sum(r.get('iterations_used', 0) for r in all_results)
        
# #         # Calculate improvement
# #         baseline_perfect = len([r for r in all_results if r.get('baseline_accuracy', 0) >= TARGET_ACCURACY])
# #         final_perfect = len([r for r in all_results if r.get('final_accuracy', 0) >= TARGET_ACCURACY])
# #         improvement = final_perfect - baseline_perfect
# #     else:
# #         avg_baseline = avg_final = total_iterations = improvement = 0
# #         baseline_perfect = final_perfect = 0
    
# #     # Log the final summary
# #     logging.info(f"\n{'='*60}")
# #     logging.info("FINAL SUMMARY - BASELINE vs REPAIR")
# #     logging.info(f"{'='*60}")
# #     logging.info(f"Total policies processed: {len(all_results)}")
# #     logging.info(f"")
# #     logging.info(f"BASELINE PERFORMANCE:")
# #     logging.info(f"  Average baseline accuracy: {avg_baseline:.1f}%")
# #     logging.info(f"  Policies at target (baseline): {baseline_perfect}")
# #     logging.info(f"")
# #     logging.info(f"FINAL PERFORMANCE:")
# #     logging.info(f"  Successfully repaired to 100%: {successful}")
# #     logging.info(f"  Already perfect (no repair needed): {already_perfect}")
# #     logging.info(f"  Failed to reach 100%: {failed}")
# #     logging.info(f"  Average final accuracy: {avg_final:.1f}%")
# #     logging.info(f"  Policies at target (final): {final_perfect}")
# #     logging.info(f"")
# #     logging.info(f"IMPROVEMENT:")
# #     logging.info(f"  Net improvement: +{improvement} policies reaching 100%")
# #     logging.info(f"  Accuracy improvement: {avg_final - avg_baseline:.1f} percentage points")
# #     logging.info(f"  Total iterations used: {total_iterations}")
# #     logging.info(f"  Average iterations per policy: {total_iterations/len(all_results):.1f}" if all_results else "0")
# #     logging.info(f"{'='*60}")
    
# #     # Print final summary to console
# #     print(f"\n{'='*60}")
# #     print("FINAL SUMMARY - BASELINE vs REPAIR")
# #     print(f"{'='*60}")
# #     print(f"Total policies processed: {len(all_results)}")
# #     print(f"")
# #     print(f"BASELINE PERFORMANCE:")
# #     print(f"  Average baseline accuracy: {avg_baseline:.1f}%")
# #     print(f"  Policies at target (baseline): {baseline_perfect}")
# #     print(f"")
# #     print(f"FINAL PERFORMANCE:")
# #     print(f"  Successfully repaired to 100%: {successful}")
# #     print(f"  Already perfect (no repair needed): {already_perfect}")
# #     print(f"  Failed to reach 100%: {failed}")
# #     print(f"  Average final accuracy: {avg_final:.1f}%")
# #     print(f"  Policies at target (final): {final_perfect}")
# #     print(f"")
# #     print(f"IMPROVEMENT:")
# #     print(f"  Net improvement: +{improvement} policies reaching 100%")
# #     print(f"  Accuracy improvement: {avg_final - avg_baseline:.1f} percentage points")
# #     print(f"  Total iterations used: {total_iterations}")
# #     print(f"  Average iterations per policy: {total_iterations/len(all_results):.1f}" if all_results else "0")
    
# #     # Show detailed policy-by-policy results
# #     print(f"\nDETAILED RESULTS:")
# #     for result in all_results:
# #         idx = result['index']
# #         baseline = result.get('baseline_accuracy', 0)
# #         final = result.get('final_accuracy', 0)
# #         status = result.get('status', 'unknown')
# #         iterations = result.get('iterations_used', 0)
        
# #         if status == 'already_perfect':
# #             print(f"  Policy {idx}: {baseline:.1f}% → {final:.1f}% (already perfect)")
# #         elif status == 'success':
# #             print(f"  Policy {idx}: {baseline:.1f}% → {final:.1f}% (SUCCESS in {iterations} iterations)")
# #         elif status == 'failed':
# #             print(f"  Policy {idx}: {baseline:.1f}% → {final:.1f}% (failed after {iterations} iterations)")
# #         else:
# #             print(f"  Policy {idx}: {baseline:.1f}% → {final:.1f}% (ERROR: {result.get('error', 'unknown')})")
    
# #     print(f"{'='*60}")
    
# #     # Cleanup temporary files
# #     if os.path.exists(TEMP_DIR):
# #         shutil.rmtree(TEMP_DIR)
# #         logging.info("Cleaned up temporary files")

# # if __name__ == "__main__":
# #     main()
# #!/usr/bin/env python3
# """
# iterative_policy_repair.py

# This script first performs baseline validation on original AWS IAM policies,
# then iteratively repairs them using Claude and validates with SMT solver.
# It attempts up to 5 iterations per policy until 100% accuracy is achieved.

# Features:
# - Baseline validation of original policies
# - Iterative repair with accuracy feedback
# - SMT solver validation integration
# - Comprehensive tracking of all iterations
# - Results saved to CSV for analysis
# - Progress tracking with resume capability
# - Complete field validation (Action, Effect, Resource, Condition, Principal)

# Usage:
#     python3 iterative_policy_repair.py
# """

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


# POLICY_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-1/original_policy"
# REQUIREMENTS_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-1/requests/request-80"
# OUTPUT_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-1/results/result-80"
# LOG_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-1/logs/log-80"
# TEMP_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-1/temp_validation/val-80"
# QUACKY_SRC_DIR = "/home/bhall2/Documents/fixmypolicy/quacky/src"
# SMT_VALIDATOR_SCRIPT = "/home/bhall2/Documents/fixmypolicy/quacky/src/validate_requests.py"


# # Global configurations
# MAX_ITERATIONS = 5
# MAX_ATTEMPT = 3
# DELAY = 5
# TARGET_ACCURACY = 100.0

# # Configure logging
# def setup_logging(log_dir: str = LOG_DIR):
#     os.makedirs(log_dir, exist_ok=True)
#     log_file = os.path.join(log_dir, f'iterative_repair_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
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

# # Enhanced policy repair prompt with complete field requirements
# def get_policy_repair_prompt(problematic_policy, requirements):
#     prompt = f"""
# You are an AWS IAM security expert. Your task is to repair a problematic AWS IAM policy based on specific security requirements.

# PROBLEMATIC POLICY:
# {problematic_policy}

# SECURITY REQUIREMENTS:
# {requirements}

# Your task:
# 1. Analyze the problematic policy against the security requirements
# 2. Identify what's wrong or missing in the current policy
# 3. Generate a repaired policy that meets ALL the security requirements
# 4. Ensure the policy follows AWS IAM best practices (principle of least privilege, proper resource specification, etc.)

# CRITICAL POLICY STRUCTURE REQUIREMENTS:

# The policy MUST include:
# - "Version": "2012-10-17"
# - "Statement": [array of statement objects]

# Each statement object MUST have ALL of the following fields:
# - "Sid": A unique identifier string (e.g., "AllowS3Access", "DenyEC2Access")
# - "Effect": Either "Allow" or "Deny"
# - "Action": AWS action(s) as string or array (e.g., "s3:GetObject", ["s3:GetObject", "s3:PutObject"])
# - "Resource": AWS resource ARN(s) as string or array (e.g., "arn:aws:s3:::my-bucket/*")
# - "Principal": Principal specification as object (e.g., {{"AWS": "arn:aws:iam::123456789012:user/username"}}, {{"Service": "ec2.amazonaws.com"}}, or {{"AWS": "*"}})
# - "Condition": Condition block as object (e.g., {{"StringEquals": {{"aws:RequestedRegion": "us-east-1"}}}}, or {{}} for no conditions)

# MANDATORY FIELD EXAMPLES:
# {{
#   "Version": "2012-10-17",
#   "Statement": [
#     {{
#       "Sid": "AllowS3ReadAccess",
#       "Effect": "Allow",
#       "Action": "s3:GetObject",
#       "Resource": "arn:aws:s3:::my-bucket/*",
#       "Principal": {{"AWS": "arn:aws:iam::123456789012:user/john"}},
#       "Condition": {{"StringEquals": {{"aws:RequestedRegion": "us-east-1"}}}}
#     }},
#     {{
#       "Sid": "DenyDangerousActions",
#       "Effect": "Deny",
#       "Action": ["iam:DeleteUser", "iam:DeleteRole"],
#       "Resource": "*",
#       "Principal": {{"AWS": "*"}},
#       "Condition": {{}}
#     }}
#   ]
# }}

# IMPORTANT VALIDATION RULES:
# 1. NO missing fields - every statement MUST have Sid, Effect, Action, Resource, Principal, AND Condition
# 2. Principal field is REQUIRED even for resource-based policies
# 3. Condition field is REQUIRED (use empty object {{}} if no conditions needed)
# 4. Sid must be a descriptive string, not empty
# 5. Effect must be exactly "Allow" or "Deny"
# 6. Action and Resource can be strings or arrays
# 7. Principal must be properly formatted object with appropriate keys (AWS, Service, Federated, etc.)

# CRITICAL: Return ONLY valid JSON with ALL required fields. No explanations, no markdown, no extra text. Start with {{ and end with }}. The JSON must be properly formatted with correct commas, brackets, and quotes.

# Repaired Policy:"""
    
#     return prompt

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
#     def __init__(self, progress_file: str = os.path.join(OUTPUT_DIR, "iterative_progress.json")):
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
#             "policy_iterations": {},  # Track iterations per policy
#             "baseline_completed": []  # Track baseline validation completion
#         }
    
#     def save_progress(self):
#         os.makedirs(os.path.dirname(self.progress_file), exist_ok=True)
#         with open(self.progress_file, 'w') as f:
#             json.dump(self.progress, f, indent=2)
    
#     def mark_baseline_completed(self, idx):
#         if idx not in self.progress["baseline_completed"]:
#             self.progress["baseline_completed"].append(idx)
#         self.save_progress()
    
#     def is_baseline_done(self, idx):
#         return idx in self.progress.get("baseline_completed", [])
    
#     def mark_completed(self, idx, final_accuracy, iterations_used):
#         self.progress["last_processed"] = idx
#         if idx not in self.progress["completed"]:
#             self.progress["completed"].append(idx)
#         if idx in self.progress["failed"]:
#             self.progress["failed"].remove(idx)
        
#         self.progress["policy_iterations"][str(idx)] = {
#             "status": "completed",
#             "final_accuracy": final_accuracy,
#             "iterations_used": iterations_used
#         }
#         self.save_progress()
    
#     def mark_failed(self, idx, final_accuracy, iterations_used):
#         if idx not in self.progress["failed"]:
#             self.progress["failed"].append(idx)
        
#         self.progress["policy_iterations"][str(idx)] = {
#             "status": "failed",
#             "final_accuracy": final_accuracy,
#             "iterations_used": iterations_used
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
#             if r.get('Principal'):
#                 lines.append(f"      Principal: {r.get('Principal')}")
#             if r.get('Condition'):
#                 lines.append(f"      Condition: {r.get('Condition')}")
    
#     if deny:
#         lines.append("MUST DENY:")
#         for i, r in enumerate(deny, 1):
#             lines.append(f"  {i}. ID: {r.get('id')} Actions: {r.get('Action')} Resources: {r.get('Resource')}")
#             if r.get('Principal'):
#                 lines.append(f"      Principal: {r.get('Principal')}")
#             if r.get('Condition'):
#                 lines.append(f"      Condition: {r.get('Condition')}")
    
#     lines.append("ADDITIONAL REQUIREMENTS:")
#     lines.extend([
#         "  - Version must be '2012-10-17'",
#         "  - ALL statements MUST have Sid, Effect, Action, Resource, Principal, AND Condition fields",
#         "  - Principal field is REQUIRED (use appropriate AWS identity or service)",
#         "  - Condition field is REQUIRED (use {} if no conditions needed)",
#         "  - Principle of least privilege",
#         "  - Specific ARNs where provided",
#         "  - Ensure actions allowed/denied as specified",
#     ])
    
#     return "\n".join(lines)

# def validate_policy_structure(policy: dict) -> list:
#     """Validate that the policy has all required fields and return any validation errors."""
#     errors = []
    
#     # Check top-level structure
#     if not isinstance(policy, dict):
#         errors.append("Policy must be a JSON object")
#         return errors
    
#     if "Version" not in policy:
#         errors.append("Missing 'Version' field in policy")
#     elif policy["Version"] != "2012-10-17":
#         errors.append(f"Version should be '2012-10-17', got '{policy['Version']}'")
    
#     if "Statement" not in policy:
#         errors.append("Missing 'Statement' field in policy")
#         return errors
    
#     if not isinstance(policy["Statement"], list):
#         errors.append("'Statement' field must be an array")
#         return errors
    
#     # Check each statement
#     required_fields = ["Sid", "Effect", "Action", "Resource", "Principal", "Condition"]
    
#     for i, statement in enumerate(policy["Statement"]):
#         if not isinstance(statement, dict):
#             errors.append(f"Statement {i} must be an object")
#             continue
        
#         # Check for all required fields
#         for field in required_fields:
#             if field not in statement:
#                 errors.append(f"Statement {i} missing required field '{field}'")
        
#         # Validate specific field values
#         if "Effect" in statement and statement["Effect"] not in ["Allow", "Deny"]:
#             errors.append(f"Statement {i} Effect must be 'Allow' or 'Deny', got '{statement['Effect']}'")
        
#         if "Sid" in statement and not isinstance(statement["Sid"], str):
#             errors.append(f"Statement {i} Sid must be a string")
        
#         if "Principal" in statement and not isinstance(statement["Principal"], dict):
#             errors.append(f"Statement {i} Principal must be an object")
        
#         if "Condition" in statement and not isinstance(statement["Condition"], dict):
#             errors.append(f"Statement {i} Condition must be an object")
    
#     return errors

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
        
#         # Enhanced validation with complete field checking
#         validation_errors = validate_policy_structure(parsed_json)
        
#         if validation_errors:
#             error_msg = "Policy validation failed:\n" + "\n".join(f"  - {error}" for error in validation_errors)
#             raise ValueError(error_msg)
        
#         logging.info("Policy structure validation passed - all required fields present")
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
            
#             # Validate the fixed JSON
#             validation_errors = validate_policy_structure(parsed_json)
#             if validation_errors:
#                 error_msg = "Fixed JSON validation failed:\n" + "\n".join(f"  - {error}" for error in validation_errors)
#                 raise ValueError(error_msg)
            
#             return parsed_json
#         except json.JSONDecodeError as e2:
#             raise ValueError(f"Failed to parse JSON even after fixes. Original error: {e}. Fixed JSON: {fixed_json}")

# @retry()
# def repair_policy_with_claude(policy: dict, requests: dict) -> dict:
#     policy_json = json.dumps(policy, indent=2)
#     req_text = format_requirements(requests)
#     prompt = get_policy_repair_prompt(policy_json, req_text)
    
#     resp = claude_client.messages.create(
#         model=claude_model_name,
#         max_tokens=4000,
#         temperature=0,
#         system="You are an AWS IAM security expert who repairs policies to meet specific security requirements. Generate only valid JSON policies with ALL required fields (Sid, Effect, Action, Resource, Principal, Condition) for every statement. NO missing fields allowed.",
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
        
#         return {
#             'accuracy': accuracy,
#             'total_requests': total_requests,
#             'correct': correct_count,
#             'incorrect': incorrect_count,
#             'misclassified_allow_to_deny': misclassified_allow_to_deny,
#             'misclassified_deny_to_allow': misclassified_deny_to_allow,
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

# def run_baseline_validation(idx: int) -> dict:
#     """Run baseline validation on the original policy."""
#     policy_file = os.path.join(POLICY_DIR, f"{idx}.json")
#     req_file = os.path.join(REQUIREMENTS_DIR, f"{idx}.json")
    
#     if not os.path.exists(policy_file) or not os.path.exists(req_file):
#         raise FileNotFoundError(f"Missing files for index {idx}")
    
#     logging.info(f"Running baseline validation for policy {idx}...")
    
#     try:
#         # Run SMT validator on original policy
#         validation_results = run_smt_validator(policy_file, req_file)
        
#         baseline_result = {
#             'policy_idx': idx,
#             'validation_type': 'baseline',
#             'accuracy': validation_results['accuracy'],
#             'total_requests': validation_results['total_requests'],
#             'correct': validation_results['correct'],
#             'incorrect': validation_results['incorrect'],
#             'misclassified_allow_to_deny': validation_results['misclassified_allow_to_deny'],
#             'misclassified_deny_to_allow': validation_results['misclassified_deny_to_allow'],
#             'output_file': validation_results['output_file']
#         }
        
#         logging.info(f"Baseline validation for policy {idx}: {validation_results['accuracy']:.1f}% accuracy")
        
#         return baseline_result
        
#     except Exception as e:
#         logging.error(f"Baseline validation failed for policy {idx}: {e}")
#         return {
#             'policy_idx': idx,
#             'validation_type': 'baseline',
#             'accuracy': 0.0,
#             'error': str(e)
#         }

# def process_policy_iteratively(idx: int, baseline_accuracy: float = 0.0) -> dict:
#     """Process a single policy with iterative repair and validation."""
#     policy_file = os.path.join(POLICY_DIR, f"{idx}.json")
#     req_file = os.path.join(REQUIREMENTS_DIR, f"{idx}.json")
    
#     if not os.path.exists(policy_file) or not os.path.exists(req_file):
#         raise FileNotFoundError(f"Missing files for index {idx}")
    
#     # Load initial policy and requests
#     original_policy = load_json_file(policy_file)
#     requests = load_json_file(req_file)
    
#     logging.info(f"Starting iterative repair for policy {idx} (baseline: {baseline_accuracy:.1f}%)...")
    
#     # If baseline is already 100%, no need to repair
#     if baseline_accuracy >= TARGET_ACCURACY:
#         logging.info(f"Policy {idx} already achieves target accuracy ({baseline_accuracy:.1f}%). Skipping repair.")
#         # Still save the original policy as the "repaired" version
#         final_output_file = os.path.join(OUTPUT_DIR, f"repaired_{idx}_already_perfect.json")
#         save_json_file(original_policy, final_output_file)
        
#         return {
#             'index': idx,
#             'status': 'already_perfect',
#             'baseline_accuracy': baseline_accuracy,
#             'final_accuracy': baseline_accuracy,
#             'iterations_used': 0,
#             'iteration_results': [],
#             'final_policy_file': final_output_file
#         }
    
#     # Track all iterations
#     iteration_results = []
#     current_policy = original_policy.copy()
#     final_accuracy = baseline_accuracy
    
#     for iteration in range(1, MAX_ITERATIONS + 1):
#         logging.info(f"Policy {idx} - Iteration {iteration}/{MAX_ITERATIONS}")
        
#         try:
#             # Repair policy with Claude (same prompt every time)
#             logging.info(f"Repairing policy with Claude (iteration {iteration})...")
#             logging.info("Enforcing complete field requirements (Sid, Effect, Action, Resource, Principal, Condition)")
#             repaired_policy = repair_policy_with_claude(current_policy, requests)
            
#             # Validate policy structure before saving
#             validation_errors = validate_policy_structure(repaired_policy)
#             if validation_errors:
#                 logging.warning(f"Iteration {iteration} - Policy structure validation failed:")
#                 for error in validation_errors:
#                     logging.warning(f"  - {error}")
#                 raise ValueError(f"Generated policy missing required fields: {validation_errors}")
#             else:
#                 logging.info(f"Iteration {iteration} - Policy structure validation passed")
            
#             # Save temporary repaired policy for validation
#             temp_policy_file = os.path.join(TEMP_DIR, f"policy_{idx}_iter_{iteration}.json")
#             os.makedirs(TEMP_DIR, exist_ok=True)
#             save_json_file(repaired_policy, temp_policy_file)
            
#             # Validate with SMT solver
#             logging.info(f"Validating with SMT solver (iteration {iteration})...")
#             validation_results = run_smt_validator(temp_policy_file, req_file)
            
#             accuracy = validation_results['accuracy']
#             logging.info(f"Iteration {iteration} accuracy: {accuracy:.1f}%")
            
#             # Record this iteration
#             iteration_record = {
#                 'policy_idx': idx,
#                 'iteration': iteration,
#                 'validation_type': 'repair',
#                 'accuracy': accuracy,
#                 'total_requests': validation_results['total_requests'],
#                 'correct': validation_results['correct'],
#                 'incorrect': validation_results['incorrect'],
#                 'misclassified_allow_to_deny': validation_results['misclassified_allow_to_deny'],
#                 'misclassified_deny_to_allow': validation_results['misclassified_deny_to_allow'],
#                 'policy_file': temp_policy_file,
#                 'structure_validation_passed': True
#             }
#             iteration_results.append(iteration_record)
            
#             final_accuracy = accuracy
            
#             # Check if we achieved target accuracy
#             if accuracy >= TARGET_ACCURACY:
#                 logging.info(f"Target accuracy achieved for policy {idx} in {iteration} iterations!")
                
#                 # Save final repaired policy
#                 final_output_file = os.path.join(OUTPUT_DIR, f"repaired_{idx}_final.json")
#                 save_json_file(repaired_policy, final_output_file)
                
#                 return {
#                     'index': idx,
#                     'status': 'success',
#                     'baseline_accuracy': baseline_accuracy,
#                     'final_accuracy': accuracy,
#                     'iterations_used': iteration,
#                     'iteration_results': iteration_results,
#                     'final_policy_file': final_output_file
#                 }
            
#             # For next iteration, use the ORIGINAL policy again (not the repaired one)
#             # This ensures we start fresh each time with the same prompt
#             current_policy = original_policy.copy()
            
#         except Exception as e:
#             logging.error(f"Error in iteration {iteration} for policy {idx}: {e}")
#             iteration_record = {
#                 'policy_idx': idx,
#                 'iteration': iteration,
#                 'validation_type': 'repair',
#                 'accuracy': 0.0,
#                 'structure_validation_passed': False,
#                 'error': str(e)
#             }
#             iteration_results.append(iteration_record)
    
#     # If we reach here, we didn't achieve target accuracy
#     logging.warning(f"Failed to achieve target accuracy for policy {idx} after {MAX_ITERATIONS} iterations. Final accuracy: {final_accuracy:.1f}%")
    
#     # Save best attempt
#     if iteration_results:
#         best_iteration = max(iteration_results, key=lambda x: x.get('accuracy', 0))
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
#         'iterations_used': MAX_ITERATIONS,
#         'iteration_results': iteration_results,
#         'final_policy_file': final_output_file
#     }

# def main():
#     log_file = setup_logging()
#     logging.info("Starting iterative policy repair system with baseline validation and complete field requirements")
    
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
#     for directory in [OUTPUT_DIR, TEMP_DIR]:
#         os.makedirs(directory, exist_ok=True)
    
#     # Initialize progress tracker
#     tracker = IterativeProgressTracker()
#     total = 10
    
#     # Step 1: Run baseline validation for all policies
#     print("=" * 60)
#     print("STEP 1: BASELINE VALIDATION")
#     print("=" * 60)
    
#     baseline_results = []
#     baseline_to_process = [i for i in range(total) if not tracker.is_baseline_done(i)]
    
#     if baseline_to_process:
#         logging.info(f"Running baseline validation for policies: {baseline_to_process}")
        
#         for idx in tqdm(baseline_to_process, desc="Baseline validation"):
#             try:
#                 baseline_result = run_baseline_validation(idx)
#                 baseline_results.append(baseline_result)
#                 tracker.mark_baseline_completed(idx)
                
#                 # Log baseline result
#                 if 'error' not in baseline_result:
#                     logging.info(f"Policy {idx} baseline: {baseline_result['accuracy']:.1f}% accuracy")
#                 else:
#                     logging.error(f"Policy {idx} baseline failed: {baseline_result['error']}")
                    
#             except Exception as e:
#                 logging.error(f"Baseline validation failed for policy {idx}: {e}")
#                 baseline_results.append({
#                     'policy_idx': idx,
#                     'validation_type': 'baseline',
#                     'accuracy': 0.0,
#                     'error': str(e)
#                 })
#                 tracker.mark_baseline_completed(idx)  # Mark as done even if failed
#     else:
#         logging.info("All baseline validations already completed. Loading existing results...")
#         # Load existing baseline results if available
#         existing_baseline_file = os.path.join(OUTPUT_DIR, "baseline_results.csv")
#         if os.path.exists(existing_baseline_file):
#             baseline_df = pd.read_csv(existing_baseline_file)
#             baseline_results = baseline_df.to_dict('records')
#         else:
#             # If no existing file, create empty baseline results with 0% accuracy
#             baseline_results = [{'policy_idx': i, 'validation_type': 'baseline', 'accuracy': 0.0} for i in range(total)]
    
#     # Save baseline results
#     if baseline_results:
#         timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
#         baseline_csv = os.path.join(OUTPUT_DIR, f"baseline_results_{timestamp}.csv")
#         baseline_df = pd.DataFrame(baseline_results)
#         baseline_df.to_csv(baseline_csv, index=False)
#         logging.info(f"Baseline results saved to {baseline_csv}")
        
#         # Also save as latest baseline
#         latest_baseline_csv = os.path.join(OUTPUT_DIR, "baseline_results.csv")
#         baseline_df.to_csv(latest_baseline_csv, index=False)
    
#     # Print baseline summary
#     print(f"\n{'='*60}")
#     print("BASELINE VALIDATION SUMMARY")
#     print(f"{'='*60}")
#     successful_baselines = [r for r in baseline_results if r.get('accuracy', 0) > 0 and 'error' not in r]
#     failed_baselines = [r for r in baseline_results if 'error' in r]
#     perfect_baselines = [r for r in baseline_results if r.get('accuracy', 0) >= TARGET_ACCURACY]
    
#     if successful_baselines:
#         avg_baseline_accuracy = sum(r['accuracy'] for r in successful_baselines) / len(successful_baselines)
#         print(f"Successfully validated policies: {len(successful_baselines)}")
#         print(f"Failed baseline validations: {len(failed_baselines)}")
#         print(f"Average baseline accuracy: {avg_baseline_accuracy:.1f}%")
#         print(f"Policies already at target accuracy: {len(perfect_baselines)}")
        
#         if perfect_baselines:
#             perfect_indices = [r['policy_idx'] for r in perfect_baselines]
#             print(f"Perfect baseline policies: {perfect_indices}")
    
#     print(f"{'='*60}")
    
#     # Step 2: Iterative repair for policies that need improvement
#     print("\nSTEP 2: ITERATIVE REPAIR WITH COMPLETE FIELD VALIDATION")
#     print("=" * 60)
#     print("Enforcing ALL required fields: Sid, Effect, Action, Resource, Principal, Condition")
#     print("=" * 60)
    
#     # Create baseline accuracy lookup
#     baseline_accuracy_map = {r['policy_idx']: r.get('accuracy', 0.0) for r in baseline_results}
    
#     to_process = [i for i in range(total) if not tracker.is_done(i)]
#     logging.info(f"Policies to process for repair: {to_process}")
    
#     all_results = []
#     all_iteration_data = baseline_results.copy()  # Start with baseline data
    
#     # Process each policy
#     for idx in tqdm(to_process, desc="Processing policies iteratively"):
#         try:
#             baseline_acc = baseline_accuracy_map.get(idx, 0.0)
#             result = process_policy_iteratively(idx, baseline_acc)
            
#             # Track completion/failure
#             if result['status'] in ['success', 'already_perfect']:
#                 tracker.mark_completed(idx, result['final_accuracy'], result['iterations_used'])
#             else:
#                 tracker.mark_failed(idx, result['final_accuracy'], result['iterations_used'])
            
#             all_results.append(result)
            
#             # Collect iteration data for detailed analysis
#             for iter_data in result['iteration_results']:
#                 all_iteration_data.append(iter_data)
            
#         except Exception as e:
#             logging.error(f"Policy {idx} failed completely: {e}")
#             tracker.mark_failed(idx, 0.0, 0)
#             baseline_acc = baseline_accuracy_map.get(idx, 0.0)
#             all_results.append({
#                 'index': idx,
#                 'status': 'error',
#                 'baseline_accuracy': baseline_acc,
#                 'final_accuracy': 0.0,
#                 'iterations_used': 0,
#                 'error': str(e)
#             })
    
#     # Save comprehensive results
#     timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
#     # Summary results
#     if all_results:
#         df_summary = pd.DataFrame(all_results)
#         summary_csv = os.path.join(OUTPUT_DIR, f"iterative_repair_summary_{timestamp}.csv")
#         df_summary.to_csv(summary_csv, index=False)
#         logging.info(f"Summary results saved to {summary_csv}")
    
#     # Detailed iteration results (includes baseline + all repair iterations)
#     if all_iteration_data:
#         df_iterations = pd.DataFrame(all_iteration_data)
#         iterations_csv = os.path.join(OUTPUT_DIR, f"iterative_repair_details_{timestamp}.csv")
#         df_iterations.to_csv(iterations_csv, index=False)
#         logging.info(f"Detailed iteration results saved to {iterations_csv}")
    
#     # Calculate structure validation statistics
#     structure_validation_stats = {}
#     for result in all_results:
#         if 'iteration_results' in result:
#             for iter_data in result['iteration_results']:
#                 if iter_data.get('validation_type') == 'repair':
#                     passed = iter_data.get('structure_validation_passed', False)
#                     policy_idx = iter_data.get('policy_idx')
#                     if policy_idx not in structure_validation_stats:
#                         structure_validation_stats[policy_idx] = {'passed': 0, 'failed': 0}
#                     if passed:
#                         structure_validation_stats[policy_idx]['passed'] += 1
#                     else:
#                         structure_validation_stats[policy_idx]['failed'] += 1
    
#     # Print final summary
#     successful = len([r for r in all_results if r.get('status') in ['success', 'already_perfect']])
#     failed = len([r for r in all_results if r.get('status') in ['failed', 'error']])
#     already_perfect = len([r for r in all_results if r.get('status') == 'already_perfect'])
    
#     if all_results:
#         avg_baseline = sum(r.get('baseline_accuracy', 0) for r in all_results) / len(all_results)
#         avg_final = sum(r.get('final_accuracy', 0) for r in all_results) / len(all_results)
#         total_iterations = sum(r.get('iterations_used', 0) for r in all_results)
        
#         # Calculate improvement
#         baseline_perfect = len([r for r in all_results if r.get('baseline_accuracy', 0) >= TARGET_ACCURACY])
#         final_perfect = len([r for r in all_results if r.get('final_accuracy', 0) >= TARGET_ACCURACY])
#         improvement = final_perfect - baseline_perfect
        
#         # Structure validation stats
#         total_structure_passed = sum(stats['passed'] for stats in structure_validation_stats.values())
#         total_structure_failed = sum(stats['failed'] for stats in structure_validation_stats.values())
#         structure_success_rate = (total_structure_passed / (total_structure_passed + total_structure_failed) * 100) if (total_structure_passed + total_structure_failed) > 0 else 0
#     else:
#         avg_baseline = avg_final = total_iterations = improvement = 0
#         baseline_perfect = final_perfect = 0
#         total_structure_passed = total_structure_failed = structure_success_rate = 0
    
#     # Log the final summary
#     logging.info(f"\n{'='*60}")
#     logging.info("FINAL SUMMARY - BASELINE vs REPAIR WITH COMPLETE FIELD VALIDATION")
#     logging.info(f"{'='*60}")
#     logging.info(f"Total policies processed: {len(all_results)}")
#     logging.info(f"")
#     logging.info(f"BASELINE PERFORMANCE:")
#     logging.info(f"  Average baseline accuracy: {avg_baseline:.1f}%")
#     logging.info(f"  Policies at target (baseline): {baseline_perfect}")
#     logging.info(f"")
#     logging.info(f"FINAL PERFORMANCE:")
#     logging.info(f"  Successfully repaired to 100%: {successful}")
#     logging.info(f"  Already perfect (no repair needed): {already_perfect}")
#     logging.info(f"  Failed to reach 100%: {failed}")
#     logging.info(f"  Average final accuracy: {avg_final:.1f}%")
#     logging.info(f"  Policies at target (final): {final_perfect}")
#     logging.info(f"")
#     logging.info(f"IMPROVEMENT:")
#     logging.info(f"  Net improvement: +{improvement} policies reaching 100%")
#     logging.info(f"  Accuracy improvement: {avg_final - avg_baseline:.1f} percentage points")
#     logging.info(f"  Total iterations used: {total_iterations}")
#     logging.info(f"  Average iterations per policy: {total_iterations/len(all_results):.1f}" if all_results else "0")
#     logging.info(f"")
#     logging.info(f"STRUCTURE VALIDATION PERFORMANCE:")
#     logging.info(f"  Structure validations passed: {total_structure_passed}")
#     logging.info(f"  Structure validations failed: {total_structure_failed}")
#     logging.info(f"  Structure validation success rate: {structure_success_rate:.1f}%")
#     logging.info(f"{'='*60}")
    
#     # Print final summary to console
#     print(f"\n{'='*60}")
#     print("FINAL SUMMARY - BASELINE vs REPAIR WITH COMPLETE FIELD VALIDATION")
#     print(f"{'='*60}")
#     print(f"Total policies processed: {len(all_results)}")
#     print(f"")
#     print(f"BASELINE PERFORMANCE:")
#     print(f"  Average baseline accuracy: {avg_baseline:.1f}%")
#     print(f"  Policies at target (baseline): {baseline_perfect}")
#     print(f"")
#     print(f"FINAL PERFORMANCE:")
#     print(f"  Successfully repaired to 100%: {successful}")
#     print(f"  Already perfect (no repair needed): {already_perfect}")
#     print(f"  Failed to reach 100%: {failed}")
#     print(f"  Average final accuracy: {avg_final:.1f}%")
#     print(f"  Policies at target (final): {final_perfect}")
#     print(f"")
#     print(f"IMPROVEMENT:")
#     print(f"  Net improvement: +{improvement} policies reaching 100%")
#     print(f"  Accuracy improvement: {avg_final - avg_baseline:.1f} percentage points")
#     print(f"  Total iterations used: {total_iterations}")
#     print(f"  Average iterations per policy: {total_iterations/len(all_results):.1f}" if all_results else "0")
#     print(f"")
#     print(f"STRUCTURE VALIDATION PERFORMANCE:")
#     print(f"  Structure validations passed: {total_structure_passed}")
#     print(f"  Structure validations failed: {total_structure_failed}")
#     print(f"  Structure validation success rate: {structure_success_rate:.1f}%")
    
#     # Show detailed policy-by-policy results
#     print(f"\nDETAILED RESULTS:")
#     for result in all_results:
#         idx = result['index']
#         baseline = result.get('baseline_accuracy', 0)
#         final = result.get('final_accuracy', 0)
#         status = result.get('status', 'unknown')
#         iterations = result.get('iterations_used', 0)
        
#         # Structure validation info for this policy
#         policy_structure_stats = structure_validation_stats.get(idx, {'passed': 0, 'failed': 0})
#         structure_info = f"(struct: {policy_structure_stats['passed']}P/{policy_structure_stats['failed']}F)" if policy_structure_stats['passed'] + policy_structure_stats['failed'] > 0 else ""
        
#         if status == 'already_perfect':
#             print(f"  Policy {idx}: {baseline:.1f}% → {final:.1f}% (already perfect)")
#         elif status == 'success':
#             print(f"  Policy {idx}: {baseline:.1f}% → {final:.1f}% (SUCCESS in {iterations} iterations) {structure_info}")
#         elif status == 'failed':
#             print(f"  Policy {idx}: {baseline:.1f}% → {final:.1f}% (failed after {iterations} iterations) {structure_info}")
#         else:
#             print(f"  Policy {idx}: {baseline:.1f}% → {final:.1f}% (ERROR: {result.get('error', 'unknown')})")
    

    
#     # Cleanup temporary files
#     if os.path.exists(TEMP_DIR):
#         shutil.rmtree(TEMP_DIR)
#         logging.info("Cleaned up temporary files")

# if __name__ == "__main__":
#     main()

#!/usr/bin/env python3
"""
iterative_policy_repair.py

This script first performs baseline validation on original AWS IAM policies,
then iteratively repairs them using Claude and validates with SMT solver.
It attempts up to 5 iterations per policy until 100% accuracy is achieved.

Features:
- Baseline validation of original policies
- Iterative repair with accuracy feedback
- SMT solver validation integration
- Comprehensive tracking of all iterations
- Results saved to CSV for analysis
- Progress tracking with resume capability
- Complete field validation (Action, Effect, Resource, Condition, Principal)

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
REQUIREMENTS_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-1/requests/request-120"
OUTPUT_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-1/results/result-120"
LOG_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-1/logs/log-120"
TEMP_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-1/temp_validation/val-120"
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

# Enhanced policy repair prompt with complete field requirements
def get_policy_repair_prompt(problematic_policy, requirements):
    prompt = f"""
You are an AWS IAM security expert. Your task is to repair a problematic AWS IAM policy based on specific the given request sets.

PROBLEMATIC POLICY:
{problematic_policy}

SECURITY REQUIREMENTS:
{requirements}

Your task:
1. Repair the policy

CRITICAL: Return ONLY valid JSON with ALL required fields. No explanations, no markdown, no extra text. Start with {{ and end with }}. The JSON must be properly formatted with correct commas, brackets, and quotes.

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
            "policy_iterations": {},  # Track iterations per policy
            "baseline_completed": []  # Track baseline validation completion
        }
    
    def save_progress(self):
        os.makedirs(os.path.dirname(self.progress_file), exist_ok=True)
        with open(self.progress_file, 'w') as f:
            json.dump(self.progress, f, indent=2)
    
    def mark_baseline_completed(self, idx):
        if idx not in self.progress["baseline_completed"]:
            self.progress["baseline_completed"].append(idx)
        self.save_progress()
    
    def is_baseline_done(self, idx):
        return idx in self.progress.get("baseline_completed", [])
    
    def mark_completed(self, idx, final_accuracy, iterations_used):
        self.progress["last_processed"] = idx
        if idx not in self.progress["completed"]:
            self.progress["completed"].append(idx)
        if idx in self.progress["failed"]:
            self.progress["failed"].remove(idx)
        
        self.progress["policy_iterations"][str(idx)] = {
            "status": "completed",
            "final_accuracy": final_accuracy,
            "iterations_used": iterations_used
        }
        self.save_progress()
    
    def mark_failed(self, idx, final_accuracy, iterations_used):
        if idx not in self.progress["failed"]:
            self.progress["failed"].append(idx)
        
        self.progress["policy_iterations"][str(idx)] = {
            "status": "failed",
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
            if r.get('Principal'):
                lines.append(f"      Principal: {r.get('Principal')}")
            if r.get('Condition'):
                lines.append(f"      Condition: {r.get('Condition')}")
    
    if deny:
        lines.append("MUST DENY:")
        for i, r in enumerate(deny, 1):
            lines.append(f"  {i}. ID: {r.get('id')} Actions: {r.get('Action')} Resources: {r.get('Resource')}")
            if r.get('Principal'):
                lines.append(f"      Principal: {r.get('Principal')}")
            if r.get('Condition'):
                lines.append(f"      Condition: {r.get('Condition')}")

    
    return "\n".join(lines)

def validate_policy_structure(policy: dict) -> list:
    """Validate that the policy has all required fields and return any validation errors."""
    errors = []
    
    # Check top-level structure
    if not isinstance(policy, dict):
        errors.append("Policy must be a JSON object")
        return errors
    
    if "Version" not in policy:
        errors.append("Missing 'Version' field in policy")
    elif policy["Version"] != "2012-10-17":
        errors.append(f"Version should be '2012-10-17', got '{policy['Version']}'")
    
    if "Statement" not in policy:
        errors.append("Missing 'Statement' field in policy")
        return errors
    
    if not isinstance(policy["Statement"], list):
        errors.append("'Statement' field must be an array")
        return errors
    
    # Check each statement
    required_fields = ["Sid", "Effect", "Action", "Resource", "Principal", "Condition"]
    
    for i, statement in enumerate(policy["Statement"]):
        if not isinstance(statement, dict):
            errors.append(f"Statement {i} must be an object")
            continue
        
        # Check for all required fields
        for field in required_fields:
            if field not in statement:
                errors.append(f"Statement {i} missing required field '{field}'")
        
        # Validate specific field values
        if "Effect" in statement and statement["Effect"] not in ["Allow", "Deny"]:
            errors.append(f"Statement {i} Effect must be 'Allow' or 'Deny', got '{statement['Effect']}'")
        
        if "Sid" in statement and not isinstance(statement["Sid"], str):
            errors.append(f"Statement {i} Sid must be a string")
        
        if "Principal" in statement and not isinstance(statement["Principal"], dict):
            errors.append(f"Statement {i} Principal must be an object")
        
        if "Condition" in statement and not isinstance(statement["Condition"], dict):
            errors.append(f"Statement {i} Condition must be an object")
    
    return errors

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
        
        # Enhanced validation with complete field checking
        validation_errors = validate_policy_structure(parsed_json)
        
        if validation_errors:
            error_msg = "Policy validation failed:\n" + "\n".join(f"  - {error}" for error in validation_errors)
            raise ValueError(error_msg)
        
        logging.info("Policy structure validation passed - all required fields present")
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
            
            # Validate the fixed JSON
            validation_errors = validate_policy_structure(parsed_json)
            if validation_errors:
                error_msg = "Fixed JSON validation failed:\n" + "\n".join(f"  - {error}" for error in validation_errors)
                raise ValueError(error_msg)
            
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
        system="You are an AWS IAM security expert who repairs policies to meet specific security requirements. Generate only valid JSON policies with ALL necessary fields for the policy. NO missing fields allowed.",
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
            'error': str(e)
        }

def process_policy_iteratively(idx: int, baseline_accuracy: float = 0.0) -> dict:
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
            'iterations_used': 0,
            'iteration_results': [],
            'final_policy_file': final_output_file
        }
    
    # Track all iterations
    iteration_results = []
    current_policy = original_policy.copy()
    final_accuracy = baseline_accuracy
    
    for iteration in range(1, MAX_ITERATIONS + 1):
        logging.info(f"Policy {idx} - Iteration {iteration}/{MAX_ITERATIONS}")
        
        try:
            # Repair policy with Claude (minimal prompt)
            logging.info(f"Repairing policy with Claude (iteration {iteration}) - MINIMAL PROMPT")
            logging.info("Using challenging minimal prompt: 'Fix this policy'")
            repaired_policy = repair_policy_with_claude(current_policy, requests)
            
            # Validate policy structure before saving
            validation_errors = validate_policy_structure(repaired_policy)
            if validation_errors:
                logging.warning(f"Iteration {iteration} - Policy structure validation failed:")
                for error in validation_errors:
                    logging.warning(f"  - {error}")
                raise ValueError(f"Generated policy missing required fields: {validation_errors}")
            else:
                logging.info(f"Iteration {iteration} - Policy structure validation passed")
            
            # Save temporary repaired policy for validation
            temp_policy_file = os.path.join(TEMP_DIR, f"policy_{idx}_iter_{iteration}.json")
            os.makedirs(TEMP_DIR, exist_ok=True)
            save_json_file(repaired_policy, temp_policy_file)
            
            # Validate with SMT solver
            logging.info(f"Validating with SMT solver (iteration {iteration})...")
            validation_results = run_smt_validator(temp_policy_file, req_file)
            
            accuracy = validation_results['accuracy']
            logging.info(f"Iteration {iteration} accuracy: {accuracy:.1f}%")
            
            # Record this iteration
            iteration_record = {
                'policy_idx': idx,
                'iteration': iteration,
                'validation_type': 'repair',
                'accuracy': accuracy,
                'total_requests': validation_results['total_requests'],
                'correct': validation_results['correct'],
                'incorrect': validation_results['incorrect'],
                'misclassified_allow_to_deny': validation_results['misclassified_allow_to_deny'],
                'misclassified_deny_to_allow': validation_results['misclassified_deny_to_allow'],
                'policy_file': temp_policy_file,
                'structure_validation_passed': True
            }
            iteration_results.append(iteration_record)
            
            final_accuracy = accuracy
            
            # Check if we achieved target accuracy
            if accuracy >= TARGET_ACCURACY:
                logging.info(f"Target accuracy achieved for policy {idx} in {iteration} iterations!")
                
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
                    'final_policy_file': final_output_file
                }
            
            # For next iteration, use the ORIGINAL policy again (not the repaired one)
            # This ensures we start fresh each time with the same prompt
            current_policy = original_policy.copy()
            
        except Exception as e:
            logging.error(f"Error in iteration {iteration} for policy {idx}: {e}")
            iteration_record = {
                'policy_idx': idx,
                'iteration': iteration,
                'validation_type': 'repair',
                'accuracy': 0.0,
                'structure_validation_passed': False,
                'error': str(e)
            }
            iteration_results.append(iteration_record)
    
    # If we reach here, we didn't achieve target accuracy
    logging.warning(f"Failed to achieve target accuracy for policy {idx} after {MAX_ITERATIONS} iterations. Final accuracy: {final_accuracy:.1f}%")
    
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
        'iterations_used': MAX_ITERATIONS,
        'iteration_results': iteration_results,
        'final_policy_file': final_output_file
    }

def main():
    log_file = setup_logging()
    logging.info("Starting iterative policy repair system with minimal prompting (challenging for LLM)")
    
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
                tracker.mark_baseline_completed(idx)
                
                # Log baseline result
                if 'error' not in baseline_result:
                    logging.info(f"Policy {idx} baseline: {baseline_result['accuracy']:.1f}% accuracy")
                else:
                    logging.error(f"Policy {idx} baseline failed: {baseline_result['error']}")
                    
            except Exception as e:
                logging.error(f"Baseline validation failed for policy {idx}: {e}")
                baseline_results.append({
                    'policy_idx': idx,
                    'validation_type': 'baseline',
                    'accuracy': 0.0,
                    'error': str(e)
                })
                tracker.mark_baseline_completed(idx)  # Mark as done even if failed
    else:
        logging.info("All baseline validations already completed. Loading existing results...")
        # Load existing baseline results if available
        existing_baseline_file = os.path.join(OUTPUT_DIR, "baseline_results.csv")
        if os.path.exists(existing_baseline_file):
            baseline_df = pd.read_csv(existing_baseline_file)
            baseline_results = baseline_df.to_dict('records')
        else:
            # If no existing file, create empty baseline results with 0% accuracy
            baseline_results = [{'policy_idx': i, 'validation_type': 'baseline', 'accuracy': 0.0} for i in range(total)]
    
    # Save baseline results
    if baseline_results:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        baseline_csv = os.path.join(OUTPUT_DIR, f"baseline_results_{timestamp}.csv")
        baseline_df = pd.DataFrame(baseline_results)
        baseline_df.to_csv(baseline_csv, index=False)
        logging.info(f"Baseline results saved to {baseline_csv}")
        
        # Also save as latest baseline
        latest_baseline_csv = os.path.join(OUTPUT_DIR, "baseline_results.csv")
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
        print(f"Successfully validated policies: {len(successful_baselines)}")
        print(f"Failed baseline validations: {len(failed_baselines)}")
        print(f"Average baseline accuracy: {avg_baseline_accuracy:.1f}%")
        print(f"Policies already at target accuracy: {len(perfect_baselines)}")
        
        if perfect_baselines:
            perfect_indices = [r['policy_idx'] for r in perfect_baselines]
            print(f"Perfect baseline policies: {perfect_indices}")
    
    print(f"{'='*60}")
    
    # Step 2: Iterative repair for policies that need improvement
    print("\nSTEP 2: MINIMAL PROMPT ITERATIVE REPAIR")
    print("=" * 60)
    print("Using minimal 'Fix this policy' prompt - challenging for LLM")
    print("=" * 60)
    
    # Create baseline accuracy lookup
    baseline_accuracy_map = {r['policy_idx']: r.get('accuracy', 0.0) for r in baseline_results}
    
    to_process = [i for i in range(total) if not tracker.is_done(i)]
    logging.info(f"Policies to process for repair: {to_process}")
    
    all_results = []
    all_iteration_data = baseline_results.copy()  # Start with baseline data
    
    # Process each policy
    for idx in tqdm(to_process, desc="Processing policies iteratively"):
        try:
            baseline_acc = baseline_accuracy_map.get(idx, 0.0)
            result = process_policy_iteratively(idx, baseline_acc)
            
            # Track completion/failure
            if result['status'] in ['success', 'already_perfect']:
                tracker.mark_completed(idx, result['final_accuracy'], result['iterations_used'])
            else:
                tracker.mark_failed(idx, result['final_accuracy'], result['iterations_used'])
            
            all_results.append(result)
            
            # Collect iteration data for detailed analysis
            for iter_data in result['iteration_results']:
                all_iteration_data.append(iter_data)
            
        except Exception as e:
            logging.error(f"Policy {idx} failed completely: {e}")
            tracker.mark_failed(idx, 0.0, 0)
            baseline_acc = baseline_accuracy_map.get(idx, 0.0)
            all_results.append({
                'index': idx,
                'status': 'error',
                'baseline_accuracy': baseline_acc,
                'final_accuracy': 0.0,
                'iterations_used': 0,
                'error': str(e)
            })
    
    # Save comprehensive results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Summary results
    if all_results:
        df_summary = pd.DataFrame(all_results)
        summary_csv = os.path.join(OUTPUT_DIR, f"iterative_repair_summary_{timestamp}.csv")
        df_summary.to_csv(summary_csv, index=False)
        logging.info(f"Summary results saved to {summary_csv}")
    
    # Detailed iteration results (includes baseline + all repair iterations)
    if all_iteration_data:
        df_iterations = pd.DataFrame(all_iteration_data)
        iterations_csv = os.path.join(OUTPUT_DIR, f"iterative_repair_details_{timestamp}.csv")
        df_iterations.to_csv(iterations_csv, index=False)
        logging.info(f"Detailed iteration results saved to {iterations_csv}")
    
    # Calculate structure validation statistics
    structure_validation_stats = {}
    for result in all_results:
        if 'iteration_results' in result:
            for iter_data in result['iteration_results']:
                if iter_data.get('validation_type') == 'repair':
                    passed = iter_data.get('structure_validation_passed', False)
                    policy_idx = iter_data.get('policy_idx')
                    if policy_idx not in structure_validation_stats:
                        structure_validation_stats[policy_idx] = {'passed': 0, 'failed': 0}
                    if passed:
                        structure_validation_stats[policy_idx]['passed'] += 1
                    else:
                        structure_validation_stats[policy_idx]['failed'] += 1
    
    # Print final summary
    successful = len([r for r in all_results if r.get('status') in ['success', 'already_perfect']])
    failed = len([r for r in all_results if r.get('status') in ['failed', 'error']])
    already_perfect = len([r for r in all_results if r.get('status') == 'already_perfect'])
    
    if all_results:
        avg_baseline = sum(r.get('baseline_accuracy', 0) for r in all_results) / len(all_results)
        avg_final = sum(r.get('final_accuracy', 0) for r in all_results) / len(all_results)
        total_iterations = sum(r.get('iterations_used', 0) for r in all_results)
        
        # Calculate improvement
        baseline_perfect = len([r for r in all_results if r.get('baseline_accuracy', 0) >= TARGET_ACCURACY])
        final_perfect = len([r for r in all_results if r.get('final_accuracy', 0) >= TARGET_ACCURACY])
        improvement = final_perfect - baseline_perfect
        
        # Structure validation stats
        total_structure_passed = sum(stats['passed'] for stats in structure_validation_stats.values())
        total_structure_failed = sum(stats['failed'] for stats in structure_validation_stats.values())
        structure_success_rate = (total_structure_passed / (total_structure_passed + total_structure_failed) * 100) if (total_structure_passed + total_structure_failed) > 0 else 0
    else:
        avg_baseline = avg_final = total_iterations = improvement = 0
        baseline_perfect = final_perfect = 0
        total_structure_passed = total_structure_failed = structure_success_rate = 0
    
    # Log the final summary
    logging.info(f"\n{'='*60}")
    logging.info("FINAL SUMMARY - MINIMAL PROMPT EXPERIMENT")
    logging.info(f"{'='*60}")
    logging.info(f"Total policies processed: {len(all_results)}")
    logging.info(f"")
    logging.info(f"BASELINE PERFORMANCE:")
    logging.info(f"  Average baseline accuracy: {avg_baseline:.1f}%")
    logging.info(f"  Policies at target (baseline): {baseline_perfect}")
    logging.info(f"")
    logging.info(f"FINAL PERFORMANCE:")
    logging.info(f"  Successfully repaired to 100%: {successful}")
    logging.info(f"  Already perfect (no repair needed): {already_perfect}")
    logging.info(f"  Failed to reach 100%: {failed}")
    logging.info(f"  Average final accuracy: {avg_final:.1f}%")
    logging.info(f"  Policies at target (final): {final_perfect}")
    logging.info(f"")
    logging.info(f"IMPROVEMENT:")
    logging.info(f"  Net improvement: +{improvement} policies reaching 100%")
    logging.info(f"  Accuracy improvement: {avg_final - avg_baseline:.1f} percentage points")
    logging.info(f"  Total iterations used: {total_iterations}")
    logging.info(f"  Average iterations per policy: {total_iterations/len(all_results):.1f}" if all_results else "0")
    logging.info(f"")
    logging.info(f"MINIMAL PROMPT EXPERIMENT:")
    logging.info(f"  Prompt: 'Fix this policy' + basic requirements")
    logging.info(f"  Structure validations passed: {total_structure_passed}")
    logging.info(f"  Structure validations failed: {total_structure_failed}")
    logging.info(f"  Structure validation success rate: {structure_success_rate:.1f}%")
    logging.info(f"{'='*60}")
    
    # Print final summary to console
    print(f"\n{'='*60}")
    print("FINAL SUMMARY - MINIMAL PROMPT EXPERIMENT")
    print(f"{'='*60}")
    print(f"Total policies processed: {len(all_results)}")
    print(f"")
    print(f"BASELINE PERFORMANCE:")
    print(f"  Average baseline accuracy: {avg_baseline:.1f}%")
    print(f"  Policies at target (baseline): {baseline_perfect}")
    print(f"")
    print(f"FINAL PERFORMANCE:")
    print(f"  Successfully repaired to 100%: {successful}")
    print(f"  Already perfect (no repair needed): {already_perfect}")
    print(f"  Failed to reach 100%: {failed}")
    print(f"  Average final accuracy: {avg_final:.1f}%")
    print(f"  Policies at target (final): {final_perfect}")
    print(f"")
    print(f"IMPROVEMENT:")
    print(f"  Net improvement: +{improvement} policies reaching 100%")
    print(f"  Accuracy improvement: {avg_final - avg_baseline:.1f} percentage points")
    print(f"  Total iterations used: {total_iterations}")
    print(f"  Average iterations per policy: {total_iterations/len(all_results):.1f}" if all_results else "0")
    print(f"")
    print(f"MINIMAL PROMPT EXPERIMENT:")
    print(f"  Prompt: 'Fix this policy' + basic requirements")
    print(f"  Structure validations passed: {total_structure_passed}")
    print(f"  Structure validations failed: {total_structure_failed}")
    print(f"  Structure validation success rate: {structure_success_rate:.1f}%")
    
    # Show detailed policy-by-policy results
    print(f"\nDETAILED RESULTS:")
    for result in all_results:
        idx = result['index']
        baseline = result.get('baseline_accuracy', 0)
        final = result.get('final_accuracy', 0)
        status = result.get('status', 'unknown')
        iterations = result.get('iterations_used', 0)
        
        # Structure validation info for this policy
        policy_structure_stats = structure_validation_stats.get(idx, {'passed': 0, 'failed': 0})
        structure_info = f"(struct: {policy_structure_stats['passed']}P/{policy_structure_stats['failed']}F)" if policy_structure_stats['passed'] + policy_structure_stats['failed'] > 0 else ""
        
        if status == 'already_perfect':
            print(f"  Policy {idx}: {baseline:.1f}% -> {final:.1f}% (already perfect)")
        elif status == 'success':
            print(f"  Policy {idx}: {baseline:.1f}% -> {final:.1f}% (SUCCESS in {iterations} iterations) {structure_info}")
        elif status == 'failed':
            print(f"  Policy {idx}: {baseline:.1f}% -> {final:.1f}% (failed after {iterations} iterations) {structure_info}")
        else:
            print(f"  Policy {idx}: {baseline:.1f}% -> {final:.1f}% (ERROR: {result.get('error', 'unknown')})")

    print(f"{'='*60}")
    print("Minimal Prompt Experiment Results:")
    print("Used extremely minimal prompting: 'Fix this policy'")
    print("No detailed guidance or field requirements given to LLM")
    print("Tests LLM's ability to infer requirements from policy structure")
    print("Structure validation still enforced post-generation")
    print(f"{'='*60}")
    
    # Cleanup temporary files
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
        logging.info("Cleaned up temporary files")

if __name__ == "__main__":
    main()