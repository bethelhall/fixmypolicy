
import re
import subprocess
import tempfile
import shutil
from functools import wraps
from datetime import datetime
import pandas as pd 
from tqdm import tqdm
from ollama import chat, ChatResponse 
import os
import sys
import time
import json
import tempfile
from functools import wraps
from datetime import datetime, timedelta
from pathlib import Path
import signal
import threading
from timeout_decorator import timeout
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from ollama import chat
import logging

import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"

req = 20
TOTAL_POLICIES = 282
MAX_ITERATIONS = 5
MAX_ATTEMPT = 1
DELAY = 1
TARGET_ACCURACY = 100.0
OLLAMA_MODEL = "codellama-7b"
# # LLAMA_MODEL = "ibm-granite/granite-3.3-8b-instruct"
LLAMA_MODEL = "codellama/CodeLlama-7b-Instruct-hf"
POLICY_DIR = Path("/home/bhall2/fixmypolicy/FL/Experiment-2/original_policy")
REQUIREMENTS_DIR = Path(f"/home/bhall2/fixmypolicy/FL/Experiment-2/requests/req_extended_test")
OUTPUT_DIR = Path(f"/home/bhall2/fixmypolicy/FL/Experiment-2/results/result-fl-repair-generalize")
LOG_DIR = Path(f"/home/bhall2/fixmypolicy/FL/Experiment-2/logs/log-fl-repair-generalize")
TEMP_DIR = Path(f"/home/bhall2/fixmypolicy/FL/Experiment-2/temp_validation/val-{req}-fl-repair-generalize")
QUACKY_SRC_DIR = Path("/home/bhall2/fixmypolicy/quacky/src")
SMT_VALIDATOR_SCRIPT = QUACKY_SRC_DIR / "validate_requests.py"
FAULT_LOCALIZATION_DIR = Path(f"/home/bhall2/fixmypolicy/FL/Experiment-2/results/result-{req}-ollama/Quacky_output")

def parse_smt_timing_from_output(output_content: str) -> dict:
    """Parse SMT solver timing information from validator output"""
    smt_data = {
        'total_solver_calls': 0,
        'total_solver_time': 0.0,
        'individual_call_times': [],
        'average_call_time': 0.0,
        'min_call_time': 0.0,
        'max_call_time': 0.0
    }
    
    try:
        lines = output_content.split('\n')
        
        # Extract solver call times
        call_times = []
        for line in lines:
            if 'Solver time:' in line:
                # Extract time value (format: "Solver time: 0.0123 seconds")
                time_match = re.search(r'Solver time:\s*([\d.]+)\s*seconds', line)
                if time_match:
                    call_time = float(time_match.group(1))
                    call_times.append(call_time)
        
        # Extract total solver calls
        for line in lines:
            if 'Total Solver Calls:' in line:
                calls_match = re.search(r'Total Solver Calls:\s*(\d+)', line)
                if calls_match:
                    smt_data['total_solver_calls'] = int(calls_match.group(1))
                break
        
        if call_times:
            smt_data['individual_call_times'] = call_times
            smt_data['total_solver_time'] = sum(call_times)
            smt_data['average_call_time'] = smt_data['total_solver_time'] / len(call_times)
            smt_data['min_call_time'] = min(call_times)
            smt_data['max_call_time'] = max(call_times)
        
        # If we didn't find individual times but have total calls, estimate
        if not call_times and smt_data['total_solver_calls'] > 0:
            logging.warning("Could not extract individual solver times, but found total calls")
        
    except Exception as e:
        logging.warning(f"Error parsing SMT timing data: {e}")
    
    return smt_data

def setup_logging(log_dir: str = LOG_DIR):  
    """Configure logging"""
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f'simple_repair_{OLLAMA_MODEL}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler() 
        ]
    )
    return log_file

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


# LLAMA_MODEL = "deepseek-ai/DeepSeek-Coder-V2-Lite-Base"
# LLAMA_MODEL = "meta-llama/Llama-3.2-3B"
LLAMA_MODEL = "codellama/CodeLlama-7b-Instruct-hf"
# LLAMA_MODEL = "ibm-granite/granite-3.3-8b-instruct"
# LLAMA_MODEL = "deepseek-ai/deepseek-coder-7b-instruct-v1.5"


from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
import torch
import logging
# Load once globally
tokenizer = AutoTokenizer.from_pretrained(LLAMA_MODEL)

os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'expandable_segments:True'

# Load once globally with memory optimizations
tokenizer = AutoTokenizer.from_pretrained(LLAMA_MODEL)

# Add padding token if missing
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

model = AutoModelForCausalLM.from_pretrained(
    LLAMA_MODEL,
    device_map="auto",       
    torch_dtype=torch.float16
    )

if hasattr(model, 'gradient_checkpointing_enable'):
    model.gradient_checkpointing_enable()

generator = pipeline(
    "text-generation", 
    model=model, 
    tokenizer=tokenizer,
    torch_dtype=torch.float16
)

def call_ollama(prompt: str, system_prompt: str = "") -> str:
    """Drop-in replacement for call_ollama using Hugging Face DeepSeek Coder"""
    try:
        # Clear cache before generation
        torch.cuda.empty_cache()
        
        if system_prompt:
            full_prompt = f"<|system|>\n{system_prompt}\n<|user|>\n{prompt}"
        else:
            full_prompt = prompt

        outputs = generator(
            full_prompt,    
            temperature=0.1,
            top_p=0.3,
            top_k=40,
            repetition_penalty=1.1,
            do_sample=True,
            eos_token_id=tokenizer.eos_token_id,
            return_full_text=False,
            max_new_tokens=12800,
            pad_token_id=tokenizer.eos_token_id
        )

        return outputs[0]["generated_text"]

    except torch.cuda.OutOfMemoryError as e:
        logging.error(f"CUDA out of memory: {e}")
        torch.cuda.empty_cache()  # Clear cache on OOM
        raise Exception(f"CUDA out of memory: {e}")
    except Exception as e:
        logging.error(f"Model generation error: {e}")
        raise Exception(f"Model generation error: {e}")
    

def create_simple_repair_prompt(original_policy: dict, requirements: dict, fault_localization_report: str, iteration: int = 1, previous_accuracy: float = 0.0) -> str:
    """
    """

    prompt = f"""You are an AWS IAM policy expert. You must use security best practices to repair the following policy so that the provided test sets are allowed and denied.
    You are an AWS IAM policy expert. Your task is to update the following policy by applying AWS security best practices so that all requests in the provided test sets are correctly allowed or denied.

        - Analyze the given requests to identify common patterns.  
        - Create policy statements that generalize these patterns to correctly allow or deny all related requests.  
        - Use an appropriate number of statements (neither overly specific nor overly broad) to achieve correct and secure coverage.  
        - Ensure the resulting policy adheres to the principle of least privilege.

        ORIGINAL POLICY:    
        {json.dumps(original_policy, indent=2)}

        REQUIREMENTS to SATISFY:
        {json.dumps(requirements, indent=2)}

        FAULT LOCALIZATION REPORT TO CHECK WHICH REQUIREMENTS ARE BEING INCORRECTLY ALLOWED/DENIED AND FIX:
        {fault_localization_report}

        Return ONLY the complete corrected policy as valid JSON. No explanations, no markdown formatting.

        CORRECTED POLICY:"""

    return prompt

def create_simple_system_prompt() -> str:
    """Simple system prompt for policy repair"""
    return """You are an expert AWS IAM policy engineer. 

CRITICAL OUTPUT REQUIREMENTS:
- You MUST return a complete, valid JSON policy
- Start your response immediately with { and end with }
- Do NOT include any explanations, comments, or text before or after the JSON
- Do NOT use markdown formatting or code blocks
- The JSON must be syntactically correct and complete


Return ONLY the JSON policy, nothing else."""

def extract_and_validate_json(response_text: str) -> dict:
    """Extract and validate JSON from Ollama response with debugging"""
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
        logging.error(f"No JSON object found in response. Full text: {text}")
        raise ValueError(f"No JSON object found in response. Text: {text[:200]}...")
    
    json_text = text[start_idx:end_idx+1]
    
    try:
        parsed_json = json.loads(json_text)
        
        # Validate essential fields only
        if not isinstance(parsed_json, dict):
            raise ValueError("Response is not a JSON object")
        
        if "Statement" not in parsed_json:
            raise ValueError("Missing 'Statement' field in policy")
        
        if not isinstance(parsed_json["Statement"], list):
            raise ValueError("'Statement' field must be an array")
        
        # Add default version if missing (AWS default)
        if "Version" not in parsed_json:
            parsed_json["Version"] = "2012-10-17"
        
        return parsed_json
        
    except json.JSONDecodeError as e:
        # Log what the LLM actually generated
        logging.error(f"LLM generated invalid JSON!")
        logging.error(f"JSON parsing failed at line {e.lineno}, column {e.colno}: {e.msg}")
        logging.error("=== FULL LLM RESPONSE ===")
        logging.error(response_text)
        logging.error("=== END LLM RESPONSE ===")
        
        logging.error("=== EXTRACTED JSON ===")
        logging.error(json_text)
        logging.error("=== END EXTRACTED JSON ===")
        
        # Show the problematic area with line numbers
        json_lines = json_text.split('\n')
        logging.error("JSON with line numbers (error location marked):")
        for i, line in enumerate(json_lines, 1):
            marker = " <-- Error Here" if i == e.lineno else ""
            logging.error(f"{i:2}: {line}{marker}")
        
        raise ValueError(f"LLM generated invalid JSON: {e}")

def extract_failing_requests(validator_output: str, original_reqs: dict) -> dict:
    """
    Parse SMT validator output and return only the failing requests
    in the same JSON schema as original requirements.
    """
    failing_ids = set()
    lines = validator_output.splitlines()

    for line in lines:
        if line.startswith("Request:"):
            # Example: "Request: deny_08f8eeec ..."
            parts = line.split()
            if len(parts) >= 2:
                failing_ids.add(parts[1].strip())

    # Filter the original requirements by these IDs
    failing_reqs = [r for r in original_reqs.get("Requests", []) if r.get("id") in failing_ids]
    return {"Requests": failing_reqs}

@retry()
def repair_policy_simple(policy: dict, requirements: dict, fault_localization_report: str, iteration: int = 1, policy_idx: int = None) -> dict:
    """Simplified policy repair using three inputs"""
    # requirements = simplify_requirements(requirements)
    prompt = create_simple_repair_prompt(policy, requirements, fault_localization_report, iteration)

    system_prompt = create_simple_system_prompt()

    logging.info(f"{'='*80}")
    logging.info(f"Iterative Repair - ITERATION {iteration}")
    logging.info(f"{'='*80}")
    
    # Log all LLM inputs in detail
    logging.info(f"{'='*120}")
    logging.info(f"LLM input - Iteration {iteration}")
    logging.info(f"{'='*120}")
    
    logging.info(f"sys prompt:")
    logging.info(f"{'='*60}")
    logging.info(system_prompt)
    logging.info(f"{'='*60}")
    
    logging.info(f"User prompt:")
    logging.info(f"{'='*60}")
    logging.info(prompt)
    logging.info(f"{'='*60}")
    
    logging.info(f"  System prompt length: {len(system_prompt)} characters")
    logging.info(f"  User prompt length: {len(prompt)} characters")
    logging.info(f"  Total input length: {len(system_prompt) + len(prompt)} characters")
    
    logging.info(f"Original policy (Input):")
    logging.info(f"{'='*60}")
    logging.info(json.dumps(policy, indent=2))
    logging.info(f"{'='*60}")
    
    logging.info(f"Request (Input):")
    logging.info(f"{'='*60}")
    logging.info(json.dumps(requirements, indent=2))
    logging.info(f"{'='*60}")
    
    logging.info(f"Fl (Input):")
    logging.info(f"{'='*60}")
    logging.info(fault_localization_report)
    logging.info(f"{'='*60}")
    
    logging.info(f"{'='*120}")
    logging.info(f"END OF LLM INPUTS - ITERATION {iteration}")
    logging.info(f"{'='*120}")
    
    # Call LLM
    response_text = call_ollama(prompt, system_prompt)
    # Save raw LLM output for every iteration
    raw_output_file = os.path.join(TEMP_DIR, f"raw_llm_output_policy_{policy_idx:03d}_iter_{iteration}.txt")
    os.makedirs(TEMP_DIR, exist_ok=True)
    with open(raw_output_file, 'w', encoding='utf-8') as f:
        f.write(response_text)
    
    logging.info(f"{'='*80}")
    logging.info(f"LLM response - iteration {iteration}")
    
    logging.info(f"{'='*80}")
    logging.info(f"LLM response - iteration {iteration}")
    logging.info(f"{'='*80}")
    logging.info(f"Response length: {len(response_text)} characters")
    logging.info(f"Complete Response - Iteration {iteration}: ")
    logging.info(f"{'='*120}")
    logging.info(response_text)
    logging.info(f"{'='*120}")

    if not response_text:
        raise ValueError("Empty response from LLM")
    
    # Parse and validate response
    repaired_policy = extract_and_validate_json(response_text)
    
    # Enhanced change analysis
    original_statements = policy.get('Statement', [])
    repaired_statements = repaired_policy.get('Statement', [])
    
    logging.info(f"POLICY CHANGES ANALYSIS:")
    logging.info(f"  Original statements: {len(original_statements)}")
    logging.info(f"  Repaired statements: {len(repaired_statements)}")
    logging.info(f"{'='*80}")
    
    return repaired_policy

def run_smt_validator(policy_file: str, requests_file: str, policy_idx: int = None) -> dict:
    """Run SMT validator - get accuracy only"""
    try:
        original_dir = os.getcwd()
        os.chdir(QUACKY_SRC_DIR)
        
        # Create output directories
        if policy_idx is not None:
            policy_specific_dir = os.path.join(OUTPUT_DIR, "Quacky_output", f"policy_{policy_idx:03d}")
            os.makedirs(policy_specific_dir, exist_ok=True)
            
            # File paths for validation
            accuracy_output_path = os.path.join(policy_specific_dir, f"policy_{policy_idx:03d}_accuracy_validation.txt")
        else:
            quacky_output_dir = os.path.join(OUTPUT_DIR, "Quacky_output")
            os.makedirs(quacky_output_dir, exist_ok=True)
            timestamp = int(time.time())
            pid = os.getpid()
            accuracy_output_path = os.path.join(quacky_output_dir, f"temp_accuracy_{pid}_{timestamp}.txt")
        
        cmd_accuracy = [
            sys.executable, 'validate_requests.py',
            '-p1', policy_file,
            '--requests', requests_file,
            '-s'
        ]
        
        logging.debug(f"Running accuracy validation: {' '.join(cmd_accuracy)}")
        
        with open(accuracy_output_path, 'w') as output_file:
            result = subprocess.run(cmd_accuracy, stdout=output_file, stderr=subprocess.PIPE, text=True, timeout=300)
        
        if result.returncode != 0:
            logging.error(f"Accuracy validation failed: {result.stderr}")
            raise Exception(f"Accuracy validation failed: {result.stderr}")
        
        with open(accuracy_output_path, 'r') as f:
            accuracy_output_content = f.read()
        
        os.chdir(original_dir)
        
        accuracy_lines = accuracy_output_content.split('\n')
        accuracy = 0.0
        total_requests = 0
        correct_count = 0
        incorrect_count = 0
        misclassified_allow_to_deny = 0
        misclassified_deny_to_allow = 0
        
        in_analysis_section = False
        for i, line in enumerate(accuracy_lines):
            line = line.strip()
            
            if "INDIVIDUAL REQUEST ANALYSIS" in line:
                in_analysis_section = True
                continue
            elif line.startswith("=") and in_analysis_section and len(line) > 10:
                if any(phrase in ''.join(accuracy_lines[i:i+5]) for phrase in ["Results saved", "saved to HOME"]):
                    break
            
            if in_analysis_section:
                if line.startswith("Total Individual Requests:"):
                    import re
                    total_match = re.search(r'(\d+)', line)
                    if total_match:
                        total_requests = int(total_match.group(1))
                elif line.startswith("Correct Classifications:"):
                    import re
                    correct_match = re.search(r'(\d+)', line)
                    if correct_match:
                        correct_count = int(correct_match.group(1))
                elif line.startswith("Incorrect Classifications:"):
                    import re
                    incorrect_match = re.search(r'(\d+)', line)
                    if incorrect_match:
                        incorrect_count = int(incorrect_match.group(1))
                elif line.startswith("Overall Accuracy:"):
                    import re
                    accuracy_match = re.search(r'(\d+\.?\d*)%', line)
                    if accuracy_match:
                        accuracy = float(accuracy_match.group(1))
                elif line.startswith("Expected Allow -> Got Deny:"):
                    import re
                    allow_deny_match = re.search(r'(\d+)', line)
                    if allow_deny_match:
                        misclassified_allow_to_deny = int(allow_deny_match.group(1))
                elif line.startswith("Expected Deny -> Got Allow:"):
                    import re
                    deny_allow_match = re.search(r'(\d+)', line)
                    if deny_allow_match:
                        misclassified_deny_to_allow = int(deny_allow_match.group(1))
        
        logging.info(f"Validation completed - Accuracy: {accuracy}%, Total: {total_requests}, Correct: {correct_count}, Incorrect: {incorrect_count}")
        
        # Clean up temporary files
        if os.path.exists(accuracy_output_path):
            os.unlink(accuracy_output_path)
        
        return {
            'accuracy': accuracy, 
            'total_requests': total_requests,
            'correct': correct_count,
            'incorrect': incorrect_count,
            'misclassified_allow_to_deny': misclassified_allow_to_deny,
            'misclassified_deny_to_allow': misclassified_deny_to_allow,
            'raw_output': accuracy_output_content,
            'output_file': accuracy_output_path
        }
        
    except subprocess.TimeoutExpired:
        try:
            os.chdir(original_dir)
        except:
            pass
        logging.error("SMT validator timed out")
        raise Exception("SMT validator timed out")
    except Exception as e:
        try:
            os.chdir(original_dir)
        except:
            pass
        logging.error(f"Error running SMT validator: {e}")
        raise

def run_smt_validator(policy_file: str, requests_file: str, policy_idx: int = None) -> dict:
    """Run SMT validator - robust accuracy parsing."""
    try:
        original_dir = os.getcwd()
        os.chdir(QUACKY_SRC_DIR)

        if policy_idx is not None:
            policy_specific_dir = os.path.join(OUTPUT_DIR, "Quacky_output", f"policy_{policy_idx:03d}")
            os.makedirs(policy_specific_dir, exist_ok=True)
            accuracy_output_path = os.path.join(policy_specific_dir, f"policy_{policy_idx:03d}_accuracy_validation.txt")
        else:
            quacky_output_dir = os.path.join(OUTPUT_DIR, "Quacky_output")
            os.makedirs(quacky_output_dir, exist_ok=True)
            timestamp = int(time.time())
            pid = os.getpid()
            accuracy_output_path = os.path.join(quacky_output_dir, f"temp_accuracy_{pid}_{timestamp}.txt")

        cmd_accuracy = [
            sys.executable, 'validate_requests.py',
            '-p1', policy_file,
            '--requests', requests_file,
            '-s'
        ]
        logging.debug(f"Running accuracy validation: {' '.join(cmd_accuracy)}")

        with open(accuracy_output_path, 'w') as output_file:
            result = subprocess.run(cmd_accuracy, stdout=output_file, stderr=subprocess.PIPE,
                                    text=True, timeout=300)

        if result.returncode != 0:
            logging.error(f"Accuracy validation failed: {result.stderr}")
            raise Exception(f"Accuracy validation failed: {result.stderr}")

        with open(accuracy_output_path, 'r') as f:
            accuracy_output_content = f.read()

        os.chdir(original_dir)

        # Default values
        accuracy = 0.0
        total_requests = correct_count = incorrect_count = 0
        misclassified_allow_to_deny = misclassified_deny_to_allow = 0

        in_analysis_section = False
        for line in accuracy_output_content.splitlines():
            line = line.strip()

            if "INDIVIDUAL REQUEST ANALYSIS" in line:
                in_analysis_section = True
                continue
            if not in_analysis_section:
                continue

            if line.startswith("Total Individual Requests:"):
                total_requests = int(re.search(r'(\d+)', line).group(1))
            elif line.startswith("Correct Classifications:"):
                correct_count = int(re.search(r'(\d+)', line).group(1))
            elif line.startswith("Incorrect Classifications:"):
                incorrect_count = int(re.search(r'(\d+)', line).group(1))
            elif line.startswith("Overall Accuracy:"):
                m = re.search(r'(\d+\.?\d*)\s*%', line)
                if m:
                    accuracy = float(m.group(1))
            elif line.startswith("Expected Allow -> Got Deny:"):
                misclassified_allow_to_deny = int(re.search(r'(\d+)', line).group(1))
            elif line.startswith("Expected Deny -> Got Allow:"):
                misclassified_deny_to_allow = int(re.search(r'(\d+)', line).group(1))

        # SMT timing
        smt_timing_data = parse_smt_timing_from_output(accuracy_output_content)
        
        # Debug if accuracy is zero
        if accuracy == 0.0 and total_requests > 0:
            logging.warning("⚠️ Accuracy parsed as 0. Dumping raw Quacky output for debugging.")
            dump_path = accuracy_output_path.replace("_accuracy_validation.txt", "_debug_dump.txt")
            with open(dump_path, 'w') as df:
                df.write(accuracy_output_content)
            logging.warning(f"Raw validator output dumped to {dump_path}")
        
        logging.info(f"Validation completed - Accuracy: {accuracy:.1f}%, "
                     f"Total: {total_requests}, Correct: {correct_count}, Incorrect: {incorrect_count}")
        logging.info(f"SMT Timing - Calls: {smt_timing_data['total_solver_calls']}, "
                     f"Total Time: {smt_timing_data['total_solver_time']:.3f}s, "
                     f"Avg: {smt_timing_data['average_call_time']:.4f}s")

        if os.path.exists(accuracy_output_path):
            os.unlink(accuracy_output_path)

        return {
            'accuracy': accuracy,
            'total_requests': total_requests,
            'correct': correct_count,
            'incorrect': incorrect_count,
            'misclassified_allow_to_deny': misclassified_allow_to_deny,
            'misclassified_deny_to_allow': misclassified_deny_to_allow,
            'raw_output': accuracy_output_content,
            'output_file': accuracy_output_path,
            'smt_timing': smt_timing_data,
            'total_solver_calls': smt_timing_data.get('total_solver_calls', 0),
            'total_solver_time': smt_timing_data.get('total_solver_time', 0.0),
            'average_solver_time': smt_timing_data.get('average_call_time', 0.0),
            'min_solver_time': smt_timing_data.get('min_call_time', 0.0),
            'max_solver_time': smt_timing_data.get('max_call_time', 0.0)
        }

    except subprocess.TimeoutExpired:
        os.chdir(original_dir)
        logging.error("SMT validator timed out")
        raise Exception("SMT validator timed out")
    except Exception as e:
        os.chdir(original_dir)
        logging.error(f"Error running SMT validator: {e}")
        raise

# def run_smt_validator(policy_file: str, requests_file: str, policy_idx: int = None) -> dict:
#     """Run SMT validator - get accuracy only"""
#     try:
#         original_dir = os.getcwd()
#         os.chdir(QUACKY_SRC_DIR)
        
#         # Create output directories
#         if policy_idx is not None:
#             policy_specific_dir = os.path.join(OUTPUT_DIR, "Quacky_output", f"policy_{policy_idx:03d}")
#             os.makedirs(policy_specific_dir, exist_ok=True)
            
#             # File paths for validation
#             accuracy_output_path = os.path.join(policy_specific_dir, f"policy_{policy_idx:03d}_accuracy_validation.txt")
#         else:
#             # Fallback naming
#             quacky_output_dir = os.path.join(OUTPUT_DIR, "Quacky_output")
#             os.makedirs(quacky_output_dir, exist_ok=True)
#             timestamp = int(time.time())
#             pid = os.getpid()
#             accuracy_output_path = os.path.join(quacky_output_dir, f"temp_accuracy_{pid}_{timestamp}.txt")
        
#         cmd_accuracy = [
#             'python', 'validate_requests.py',
#             '-p1', policy_file,
#             '--requests', requests_file,
#             '-s'
#         ]
        
#         logging.debug(f"Running accuracy validation: {' '.join(cmd_accuracy)}")
        
#         with open(accuracy_output_path, 'w') as output_file:
#             result = subprocess.run(cmd_accuracy, stdout=output_file, stderr=subprocess.PIPE, text=True, timeout=300)
        
#         if result.returncode != 0:
#             logging.error(f"Accuracy validation failed: {result.stderr}")
#             raise Exception(f"Accuracy validation failed: {result.stderr}")
        
#         with open(accuracy_output_path, 'r') as f:
#             accuracy_output_content = f.read()
        
#         os.chdir(original_dir)
        
#         accuracy_lines = accuracy_output_content.split('\n')
#         accuracy = 0.0
#         total_requests = 0
#         correct_count = 0
#         incorrect_count = 0
#         misclassified_allow_to_deny = 0
#         misclassified_deny_to_allow = 0
        
#         in_analysis_section = False
#         for i, line in enumerate(accuracy_lines):
#             line = line.strip()
            
#             if "INDIVIDUAL REQUEST ANALYSIS" in line:
#                 in_analysis_section = True
#                 continue
#             elif line.startswith("=") and in_analysis_section and len(line) > 10:
#                 if any(phrase in ''.join(accuracy_lines[i:i+5]) for phrase in ["Results saved", "saved to HOME"]):
#                     break
            
#             if in_analysis_section:
#                 if line.startswith("Total Individual Requests:"):
#                     import re
#                     total_match = re.search(r'(\d+)', line)
#                     if total_match:
#                         total_requests = int(total_match.group(1))
#                 elif line.startswith("Correct Classifications:"):
#                     import re
#                     correct_match = re.search(r'(\d+)', line)
#                     if correct_match:
#                         correct_count = int(correct_match.group(1))
#                 elif line.startswith("Incorrect Classifications:"):
#                     import re
#                     incorrect_match = re.search(r'(\d+)', line)
#                     if incorrect_match:
#                         incorrect_count = int(incorrect_match.group(1))
#                 elif line.startswith("Overall Accuracy:"):
#                     import re
#                     accuracy_match = re.search(r'(\d+\.?\d*)%', line)
#                     if accuracy_match:
#                         accuracy = float(accuracy_match.group(1))
#                 elif line.startswith("Expected Allow -> Got Deny:"):
#                     import re
#                     allow_deny_match = re.search(r'(\d+)', line)
#                     if allow_deny_match:
#                         misclassified_allow_to_deny = int(allow_deny_match.group(1))
#                 elif line.startswith("Expected Deny -> Got Allow:"):
#                     import re
#                     deny_allow_match = re.search(r'(\d+)', line)
#                     if deny_allow_match:
#                         misclassified_deny_to_allow = int(deny_allow_match.group(1))
        
#         # ===== PARSE SMT TIMING DATA =====
#         smt_timing_data = parse_smt_timing_from_output(accuracy_output_content)
        
#         logging.info(f"Validation completed - Accuracy: {accuracy}%, Total: {total_requests}, Correct: {correct_count}, Incorrect: {incorrect_count}")
#         logging.info(f"SMT Timing - Calls: {smt_timing_data['total_solver_calls']}, Total Time: {smt_timing_data['total_solver_time']:.3f}s, Avg: {smt_timing_data['average_call_time']:.4f}s")
        
#         # Clean up temporary files
#         if os.path.exists(accuracy_output_path):
#             os.unlink(accuracy_output_path)
        
#         return {
#             'accuracy': accuracy, 
#             'total_requests': total_requests,
#             'correct': correct_count,
#             'incorrect': incorrect_count,
#             'misclassified_allow_to_deny': misclassified_allow_to_deny,
#             'misclassified_deny_to_allow': misclassified_deny_to_allow,
#             'raw_output': accuracy_output_content,
#             'output_file': accuracy_output_path,
#             'smt_timing': smt_timing_data,
#             'total_solver_calls': smt_timing_data.get('total_solver_calls', 0),
#             'total_solver_time': smt_timing_data.get('total_solver_time', 0.0),
#             'average_solver_time': smt_timing_data.get('average_call_time', 0.0),
#             'min_solver_time': smt_timing_data.get('min_call_time', 0.0),
#             'max_solver_time': smt_timing_data.get('max_call_time', 0.0)
#         }
        
#     except subprocess.TimeoutExpired:
#         try:
#             os.chdir(original_dir)
#         except:
#             pass
#         logging.error("SMT validator timed out")
#         raise Exception("SMT validator timed out")
#     except Exception as e:
#         try:
#             os.chdir(original_dir)
#         except:
#             pass
#         logging.error(f"Error running SMT validator: {e}")
#         raise
def load_json_file(path: str) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json_file(data: dict, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def load_fault_localization_report(policy_idx: int, iteration: int, fault_localization_dir: str) -> str:
    """Load fault localization report text for a specific policy and iteration"""
    
    policy_iteration_dir = os.path.join(fault_localization_dir, f"policy_{policy_idx:03d}", f"iteration_{iteration}")
    main_report_file = os.path.join(policy_iteration_dir, "fault_localization_report.txt")
    
    logging.info(f"Looking for fault localization in: {main_report_file}")
    
    if os.path.exists(main_report_file):
        try:
            with open(main_report_file, 'r', encoding='utf-8') as f:
                report_text = f.read().strip()
            
            logging.info(f"Loaded fault localization report for policy {policy_idx} iteration {iteration}: {len(report_text)} characters")
            return report_text
        
        except Exception as e:
            logging.error(f"Error reading fault localization report {main_report_file}: {e}")
    
    # Fallback: try alternative locations and naming patterns
    possible_locations = [
        # Direct in fault_localization_dir with various naming patterns
        os.path.join(fault_localization_dir, f"policy_{policy_idx:03d}_iter_{iteration}_llm_report.txt"),
        os.path.join(fault_localization_dir, f"{policy_idx}_iter_{iteration}_llm_report.txt"),
        os.path.join(fault_localization_dir, f"policy_{policy_idx:03d}_llm_report.txt"), 
        os.path.join(fault_localization_dir, f"{policy_idx}_llm_report.txt"),
    ]
    
    for file_path in possible_locations:
        logging.info(f"Trying fallback location: {file_path}")
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    report_text = f.read().strip()
                
                logging.info(f"Loaded fault localization report from fallback location {file_path}: {len(report_text)} characters")
                return report_text
            
            except Exception as e:
                logging.error(f"Error reading fault localization report {file_path}: {e}")
                continue
    
    # If no file found, list what's actually in the directories for debugging
    logging.warning(f"No fault localization report found for policy {policy_idx} iteration {iteration}")
    
    # Debug: list contents of expected directory
    if os.path.exists(policy_iteration_dir):
        files = os.listdir(policy_iteration_dir)
        logging.info(f"Files in {policy_iteration_dir}: {files}")
    else:
        logging.info(f"Directory does not exist: {policy_iteration_dir}")
    
    # Debug: list contents of fault_localization_dir
    if os.path.exists(fault_localization_dir):
        files = os.listdir(fault_localization_dir)
        logging.info(f"Files in {fault_localization_dir}: {files}")
    else:
        logging.info(f"Fault localization directory does not exist: {fault_localization_dir}")
    
    return ""

def save_policy_for_fault_localization(policy: dict, policy_idx: int, iteration: int, temp_dir: str) -> str:
    """Save repaired policy for fault localization analysis"""
    policy_file = os.path.join(temp_dir, f"repaired_policy_{policy_idx}_iter_{iteration}.json")
    os.makedirs(temp_dir, exist_ok=True)
    
    with open(policy_file, 'w', encoding='utf-8') as f:
        json.dump(policy, f, indent=2)
    
    logging.info(f"Saved repaired policy for fault localization: {policy_file}")
    return policy_file

def run_fault_localization(policy_file: str, requests_file: str, policy_idx: int, iteration: int, fault_output_dir: str) -> str:
    """Run fault localization on a policy and return the LLM report path"""
    try:
        # Change to quacky source directory
        original_dir = os.getcwd()
        os.chdir(QUACKY_SRC_DIR)
        
        # Create fault localization output directory for this specific policy and iteration
        policy_iteration_dir = os.path.join(fault_output_dir, f"policy_{policy_idx:03d}", f"iteration_{iteration}")
        os.makedirs(policy_iteration_dir, exist_ok=True)
        
        # Create output name for this specific run - this will be the base name for the validator
        output_base = os.path.join(policy_iteration_dir, f"fault_analysis_{policy_idx:03d}_iter_{iteration}")
        
        # Correct command format as specified
        cmd = [
            sys.executable, 'validate_requests.py',
            '-p1', policy_file,
            '--requests', requests_file,
            '-s',
            '--identify-faulty',
            '--output', output_base
        ]
        
        logging.info(f"Running fault localization for policy {policy_idx} iteration {iteration}: {' '.join(cmd)}")
        
        # Run the fault localization and capture output
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        # Save the stdout and stderr for debugging
        stdout_file = os.path.join(policy_iteration_dir, f"stdout_{policy_idx:03d}_iter_{iteration}.txt")
        stderr_file = os.path.join(policy_iteration_dir, f"stderr_{policy_idx:03d}_iter_{iteration}.txt")
        
        with open(stdout_file, 'w') as f:
            f.write(result.stdout)
        
        with open(stderr_file, 'w') as f:
            f.write(result.stderr)
        
        if result.returncode != 0:
            logging.error(f"Fault localization failed for policy {policy_idx} iteration {iteration}")
            logging.error(f"Error output: {result.stderr}")
            return ""
        
        # The validator saves the LLM report to a hardcoded directory structure
        # Based on the validator code, it saves to: 
        base_filename = os.path.basename(output_base)
        validator_output_dir = Path(f"/home/bhall2/fixmypolicy/FL/Experiment-2/results/result-{req}-ollama/Quacky_output")
        expected_report_path = validator_output_dir / f"{base_filename}_llm_report.txt"
        
        # Target path for our organized structure
        target_report_path = os.path.join(policy_iteration_dir, f"fault_localization_report.txt")
        
        logging.info(f"Looking for LLM report at: {expected_report_path}")
        
        if os.path.exists(expected_report_path):
            # Copy the file to our standardized location
            shutil.copy2(expected_report_path, target_report_path)
            logging.info(f"Fault localization report saved to: {target_report_path}")
            
            return target_report_path
        else:
            logging.warning(f"Expected fault localization report not found at: {expected_report_path}")
            # List what files were actually created for debugging
            if os.path.exists(validator_output_dir):
                actual_files = os.listdir(validator_output_dir)
                logging.info(f"Files found in validator output dir {validator_output_dir}: {actual_files}")
                
                # Check if there are any *_llm_report.txt files
                llm_reports = [f for f in actual_files if f.endswith('_llm_report.txt')]
                if llm_reports:
                    logging.info(f"Found LLM report files: {llm_reports}")
                    # Try to use the first one found
                    alternative_report = os.path.join(validator_output_dir, llm_reports[0])
                    shutil.copy2(alternative_report, target_report_path)
                    logging.info(f"Used alternative LLM report: {alternative_report}")
                    return target_report_path
            
            return ""
        
    except subprocess.TimeoutExpired:
        logging.error("Fault localization timed out")
        return ""
    except Exception as e:
        logging.error(f"Error running fault localization: {e}")
        return ""
    finally:
        try:
            os.chdir(original_dir)
        except:
            pass

def process_policy_simple(idx: int, baseline_accuracy: float = 0.0) -> dict:
    """Process a single policy with validator-driven repair loop (always pre-generates FL for next iteration)."""
    cycle_start_time = time.time()

    policy_file = os.path.join(POLICY_DIR, f"{idx}.json")
    req_file = os.path.join(REQUIREMENTS_DIR, f"{idx}.json")

    if not os.path.exists(policy_file) or not os.path.exists(req_file):
        raise FileNotFoundError(f"Missing files for index {idx}")

    original_policy = load_json_file(policy_file)
    requirements = load_json_file(req_file)

    logging.info(f"Starting repair for policy {idx} (baseline: {baseline_accuracy:.1f}%)...")

    if baseline_accuracy >= TARGET_ACCURACY:
        final_output_file = os.path.join(OUTPUT_DIR, f"repaired_{idx}_already_perfect.json")
        save_json_file(original_policy, final_output_file)
        return {
            'index': idx,
            'status': 'already_perfect',
            'baseline_accuracy': baseline_accuracy,
            'final_accuracy': baseline_accuracy,
            'iterations_used': 0,
            'iteration_accuracies': [baseline_accuracy],
            'final_policy_file': final_output_file,
            'cycle_duration_seconds': 0,
            'cycle_duration_formatted': "00:00:00"
        }

    iteration_results = []
    current_policy = original_policy.copy()
    current_accuracy = baseline_accuracy
    final_accuracy = baseline_accuracy
    iteration_accuracies = [baseline_accuracy]

    for iteration in range(1, MAX_ITERATIONS + 1):
        iteration_start_time = time.time()
        logging.info(f"Policy {idx} - Iteration {iteration}/{MAX_ITERATIONS}")

        try:
            fault_localization_report = load_fault_localization_report(idx, iteration, FAULT_LOCALIZATION_DIR)

            #LLM Repair
            repaired_policy = repair_policy_simple(
                current_policy, requirements, fault_localization_report, iteration, policy_idx=idx)
        

            temp_policy_file = os.path.join(TEMP_DIR, f"policy_{idx}_iter_{iteration}.json")
            save_json_file(repaired_policy, temp_policy_file)

            validation_results = run_smt_validator(temp_policy_file, req_file, policy_idx=idx)
            accuracy = validation_results['accuracy']
            iteration_accuracies.append(accuracy)
            final_accuracy = accuracy

            iteration_results.append({
                'policy_idx': idx,
                'iteration': iteration,
                'accuracy': accuracy,
                'baseline_accuracy': baseline_accuracy,
                'total_requests': validation_results['total_requests'],
                'correct': validation_results['correct'],
                'incorrect': validation_results['incorrect'],
                'misclassified_allow_to_deny': validation_results['misclassified_allow_to_deny'],
                'misclassified_deny_to_allow': validation_results['misclassified_deny_to_allow'],
                'policy_file': temp_policy_file,
                'iteration_duration_seconds': time.time() - iteration_start_time,
                'total_solver_calls': validation_results.get('total_solver_calls', 0),
                'total_solver_time': validation_results.get('total_solver_time', 0.0),
                'average_solver_time': validation_results.get('average_solver_time', 0.0),
                'min_solver_time': validation_results.get('min_solver_time', 0.0),
                'max_solver_time': validation_results.get('max_solver_time', 0.0)
            })

            if accuracy >= TARGET_ACCURACY:
                final_output_file = os.path.join(OUTPUT_DIR, f"repaired_{idx}_final.json")
                save_json_file(repaired_policy, final_output_file)
                cycle_time = time.time() - cycle_start_time
                return {
                    'index': idx,
                    'status': 'success',
                    'baseline_accuracy': baseline_accuracy,
                    'final_accuracy': accuracy,
                    'iterations_used': iteration,
                    'iteration_accuracies': iteration_accuracies,
                    'iteration_results': iteration_results,
                    'final_policy_file': final_output_file,
                    'cycle_duration_seconds': cycle_time,
                    'cycle_duration_formatted': str(timedelta(seconds=int(cycle_time)))
                }

            failing_subset = extract_failing_requests(validation_results['raw_output'],
                                                     load_json_file(req_file))
            if failing_subset["Requests"]:
                logging.info(f"Iteration {iteration}: {len(failing_subset['Requests'])} failing requests found")
                requirements = failing_subset

            if iteration < MAX_ITERATIONS:
                logging.info(f"Pre-generating fault localization for next iteration {iteration+1}...")
                fl_policy_file = save_policy_for_fault_localization(repaired_policy, idx, iteration, TEMP_DIR)
                run_fault_localization(fl_policy_file, req_file, idx, iteration+1, FAULT_LOCALIZATION_DIR)

            if current_accuracy <= accuracy:
                
                current_policy = repaired_policy.copy()
                current_accuracy = accuracy

        except Exception as e:
            logging.error(f"Iteration {iteration} failed for policy {idx}: {e}")

    #End of loop (failed case)
    cycle_time = time.time() - cycle_start_time
    best_iter = max(iteration_results, key=lambda r: r['accuracy'], default=None)
    if best_iter:
        best_file = best_iter['policy_file']
        final_output_file = os.path.join(OUTPUT_DIR, f"repaired_{idx}_best.json")
        if best_file and os.path.exists(best_file):
            shutil.copy2(best_file, final_output_file)
        else:
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
        'iteration_accuracies': iteration_accuracies,
        'iteration_results': iteration_results,
        'final_policy_file': final_output_file,
        'cycle_duration_seconds': cycle_time,
        'cycle_duration_formatted': str(timedelta(seconds=int(cycle_time)))
    }

class SimpleProgressTracker:
    """Progress tracker for simple policy repair"""
    def __init__(self, progress_file: str = os.path.join(OUTPUT_DIR, "simple_repair_progress.json")):
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
            "policy_iterations": {},
            "baseline_completed": [],
            "baseline_accuracies": {}
        }
    
    def save_progress(self):
        os.makedirs(os.path.dirname(self.progress_file), exist_ok=True)
        with open(self.progress_file, 'w') as f:
            json.dump(self.progress, f, indent=2)
    
    def mark_baseline_completed(self, idx, baseline_accuracy=None):
        if idx not in self.progress["baseline_completed"]:
            self.progress["baseline_completed"].append(idx)
        
        if baseline_accuracy is not None:
            self.progress["baseline_accuracies"][str(idx)] = baseline_accuracy
            
        self.save_progress()
    
    def get_baseline_accuracy(self, idx):
        return self.progress["baseline_accuracies"].get(str(idx), 0.0)
    
    def is_baseline_done(self, idx):
        return idx in self.progress.get("baseline_completed", [])
    
    def mark_completed(self, idx, baseline_accuracy, final_accuracy, iterations_used, iteration_accuracies, cycle_duration=0.0):
        self.progress["last_processed"] = idx
        if idx not in self.progress["completed"]:
            self.progress["completed"].append(idx)
        if idx in self.progress["failed"]:
            self.progress["failed"].remove(idx)
        
        self.progress["baseline_accuracies"][str(idx)] = baseline_accuracy
        
        # Calculate average accuracy across repair iterations only (excluding baseline)
        repair_accuracies = iteration_accuracies[1:] if len(iteration_accuracies) > 1 else []
        average_accuracy = sum(repair_accuracies) / len(repair_accuracies) if repair_accuracies else final_accuracy
        
        self.progress["policy_iterations"][str(idx)] = {
            "status": "completed",
            "baseline_accuracy": baseline_accuracy,
            "final_accuracy": final_accuracy,
            "improvement": final_accuracy - baseline_accuracy,
            "iterations_used": iterations_used,
            "iteration_accuracies": iteration_accuracies,
            "average_accuracy": average_accuracy,
            "cycle_duration_seconds": cycle_duration,
            "cycle_duration_formatted": str(timedelta(seconds=int(cycle_duration))) if cycle_duration > 0 else "00:00:00"
        }
        self.save_progress()
    
    def mark_failed(self, idx, baseline_accuracy, final_accuracy, iterations_used, iteration_accuracies, cycle_duration=0.0):
        if idx not in self.progress["failed"]:
            self.progress["failed"].append(idx)
        
        self.progress["baseline_accuracies"][str(idx)] = baseline_accuracy
        
        # Calculate average accuracy across repair iterations only (excluding baseline)
        repair_accuracies = iteration_accuracies[1:] if len(iteration_accuracies) > 1 else []
        average_accuracy = sum(repair_accuracies) / len(repair_accuracies) if repair_accuracies else final_accuracy
        
        self.progress["policy_iterations"][str(idx)] = {
            "status": "failed",
            "baseline_accuracy": baseline_accuracy,
            "final_accuracy": final_accuracy,
            "improvement": final_accuracy - baseline_accuracy,
            "iterations_used": iterations_used,
            "iteration_accuracies": iteration_accuracies,
            "average_accuracy": average_accuracy,
            "cycle_duration_seconds": cycle_duration,
            "cycle_duration_formatted": str(timedelta(seconds=int(cycle_duration))) if cycle_duration > 0 else "00:00:00"
        }
        self.save_progress()
    
    def get_next(self):
        return self.progress.get("last_processed", -1) + 1
    
    def is_done(self, idx):
        return idx in self.progress.get("completed", [])

def test_ollama_connection():
    """Test if Ollama is running and the model is available"""
    try:
        test_response = call_ollama("Test", "Respond with only 'OK'")
        if not test_response:
            return False, "Model test failed - empty response"
        
        return True, f"Ollama connection successful with model {OLLAMA_MODEL}"
        
    except Exception as e:
        return False, f"Ollama connection error: {e}. Make sure Ollama is running and model '{OLLAMA_MODEL}' is installed."

def run_baseline_validation(idx: int) -> dict:
    """Run baseline validation on the original policy"""
    policy_file = os.path.join(POLICY_DIR, f"{idx}.json")
    req_file = os.path.join(REQUIREMENTS_DIR, f"{idx}.json")
    
    if not os.path.exists(policy_file) or not os.path.exists(req_file):
        raise FileNotFoundError(f"Missing files for index {idx}")
    
    logging.info(f"Running baseline validation for policy {idx}...")
    
    try:
        validation_results = run_smt_validator(policy_file, req_file, policy_idx=idx)
        
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

def run_baseline_validation(idx: int) -> dict:
    """Run baseline validation on the original policy"""
    policy_file = os.path.join(POLICY_DIR, f"{idx}.json")
    req_file = os.path.join(REQUIREMENTS_DIR, f"{idx}.json")
    
    if not os.path.exists(policy_file) or not os.path.exists(req_file):
        raise FileNotFoundError(f"Missing files for index {idx}")
    
    logging.info(f"Running baseline validation for policy {idx}...")
    
    try:
        validation_results = run_smt_validator(policy_file, req_file, policy_idx=idx)
        
        baseline_result = {
            'policy_idx': idx,
            'validation_type': 'baseline',
            'accuracy': validation_results['accuracy'],
            'total_requests': validation_results['total_requests'],
            'correct': validation_results['correct'],
            'incorrect': validation_results['incorrect'],
            'misclassified_allow_to_deny': validation_results['misclassified_allow_to_deny'],
            'misclassified_deny_to_allow': validation_results['misclassified_deny_to_allow'],
            'output_file': validation_results['output_file'],
            'total_solver_calls': validation_results.get('total_solver_calls', 0),
            'total_solver_time': validation_results.get('total_solver_time', 0.0),
            'average_solver_time': validation_results.get('average_solver_time', 0.0),
            'min_solver_time': validation_results.get('min_solver_time', 0.0),
            'max_solver_time': validation_results.get('max_solver_time', 0.0)
        }
        
        logging.info(f"Baseline validation for policy {idx}: {validation_results['accuracy']:.1f}% accuracy, {validation_results['total_solver_calls']} solver calls")
        
        return baseline_result
        
    except Exception as e:
        logging.error(f"Baseline validation failed for policy {idx}: {e}")
        return {
            'policy_idx': idx,
            'validation_type': 'baseline',
            'accuracy': 0.0,
            'total_solver_calls': 0,
            'total_solver_time': 0.0,
            'average_solver_time': 0.0,
            'min_solver_time': 0.0,
            'max_solver_time': 0.0,
            'error': str(e)
        }
        
# def main():
#     """Main function - Simple guided repair"""
#     log_file = setup_logging()
#     logging.info("Starting simple guided policy repair system")
    
#     print("=" * 60)
#     print("Simple Guided Policy Repair System")
#     print("=" * 60)
    
#     # # Test Ollama connection first
#     # print("Testing Ollama connection...")
#     # ollama_ok, ollama_msg = test_ollama_connection()
#     # if not ollama_ok:
#     #     logging.error(f"Ollama connection failed: {ollama_msg}")
#     #     print(f"Ollama connection failed: {ollama_msg}")
#     #     print("\nPlease ensure:")
#     #     print("1. Ollama is running (ollama serve)")
#     #     print(f"2. Model '{OLLAMA_MODEL}' is installed (ollama pull {OLLAMA_MODEL})")
#     #     print("3. Ollama is accessible")
#     #     sys.exit(1)
    
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
#     for directory in [OUTPUT_DIR, TEMP_DIR, FAULT_LOCALIZATION_DIR, os.path.join(OUTPUT_DIR, "Quacky_output")]:
#         os.makedirs(directory, exist_ok=True)
    
#     # Initialize progress tracker
#     tracker = SimpleProgressTracker()
#     total = TOTAL_POLICIES
    
#     # Step 1: Run baseline validation for all policies
#     print("\n" + "=" * 60)
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
                
#                 baseline_accuracy = baseline_result.get('accuracy', 0.0)
#                 tracker.mark_baseline_completed(idx, baseline_accuracy)
                
#                 if 'error' not in baseline_result:
#                     logging.info(f"Policy {idx} baseline: {baseline_accuracy:.1f}% accuracy")
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
#                 tracker.mark_baseline_completed(idx, 0.0)
#     else:
#         logging.info("All baseline validations already completed. Loading existing results...")
#         for i in range(total):
#             baseline_accuracy = tracker.get_baseline_accuracy(i)
#             baseline_results.append({
#                 'policy_idx': i,
#                 'validation_type': 'baseline',
#                 'accuracy': baseline_accuracy
#             })
    
#     # Save baseline results
#     if baseline_results:
#         baseline_csv = os.path.join(OUTPUT_DIR, "baseline_results_simple.csv")
#         baseline_df = pd.DataFrame(baseline_results)
#         baseline_df.to_csv(baseline_csv, index=False)
#         logging.info(f"Baseline results saved to {baseline_csv}")
    
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
    
#     # Step 2: Simple guided repair
#     print("\nSTEP 2: SIMPLE GUIDED REPAIR")
#     print("=" * 60)
    
#     baseline_accuracy_map = {r['policy_idx']: r.get('accuracy', 0.0) for r in baseline_results}
    
#     to_process = [i for i in range(total) if not tracker.is_done(i)]
#     logging.info(f"Policies to process for simple repair: {to_process}")
    
#     all_results = []
#     all_iteration_data = baseline_results.copy()
    
#     # Process each policy with simple repair
#     for idx in tqdm(to_process, desc="Processing policies with simple repair"):
#         try:
#             baseline_acc = baseline_accuracy_map.get(idx, 0.0)
            
#             # Generate initial fault localization for iteration 1 using the ORIGINAL policy
#             logging.info(f"Generating initial fault localization for policy {idx}...")
#             original_policy_file = os.path.join(POLICY_DIR, f"{idx}.json")
#             requests_file = os.path.join(REQUIREMENTS_DIR, f"{idx}.json")
            
#             initial_fl_path = run_fault_localization(
#                 original_policy_file, 
#                 requests_file, 
#                 idx, 1, FAULT_LOCALIZATION_DIR
#             )
            
#             if initial_fl_path:
#                 logging.info(f"Generated initial fault localization: {initial_fl_path}")
#             else:
#                 logging.warning(f"Failed to generate initial fault localization for policy {idx}")
#                 # Create an empty report so the process can continue
#                 policy_iteration_dir = os.path.join(FAULT_LOCALIZATION_DIR, f"policy_{idx:03d}", f"iteration_1")
#                 os.makedirs(policy_iteration_dir, exist_ok=True)
#                 empty_report_path = os.path.join(policy_iteration_dir, f"fault_localization_report.txt")
#                 with open(empty_report_path, 'w') as f:
#                     f.write("No fault localization report available for this iteration.\n")
#                 logging.info(f"Created empty fault localization report: {empty_report_path}")
            
#             # Now run the actual repair process
#             result = process_policy_simple(idx, baseline_acc)
#             logging.info(f"Policy {idx} completed:")
#             logging.info(f"  Status: {result['status']}")
#             logging.info(f"  Baseline: {result['baseline_accuracy']:.1f}%")
#             logging.info(f"  Final: {result['final_accuracy']:.1f}%")
#             logging.info(f"  Iterations: {result['iterations_used']}")
#             logging.info(f"  Iteration accuracies: {result['iteration_accuracies']}")
            
#             # Track completion/failure
#             if result['status'] in ['success', 'already_perfect']:
#                 tracker.mark_completed(
#                     idx, 
#                     result['baseline_accuracy'], 
#                     result['final_accuracy'], 
#                     result['iterations_used'], 
#                     result['iteration_accuracies'],
#                     result.get('cycle_duration_seconds', 0.0)
#                 )
#             else:
#                 tracker.mark_failed(
#                     idx, 
#                     result['baseline_accuracy'], 
#                     result['final_accuracy'], 
#                     result['iterations_used'], 
#                     result.get('iteration_accuracies', []),
#                     result.get('cycle_duration_seconds', 0.0)
#                 )
            
#             all_results.append(result)
            
#             # Collect iteration data
#             for iter_data in result['iteration_results']:
#                 all_iteration_data.append(iter_data)
            
#         except Exception as e:
#             logging.error(f"Policy {idx} failed completely: {e}")
#             baseline_acc = baseline_accuracy_map.get(idx, 0.0)
#             tracker.mark_failed(idx, baseline_acc, 0.0, 0, [])
#             all_results.append({
#                 'index': idx,
#                 'status': 'error',
#                 'baseline_accuracy': baseline_acc,
#                 'final_accuracy': 0.0,
#                 'improvement_from_baseline': 0.0,
#                 'iterations_used': 0,
#                 'iteration_accuracies': [],
#                 'error': str(e)
#             })
    
#     # Save comprehensive results
    
#     # Summary results
#     if all_results:
#         df_summary = pd.DataFrame(all_results)
#         summary_csv = os.path.join(OUTPUT_DIR, "simple_repair_summary.csv")
#         df_summary.to_csv(summary_csv, index=False)
#         logging.info(f"Summary results saved to {summary_csv}")
    
#     # Detailed iteration results
#     if all_iteration_data:
#         df_iterations = pd.DataFrame(all_iteration_data)
#         iterations_csv = os.path.join(OUTPUT_DIR, "simple_repair_details.csv")
#         df_iterations.to_csv(iterations_csv, index=False)
#         logging.info(f"Detailed iteration results saved to {iterations_csv}")
    
#     # Final summary
#     successful = len([r for r in all_results if r.get('status') in ['success', 'already_perfect']])
#     already_perfect = len([r for r in all_results if r.get('status') == 'already_perfect'])
#     improved = len([r for r in all_results if r.get('status') == 'success'])
#     failed = len([r for r in all_results if r.get('status') in ['failed', 'error']])
    
#     if all_results:
#         avg_baseline = sum(r.get('baseline_accuracy', 0) for r in all_results) / len(all_results)
#         avg_final = sum(r.get('final_accuracy', 0) for r in all_results) / len(all_results)
#         avg_improvement = avg_final - avg_baseline
#         total_iterations = sum(r.get('iterations_used', 0) for r in all_results)
        
#         baseline_perfect = len([r for r in all_results if r.get('baseline_accuracy', 0) >= TARGET_ACCURACY])
#         final_perfect = len([r for r in all_results if r.get('final_accuracy', 0) >= TARGET_ACCURACY])
#         improvement_count = final_perfect - baseline_perfect
#          # Baseline SMT stats
#         baseline_solver_calls = sum(r.get('total_solver_calls', 0) for r in baseline_results if 'error' not in r)
#         baseline_solver_time = sum(r.get('total_solver_time', 0.0) for r in baseline_results if 'error' not in r)
        
#         # Repair iteration SMT stats  
#         repair_solver_calls = sum(r.get('total_solver_calls', 0) for r in all_iteration_data if r.get('validation_type') == 'simple_repair')
#         repair_solver_time = sum(r.get('total_solver_time', 0.0) for r in all_iteration_data if r.get('validation_type') == 'simple_repair')
        
#         total_solver_calls = baseline_solver_calls + repair_solver_calls
#         total_solver_time = baseline_solver_time + repair_solver_time
#         avg_solver_time_per_call = total_solver_time / total_solver_calls if total_solver_calls > 0 else 0
#     else:
#         avg_baseline = avg_final = avg_improvement = total_iterations = improvement_count = 0
#         baseline_perfect = final_perfect = 0
#         baseline_solver_calls = repair_solver_calls = total_solver_calls = 0
#         baseline_solver_time = repair_solver_time = total_solver_time = avg_solver_time_per_call = 0.0
    
    
#     # Print final summary to console
#     print(f"\n{'='*60}")
#     print("SIMPLE GUIDED REPAIR - FINAL SUMMARY")
#     print(f"{'='*60}")
#     print(f"Total policies processed: {len(all_results)}")
#     print(f"Model used: {OLLAMA_MODEL}")
#     print(f"")
#     print(f"BASELINE PERFORMANCE:")
#     print(f"  Average baseline accuracy: {avg_baseline:.1f}%")
#     print(f"  Policies at target (baseline): {baseline_perfect}")
#     print(f"")
#     print(f"FINAL PERFORMANCE:")
#     print(f"  Successfully repaired to 100%: {improved}")
#     print(f"  Already perfect (no repair needed): {already_perfect}")
#     print(f"  Failed to reach 100%: {failed}")
#     print(f"  Average final accuracy: {avg_final:.1f}%")
#     print(f"  Policies at target (final): {final_perfect}")
#     print(f"")
#     print(f"IMPROVEMENT:")
#     print(f"  Net improvement: +{improvement_count} policies reaching 100%")
#     print(f"  Accuracy improvement: {avg_improvement:.1f} percentage points")
#     print(f"  Total iterations used: {total_iterations}")
#     print(f"  Average iterations per policy: {total_iterations/len(all_results):.1f}" if all_results else "0")
    
#     # Show detailed results
#     print(f"\nDETAILED RESULTS:")
#     for result in all_results:
#         idx = result['index']
#         baseline = result.get('baseline_accuracy', 0)
#         final = result.get('final_accuracy', 0)
#         status = result.get('status', 'unknown')
#         iterations = result.get('iterations_used', 0)
#         improvement = result.get('improvement_from_baseline', 0)
        
#         if status == 'already_perfect':
#             print(f"  Policy {idx}: {baseline:.1f}% -> {final:.1f}% (already perfect)")
#         elif status == 'success':
#             print(f"  Policy {idx}: {baseline:.1f}% -> {final:.1f}% (SUCCESS in {iterations} iterations, +{improvement:.1f}%)")
#         elif status == 'failed':
#             print(f"  Policy {idx}: {baseline:.1f}% -> {final:.1f}% (failed after {iterations} iterations, +{improvement:.1f}%)")
#         else:
#             print(f"  Policy {idx}: {baseline:.1f}% -> {final:.1f}% (ERROR: {result.get('error', 'unknown')})")

#     print(f"{'='*60}")
#     print("Results files:")
#     print(f"  - Baseline: baseline_results_simple.csv")
#     print(f"  - Summary: simple_repair_summary.csv")
#     print(f"  - Detailed iterations: simple_repair_details.csv")
#     print(f"  - Progress tracker: {tracker.progress_file}")
#     print(f"{'='*60}")
#     print("\nKEY APPROACH:")
#     print("- Simple repair using three inputs: requirements, fault localization output, and original policy")
#     print("- Iterative fault localization generated per iteration")
#     print("- Clean and straightforward repair methodology")

#     # Cleanup
#     if os.path.exists(TEMP_DIR):
#         logging.info(f"Temporary files kept for analysis in: {TEMP_DIR}")
        
def main():
    """Main function - Simple guided repair"""
    log_file = setup_logging()
    logging.info("Starting simple guided policy repair system")
    
    print("=" * 60)
    print("Simple Guided Policy Repair System")
    print("=" * 60)
    
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
    for directory in [OUTPUT_DIR, TEMP_DIR, FAULT_LOCALIZATION_DIR, os.path.join(OUTPUT_DIR, "Quacky_output")]:
        os.makedirs(directory, exist_ok=True)
    
    # Initialize progress tracker
    tracker = SimpleProgressTracker()
    total = TOTAL_POLICIES
    
    # Step 1: Run baseline validation for all policies
    print("\n" + "=" * 60)
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
                
                baseline_accuracy = baseline_result.get('accuracy', 0.0)
                tracker.mark_baseline_completed(idx, baseline_accuracy)
                
                if 'error' not in baseline_result:
                    logging.info(f"Policy {idx} baseline: {baseline_accuracy:.1f}% accuracy")
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
                tracker.mark_baseline_completed(idx, 0.0)
    else:
        logging.info("All baseline validations already completed. Loading existing results...")
        for i in range(total):
            baseline_accuracy = tracker.get_baseline_accuracy(i)
            baseline_results.append({
                'policy_idx': i,
                'validation_type': 'baseline',
                'accuracy': baseline_accuracy
            })
    
    # Save baseline results
    if baseline_results:
        baseline_csv = os.path.join(OUTPUT_DIR, "baseline_results_simple.csv")
        baseline_df = pd.DataFrame(baseline_results)
        baseline_df.to_csv(baseline_csv, index=False)
        logging.info(f"Baseline results saved to {baseline_csv}")
    
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
    
    # Step 2: Simple guided repair
    print("\nSTEP 2: SIMPLE GUIDED REPAIR")
    print("=" * 60)
    
    baseline_accuracy_map = {r['policy_idx']: r.get('accuracy', 0.0) for r in baseline_results}
    
    to_process = [i for i in range(total) if not tracker.is_done(i)]
    logging.info(f"Policies to process for simple repair: {to_process}")
    
    all_results = []
    all_iteration_data = baseline_results.copy()
    
    # Process each policy with simple repair
    for idx in tqdm(to_process, desc="Processing policies with simple repair"):
        baseline_acc = baseline_accuracy_map.get(idx, 0.0)
        
        # Step A: Generate initial fault localization (separate try-except)
        try:
            logging.info(f"Generating initial fault localization for policy {idx}...")
            original_policy_file = os.path.join(POLICY_DIR, f"{idx}.json")
            requests_file = os.path.join(REQUIREMENTS_DIR, f"{idx}.json")
            
            initial_fl_path = run_fault_localization(
                original_policy_file, 
                requests_file, 
                idx, 1, FAULT_LOCALIZATION_DIR
            )
            
            if initial_fl_path:
                logging.info(f"Generated initial fault localization: {initial_fl_path}")
            else:
                logging.warning(f"Failed to generate initial fault localization for policy {idx}")
                policy_iteration_dir = os.path.join(FAULT_LOCALIZATION_DIR, f"policy_{idx:03d}", f"iteration_1")
                os.makedirs(policy_iteration_dir, exist_ok=True)
                empty_report_path = os.path.join(policy_iteration_dir, f"fault_localization_report.txt")
                with open(empty_report_path, 'w') as f:
                    f.write("No fault localization report available for this iteration.\n")
                logging.info(f"Created empty fault localization report: {empty_report_path}")
        
        except Exception as fl_error:
            logging.error(f"Initial fault localization failed for policy {idx}: {fl_error}")
            # Create empty report and continue
            policy_iteration_dir = os.path.join(FAULT_LOCALIZATION_DIR, f"policy_{idx:03d}", f"iteration_1")
            os.makedirs(policy_iteration_dir, exist_ok=True)
            empty_report_path = os.path.join(policy_iteration_dir, f"fault_localization_report.txt")
            with open(empty_report_path, 'w') as f:
                f.write("No fault localization report available for this iteration.\n")
        
        # Step B & C: Process policy and save results (separate try-except)
        try:
            result = process_policy_simple(idx, baseline_acc)
            
            logging.info(f"Policy {idx} completed: status={result['status']}, final_accuracy={result['final_accuracy']:.1f}%")
            
            # Track completion/failure
            if result['status'] in ['success', 'already_perfect']:
                tracker.mark_completed(
                    idx, 
                    result['baseline_accuracy'], 
                    result['final_accuracy'], 
                    result['iterations_used'], 
                    result['iteration_accuracies'],
                    result.get('cycle_duration_seconds', 0.0)
                )
            else:
                tracker.mark_failed(
                    idx, 
                    result['baseline_accuracy'], 
                    result['final_accuracy'], 
                    result['iterations_used'], 
                    result.get('iteration_accuracies', []),
                    result.get('cycle_duration_seconds', 0.0)
                )
            
            all_results.append(result)
            
            # Collect iteration data
            for iter_data in result['iteration_results']:
                all_iteration_data.append(iter_data)
            
        except Exception as e:
            logging.error(f"Policy {idx} processing failed: {e}", exc_info=True)
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
    
    # Summary results
    if all_results:
        df_summary = pd.DataFrame(all_results)
        summary_csv = os.path.join(OUTPUT_DIR, "simple_repair_summary.csv")
        df_summary.to_csv(summary_csv, index=False)
        logging.info(f"Summary results saved to {summary_csv}")
    
    # Detailed iteration results
    if all_iteration_data:
        df_iterations = pd.DataFrame(all_iteration_data)
        iterations_csv = os.path.join(OUTPUT_DIR, "simple_repair_details.csv")
        df_iterations.to_csv(iterations_csv, index=False)
        logging.info(f"Detailed iteration results saved to {iterations_csv}")
    
    # Final summary
    successful = len([r for r in all_results if r.get('status') in ['success', 'already_perfect']])
    already_perfect = len([r for r in all_results if r.get('status') == 'already_perfect'])
    improved = len([r for r in all_results if r.get('status') == 'success'])
    failed = len([r for r in all_results if r.get('status') in ['failed', 'error']])
    
    if all_results:
        avg_baseline = sum(r.get('baseline_accuracy', 0) for r in all_results) / len(all_results)
        avg_final = sum(r.get('final_accuracy', 0) for r in all_results) / len(all_results)
        avg_improvement = avg_final - avg_baseline
        total_iterations = sum(r.get('iterations_used', 0) for r in all_results)
        
        baseline_perfect = len([r for r in all_results if r.get('baseline_accuracy', 0) >= TARGET_ACCURACY])
        final_perfect = len([r for r in all_results if r.get('final_accuracy', 0) >= TARGET_ACCURACY])
        improvement_count = final_perfect - baseline_perfect
        baseline_solver_calls = sum(r.get('total_solver_calls', 0) for r in baseline_results if 'error' not in r)
        baseline_solver_time = sum(r.get('total_solver_time', 0.0) for r in baseline_results if 'error' not in r)
        
        repair_solver_calls = sum(r.get('total_solver_calls', 0) for r in all_iteration_data if r.get('validation_type') == 'simple_repair')
        repair_solver_time = sum(r.get('total_solver_time', 0.0) for r in all_iteration_data if r.get('validation_type') == 'simple_repair')
        
        total_solver_calls = baseline_solver_calls + repair_solver_calls
        total_solver_time = baseline_solver_time + repair_solver_time
        avg_solver_time_per_call = total_solver_time / total_solver_calls if total_solver_calls > 0 else 0
    else:
        avg_baseline = avg_final = avg_improvement = total_iterations = improvement_count = 0
        baseline_perfect = final_perfect = 0
        baseline_solver_calls = repair_solver_calls = total_solver_calls = 0
        baseline_solver_time = repair_solver_time = total_solver_time = avg_solver_time_per_call = 0.0
    
    
    # Print final summary to console
    print(f"\n{'='*60}")
    print("SIMPLE GUIDED REPAIR - FINAL SUMMARY")
    print(f"{'='*60}")
    print(f"Total policies processed: {len(all_results)}")
    print(f"Model used: {OLLAMA_MODEL}")
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
    
    # Show detailed results
    print(f"\nDETAILED RESULTS:")
    for result in all_results:
        idx = result['index']
        baseline = result.get('baseline_accuracy', 0)
        final = result.get('final_accuracy', 0)
        status = result.get('status', 'unknown')
        iterations = result.get('iterations_used', 0)
        improvement = result.get('improvement_from_baseline', 0)
        
        if status == 'already_perfect':
            print(f"  Policy {idx}: {baseline:.1f}% -> {final:.1f}% (already perfect)")
        elif status == 'success':
            print(f"  Policy {idx}: {baseline:.1f}% -> {final:.1f}% (SUCCESS in {iterations} iterations, +{improvement:.1f}%)")
        elif status == 'failed':
            print(f"  Policy {idx}: {baseline:.1f}% -> {final:.1f}% (failed after {iterations} iterations, +{improvement:.1f}%)")
        else:
            print(f"  Policy {idx}: {baseline:.1f}% -> {final:.1f}% (ERROR: {result.get('error', 'unknown')})")

    print(f"{'='*60}")
    print("Results files:")
    print(f"  - Baseline: baseline_results_simple.csv")
    print(f"  - Summary: simple_repair_summary.csv")
    print(f"  - Detailed iterations: simple_repair_details.csv")
    print(f"  - Progress tracker: {tracker.progress_file}")
    print(f"{'='*60}")
    print("\nKEY APPROACH:")
    print("- Simple repair using three inputs: requirements, fault localization output, and original policy")
    print("- Iterative fault localization generated per iteration")
    print("- Clean and straightforward repair methodology")

    # Cleanup
    if os.path.exists(TEMP_DIR):
        logging.info(f"Temporary files kept for analysis in: {TEMP_DIR}")

if __name__ == "__main__":
    main()


