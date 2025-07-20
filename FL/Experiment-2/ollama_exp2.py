
# """
# improved_iterative_policy_repair.py
# Enhanced counter-example guided policy repair that better utilizes SMT validator feedback.
# Key improvements:
# 1. Structured analysis of failed examples
# 2. Targeted repair prompts based on failure patterns
# 3. Better understanding of allow vs deny misclassifications
# 4. More precise requirement extraction and mapping


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
from ollama import chat, ChatResponse 

POLICY_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-2/original_policy"
REQUIREMENTS_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-2/requests/request-25"
OUTPUT_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-2/results/result-25-ollama/"
LOG_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-2/logs/log-25-ollama"
TEMP_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-2/temp_validation/val-25-ollama"
QUACKY_SRC_DIR = "/home/bhall2/Documents/fixmypolicy/quacky/src"
SMT_VALIDATOR_SCRIPT = "/home/bhall2/Documents/fixmypolicy/quacky/src/validate_requests.py"

MAX_ITERATIONS = 5
MAX_ATTEMPT = 3
DELAY = 5
TARGET_ACCURACY = 100.0
OLLAMA_MODEL = "codellama:13b"

def setup_logging(log_dir: str = LOG_DIR):  
    """Configure logging"""
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f'improved_policy_repair_{OLLAMA_MODEL}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler() 
        ]
    )
    return log_file
    
def call_ollama(prompt, system_prompt=""):
    """Call Ollama using the official Python client"""
    try:
        messages = []
        
        if system_prompt:
            messages.append({
                'role': 'system',
                'content': system_prompt
            })
        
        messages.append({
            'role': 'user',
            'content': prompt
        })
        
        response: ChatResponse = chat(
            model=OLLAMA_MODEL,
            messages=messages,
            options={
                'temperature': 0.1,
                'top_p': 0.9,
                'num_predict': 10000,
                'stop': ['\n```', '```\n'],
            }
        )
        
        return response.message.content
        
    except Exception as e:
        raise Exception(f"Ollama chat error: {e}")

def analyze_failed_examples(failed_examples, requirements_dict):
    """
    Analyze failed examples to understand patterns and create targeted repair guidance.
    """
    analysis = {
        'allow_to_deny_failures': [],  
        'deny_to_allow_failures': [], 
        'missing_allow_statements': [],
        'incorrect_deny_statements': [],
        'resource_mismatches': [],
        'action_mismatches': [],
        'condition_issues': [],
        'principal_issues': []
    }
    
    # Extract requirements for easier lookup
    allow_requirements = []
    deny_requirements = []
    
    if "Requests" in requirements_dict:
        for req in requirements_dict["Requests"]:
            if req.get("Effect", "").lower() == "allow":
                allow_requirements.append(req)
            else:
                deny_requirements.append(req)
    
    for example in failed_examples:
        example_action = example.get('action', '')
        example_resource = example.get('resource', '')
        example_principal = example.get('principal')
        example_condition = example.get('condition')
        expected = example.get('expected', '').lower()
        actual = example.get('actual', '').lower()
        
        if expected == 'allow' and actual == 'deny':
            analysis['allow_to_deny_failures'].append(example)
            
            # Find matching requirement
            matching_req = None
            for req in allow_requirements:
                req_actions = req.get('Action', [])
                req_resources = req.get('Resource', [])
                
                if isinstance(req_actions, str):
                    req_actions = [req_actions]
                if isinstance(req_resources, str):
                    req_resources = [req_resources]
                
                if (example_action in req_actions and 
                    any(resource_matches(example_resource, req_res) for req_res in req_resources)):
                    matching_req = req
                    break
            
            if matching_req:
                analysis['missing_allow_statements'].append({
                    'example': example,
                    'requirement': matching_req,
                    'suggested_fix': {
                        'Effect': 'Allow',
                        'Action': matching_req.get('Action'),
                        'Resource': matching_req.get('Resource'),
                        'Principal': matching_req.get('Principal'),
                        'Condition': matching_req.get('Condition')
                    }
                })
        
        elif expected == 'deny' and actual == 'allow':
            analysis['deny_to_allow_failures'].append(example)
            
            # This indicates policy is too permissive
            analysis['incorrect_deny_statements'].append({
                'example': example,
                'suggested_fix': {
                    'Effect': 'Deny',
                    'Action': example_action,
                    'Resource': example_resource,
                    'Principal': example_principal,
                    'Condition': example_condition
                }
            })
    
    return analysis

def resource_matches(test_resource, policy_resource):
    """Check if a test resource matches a policy resource (considering wildcards)"""
    if test_resource == policy_resource:
        return True
    
    # Handle wildcard matching
    if policy_resource.endswith('/*'):
        prefix = policy_resource[:-2]
        return test_resource.startswith(prefix)
    
    if policy_resource.endswith('*'):
        prefix = policy_resource[:-1]
        return test_resource.startswith(prefix)
    
    return False

def generate_targeted_repair_prompt(current_policy, requirements, failed_analysis, iteration):
    """
    Generate a targeted repair prompt with original policy context for structure preservation.
    """
    
    prompt = f"""You are an AWS IAM policy expert. Fix the current policy while maintaining its structure.

ORIGINAL POLICY (maintain similar structure and statement count):
{json.dumps(current_policy, indent=2)}

REQUIREMENTS:
{format_requirements_detailed(requirements)}

ITERATION: {iteration}/{MAX_ITERATIONS}

FAILURE ANALYSIS:
"""

    if failed_analysis['allow_to_deny_failures']:
        prompt += f"\nCRITICAL: Currently DENYING {len(failed_analysis['allow_to_deny_failures'])} requests that should be ALLOWED:\n"
        for i, failure in enumerate(failed_analysis['allow_to_deny_failures'][:5], 1):  # Show top 5
            prompt += f"   {i}. Action: {failure['action']}\n"
            prompt += f"      Resource: {failure['resource']}\n"
            if failure.get('principal'):
                prompt += f"      Principal: {failure['principal']}\n"
            if failure.get('condition'):
                prompt += f"      Condition: {failure['condition']}\n"
            prompt += "\n"
    
    if failed_analysis['deny_to_allow_failures']:
        prompt += f"\nWARNING: Currently ALLOWING {len(failed_analysis['deny_to_allow_failures'])} requests that should be DENIED:\n"
        for i, failure in enumerate(failed_analysis['deny_to_allow_failures'][:5], 1):  # Show top 5
            prompt += f"   {i}. Action: {failure['action']}\n"
            prompt += f"      Resource: {failure['resource']}\n"
            if failure.get('principal'):
                prompt += f"      Principal: {failure['principal']}\n"
            if failure.get('condition'):
                prompt += f"      Condition: {failure['condition']}\n"
            prompt += "\n"

    if failed_analysis['missing_allow_statements']:
        prompt += f"\nREQUIRED FIXES (modify existing statements to allow these):\n"
        for i, missing in enumerate(failed_analysis['missing_allow_statements'][:3], 1):
            req = missing['requirement']
            prompt += f"   {i}. Effect: Allow\n"
            prompt += f"      Action: {req.get('Action')}\n"
            prompt += f"      Resource: {req.get('Resource')}\n"
            if req.get('Principal'):
                prompt += f"      Principal: {req.get('Principal')}\n"
            if req.get('Condition'):
                prompt += f"      Condition: {req.get('Condition')}\n"
            prompt += "\n"

    if failed_analysis['incorrect_deny_statements']:
        prompt += f"\nREQUIRED RESTRICTIONS (add conditions to existing statements):\n"
        for i, incorrect in enumerate(failed_analysis['incorrect_deny_statements'][:3], 1):
            fix = incorrect['suggested_fix']
            prompt += f"   {i}. Add restriction for:\n"
            prompt += f"      Action: {fix['Action']}\n"
            prompt += f"      Resource: {fix['Resource']}\n"
            if fix.get('Principal'):
                prompt += f"      Principal: {fix['Principal']}\n"
            if fix.get('Condition'):
                prompt += f"      Condition: {fix['Condition']}\n"
            prompt += "\n"

    prompt += f"""

REPAIR INSTRUCTIONS:
1. MAINTAIN STRUCTURE: Keep the same number of statements as the original ({len(current_policy.get('Statement', []))})
2. MODIFY EXISTING: Fix existing statements rather than adding new ones
3. ADD CONSTRAINTS: Add Principal and Condition fields when specified in requirements
4. MINIMAL CHANGES: Make the smallest changes necessary to fix the failures

IMPORTANT RULES:
- Keep the same number of statements ({len(current_policy.get('Statement', []))})
- Modify existing statements to meet requirements
- Add Principal and Condition constraints when specified
- Deny statements take precedence over Allow statements

OUTPUT FORMAT:
Return ONLY the corrected policy as valid JSON. No explanations.

CORRECTED POLICY:"""

    return prompt

def format_requirements_detailed(requirements):
    """Format requirements with more detail for better understanding"""
    if "Requests" not in requirements:
        return "No valid requirements found"
    
    lines = []
    allow_reqs = [r for r in requirements["Requests"] if r.get("Effect", "").lower() == "allow"]
    deny_reqs = [r for r in requirements["Requests"] if r.get("Effect", "").lower() != "allow"]
    
    if allow_reqs:
        lines.append("MUST ALLOW:")
        for i, req in enumerate(allow_reqs, 1):
            lines.append(f"  {i}. ID: {req.get('id', 'unknown')}")
            lines.append(f"     Actions: {req.get('Action', [])}")
            lines.append(f"     Resources: {req.get('Resource', [])}")
            if req.get('Principal'):
                lines.append(f"     Principal: {req.get('Principal')}")
            if req.get('Condition'):
                lines.append(f"     Condition: {req.get('Condition')}")
            lines.append("")
    
    if deny_reqs:
        lines.append("MUST DENY:")
        for i, req in enumerate(deny_reqs, 1):
            lines.append(f"  {i}. ID: {req.get('id', 'unknown')}")
            lines.append(f"     Actions: {req.get('Action', [])}")
            lines.append(f"     Resources: {req.get('Resource', [])}")
            if req.get('Principal'):
                lines.append(f"     Principal: {req.get('Principal')}")
            if req.get('Condition'):
                lines.append(f"     Condition: {req.get('Condition')}")
            lines.append("")
    
    return "\n".join(lines)

def extract_and_validate_json(response_text: str) -> dict:
    """Extract and validate JSON from Ollama response with improved error handling"""
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
        # Try to fix common JSON issues
        fixed_json = json_text
        
        # Fix trailing commas
        fixed_json = re.sub(r',(\s*[}\]])', r'\1', fixed_json)
        
        # Fix missing quotes around property names
        fixed_json = re.sub(r'(\w+)(\s*):', r'"\1"\2:', fixed_json)
        
        # Fix single quotes to double quotes
        fixed_json = re.sub(r"'([^']*)'", r'"\1"', fixed_json)
        
        try:
            parsed_json = json.loads(fixed_json)
            logging.info("Successfully fixed JSON syntax issues")
            
            if not isinstance(parsed_json, dict):
                raise ValueError("Fixed response is not a JSON object")
            
            if "Version" not in parsed_json:
                raise ValueError("Missing 'Version' field in fixed policy")
            
            if "Statement" not in parsed_json:
                raise ValueError("Missing 'Statement' field in fixed policy")
            
            if not isinstance(parsed_json["Statement"], list):
                raise ValueError("'Statement' field must be an array in fixed policy")
            
            return parsed_json
            
        except json.JSONDecodeError as e2:
            raise ValueError(f"Failed to parse JSON even after fixes. Error: {e2}")

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


@retry()

def repair_policy_with_targeted_approach(policy: dict, requirements: dict, iteration: int = 1, 
                                        erroneous_policy: dict = None, failed_examples: list = None) -> dict:
    """Enhanced policy repair using erroneous policy from SMT solver with original policy context"""
    
    if erroneous_policy:
        # Extract analysis results and detailed failure information
        analysis_results = erroneous_policy.get('analysis_result', [])
        faulty_statements = erroneous_policy.get('Statement', [])
        
        # Organize failed examples by statement if available in the erroneous policy structure
        statement_failures = {}
        if hasattr(erroneous_policy, 'keys') and any('stmt' in str(key) for key in erroneous_policy.keys()):
            for key, value in erroneous_policy.items():
                if isinstance(value, dict) and 'must_allow_but_got_denied' in value:
                    statement_failures[key] = value
        
        # Build detailed analysis of each faulty statement
        statement_analysis = ""
        for i, stmt in enumerate(faulty_statements, 1):
            stmt_id = stmt.get('Sid', f'Statement{i}')
            actions = stmt.get('Action', [])
            resources = stmt.get('Resource', [])
            effect = stmt.get('Effect', 'Allow')
            principal = stmt.get('Principal', 'Not specified')
            condition = stmt.get('Condition', 'Not specified')
            
            statement_analysis += f"\nFAULTY STATEMENT {i} ({stmt_id}):\n"
            statement_analysis += f"  Current Effect: {effect}\n"
            statement_analysis += f"  Actions: {actions}\n"
            statement_analysis += f"  Resources: {resources}\n"
            statement_analysis += f"  Principal: {principal}\n"
            statement_analysis += f"  Condition: {condition}\n"
            
            # Add specific failure information if available
            if stmt_id in statement_failures:
                failures = statement_failures[stmt_id]
                allow_failures = failures.get('must_allow_but_got_denied', [])
                deny_failures = failures.get('must_deny_but_got_allow', [])
                
                if allow_failures:
                    statement_analysis += f"  CRITICAL: {len(allow_failures)} requests that should be ALLOWED are being DENIED\n"
                    statement_analysis += f"  Sample failing requests:\n"
                    for j, failure in enumerate(allow_failures[:3], 1):  # Show top 3
                        statement_analysis += f"    {j}. Action: {failure.get('action')}\n"
                        statement_analysis += f"       Resource: {failure.get('resource')}\n"
                        statement_analysis += f"       Principal: {failure.get('principal')}\n"
                        statement_analysis += f"       Condition: {failure.get('condition')}\n"
                        statement_analysis += f"       Expected: {failure.get('expected_effect')} | Got: {failure.get('actual_result')}\n"
                
                if deny_failures:
                    statement_analysis += f"  WARNING: {len(deny_failures)} requests that should be DENIED are being ALLOWED\n"
            
            # Find matching requirements for this statement
            matching_reqs = []
            for req in requirements.get("Requests", []):
                req_actions = req.get('Action', [])
                req_resources = req.get('Resource', [])
                if isinstance(req_actions, str):
                    req_actions = [req_actions]
                if isinstance(req_resources, str):
                    req_resources = [req_resources]
                
                # Check if any statement actions/resources match requirement actions/resources
                if any(action in req_actions for action in actions) or any(resource in req_resources for resource in resources):
                    matching_reqs.append(req)
            
            if matching_reqs:
                statement_analysis += f"  Matching Requirements:\n"
                for req in matching_reqs[:2]:  # Show top 2 matches
                    statement_analysis += f"    - ID: {req.get('id')} | Effect: {req.get('Effect')}\n"
                    statement_analysis += f"      Actions: {req.get('Action')}\n"
                    statement_analysis += f"      Resources: {req.get('Resource')}\n"
                    if req.get('Principal'):
                        statement_analysis += f"      Principal: {req.get('Principal')}\n"
                    if req.get('Condition'):
                        statement_analysis += f"      Condition: {req.get('Condition')}\n"
        
        # Enhanced prompt with original policy context
        prompt = f"""You are an AWS IAM policy expert. Fix the faulty statements while maintaining the original policy structure.

ORIGINAL POLICY (for context - maintain similar structure and statement count):
{json.dumps(policy, indent=2)}

FAULTY STATEMENTS TO FIX:
{json.dumps(erroneous_policy, indent=2)}

REQUIREMENTS TO SATISFY:
{format_requirements_detailed(requirements)}

ITERATION: {iteration}/{MAX_ITERATIONS}

DETAILED FAILURE ANALYSIS:
{statement_analysis}

SOLVER ANALYSIS RESULTS:
{chr(10).join(f"• {result}" for result in analysis_results)}

REPAIR INSTRUCTIONS:
1. MAINTAIN STRUCTURE: Keep the same number of statements as the original policy ({len(policy.get('Statement', []))})
2. FIX FAULTY STATEMENTS: Modify only the problematic statements identified above
3. PRESERVE WORKING STATEMENTS: Keep statements that are working correctly unchanged
4. ADD CONSTRAINTS: Add Principal and Condition fields when specified in requirements
5. MINIMAL CHANGES: Make the smallest changes necessary to fix the issues

IMPORTANT RULES:
- Return a policy with {len(policy.get('Statement', []))} statements (same as original)
- Do NOT add new statements unless absolutely necessary
- Do NOT remove working statements
- Focus on fixing the specific faulty statements provided
- Add Principal field when specified in requirements
- Add Condition field when specified in requirements
- Return a complete, valid IAM policy (with Version and Statement fields)

OUTPUT FORMAT:
Return ONLY the complete corrected policy as valid JSON. No explanations.

CORRECTED POLICY:"""
        
    elif failed_examples:
        # Fallback to failed examples analysis with original context
        failed_analysis = analyze_failed_examples(failed_examples, requirements)
        prompt = generate_targeted_repair_prompt(policy, requirements, failed_analysis, iteration)
    else:
        # Basic repair for first iteration with structure preservation
        policy_json = json.dumps(policy, indent=2)
        req_text = format_requirements_detailed(requirements)
        prompt = f"""Fix this AWS IAM policy while maintaining its structure.

ORIGINAL POLICY:
{policy_json}

REQUIREMENTS:
{req_text}

REPAIR INSTRUCTIONS:
- Keep the same number of statements ({len(policy.get('Statement', []))})
- Make minimal changes to fix the issues
- Do not add unnecessary statements
- Focus on modifying existing statements to meet requirements

Return ONLY the corrected policy as valid JSON.

CORRECTED POLICY:"""

    system_prompt = """You are an AWS IAM expert specializing in policy repair. Your goal is to fix policies with minimal structural changes.

Key principles:
1. STRUCTURE PRESERVATION: Maintain the same number of statements as the original
2. MINIMAL CHANGES: Make only the necessary changes to fix failures
3. TARGETED FIXES: Focus on the specific faulty statements identified
4. CONSTRAINT ADDITION: Add Principal and Condition when specified in requirements
5. WORKING PRESERVATION: Keep statements that work correctly unchanged

Output ONLY valid JSON policy. No explanations. No thinking steps."""
    
    response_text = call_ollama(prompt, system_prompt)
    
    if not response_text:
        raise ValueError("Empty response from Ollama")
    
    return extract_and_validate_json(response_text)


def extract_failed_examples(output_content: str) -> list:
    """Extract failed examples from validator output with improved parsing"""
    failed_examples = []
    lines = output_content.split('\n')
    
    current_request = None
    
    for line in lines:
        line = line.strip()
        
        if "Validating individual request:" in line:
            match = re.search(r'Validating individual request: (\w+)_combo_\d+', line)
            if match:
                current_request = {"id": match.group(1)}
        
        elif line.startswith("Action:") and current_request:
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
                    current_request["condition"] = condition_val if condition_val != "None" else None
        
        elif "INCORRECT:" in line and current_request:
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
                logging.debug(f"Found failed example: {failed_example}")
        
        elif "CORRECT:" in line or "Processing request object:" in line:
            current_request = None
    
    logging.info(f"Extracted {len(failed_examples)} failed examples from validator output")
    return failed_examples

def run_smt_validator(policy_file: str, requests_file: str, policy_idx: int = None) -> dict:
    """Run both validation methods - complete policy for accuracy, identify-faulty for repair guidance"""
    try:
        original_dir = os.getcwd()
        os.chdir(QUACKY_SRC_DIR)
        
        # Create output directories
        if policy_idx is not None:
            policy_specific_dir = os.path.join(OUTPUT_DIR, "Quacky_output", f"policy_{policy_idx:03d}")
            os.makedirs(policy_specific_dir, exist_ok=True)
            
            # File paths for both validations
            accuracy_output_path = os.path.join(policy_specific_dir, f"policy_{policy_idx:03d}_accuracy_validation.txt")
            faulty_output_path = os.path.join(policy_specific_dir, f"policy_{policy_idx:03d}_faulty_validation.txt")
            erroneous_policy_path = os.path.join(policy_specific_dir, f"policy_{policy_idx:03d}_erroneous_policy.json")
        else:
            # Fallback naming
            quacky_output_dir = os.path.join(OUTPUT_DIR, "Quacky_output")
            os.makedirs(quacky_output_dir, exist_ok=True)
            timestamp = int(time.time())
            pid = os.getpid()
            accuracy_output_path = os.path.join(quacky_output_dir, f"temp_accuracy_{pid}_{timestamp}.txt")
            faulty_output_path = os.path.join(quacky_output_dir, f"temp_faulty_{pid}_{timestamp}.txt")
            erroneous_policy_path = os.path.join(quacky_output_dir, f"erroneous_policy_{pid}_{timestamp}.json")
        
        # ===== VALIDATION 1: Complete Policy (for accurate accuracy measurement) =====
        cmd_accuracy = [
            'python3', 'validate_requests.py',
            '-p1', policy_file,
            '--requests', requests_file,
            '-s'
            # No --identify-faulty flag
        ]
        
        logging.debug(f"Running accuracy validation: {' '.join(cmd_accuracy)}")
        
        with open(accuracy_output_path, 'w') as output_file:
            result = subprocess.run(cmd_accuracy, stdout=output_file, stderr=subprocess.PIPE, text=True, timeout=300)
        
        if result.returncode != 0:
            logging.error(f"Accuracy validation failed: {result.stderr}")
            raise Exception(f"Accuracy validation failed: {result.stderr}")
        
        with open(accuracy_output_path, 'r') as f:
            accuracy_output_content = f.read()
        
        # ===== VALIDATION 2: Identify Faulty (for repair guidance) =====
        cmd_faulty = [
            'python3', 'validate_requests.py',
            '-p1', policy_file,
            '--requests', requests_file,
            '-s',
            '--identify-faulty',
            '-o', erroneous_policy_path
        ]
        
        logging.debug(f"Running faulty identification: {' '.join(cmd_faulty)}")
        
        with open(faulty_output_path, 'w') as output_file:
            result = subprocess.run(cmd_faulty, stdout=output_file, stderr=subprocess.PIPE, text=True, timeout=300)
        
        os.chdir(original_dir)
        
        if result.returncode != 0:
            logging.warning(f"Faulty identification failed: {result.stderr}")
            # Don't throw error - we still have accuracy results
        
        # Load erroneous policy if it exists
        erroneous_policy = None
        if os.path.exists(erroneous_policy_path):
            try:
                with open(erroneous_policy_path, 'r') as f:
                    erroneous_policy = json.load(f)
                logging.info(f"Loaded erroneous policy with {len(erroneous_policy.get('Statement', []))} faulty statements")
            except Exception as e:
                logging.warning(f"Failed to load erroneous policy: {e}")
        else:
            logging.warning(f"Erroneous policy file not found at {erroneous_policy_path}")
        
        # ===== PARSE ACCURACY RESULTS (from complete policy validation) =====
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
        
        # Extract failed examples from accuracy validation
        failed_examples = extract_failed_examples(accuracy_output_content)
        
        logging.info(f"Validation completed - Accuracy: {accuracy}%, Total: {total_requests}, Correct: {correct_count}, Incorrect: {incorrect_count}")
        
        # Clean up temporary files
        if os.path.exists(accuracy_output_path):
            os.unlink(accuracy_output_path)
        if os.path.exists(faulty_output_path):
            os.unlink(faulty_output_path)
        
        return {
            'accuracy': accuracy,  # ← From complete policy validation
            'total_requests': total_requests,  # ← Should be 10, not 60
            'correct': correct_count,
            'incorrect': incorrect_count,
            'misclassified_allow_to_deny': misclassified_allow_to_deny,
            'misclassified_deny_to_allow': misclassified_deny_to_allow,
            'failed_examples': failed_examples,
            'erroneous_policy': erroneous_policy,  # ← From identify-faulty for repair guidance
            'erroneous_policy_file': erroneous_policy_path,
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
def load_json_file(path: str) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json_file(data: dict, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def format_requirements(requests: dict) -> str:
    """Simple format for backward compatibility"""
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

def process_policy_with_improved_repair(idx: int, baseline_accuracy: float = 0.0, 
                                              baseline_failed_examples: list = None,
                                              baseline_erroneous_policy: dict = None) -> dict:
    """Process a single policy with erroneous policy guided repair"""
    policy_file = os.path.join(POLICY_DIR, f"{idx}.json")
    req_file = os.path.join(REQUIREMENTS_DIR, f"{idx}.json")
    
    if not os.path.exists(policy_file) or not os.path.exists(req_file):
        raise FileNotFoundError(f"Missing files for index {idx}")
    
    original_policy = load_json_file(policy_file)
    requirements = load_json_file(req_file)
    
    logging.info(f"Starting erroneous policy guided repair for policy {idx} (baseline: {baseline_accuracy:.1f}%)...")
    
    if baseline_accuracy >= TARGET_ACCURACY:
        logging.info(f"Policy {idx} already achieves target accuracy ({baseline_accuracy:.1f}%). Skipping repair.")
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
    
    iteration_results = []
    current_policy = original_policy.copy()
    current_erroneous_policy = baseline_erroneous_policy
    failed_examples = baseline_failed_examples or []
    final_accuracy = baseline_accuracy
    iteration_accuracies = [baseline_accuracy]
    
    for iteration in range(0, MAX_ITERATIONS):
        logging.info(f"Policy {idx} - Iteration {iteration}/{MAX_ITERATIONS} (Previous: {final_accuracy:.1f}%)")
        
        iteration_success = False
        iteration_accuracy = 0.0
        iteration_policy_file = None
        
        try:
            logging.info(f"Repairing policy with erroneous policy guidance (iteration {iteration})...")
            
            if current_erroneous_policy:
                logging.info(f"Using erroneous policy with {len(current_erroneous_policy.get('Statement', []))} faulty statements")
            elif failed_examples:
                logging.info(f"Fallback to analyzing {len(failed_examples)} failed examples")
            
            # Use erroneous policy guided repair
            repaired_policy = repair_policy_with_targeted_approach(
                current_policy, requirements, iteration, current_erroneous_policy, failed_examples
            )
            
            temp_policy_file = os.path.join(TEMP_DIR, f"policy_{idx}_iter_{iteration}.json")
            os.makedirs(TEMP_DIR, exist_ok=True)
            save_json_file(repaired_policy, temp_policy_file)
            
            logging.info(f"Validating with SMT solver (iteration {iteration})...")
            validation_results = run_smt_validator(temp_policy_file, req_file, policy_idx=idx)
            
            accuracy = validation_results['accuracy']
            iteration_accuracy = accuracy  # Store for tracking
            iteration_policy_file = temp_policy_file  # Store for tracking
            
            current_failed_examples = validation_results.get('failed_examples', [])
            current_erroneous_policy = validation_results.get('erroneous_policy')
            
            # ALWAYS append iteration accuracy before any potential exceptions
            iteration_accuracies.append(accuracy)
            improvement = accuracy - baseline_accuracy
            
            logging.info(f"Iteration {iteration} Results:")
            logging.info(f"  Accuracy: {accuracy:.1f}% (Baseline: {baseline_accuracy:.1f}%, Improvement: {improvement:+.1f}%)")
            logging.info(f"  Failed Examples: {len(current_failed_examples)}")
            if current_erroneous_policy:
                logging.info(f"  New erroneous policy has {len(current_erroneous_policy.get('Statement', []))} faulty statements")
            
            # Create iteration record BEFORE success check
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
                'erroneous_policy': current_erroneous_policy,
                'policy_file': temp_policy_file
            }
            iteration_results.append(iteration_record)
            
            final_accuracy = accuracy
            
            # Check if we achieved target accuracy
            if accuracy >= TARGET_ACCURACY:
                logging.info(f"Target accuracy achieved for policy {idx} in {iteration} iterations!")
                logging.info(f"Final accuracy: {accuracy:.1f}% (Improvement from baseline: {improvement:+.1f}%)")
                
                # Try to save final policy with error handling
                try:
                    final_output_file = os.path.join(OUTPUT_DIR, f"repaired_{idx}_final.json")
                    save_json_file(repaired_policy, final_output_file)
                    iteration_success = True
                    
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
                except Exception as save_error:
                    logging.error(f"Error saving final policy for {idx}: {save_error}")
                    # Continue to try saving as best policy below
                    iteration_success = True  # We still achieved target accuracy
            
            # Update for next iteration
            current_policy = repaired_policy.copy()
            failed_examples = current_failed_examples if current_failed_examples else None
            
        except Exception as e:
            logging.error(f"Error in iteration {iteration} for policy {idx}: {e}")
            
            # If we haven't recorded the iteration yet, add an error record
            if not any(record.get('iteration') == iteration for record in iteration_results):
                iteration_record = {
                    'policy_idx': idx,
                    'iteration': iteration,
                    'validation_type': 'repair',
                    'accuracy': iteration_accuracy,  # Use actual accuracy if we got it
                    'baseline_accuracy': baseline_accuracy,
                    'improvement_from_baseline': iteration_accuracy - baseline_accuracy,
                    'failed_examples_count': 0,
                    'error': str(e),
                    'policy_file': iteration_policy_file  # Include file if we got it
                }
                iteration_results.append(iteration_record)
                
                # Only append to iteration_accuracies if we got a real accuracy
                if iteration_accuracy > 0:
                    iteration_accuracies.append(iteration_accuracy)
            
            # If we achieved target accuracy but had a save error, try to save as best
            if iteration_success and iteration_accuracy >= TARGET_ACCURACY:
                try:
                    final_output_file = os.path.join(OUTPUT_DIR, f"repaired_{idx}_final.json")
                    if iteration_policy_file and os.path.exists(iteration_policy_file):
                        shutil.copy2(iteration_policy_file, final_output_file)
                        
                        return {
                            'index': idx,
                            'status': 'success',
                            'baseline_accuracy': baseline_accuracy,
                            'final_accuracy': iteration_accuracy,
                            'improvement_from_baseline': iteration_accuracy - baseline_accuracy,
                            'iterations_used': iteration,
                            'iteration_accuracies': iteration_accuracies,
                            'iteration_results': iteration_results,
                            'final_policy_file': final_output_file
                        }
                except Exception as fallback_error:
                    logging.error(f"Error in fallback save for {idx}: {fallback_error}")

    # === DEBUGGING SECTION: BEST POLICY SELECTION ===
    # If we reach here, we didn't achieve target accuracy
    # Find the best iteration result
    best_accuracy = baseline_accuracy
    best_iteration = None

    if iteration_results:
        # Debug: Show all iterations and their accuracies
        logging.info(f"Policy {idx}: All iteration results:")
        for i, result in enumerate(iteration_results):
            logging.info(f"  Iteration {result.get('iteration')}: {result.get('accuracy', 0):.1f}% - File: {result.get('policy_file')}")
        
        best_iteration = max(iteration_results, key=lambda x: x.get('accuracy', 0))
        best_accuracy = best_iteration.get('accuracy', baseline_accuracy)
        best_file = best_iteration.get('policy_file')
        best_iter_num = best_iteration.get('iteration')
        
        logging.info(f"Policy {idx}: Selected best iteration {best_iter_num} with accuracy {best_accuracy:.1f}%")
        logging.info(f"Policy {idx}: Best file path: {best_file}")
        logging.info(f"Policy {idx}: Best file exists: {os.path.exists(best_file) if best_file else False}")
        logging.info(f"Policy {idx}: Final iteration accuracy was {final_accuracy:.1f}%")
        
        if 'policy_file' in best_iteration and os.path.exists(best_iteration['policy_file']):
            final_output_file = os.path.join(OUTPUT_DIR, f"repaired_{idx}_best.json")
            
            # Debug: Check file before and after copy
            import hashlib
            try:
                with open(best_iteration['policy_file'], 'rb') as f:
                    original_hash = hashlib.md5(f.read()).hexdigest()
                
                shutil.copy2(best_iteration['policy_file'], final_output_file)
                
                with open(final_output_file, 'rb') as f:
                    copied_hash = hashlib.md5(f.read()).hexdigest()
                
                logging.info(f"Policy {idx}: File copy hash match: {original_hash == copied_hash}")
                
                # Debug: Immediately validate the copied file
                try:
                    immediate_validation = run_smt_validator(final_output_file, req_file, policy_idx=idx)
                    immediate_accuracy = immediate_validation['accuracy']
                    logging.info(f"Policy {idx}: Immediate validation of copied file: {immediate_accuracy:.1f}%")
                    
                    if abs(best_accuracy - immediate_accuracy) > 0.1:
                        logging.warning(f"Policy {idx}: ACCURACY MISMATCH after copy!")
                        logging.warning(f"Policy {idx}: Expected {best_accuracy:.1f}%, got {immediate_accuracy:.1f}%")
                        
                        # Compare the policies themselves
                        with open(best_iteration['policy_file'], 'r') as f:
                            original_policy_content = f.read()
                        with open(final_output_file, 'r') as f:
                            copied_policy_content = f.read()
                        
                        if original_policy_content != copied_policy_content:
                            logging.error(f"Policy {idx}: FILE CONTENT MISMATCH during copy!")
                        else:
                            logging.warning(f"Policy {idx}: File content identical, SMT solver gave different result")
                    else:
                        logging.info(f"Policy {idx}: Validation accuracy matches expected")
                        
                except Exception as val_e:
                    logging.error(f"Policy {idx}: Failed to validate copied file: {val_e}")
                    
            except Exception as copy_e:
                logging.error(f"Policy {idx}: Error during file copy/validation: {copy_e}")
        else:
            final_output_file = os.path.join(OUTPUT_DIR, f"repaired_{idx}_original.json")
            save_json_file(original_policy, final_output_file)
            best_accuracy = baseline_accuracy
            logging.warning(f"Policy {idx}: No valid best iteration file found, saving original policy")
    else:
        final_output_file = os.path.join(OUTPUT_DIR, f"repaired_{idx}_original.json")
        save_json_file(original_policy, final_output_file)
        logging.warning(f"Policy {idx}: No iteration results found, saving original policy")

    improvement = best_accuracy - baseline_accuracy
    logging.warning(f"Failed to achieve target accuracy for policy {idx} after {MAX_ITERATIONS} iterations.")
    logging.warning(f"Best accuracy: {best_accuracy:.1f}% (Baseline: {baseline_accuracy:.1f}%, Improvement: {improvement:+.1f}%)")

    return {
        'index': idx,
        'status': 'failed',
        'baseline_accuracy': baseline_accuracy,
        'final_accuracy': best_accuracy,  # Use best accuracy, not final iteration
        'improvement_from_baseline': improvement,
        'iterations_used': MAX_ITERATIONS,
        'iteration_accuracies': iteration_accuracies,
        'iteration_results': iteration_results,
        'final_policy_file': final_output_file
    }
class IterativeProgressTracker:
    """Progress tracker for iterative policy repair"""
    def __init__(self, progress_file: str = os.path.join(OUTPUT_DIR, "improved_iterative_progress.json")):
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
    
    def mark_completed(self, idx, baseline_accuracy, final_accuracy, iterations_used, iteration_accuracies):
        self.progress["last_processed"] = idx
        if idx not in self.progress["completed"]:
            self.progress["completed"].append(idx)
        if idx in self.progress["failed"]:
            self.progress["failed"].remove(idx)
        
        self.progress["baseline_accuracies"][str(idx)] = baseline_accuracy
        
        self.progress["policy_iterations"][str(idx)] = {
            "status": "completed",
            "baseline_accuracy": baseline_accuracy,
            "final_accuracy": final_accuracy,
            "improvement": final_accuracy - baseline_accuracy,
            "iterations_used": iterations_used,
            "iteration_accuracies": iteration_accuracies
        }
        self.save_progress()
    
    def mark_failed(self, idx, baseline_accuracy, final_accuracy, iterations_used, iteration_accuracies):
        if idx not in self.progress["failed"]:
            self.progress["failed"].append(idx)
        
        self.progress["baseline_accuracies"][str(idx)] = baseline_accuracy
        
        self.progress["policy_iterations"][str(idx)] = {
            "status": "failed",
            "baseline_accuracy": baseline_accuracy,
            "final_accuracy": final_accuracy,
            "improvement": final_accuracy - baseline_accuracy,
            "iterations_used": iterations_used,
            "iteration_accuracies": iteration_accuracies
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
            'failed_examples_count': len(validation_results.get('failed_examples', [])),
            'failed_examples': validation_results.get('failed_examples', []),
            'erroneous_policy': validation_results.get('erroneous_policy'),
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
def main():
    """Main function - Improved counter-example guided repair"""
    log_file = setup_logging()
    logging.info("Starting improved counter-example guided policy repair system")
    
    print("=" * 60)
    print("IMPROVED COUNTER-EXAMPLE GUIDED POLICY REPAIR")
    print("=" * 60)
    
    # Test Ollama connection first
    print("Testing Ollama connection...")
    ollama_ok, ollama_msg = test_ollama_connection()
    if not ollama_ok:
        logging.error(f"Ollama connection failed: {ollama_msg}")
        print(f"Ollama connection failed: {ollama_msg}")
        print("\nPlease ensure:")
        print("1. Ollama is running (ollama serve)")
        print(f"2. Model '{OLLAMA_MODEL}' is installed (ollama pull {OLLAMA_MODEL})")
        print("3. Ollama is accessible")
        sys.exit(1)
    
    logging.info(f"Ollama connection successful: {ollama_msg}")
    print(f"{ollama_msg}")
    print(f"Using model: {OLLAMA_MODEL}")
    print("\nKey improvements:")
    print("- Detailed failure analysis of SMT solver output")
    print("- Targeted repair prompts based on failure patterns")
    print("- Better understanding of allow vs deny misclassifications")
    print("- Structured approach to counter-example guided repair")
    
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
                tracker.mark_baseline_completed(idx, 0.0)
    else:
        logging.info("All baseline validations already completed. Loading existing results...")
        for i in range(total):
            baseline_accuracy = tracker.get_baseline_accuracy(i)
            baseline_results.append({
                'policy_idx': i,
                'validation_type': 'baseline',
                'accuracy': baseline_accuracy,
                'failed_examples_count': 0,
                'failed_examples': []
            })
    
    # Save baseline results (REMOVED TIMESTAMP)
    if baseline_results:
        baseline_csv = os.path.join(OUTPUT_DIR, "baseline_results_improved.csv")
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
    
    # Step 2: Improved counter-example guided repair
    print("\nSTEP 2: IMPROVED COUNTER-EXAMPLE GUIDED REPAIR")
    print("=" * 60)
    
    baseline_accuracy_map = {r['policy_idx']: r.get('accuracy', 0.0) for r in baseline_results}
    baseline_failed_examples_map = {r['policy_idx']: r.get('failed_examples', []) for r in baseline_results}
    baseline_erroneous_policy_map = {r['policy_idx']: r.get('erroneous_policy') for r in baseline_results}
    
    to_process = [i for i in range(total) if not tracker.is_done(i)]
    logging.info(f"Policies to process for improved repair: {to_process}")
    
    all_results = []
    all_iteration_data = baseline_results.copy()
    
    # Process each policy
    for idx in tqdm(to_process, desc="Processing policies with improved repair"):
        try:
            baseline_acc = baseline_accuracy_map.get(idx, 0.0)
            baseline_failed = baseline_failed_examples_map.get(idx, [])
            baseline_erroneous = baseline_erroneous_policy_map.get(idx)
            result = process_policy_with_improved_repair(idx, baseline_acc, baseline_failed, baseline_erroneous)
            
            # Track completion/failure
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
            
            # Collect iteration data
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
    
    # Save comprehensive results (REMOVED TIMESTAMPS)
    
    # Summary results
    if all_results:
        df_summary = pd.DataFrame(all_results)
        summary_csv = os.path.join(OUTPUT_DIR, "improved_repair_summary.csv")
        df_summary.to_csv(summary_csv, index=False)
        logging.info(f"Summary results saved to {summary_csv}")
    
    # Detailed iteration results
    if all_iteration_data:
        df_iterations = pd.DataFrame(all_iteration_data)
        iterations_csv = os.path.join(OUTPUT_DIR, "improved_repair_details.csv")
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
    
    # Include baseline failed examples
    for baseline_result in baseline_results:
        if 'failed_examples' in baseline_result and baseline_result['failed_examples']:
            for example in baseline_result['failed_examples']:
                failed_examples_analysis.append({
                    'policy_idx': baseline_result['policy_idx'],
                    'iteration': 0,
                    'iteration_type': 'baseline',
                    'request_id': example['request_id'],
                    'action': example['action'],
                    'resource': example['resource'],
                    'expected': example['expected'],
                    'actual': example['actual']
                })
    
    if failed_examples_analysis:
        df_failed = pd.DataFrame(failed_examples_analysis)
        failed_csv = os.path.join(OUTPUT_DIR, "improved_repair_failed_examples.csv")
        df_failed.to_csv(failed_csv, index=False)
        logging.info(f"Failed examples analysis saved to {failed_csv}")
    
    
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
    else:
        avg_baseline = avg_final = avg_improvement = total_iterations = improvement_count = 0
        baseline_perfect = final_perfect = 0
    
    # Print final summary to console
    print(f"\n{'='*60}")
    print("IMPROVED COUNTER-EXAMPLE GUIDED REPAIR - FINAL SUMMARY")
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
            print(f"  Policy {idx}: {baseline:.1f}% → {final:.1f}% (already perfect)")
        elif status == 'success':
            print(f"  Policy {idx}: {baseline:.1f}% → {final:.1f}% (SUCCESS in {iterations} iterations, +{improvement:.1f}%)")
        elif status == 'failed':
            print(f"  Policy {idx}: {baseline:.1f}% → {final:.1f}% (failed after {iterations} iterations, +{improvement:.1f}%)")
        else:
            print(f"  Policy {idx}: {baseline:.1f}% → {final:.1f}% (ERROR: {result.get('error', 'unknown')})")
    
    print(f"{'='*60}")
    print("Results files:")
    print(f"  - Baseline: baseline_results_improved.csv")
    print(f"  - Summary: improved_repair_summary.csv")
    print(f"  - Detailed iterations: improved_repair_details.csv")
    print(f"  - Failed examples: improved_repair_failed_examples.csv")
    print(f"  - Progress tracker: {tracker.progress_file}")
    print(f"{'='*60}")
    print("\nKEY IMPROVEMENTS:")
    print("Detailed analysis of SMT solver counter-examples")
    print("Targeted repair prompts based on failure patterns")
    print("Better understanding of allow→deny vs deny→allow failures")
    print("Structured approach to requirement matching")
    print("Enhanced error handling and JSON parsing")

    # Cleanup
    if os.path.exists(TEMP_DIR):
        logging.info(f"Temporary files kept for analysis in: {TEMP_DIR}")

if __name__ == "__main__":
    main()