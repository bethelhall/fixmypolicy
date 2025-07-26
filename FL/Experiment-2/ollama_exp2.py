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

req = 25
POLICY_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-2/original_policy"
REQUIREMENTS_DIR = f"/home/bhall2/Documents/fixmypolicy/FL/Experiment-2/requests/request-{req}"
OUTPUT_DIR = f"/home/bhall2/Documents/fixmypolicy/FL/Experiment-2/results/result-{req}-ollamaa"
LOG_DIR = f"/home/bhall2/Documents/fixmypolicy/FL/Experiment-2/logs/log-{req}-ollamaa"
TEMP_DIR = f"/home/bhall2/Documents/fixmypolicy/FL/Experiment-2/temp_validation/val-{req}-ollamaa"
QUACKY_SRC_DIR = "/home/bhall2/Documents/fixmypolicy/quacky/src"
SMT_VALIDATOR_SCRIPT = "/home/bhall2/Documents/fixmypolicy/quacky/src/validate_requests.py"

MAX_ITERATIONS = 7
MAX_ATTEMPT = 4
DELAY = 1
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
                'temperature': 0.1,     # Keep low for consistency
                'top_p': 0.3,          # Keep low for focused output
                'num_predict': 8000,    # 🔥 DOUBLED: Allow longer outputs
                'num_ctx': 16000,       # 🔥 DOUBLED: Much larger context window
                'stop': ['\n```', '```\n'],
                # Additional optimizations
                'repeat_penalty': 1.1,   # Reduce repetitive statements
                'top_k': 40,            # Limit vocabulary for more focused output
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

def generate_focused_repair_prompt(current_policy, requirements, erroneous_policy, iteration):
    """
    Generate a highly focused repair prompt that includes both SMT analysis and failed request examples
    """
    
    faulty_statements = erroneous_policy.get('Statement', []) if erroneous_policy else []
    analysis_results = erroneous_policy.get('analysis_result', []) if erroneous_policy else []
    
    # Extract specific requirements for context
    allow_requirements = []
    deny_requirements = []
    
    if "Requests" in requirements:
        for req in requirements["Requests"]:
            if req.get("Effect", "").lower() == "allow":
                allow_requirements.append(req)
            else:
                deny_requirements.append(req)
    
    prompt = f"""You are an AWS IAM policy expert. Fix this policy by addressing the specific failures identified by the SMT solver.

CURRENT POLICY TO FIX:
{json.dumps(current_policy, indent=2)}

SMT SOLVER FOUND {len(faulty_statements)} PROBLEMATIC STATEMENTS:

"""

    # Provide detailed analysis for each faulty statement with specific fixes
    for i, (stmt, analysis) in enumerate(zip(faulty_statements, analysis_results)):
        stmt_effect = stmt.get('Effect', 'Unknown')
        stmt_actions = stmt.get('Action', [])
        stmt_resources = stmt.get('Resource', [])
        stmt_sid = stmt.get('Sid', f'Statement{i+1}')
        
        prompt += f"""PROBLEM {i+1} - Statement ID: {stmt_sid}
Current Statement:
{json.dumps(stmt, indent=2)}

Issue: {analysis}

"""
        
        # Provide specific, actionable fix instructions
        if "must allow but got denied" in analysis.lower():
            prompt += f"""REQUIRED FIX: This statement is incorrectly DENYING requests that should be ALLOWED.

Solutions (choose the most appropriate):
1. Change "Effect": "Deny" to "Effect": "Allow"
2. If this is currently an Allow statement, expand the Actions or Resources to be more permissive
3. Remove overly restrictive Principal or Condition constraints
4. Add a new Allow statement if current statement must remain Deny

"""
            
            # Find the specific requirement that should be allowed
            for req in allow_requirements:
                req_actions = req.get('Action', [])
                req_resources = req.get('Resource', [])
                if isinstance(req_actions, str):
                    req_actions = [req_actions]
                if isinstance(req_resources, str):
                    req_resources = [req_resources]
                
                # Check for overlap with the failing statement
                action_overlap = any(action in str(stmt_actions) for action in req_actions)
                resource_overlap = any(resource in str(stmt_resources) for resource in req_resources)
                
                if action_overlap or resource_overlap:
                    prompt += f"""Matching Requirement to Allow:
- ID: {req.get('id')}
- Actions: {req_actions}
- Resources: {req_resources}"""
                    if req.get('Principal'):
                        prompt += f"\n- Principal: {req.get('Principal')}"
                    if req.get('Condition'):
                        prompt += f"\n- Condition: {req.get('Condition')}"
                    prompt += "\n\n"
                    break
        
        elif "must deny but got allow" in analysis.lower():
            prompt += f"""REQUIRED FIX: This statement is incorrectly ALLOWING requests that should be DENIED.
            
Follow this logic:
1. Make MINIMAL, TARGETED changes - avoid overcorrecting
2. If previous iterations made the policy worse, consider reverting some changes
3. Focus on the specific failures identified by SMT analysis
4. Ensure statements don't conflict with each other
5. Test your logic mentally before outputting


"""
            
            # Find deny requirements that should apply
            for req in deny_requirements:
                req_actions = req.get('Action', [])
                if isinstance(req_actions, str):
                    req_actions = [req_actions]
                
                action_overlap = any(action in str(stmt_actions) for action in req_actions)
                if action_overlap:
                    prompt += f"""Matching Requirement to Deny:
- ID: {req.get('id')}
- Actions: {req_actions}
- Resources: {req.get('Resource')}"""
                    if req.get('Principal'):
                        prompt += f"\n- Principal: {req.get('Principal')}"
                    if req.get('Condition'):
                        prompt += f"\n- Condition: {req.get('Condition')}"
                    prompt += "\n\n"
                    break

    # Provide complete requirements context
    prompt += f"""

You Must Avoid the following:
- Don't just flip Effect from Allow to Deny without considering the specific requirement
- Don't make statements too broad (overly permissive) or too narrow (overly restrictive)
- Don't ignore Principal and Condition constraints specified in requirements
- Don't create statements that conflict with each other
- Don't just copy the requests into the policy unless needed. 

OUTPUT INSTRUCTIONS:
Return ONLY the complete corrected policy as valid JSON. No explanations, no markdown formatting.

CORRECTED POLICY:"""

    return prompt

def analyze_prompt_effectiveness(original_policy, repaired_policy, erroneous_policy, requirements):
    """
    Analyze how well the prompt addressed the specific issues
    """
    analysis = {
        'structure_preserved': len(original_policy.get('Statement', [])) == len(repaired_policy.get('Statement', [])),
        'changes_made': 0,
        'targeted_fixes': 0,
        'issues_addressed': []
    }
    
    if not erroneous_policy:
        return analysis
    
    faulty_statements = erroneous_policy.get('Statement', [])
    analysis_results = erroneous_policy.get('analysis_result', [])
    
    original_statements = original_policy.get('Statement', [])
    repaired_statements = repaired_policy.get('Statement', [])
    
    for i, (faulty_stmt, smt_analysis) in enumerate(zip(faulty_statements, analysis_results)):
        if i < len(repaired_statements):
            orig_stmt = original_statements[i] if i < len(original_statements) else {}
            repair_stmt = repaired_statements[i]
            
            # Check if changes were made to this statement
            if orig_stmt != repair_stmt:
                analysis['changes_made'] += 1
                
                # Check if the change addresses the SMT analysis
                if "must allow but got denied" in smt_analysis.lower():
                    if repair_stmt.get('Effect') == 'Allow' and orig_stmt.get('Effect') != 'Allow':
                        analysis['targeted_fixes'] += 1
                        analysis['issues_addressed'].append(f"Statement {i+1}: Fixed allow issue")
                
                elif "must deny but got allow" in smt_analysis.lower():
                    if repair_stmt.get('Effect') == 'Deny' and orig_stmt.get('Effect') != 'Deny':
                        analysis['targeted_fixes'] += 1
                        analysis['issues_addressed'].append(f"Statement {i+1}: Fixed deny issue")
    
    return analysis

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
        # Log what the LLM actually generated - this is what you want to see!
        logging.error(f"LLM generated invalid JSON!")
        logging.error(f"JSON parsing failed at line {e.lineno}, column {e.colno}: {e.msg}")
        logging.error("=== FULL LLM RESPONSE (what the LLM actually generated) ===")
        logging.error(response_text)
        logging.error("=== END LLM RESPONSE ===")
        
        logging.error("=== EXTRACTED JSON (after cleaning markdown) ===")
        logging.error(json_text)
        logging.error("=== END EXTRACTED JSON ===")
        
        # Show the problematic area with line numbers
        json_lines = json_text.split('\n')
        logging.error("JSON with line numbers (error location marked):")
        for i, line in enumerate(json_lines, 1):
            marker = " <-- Error Here" if i == e.lineno else ""
            logging.error(f"{i:2}: {line}{marker}")
        
        raise ValueError(f"LLM generated invalid JSON: {e}")
def analyze_policy_structure_for_repair(current_policy, failed_examples, erroneous_policy):
    """
    Deep analysis of policy structure to provide targeted repair guidance
    """
    analysis = {
        'statement_mapping': {},
        'coverage_gaps': [],
        'overpermissive_statements': [],
        'repair_strategies': {},
        'root_causes': []
    }
    
    statements = current_policy.get('Statement', [])
    
    # Map each failed example to the responsible statement(s)
    for i, stmt in enumerate(statements):
        stmt_actions = stmt.get('Action', [])
        stmt_resources = stmt.get('Resource', [])
        stmt_effect = stmt.get('Effect')
        
        if isinstance(stmt_actions, str):
            stmt_actions = [stmt_actions]
        if isinstance(stmt_resources, str):
            stmt_resources = [stmt_resources]
        
        analysis['statement_mapping'][i] = {
            'statement': stmt,
            'covers_failed_examples': [],
            'responsible_for_failures': []
        }
        
        # Check which failed examples this statement affects
        for example in failed_examples:
            example_action = example.get('action', '')
            example_resource = example.get('resource', '')
            
            # Check if this statement could be responsible for the failure
            action_matches = any(matches_pattern(example_action, action) for action in stmt_actions)
            resource_matches = any(matches_pattern(example_resource, resource) for resource in stmt_resources)
            
            if action_matches and resource_matches:
                analysis['statement_mapping'][i]['covers_failed_examples'].append(example)
                
                # Determine if this statement is causing the failure
                expected = example.get('expected', '').lower()
                actual = example.get('actual', '').lower()
                
                if expected == 'allow' and actual == 'deny' and stmt_effect == 'Deny':
                    analysis['statement_mapping'][i]['responsible_for_failures'].append({
                        'example': example,
                        'issue': 'explicit_deny_blocking_required_allow',
                        'fix_strategy': 'make_deny_more_specific_or_add_allow_exception'
                    })
                elif expected == 'deny' and actual == 'allow' and stmt_effect == 'Allow':
                    analysis['statement_mapping'][i]['responsible_for_failures'].append({
                        'example': example,
                        'issue': 'overpermissive_allow',
                        'fix_strategy': 'add_constraints_or_specific_deny'
                    })
    
    # Identify coverage gaps (failed allows with no matching statement)
    for example in failed_examples:
        if example.get('expected', '').lower() == 'allow':
            covered = False
            for stmt_analysis in analysis['statement_mapping'].values():
                if example in stmt_analysis['covers_failed_examples']:
                    covered = True
                    break
            
            if not covered:
                analysis['coverage_gaps'].append({
                    'example': example,
                    'fix_strategy': 'add_new_allow_statement'
                })
    
    return analysis

def matches_pattern(test_value, pattern):
    """Enhanced pattern matching for AWS actions and resources"""
    if test_value == pattern:
        return True
    
    # Wildcard matching
    if pattern.endswith('*'):
        prefix = pattern[:-1]
        return test_value.startswith(prefix)
    
    # AWS service:action matching
    if ':' in pattern and ':' in test_value:
        pattern_parts = pattern.split(':')
        test_parts = test_value.split(':')
        
        if len(pattern_parts) == len(test_parts):
            return all(
                p == '*' or p == t or (p.endswith('*') and t.startswith(p[:-1]))
                for p, t in zip(pattern_parts, test_parts)
            )
    
    return False

def create_enhanced_repair_prompt(current_policy, requirements, failed_examples, erroneous_policy, iteration):
    """
    Create a much more structured and informative repair prompt
    """
    
    # Perform deep analysis
    analysis = analyze_policy_structure_for_repair(current_policy, failed_examples, erroneous_policy)
    
    prompt = f"""You are an AWS IAM policy expert. You must fix this policy by addressing specific failures with surgical precision.

CURRENT POLICY (needs repair):
{json.dumps(current_policy, indent=2)}

DIAGNOSTIC ANALYSIS:
================

"""

    # Group and prioritize failed examples
    allow_failures = [ex for ex in failed_examples if ex.get('expected', '').lower() == 'allow']
    deny_failures = [ex for ex in failed_examples if ex.get('expected', '').lower() == 'deny']
    
    if allow_failures:
        prompt += f"""CRITICAL ISSUE: {len(allow_failures)} requests are being WRONGLY DENIED
These requests MUST be allowed but are currently blocked:

"""
        for i, failure in enumerate(allow_failures, 1):
            prompt += f"""Request {i}: ID={failure.get('request_id')}
  ├─ Action: {failure.get('action')}
  ├─ Resource: {failure.get('resource')}
  ├─ Principal: {failure.get('principal', 'Any')}
  ├─ Condition: {failure.get('condition', 'None')}
  └─ PROBLEM: Expected ALLOW but got DENY

"""
    
    if deny_failures:
        prompt += f"""SECURITY ISSUE: {len(deny_failures)} requests are being WRONGLY ALLOWED
These requests MUST be denied but are currently permitted:

"""
        for i, failure in enumerate(deny_failures, 1):
            prompt += f"""Request {i}: ID={failure.get('request_id')}
  ├─ Action: {failure.get('action')}
  ├─ Resource: {failure.get('resource')}
  ├─ Principal: {failure.get('principal', 'Any')}
  ├─ Condition: {failure.get('condition', 'None')}
  └─ PROBLEM: Expected DENY but got ALLOW

"""

    # Statement-by-statement analysis
    prompt += f"""
STATEMENT-BY-STATEMENT REPAIR ANALYSIS:
======================================

"""
    
    statements = current_policy.get('Statement', [])
    for i, stmt in enumerate(statements):
        stmt_analysis = analysis['statement_mapping'].get(i, {})
        responsible_failures = stmt_analysis.get('responsible_for_failures', [])
        
        prompt += f"""Statement {i+1}: {stmt.get('Sid', f'Statement{i+1}')}
Current: {json.dumps(stmt, indent=2)}

"""
        
        if responsible_failures:
            prompt += f"""This statement is causing {len(responsible_failures)} failures:
"""
            for failure_info in responsible_failures:
                example = failure_info['example']
                issue = failure_info['issue']
                strategy = failure_info['fix_strategy']
                
                prompt += f"""  • Request {example.get('request_id')}: {example.get('action')} on {example.get('resource')}
    Issue: {issue.replace('_', ' ').title()}
    Fix Strategy: {strategy.replace('_', ' ').title()}
"""
        else:
            prompt += f"""This statement is not causing any failures.
"""
        
        prompt += "\n"

    # Add SMT solver erroneous policy analysis if available
    if erroneous_policy and 'Statement' in erroneous_policy:
        faulty_statements = erroneous_policy['Statement']
        analysis_results = erroneous_policy.get('analysis_result', [])
        
        prompt += f"""
SMT SOLVER IDENTIFIED FAULTY STATEMENTS:
=======================================

"""
        
        for i, (faulty_stmt, smt_analysis) in enumerate(zip(faulty_statements, analysis_results)):
            prompt += f"""Faulty Statement {i+1}:
{json.dumps(faulty_stmt, indent=2)}

SMT Analysis: {smt_analysis}

"""

    # Provide specific repair instructions
    prompt += f"""
PRECISE REPAIR INSTRUCTIONS:
===========================

You MUST apply these specific fixes:

"""

    # Instructions for allow failures
    if allow_failures:
        prompt += f"""FOR WRONGLY DENIED REQUESTS (Expected Allow, Got Deny):
"""
        
        # Group by root cause
        explicit_deny_blocks = []
        implicit_deny_cases = []
        
        for failure in allow_failures:
            # Check if any current statement explicitly denies this
            explicitly_denied = False
            for stmt in statements:
                if (stmt.get('Effect') == 'Deny' and 
                    matches_any_pattern(failure.get('action', ''), stmt.get('Action', [])) and
                    matches_any_pattern(failure.get('resource', ''), stmt.get('Resource', []))):
                    explicitly_denied = True
                    explicit_deny_blocks.append((failure, stmt))
                    break
            
            if not explicitly_denied:
                implicit_deny_cases.append(failure)
        
        if explicit_deny_blocks:
            prompt += f"""
1. EXPLICIT DENY BLOCKS ({len(explicit_deny_blocks)} cases):
   These requests are blocked by specific Deny statements.
   
"""
            for failure, blocking_stmt in explicit_deny_blocks:
                prompt += f"""   • Request {failure.get('request_id')}: Add Principal/Condition constraints to the Deny statement
     OR create a more specific Allow statement that takes precedence
     Current blocking statement: {blocking_stmt.get('Sid', 'unnamed')}
"""
        
        if implicit_deny_cases:
            prompt += f"""
2. IMPLICIT DENY CASES ({len(implicit_deny_cases)} cases):
   These requests have no matching Allow statement.
   
"""
            for failure in implicit_deny_cases:
                prompt += f"""   • Request {failure.get('request_id')}: Add new Allow statement:
     {{
       "Effect": "Allow",
       "Action": "{failure.get('action')}",
       "Resource": "{failure.get('resource')}"
"""
                if failure.get('principal'):
                    prompt += f""",
       "Principal": "{failure.get('principal')}" """
                if failure.get('condition'):
                    prompt += f""",
       "Condition": {failure.get('condition')}"""
                prompt += f"""
     }}
"""

    # Instructions for deny failures  
    if deny_failures:
        prompt += f"""
FOR WRONGLY ALLOWED REQUESTS (Expected Deny, Got Allow):

"""
        for failure in deny_failures:
            prompt += f"""• Request {failure.get('request_id')}: Add specific Deny statement:
  {{
    "Effect": "Deny",
    "Action": "{failure.get('action')}",
    "Resource": "{failure.get('resource')}"
"""
            if failure.get('principal'):
                prompt += f""",
    "Principal": "{failure.get('principal')}" """
            if failure.get('condition'):
                prompt += f""",
    "Condition": {failure.get('condition')}"""
            prompt += f"""
  }}
"""

    # Add requirements context for validation
    prompt += f"""
REQUIREMENTS CONTEXT:
===================
{format_requirements_enhanced(requirements)}

REPAIR RULES:
============
1. Make MINIMAL changes - only fix what's broken
2. Preserve existing working statements
3. For explicit denies blocking required allows: Add constraints, don't just flip Effect
4. For missing allows: Add new Allow statements
5. For unwanted allows: Add specific Deny statements
6. Test your changes mentally against each failed example
7. Ensure Principal and Condition constraints are preserved from requirements

OUTPUT FORMAT:
=============
Return ONLY the complete corrected policy as valid JSON. No explanations or markdown.

CORRECTED POLICY:"""

    return prompt

def matches_any_pattern(test_value, patterns):
    """Check if test_value matches any pattern in the list"""
    if isinstance(patterns, str):
        patterns = [patterns]
    
    return any(matches_pattern(test_value, pattern) for pattern in patterns)

def format_requirements_enhanced(requirements):
    """Enhanced requirements formatting with clear allow/deny separation"""
    if "Requests" not in requirements:
        return "No requirements provided"
    
    allow_reqs = []
    deny_reqs = []
    
    for req in requirements["Requests"]:
        if req.get("Effect", "").lower() == "allow":
            allow_reqs.append(req)
        else:
            deny_reqs.append(req)
    
    output = []
    
    if allow_reqs:
        output.append("MUST ALLOW (these requests must succeed):")
        for i, req in enumerate(allow_reqs, 1):
            output.append(f"  {i}. ID: {req.get('id')}")
            output.append(f"     Actions: {req.get('Action')}")
            output.append(f"     Resources: {req.get('Resource')}")
            if req.get('Principal'):
                output.append(f"     Principal: {req.get('Principal')}")
            if req.get('Condition'):
                output.append(f"     Condition: {req.get('Condition')}")
            output.append("")
    
    if deny_reqs:
        output.append("MUST DENY (these requests must fail):")
        for i, req in enumerate(deny_reqs, 1):
            output.append(f"  {i}. ID: {req.get('id')}")
            output.append(f"     Actions: {req.get('Action')}")
            output.append(f"     Resources: {req.get('Resource')}")
            if req.get('Principal'):
                output.append(f"     Principal: {req.get('Principal')}")
            if req.get('Condition'):
                output.append(f"     Condition: {req.get('Condition')}")
            output.append("")
    
    return "\n".join(output)

def create_enhanced_system_prompt():
    """Enhanced system prompt with better guidance"""
    return """You are an expert AWS IAM policy engineer. Your task is to repair IAM policies with surgical precision.

CORE PRINCIPLES:
1. AWS IAM uses explicit allow model - requests are denied unless explicitly allowed
2. Deny statements always override Allow statements
3. Make minimal, targeted changes to fix specific failures
4. Preserve existing working functionality

REPAIR METHODOLOGY:
1. For each failed request, identify the root cause:
   - Implicit deny: No Allow statement covers the request → Add specific Allow
   - Explicit deny: Deny statement blocks required request → Make Deny more specific or add Allow exception
   - Overpermissive allow: Allow statement permits unwanted request → Add constraints or specific Deny

2. Apply fixes systematically:
   - Use Principal/Condition constraints to narrow scope rather than changing Effect
   - Add new statements only when necessary
   - Ensure all requirements are satisfied

3. Validate your changes mentally:
   - Trace each failed request through your repaired policy
   - Ensure the repair doesn't break existing working requests

OUTPUT REQUIREMENTS:
- Return ONLY valid JSON policy
- No explanations, comments, or markdown formatting
- Ensure all JSON syntax is correct
- Include required fields: Version, Statement"""

# Enhanced repair function using the improved prompts
@retry()
def repair_policy_with_targeted_approach(policy: dict, requirements: dict, iteration: int = 1, 
                                       erroneous_policy: dict = None, failed_examples: list = None) -> dict:
    """Enhanced policy repair with better structured information feeding"""
    
    if not failed_examples:
        failed_examples = []
    
    # Use enhanced prompt generation
    prompt = create_enhanced_repair_prompt(
        policy, requirements, failed_examples, erroneous_policy, iteration
    )
    
    system_prompt = create_enhanced_system_prompt()
    
    # Enhanced logging
    logging.info(f"{'='*80}")
    logging.info(f"ENHANCED REPAIR - ITERATION {iteration}")
    logging.info(f"{'='*80}")
    
    if failed_examples:
        allow_failures = [ex for ex in failed_examples if ex.get('expected', '').lower() == 'allow']
        deny_failures = [ex for ex in failed_examples if ex.get('expected', '').lower() == 'deny']
        logging.info(f"Failed examples breakdown:")
        logging.info(f"  - Wrongly denied (should allow): {len(allow_failures)}")
        logging.info(f"  - Wrongly allowed (should deny): {len(deny_failures)}")
        
        # Log specific examples for debugging
        if allow_failures:
            logging.info(f"  Sample wrongly denied requests:")
            for ex in allow_failures[:3]:
                logging.info(f"    • {ex.get('request_id')}: {ex.get('action')} on {ex.get('resource')}")
        
        if deny_failures:
            logging.info(f"  Sample wrongly allowed requests:")
            for ex in deny_failures[:3]:
                logging.info(f"    • {ex.get('request_id')}: {ex.get('action')} on {ex.get('resource')}")
    
    if erroneous_policy:
        faulty_count = len(erroneous_policy.get('Statement', []))
        logging.info(f"SMT erroneous policy: {faulty_count} faulty statements")
    
    logging.info(f"Prompt length: {len(prompt)} characters")
    logging.info(f"{'='*80}")
    
    # Call LLM
    response_text = call_ollama(prompt, system_prompt)
    
    # Enhanced response logging
    logging.info(f"{'='*80}")
    logging.info(f"LLM RESPONSE - ITERATION {iteration}")
    logging.info(f"{'='*80}")
    logging.info(f"Response length: {len(response_text)} characters")
    logging.info(f"Response preview: {response_text[:200]}...")
    logging.info(f"{'='*80}")
    
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
    
    changes_made = 0
    for i in range(max(len(original_statements), len(repaired_statements))):
        orig_stmt = original_statements[i] if i < len(original_statements) else None
        repair_stmt = repaired_statements[i] if i < len(repaired_statements) else None
        
        if orig_stmt != repair_stmt:
            changes_made += 1
            if orig_stmt is None:
                logging.info(f"    Statement {i+1}: ADDED")
            elif repair_stmt is None:
                logging.info(f"    Statement {i+1}: REMOVED")
            else:
                change_details = []
                if orig_stmt.get('Effect') != repair_stmt.get('Effect'):
                    change_details.append(f"Effect: {orig_stmt.get('Effect')} → {repair_stmt.get('Effect')}")
                if orig_stmt.get('Action') != repair_stmt.get('Action'):
                    change_details.append("Action modified")
                if orig_stmt.get('Resource') != repair_stmt.get('Resource'):
                    change_details.append("Resource modified")
                if orig_stmt.get('Principal') != repair_stmt.get('Principal'):
                    change_details.append("Principal modified")
                if orig_stmt.get('Condition') != repair_stmt.get('Condition'):
                    change_details.append("Condition modified")
                
                logging.info(f"    Statement {i+1}: MODIFIED ({', '.join(change_details)})")
    
    logging.info(f"  Total changes made: {changes_made}")
    logging.info(f"{'='*80}")
    
    return repaired_policy

def generate_focused_repair_prompt_with_failed_examples(current_policy, requirements, erroneous_policy, failed_examples, iteration):
    """
    Helper function that includes both SMT analysis and failed request examples in the prompt
    """
    
    faulty_statements = erroneous_policy.get('Statement', []) if erroneous_policy else []
    analysis_results = erroneous_policy.get('analysis_result', []) if erroneous_policy else []
    
    # FILTER REQUIREMENTS TO ONLY RELEVANT ONES
    filtered_requirements = {"Requests": []}
    
    if failed_examples and "Requests" in requirements:
        # Get unique request IDs from failed examples
        failed_request_ids = set()
        for example in failed_examples:
            request_id = example.get('request_id', '')
            if request_id:
                failed_request_ids.add(request_id)
        
        # Only include requirements that match failed request IDs
        for req in requirements["Requests"]:
            if req.get('id') in failed_request_ids:
                filtered_requirements["Requests"].append(req)
        
        logging.info(f"Filtered requirements: {len(requirements['Requests'])} -> {len(filtered_requirements['Requests'])}")
    else:
        # If no failed examples, include all (fallback for iteration 1)
        printing(f"Using all requirements as no failed examples provided")
        filtered_requirements = requirements
    
    # Extract specific requirements for context
    allow_requirements = []
    deny_requirements = []
    
    if "Requests" in filtered_requirements:
        for req in filtered_requirements["Requests"]:
            if req.get("Effect", "").lower() == "allow":
                allow_requirements.append(req)
            else:
                deny_requirements.append(req)
    
    prompt = f"""You are an AWS IAM policy expert. Fix this policy using both SMT solver analysis and specific failed request examples.

CURRENT POLICY TO FIX:
{json.dumps(current_policy, indent=2)}

"""

    # Add SMT solver analysis of faulty statements if available
    if faulty_statements and analysis_results:
        prompt += f"""SMT SOLVER IDENTIFIED {len(faulty_statements)} PROBLEMATIC STATEMENTS:

"""
        for i, (stmt, analysis) in enumerate(zip(faulty_statements, analysis_results)):
            stmt_effect = stmt.get('Effect', 'Unknown')
            stmt_actions = stmt.get('Action', [])
            stmt_resources = stmt.get('Resource', [])
            stmt_sid = stmt.get('Sid', f'Statement{i+1}')
            
            prompt += f"""FAULTY STATEMENT {i+1} - ID: {stmt_sid}
Current Statement:
{json.dumps(stmt, indent=2)}

SMT Analysis: {analysis}

"""

    # Add specific failed request examples if available
    if failed_examples and len(failed_examples) > 0:
        prompt += f"""SPECIFIC FAILED REQUEST EXAMPLES ({len(failed_examples)} failures):

"""
        # Group by failure type for better organization
        allow_to_deny_failures = [ex for ex in failed_examples if ex.get('expected', '').lower() == 'allow' and ex.get('actual', '').lower() == 'deny']
        deny_to_allow_failures = [ex for ex in failed_examples if ex.get('expected', '').lower() == 'deny' and ex.get('actual', '').lower() == 'allow']
        
        if allow_to_deny_failures:
            prompt += f"""CRITICAL: {len(allow_to_deny_failures)} requests that should be ALLOWED are being DENIED:
"""
            for i, failure in enumerate(allow_to_deny_failures[:5], 1):  # Show top 5
                prompt += f"""  {i}. Request ID: {failure.get('request_id', 'unknown')}
     Action: {failure.get('action', 'unknown')}
     Resource: {failure.get('resource', 'unknown')}"""
                if failure.get('principal'):
                    prompt += f"\n     Principal: {failure.get('principal')}"
                if failure.get('condition'):
                    prompt += f"\n     Condition: {failure.get('condition')}"
                prompt += f"""
     PROBLEM: Expected ALLOW but got DENY
     
"""
        
        if deny_to_allow_failures:
            prompt += f"""WARNING: {len(deny_to_allow_failures)} requests that should be DENIED are being ALLOWED:
"""
            for i, failure in enumerate(deny_to_allow_failures[:5], 1):  # Show top 5
                prompt += f"""  {i}. Request ID: {failure.get('request_id', 'unknown')}
     Action: {failure.get('action', 'unknown')}
     Resource: {failure.get('resource', 'unknown')}"""
                if failure.get('principal'):
                    prompt += f"\n     Principal: {failure.get('principal')}"
                if failure.get('condition'):
                    prompt += f"\n     Condition: {failure.get('condition')}"
                prompt += f"""
     PROBLEM: Expected DENY but got ALLOW
     
"""

    # ONLY ADD FILTERED REQUIREMENTS (not the full set)
    if len(filtered_requirements.get("Requests", [])) > 0:
        prompt += f"""
# RELEVANT REQUEST FOR CONTEXT (not all requirements are needed, only those related to failed requests):
# """
        
#         if allow_requirements:
#             prompt += "\nMUST ALLOW (these requests should get Effect: Allow):\n"
#             for req in allow_requirements:
#                 prompt += f"  {req.get('id')}: {req.get('Action')} on {req.get('Resource')}"
#                 if req.get('Principal'):
#                     prompt += f" for Principal: {req.get('Principal')}"
#                 if req.get('Condition'):
#                     prompt += f" when Condition: {req.get('Condition')}"
#                 prompt += "\n"
        
#         if deny_requirements:
#             prompt += "\nMUST DENY (these requests should get Effect: Deny):\n"
#             for req in deny_requirements:
#                 prompt += f"  {req.get('id')}: {req.get('Action')} on {req.get('Resource')}"
#                 if req.get('Principal'):
#                     prompt += f" for Principal: {req.get('Principal')}"
#                 if req.get('Condition'):
#                     prompt += f" when Condition: {req.get('Condition')}"
#                 prompt += "\n"

    prompt += f"""
    
REPAIR INSTRUCTIONS (You MUST follow these strict principles):
1. Use the SMT analysis to identify which statements are problematic
2. Instead of creating new statments for every failed request, group them into deny and request sets and repair
3. Do not create duplicated statments in the policy, only modify existing ones using the examples that are failed. 
4. Classify each failure type and apply appropriate repair strategy:
  
  IMPLICIT DENY (no matching Allow): Add new Allow statement covering the request
  - Effect: "Allow" with specific Action/Resource from failed request
  - Add Principal/Condition constraints if specified in requirements
  
  EXPLICIT DENY (blocked by Deny statement): Make Deny more specific
  - Add Principal/Condition constraints to limit scope of denial
  - Make Actions/Resources more specific rather than changing Effect
  
  EXPLICIT ALLOW (wrongly permitted): Make Allow more restrictive  
  - Add Principal/Condition constraints to limit who can access
  - Narrow Actions/Resources scope or add specific Deny statement

3. Use the failed request examples to understand exactly what's going wrong
4. Make MINIMAL changes - prefer constraints over Effect changes
5. Test your repair logic mentally before applying changes

CRITICAL FIXES NEEDED:
"""

    # Map failed examples to required fixes
    if failed_examples and len(failed_examples) > 0:
        for i, failure in enumerate(failed_examples[:3], 1):  # Top 3 most critical
            prompt += f"""
Fix {i}: Request {failure.get('request_id')} 
- Action: {failure.get('action')} on Resource: {failure.get('resource')}
- Currently: {failure.get('actual')} but should be: {failure.get('expected')}
"""

    prompt += f"""

OUTPUT INSTRUCTIONS:
Return ONLY the complete corrected policy as valid JSON. No explanations, no markdown formatting.

CORRECTED POLICY:"""

    return prompt


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
            'erroneous_policy': erroneous_policy,  
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
    """Process a single policy with erroneous policy guided repair using both analysis and failed examples"""
    policy_file = os.path.join(POLICY_DIR, f"{idx}.json")
    req_file = os.path.join(REQUIREMENTS_DIR, f"{idx}.json")
    
    if not os.path.exists(policy_file) or not os.path.exists(req_file):
        raise FileNotFoundError(f"Missing files for index {idx}")
    
    original_policy = load_json_file(policy_file)
    requirements = load_json_file(req_file)
    
    logging.info(f"Starting enhanced repair for policy {idx} (baseline: {baseline_accuracy:.1f}%)...")
    if baseline_failed_examples:
        logging.info(f"Using {len(baseline_failed_examples)} failed request examples")
    if baseline_erroneous_policy:
        logging.info(f"Using erroneous policy analysis")
    
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
    current_failed_examples = baseline_failed_examples or []
    final_accuracy = baseline_accuracy
    iteration_accuracies = [baseline_accuracy]
    
    for iteration in range(1, MAX_ITERATIONS + 1):
        logging.info(f"Policy {idx} - Iteration {iteration}/{MAX_ITERATIONS} (Previous: {final_accuracy:.1f}%)")
        
        iteration_success = False
        iteration_accuracy = 0.0
        iteration_policy_file = None
        
        try:
            logging.info(f"Repairing policy with enhanced guidance (iteration {iteration})...")
            
            if current_erroneous_policy:
                logging.info(f"Using erroneous policy with {len(current_erroneous_policy.get('Statement', []))} faulty statements")
            if current_failed_examples:
                logging.info(f"Using {len(current_failed_examples)} failed request examples")
            
            # Use BOTH erroneous policy AND failed examples for comprehensive repair
            repaired_policy = repair_policy_with_targeted_approach(
                current_policy, requirements, iteration, current_erroneous_policy, current_failed_examples
            )
            
            temp_policy_file = os.path.join(TEMP_DIR, f"policy_{idx}_iter_{iteration}.json")
            os.makedirs(TEMP_DIR, exist_ok=True)
            save_json_file(repaired_policy, temp_policy_file)
            
            logging.info(f"Validating with SMT solver (iteration {iteration})...")
            validation_results = run_smt_validator(temp_policy_file, req_file, policy_idx=idx)
            
            accuracy = validation_results['accuracy']
            iteration_accuracy = accuracy  # Store for tracking
            iteration_policy_file = temp_policy_file  # Store for tracking
            
            # Update failed examples and erroneous policy for next iteration
            current_failed_examples = validation_results.get('failed_examples', [])
            current_erroneous_policy = validation_results.get('erroneous_policy')
            
            # ALWAYS append iteration accuracy before any potential exceptions
            iteration_accuracies.append(accuracy)
            improvement = accuracy - baseline_accuracy
            
            logging.info(f"Iteration {iteration} Results:")
            logging.info(f"  Accuracy: {accuracy:.1f}% (Baseline: {baseline_accuracy:.1f}%, Improvement: {improvement:+.1f}%)")
            logging.info(f"  New Failed Examples: {len(current_failed_examples)}")
            if current_erroneous_policy:
                logging.info(f"  New erroneous policy has {len(current_erroneous_policy.get('Statement', []))} faulty statements")
            
            # Create iteration record BEFORE success check
            iteration_record = {
                'policy_idx': idx,
                'iteration': iteration,
                'validation_type': 'repair_with_examples',
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
            
        except Exception as e:
            logging.error(f"Error in iteration {iteration} for policy {idx}: {e}")
            
            # If we haven't recorded the iteration yet, add an error record
            if not any(record.get('iteration') == iteration for record in iteration_results):
                iteration_record = {
                    'policy_idx': idx,
                    'iteration': iteration,
                    'validation_type': 'repair_with_examples',
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

    # If we reach here, we didn't achieve target accuracy
    # Find the best iteration result
    best_accuracy = baseline_accuracy
    best_iteration = None

    if iteration_results:
        logging.info(f"Policy {idx}: All iteration results:")
        for i, result in enumerate(iteration_results):
            logging.info(f"  Iteration {result.get('iteration')}: {result.get('accuracy', 0):.1f}% - File: {result.get('policy_file')}")
        
        best_iteration = max(iteration_results, key=lambda x: x.get('accuracy', 0))
        best_accuracy = best_iteration.get('accuracy', baseline_accuracy)
        best_file = best_iteration.get('policy_file')
        best_iter_num = best_iteration.get('iteration')
        
        logging.info(f"Policy {idx}: Selected best iteration {best_iter_num} with accuracy {best_accuracy:.1f}%")
        
        if ('policy_file' in best_iteration and best_iteration['policy_file'] is not None and os.path.exists(best_iteration['policy_file'])):
            final_output_file = os.path.join(OUTPUT_DIR, f"repaired_{idx}_best.json")
            shutil.copy2(best_iteration['policy_file'], final_output_file)
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
            "ba seline_accuracy": baseline_accuracy,
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
    print("improved Counter-Example Guided Policy Repair System")
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
    print("- Targeted repair prompts based on erroneous policy structure")
    print("- Focus on SMT solver identified faulty statements only")
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
                    logging.info(f"Policy {idx} baseline: {baseline_accuracy:.1f}% accuracy")
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
    
    # Save baseline results
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
        print(f"Successfully validated policies: {len(successful_baselines)}")
        print(f"Failed baseline validations: {len(failed_baselines)}")
        print(f"Average baseline accuracy: {avg_baseline_accuracy:.1f}%")
        print(f"Policies already at target accuracy: {len(perfect_baselines)}")
        
        if perfect_baselines:
            perfect_indices = [r['policy_idx'] for r in perfect_baselines]
            print(f"Perfect baseline policies: {perfect_indices}")
    
    print(f"{'='*60}")
    
    # Step 2: Improved counter-example guided repair
    print("\nSTEP 2: IMPROVED COUNTER-EXAMPLE GUIDED REPAIR")
    print("=" * 60)
    
    baseline_accuracy_map = {r['policy_idx']: r.get('accuracy', 0.0) for r in baseline_results}
    baseline_erroneous_policy_map = {r['policy_idx']: r.get('erroneous_policy') for r in baseline_results}
    
    to_process = [i for i in range(total) if not tracker.is_done(i)]
    logging.info(f"Policies to process for improved repair: {to_process}")
    
    all_results = []
    all_iteration_data = baseline_results.copy()
    
    # Process each policy - ONLY use erroneous policy, no failed examples
    for idx in tqdm(to_process, desc="Processing policies with improved repair"):
        try:
            baseline_acc = baseline_accuracy_map.get(idx, 0.0)
            baseline_erroneous = baseline_erroneous_policy_map.get(idx)
            
            # Pass None for failed examples - only use erroneous policy
            result = process_policy_with_improved_repair(idx, baseline_acc, None, baseline_erroneous)
            
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
    
    # Save comprehensive results
    
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
    
    # Save failed examples analysis (only from baseline - no iteration failed examples)
    failed_examples_analysis = []
    
    # Include baseline failed examples only
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
            print(f"  Policy {idx}: {baseline:.1f}% -> {final:.1f}% (already perfect)")
        elif status == 'success':
            print(f"  Policy {idx}: {baseline:.1f}% -> {final:.1f}% (SUCCESS in {iterations} iterations, +{improvement:.1f}%)")
        elif status == 'failed':
            print(f"  Policy {idx}: {baseline:.1f}% -> {final:.1f}% (failed after {iterations} iterations, +{improvement:.1f}%)")
        else:
            print(f"  Policy {idx}: {baseline:.1f}% -> {final:.1f}% (ERROR: {result.get('error', 'unknown')})")

    print(f"{'='*60}")
    print("Results files:")
    print(f"  - Baseline: baseline_results_improved.csv")
    print(f"  - Summary: improved_repair_summary.csv")
    print(f"  - Detailed iterations: improved_repair_details.csv")
    print(f"  - Failed examples: improved_repair_failed_examples.csv")
    print(f"  - Progress tracker: {tracker.progress_file}")
    print(f"{'='*60}")
    print("\nKEY IMPROVEMENTS:")
    print("- Detailed analysis of SMT solver erroneous policy output")
    print("- Targeted repair prompts based on faulty statement structure")
    print("- Clean separation from failed request examples")
    print("- Structured approach to requirement matching")
    print("- Enhanced error handling and JSON parsing")

    # Cleanup
    if os.path.exists(TEMP_DIR):
        logging.info(f"Temporary files kept for analysis in: {TEMP_DIR}")
        
def cleanup_previous_run():
    directories_to_clean = [
        OUTPUT_DIR,
        TEMP_DIR,
        os.path.join(OUTPUT_DIR, "Quacky_output")
    ]
    
    for directory in directories_to_clean:
        if os.path.exists(directory):
            shutil.rmtree(directory)
            logging.info(f"Cleaned previous run data from {directory}")
    
    # Recreate the directories
    for directory in directories_to_clean:
        os.makedirs(directory, exist_ok=True)
        
if __name__ == "__main__":
    main()