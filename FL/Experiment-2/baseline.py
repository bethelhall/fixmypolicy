#!/usr/bin/env python3
"""
baseline_validation_only.py

Standalone script to run baseline validation on all available policies.
This helps understand the current state before attempting repairs.
"""

import os
import sys
import time
import json
import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path
import pandas as pd
from tqdm import tqdm

# Directory configurations (update these paths as needed)
POLICY_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-2/original_policy"
REQUIREMENTS_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-2/requests/request-10"
OUTPUT_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-2/results/baseline-only"
LOG_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-2/logs/baseline-only"
QUACKY_SRC_DIR = "/home/bhall2/Documents/fixmypolicy/quacky/src"
SMT_VALIDATOR_SCRIPT = "/home/bhall2/Documents/fixmypolicy/quacky/src/validate_requests.py"

def setup_logging(log_dir: str = LOG_DIR):
    """Configure logging"""
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f'baseline_validation_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return log_file

def get_available_indices():
    """Get list of indices that have both policy and requirement files"""
    available = []
    
    if not os.path.exists(POLICY_DIR) or not os.path.exists(REQUIREMENTS_DIR):
        return available
    
    policy_files = set()
    req_files = set()
    
    # Get available policy files
    try:
        for file in os.listdir(POLICY_DIR):
            if file.endswith('.json'):
                filename = file.replace('.json', '')
                if filename.isdigit():
                    policy_files.add(int(filename))
                else:
                    # Handle non-numeric filenames
                    policy_files.add(filename)
    except Exception as e:
        logging.error(f"Error reading policy directory: {e}")
    
    # Get available requirement files
    try:
        for file in os.listdir(REQUIREMENTS_DIR):
            if file.endswith('.json'):
                filename = file.replace('.json', '')
                if filename.isdigit():
                    req_files.add(int(filename))
                else:
                    # Handle non-numeric filenames
                    req_files.add(filename)
    except Exception as e:
        logging.error(f"Error reading requirements directory: {e}")
    
    # Find intersection
    available = sorted(list(policy_files.intersection(req_files)))
    return available

def extract_failed_examples(output_content: str) -> list:
    """Extract failed examples from validator output"""
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
                    if condition_val != "None":
                        try:
                            condition_json = condition_val.replace("'", '"')
                            json.loads(condition_json)
                            current_request["condition"] = condition_json
                        except:
                            current_request["condition"] = condition_val
                    else:
                        current_request["condition"] = None
        
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
        
        elif "CORRECT:" in line or "Processing request object:" in line:
            current_request = None
    
    logging.debug(f"Extracted {len(failed_examples)} failed examples from validator output")
    return failed_examples

def run_smt_validator(policy_file: str, requests_file: str, policy_idx) -> dict:
    """Run the SMT validator and return parsed results"""
    try:
        original_dir = os.getcwd()
        os.chdir(QUACKY_SRC_DIR)
        
        quacky_output_dir = os.path.join(OUTPUT_DIR, "Quacky_output")
        os.makedirs(quacky_output_dir, exist_ok=True)
        
        timestamp = int(time.time())
        pid = os.getpid()
        output_file_path = os.path.join(quacky_output_dir, f"baseline_validation_{policy_idx}_{pid}_{timestamp}.txt")
        
        cmd = [
            'python3', 'validate_requests.py',
            '-p1', policy_file,
            '--requests', requests_file,
            '-s'
        ]
        
        logging.info(f"Running SMT validator for policy {policy_idx}: cd {QUACKY_SRC_DIR} && {' '.join(cmd)} > {output_file_path}")
        
        with open(output_file_path, 'w') as output_file:
            result = subprocess.run(cmd, stdout=output_file, stderr=subprocess.PIPE, text=True, timeout=300)
        
        os.chdir(original_dir)
        
        if result.returncode != 0:
            logging.error(f"SMT validator failed for policy {policy_idx}: {result.stderr}")
            if os.path.exists(output_file_path):
                with open(output_file_path, 'r') as f:
                    output_content = f.read()
                logging.error(f"Validator stdout: {output_content}")
            raise Exception(f"SMT validator failed: {result.stderr}")
        
        with open(output_file_path, 'r') as f:
            output_content = f.read()
        
        # Parse validation results
        output_lines = output_content.split('\n')
        accuracy = 0.0
        total_requests = 0
        correct_count = 0
        incorrect_count = 0
        misclassified_allow_to_deny = 0
        misclassified_deny_to_allow = 0
        
        in_analysis_section = False
        for i, line in enumerate(output_lines):
            line = line.strip()
            
            if "INDIVIDUAL REQUEST ANALYSIS" in line:
                in_analysis_section = True
                continue
            elif line.startswith("=") and in_analysis_section and len(line) > 10:
                if any(phrase in ''.join(output_lines[i:i+5]) for phrase in ["Results saved", "saved to HOME"]):
                    break
            
            if in_analysis_section:
                if line.startswith("Total Individual Requests:"):
                    total_match = re.search(r'(\d+)', line)
                    if total_match:
                        total_requests = int(total_match.group(1))
                elif line.startswith("Correct Classifications:"):
                    correct_match = re.search(r'(\d+)', line)
                    if correct_match:
                        correct_count = int(correct_match.group(1))
                elif line.startswith("Incorrect Classifications:"):
                    incorrect_match = re.search(r'(\d+)', line)
                    if incorrect_match:
                        incorrect_count = int(incorrect_match.group(1))
                elif line.startswith("Overall Accuracy:"):
                    accuracy_match = re.search(r'(\d+\.?\d*)%', line)
                    if accuracy_match:
                        accuracy = float(accuracy_match.group(1))
                elif line.startswith("Expected Allow -> Got Deny:"):
                    allow_deny_match = re.search(r'(\d+)', line)
                    if allow_deny_match:
                        misclassified_allow_to_deny = int(allow_deny_match.group(1))
                elif line.startswith("Expected Deny -> Got Allow:"):
                    deny_allow_match = re.search(r'(\d+)', line)
                    if deny_allow_match:
                        misclassified_deny_to_allow = int(deny_allow_match.group(1))
        
        failed_examples = extract_failed_examples(output_content)
        
        logging.info(f"Policy {policy_idx} validation completed - Accuracy: {accuracy}%, Total: {total_requests}, Correct: {correct_count}, Incorrect: {incorrect_count}")
        
        return {
            'policy_idx': policy_idx,
            'accuracy': accuracy,
            'total_requests': total_requests,
            'correct': correct_count,
            'incorrect': incorrect_count,
            'misclassified_allow_to_deny': misclassified_allow_to_deny,
            'misclassified_deny_to_allow': misclassified_deny_to_allow,
            'failed_examples': failed_examples,
            'failed_examples_count': len(failed_examples),
            'raw_output': output_content,
            'output_file': output_file_path
        }
        
    except subprocess.TimeoutExpired:
        try:
            os.chdir(original_dir)
        except:
            pass
        logging.error(f"SMT validator timed out for policy {policy_idx}")
        raise Exception(f"SMT validator timed out for policy {policy_idx}")
    except Exception as e:
        try:
            os.chdir(original_dir)
        except:
            pass
        logging.error(f"Error running SMT validator for policy {policy_idx}: {e}")
        raise

def load_json_file(path: str) -> dict:
    """Load JSON file with error handling"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Error loading JSON file {path}: {e}")
        raise

def analyze_policy_and_requirements(policy_idx, policy_data, requirements_data):
    """Analyze the structure of policy and requirements"""
    analysis = {
        'policy_idx': policy_idx,
        'policy_structure': {},
        'requirements_structure': {}
    }
    
    # Analyze policy structure
    if isinstance(policy_data, dict):
        analysis['policy_structure'] = {
            'version': policy_data.get('Version', 'Not specified'),
            'statement_count': len(policy_data.get('Statement', [])),
            'has_allow_statements': False,
            'has_deny_statements': False,
            'actions': set(),
            'resources': set()
        }
        
        for stmt in policy_data.get('Statement', []):
            effect = stmt.get('Effect', '').lower()
            if effect == 'allow':
                analysis['policy_structure']['has_allow_statements'] = True
            elif effect == 'deny':
                analysis['policy_structure']['has_deny_statements'] = True
            
            # Collect actions
            actions = stmt.get('Action', [])
            if isinstance(actions, str):
                analysis['policy_structure']['actions'].add(actions)
            elif isinstance(actions, list):
                analysis['policy_structure']['actions'].update(actions)
            
            # Collect resources
            resources = stmt.get('Resource', [])
            if isinstance(resources, str):
                analysis['policy_structure']['resources'].add(resources)
            elif isinstance(resources, list):
                analysis['policy_structure']['resources'].update(resources)
    
    # Analyze requirements structure
    if isinstance(requirements_data, dict) and 'Requests' in requirements_data:
        requests = requirements_data['Requests']
        analysis['requirements_structure'] = {
            'total_requests': len(requests),
            'allow_requests': len([r for r in requests if r.get('Effect', '').lower() == 'allow']),
            'deny_requests': len([r for r in requests if r.get('Effect', '').lower() == 'deny']),
            'required_actions': set(),
            'required_resources': set()
        }
        
        for req in requests:
            actions = req.get('Action', [])
            if isinstance(actions, str):
                analysis['requirements_structure']['required_actions'].add(actions)
            elif isinstance(actions, list):
                analysis['requirements_structure']['required_actions'].update(actions)
            
            resources = req.get('Resource', [])
            if isinstance(resources, str):
                analysis['requirements_structure']['required_resources'].add(resources)
            elif isinstance(resources, list):
                analysis['requirements_structure']['required_resources'].update(resources)
    
    # Convert sets to lists for JSON serialization
    for key in ['actions', 'resources']:
        if key in analysis['policy_structure']:
            analysis['policy_structure'][key] = list(analysis['policy_structure'][key])
    
    for key in ['required_actions', 'required_resources']:
        if key in analysis['requirements_structure']:
            analysis['requirements_structure'][key] = list(analysis['requirements_structure'][key])
    
    return analysis

def main():
    """Main function for baseline validation only"""
    log_file = setup_logging()
    logging.info("Starting baseline validation system - Experiment 2")
    
    print("=" * 70)
    print("BASELINE VALIDATION SYSTEM - EXPERIMENT 2")
    print("=" * 70)
    
    # Check directories
    print("📁 Checking directories...")
    for directory, name in [
        (POLICY_DIR, "Policy directory"),
        (REQUIREMENTS_DIR, "Requirements directory"),
        (QUACKY_SRC_DIR, "Quacky source directory")
    ]:
        if os.path.exists(directory):
            print(f"  ✅ {name}: {directory}")
        else:
            print(f"  ❌ {name}: {directory} (NOT FOUND)")
            logging.error(f"{name} not found: {directory}")
            sys.exit(1)
    
    # Check SMT validator script
    if os.path.exists(SMT_VALIDATOR_SCRIPT):
        print(f"  ✅ SMT validator: {SMT_VALIDATOR_SCRIPT}")
    else:
        print(f"  ❌ SMT validator: {SMT_VALIDATOR_SCRIPT} (NOT FOUND)")
        logging.error(f"SMT validator script not found: {SMT_VALIDATOR_SCRIPT}")
        sys.exit(1)
    
    # Create output directories
    for directory in [OUTPUT_DIR, os.path.join(OUTPUT_DIR, "Quacky_output")]:
        os.makedirs(directory, exist_ok=True)
    
    # Get available policy-requirement pairs
    print("\n🔍 Scanning for available policy-requirement pairs...")
    available_indices = get_available_indices()
    
    if not available_indices:
        print("  ❌ No matching policy-requirement pairs found!")
        print(f"     Policy directory: {POLICY_DIR}")
        print(f"     Requirements directory: {REQUIREMENTS_DIR}")
        logging.error("No matching policy-requirement pairs found")
        sys.exit(1)
    
    print(f"  ✅ Found {len(available_indices)} policy-requirement pairs:")
    print(f"     Indices: {available_indices}")
    
    # Run baseline validation
    print(f"\n{'='*70}")
    print("BASELINE VALIDATION")
    print(f"{'='*70}")
    
    baseline_results = []
    policy_analyses = []
    
    for idx in tqdm(available_indices, desc="Running baseline validation"):
        policy_file = os.path.join(POLICY_DIR, f"{idx}.json")
        req_file = os.path.join(REQUIREMENTS_DIR, f"{idx}.json")
        
        try:
            # Load files for analysis
            policy_data = load_json_file(policy_file)
            requirements_data = load_json_file(req_file)
            
            # Analyze structure
            analysis = analyze_policy_and_requirements(idx, policy_data, requirements_data)
            policy_analyses.append(analysis)
            
            logging.info(f"Running baseline validation for policy {idx}...")
            print(f"\n📊 Policy {idx}:")
            print(f"  Policy statements: {analysis['policy_structure'].get('statement_count', 0)}")
            print(f"  Required requests: {analysis['requirements_structure'].get('total_requests', 0)}")
            print(f"  Allow requests: {analysis['requirements_structure'].get('allow_requests', 0)}")
            print(f"  Deny requests: {analysis['requirements_structure'].get('deny_requests', 0)}")
            
            # Run validation
            validation_result = run_smt_validator(policy_file, req_file, idx)
            
            # Add analysis data to validation result
            validation_result.update({
                'policy_statements': analysis['policy_structure'].get('statement_count', 0),
                'total_requirements': analysis['requirements_structure'].get('total_requests', 0),
                'allow_requirements': analysis['requirements_structure'].get('allow_requests', 0),
                'deny_requirements': analysis['requirements_structure'].get('deny_requests', 0)
            })
            
            baseline_results.append(validation_result)
            
            print(f"  🎯 Accuracy: {validation_result['accuracy']:.1f}%")
            print(f"  ✅ Correct: {validation_result['correct']}")
            print(f"  ❌ Incorrect: {validation_result['incorrect']}")
            print(f"  🔍 Failed examples: {validation_result['failed_examples_count']}")
            
            if validation_result['failed_examples_count'] > 0:
                print(f"     Failed breakdown:")
                print(f"       Allow→Deny: {validation_result['misclassified_allow_to_deny']}")
                print(f"       Deny→Allow: {validation_result['misclassified_deny_to_allow']}")
            
        except Exception as e:
            logging.error(f"Baseline validation failed for policy {idx}: {e}")
            print(f"  ❌ ERROR: {str(e)}")
            
            baseline_results.append({
                'policy_idx': idx,
                'accuracy': 0.0,
                'total_requests': 0,
                'correct': 0,
                'incorrect': 0,
                'misclassified_allow_to_deny': 0,
                'misclassified_deny_to_allow': 0,
                'failed_examples_count': 0,
                'failed_examples': [],
                'error': str(e)
            })
    
    # Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Baseline results CSV
    if baseline_results:
        baseline_df = pd.DataFrame(baseline_results)
        baseline_csv = os.path.join(OUTPUT_DIR, f"baseline_results_{timestamp}.csv")
        baseline_df.to_csv(baseline_csv, index=False)
        logging.info(f"Baseline results saved to {baseline_csv}")
        print(f"\n💾 Results saved to: {baseline_csv}")
    
    # Policy analysis JSON
    if policy_analyses:
        analysis_file = os.path.join(OUTPUT_DIR, f"policy_analysis_{timestamp}.json")
        with open(analysis_file, 'w') as f:
            json.dump(policy_analyses, f, indent=2)
        logging.info(f"Policy analysis saved to {analysis_file}")
        print(f"📊 Analysis saved to: {analysis_file}")
    
    # Failed examples detailed CSV
    failed_examples_data = []
    for result in baseline_results:
        if result.get('failed_examples'):
            for example in result['failed_examples']:
                failed_examples_data.append({
                    'policy_idx': result['policy_idx'],
                    'request_id': example['request_id'],
                    'action': example['action'],
                    'resource': example['resource'],
                    'principal': example.get('principal'),
                    'condition': example.get('condition'),
                    'expected': example['expected'],
                    'actual': example['actual']
                })
    
    if failed_examples_data:
        failed_df = pd.DataFrame(failed_examples_data)
        failed_csv = os.path.join(OUTPUT_DIR, f"failed_examples_{timestamp}.csv")
        failed_df.to_csv(failed_csv, index=False)
        logging.info(f"Failed examples saved to {failed_csv}")
        print(f"🔍 Failed examples saved to: {failed_csv}")
    
    # Summary statistics
    print(f"\n{'='*70}")
    print("BASELINE VALIDATION SUMMARY")
    print(f"{'='*70}")
    
    successful_validations = [r for r in baseline_results if 'error' not in r]
    failed_validations = [r for r in baseline_results if 'error' in r]
    
    if successful_validations:
        accuracies = [r['accuracy'] for r in successful_validations]
        avg_accuracy = sum(accuracies) / len(accuracies)
        min_accuracy = min(accuracies)
        max_accuracy = max(accuracies)
        
        perfect_policies = len([r for r in successful_validations if r['accuracy'] >= 100.0])
        good_policies = len([r for r in successful_validations if r['accuracy'] >= 80.0])
        poor_policies = len([r for r in successful_validations if r['accuracy'] < 50.0])
        
        total_failed_examples = sum(r['failed_examples_count'] for r in successful_validations)
        
        print(f"📊 STATISTICS:")
        print(f"  Total policies processed: {len(baseline_results)}")
        print(f"  Successful validations: {len(successful_validations)}")
        print(f"  Failed validations: {len(failed_validations)}")
        print(f"")
        print(f"🎯 ACCURACY DISTRIBUTION:")
        print(f"  Average accuracy: {avg_accuracy:.1f}%")
        print(f"  Min accuracy: {min_accuracy:.1f}%")
        print(f"  Max accuracy: {max_accuracy:.1f}%")
        print(f"  Perfect policies (100%): {perfect_policies}")
        print(f"  Good policies (≥80%): {good_policies}")
        print(f"  Poor policies (<50%): {poor_policies}")
        print(f"")
        print(f"❌ FAILED EXAMPLES:")
        print(f"  Total failed examples: {total_failed_examples}")
        print(f"  Average per policy: {total_failed_examples/len(successful_validations):.1f}")
        
        # Show individual results
        print(f"\n📋 INDIVIDUAL RESULTS:")
        for result in successful_validations:
            idx = result['policy_idx']
            acc = result['accuracy']
            failed = result['failed_examples_count']
            total = result['total_requests']
            
            if acc >= 100.0:
                status = "PERFECT ✅"
            elif acc >= 80.0:
                status = "GOOD 🟢"
            elif acc >= 50.0:
                status = "FAIR 🟡"
            else:
                status = "POOR 🔴"
            
            print(f"  Policy {idx}: {acc:.1f}% ({result['correct']}/{total}) - {failed} failed - {status}")
        
        if failed_validations:
            print(f"\n❌ FAILED VALIDATIONS:")
            for result in failed_validations:
                print(f"  Policy {result['policy_idx']}: {result.get('error', 'Unknown error')}")
    
    else:
        print("❌ No successful validations!")
    
    print(f"\n{'='*70}")
    print("NEXT STEPS:")
    print(f"{'='*70}")
    print("1. Review the baseline results CSV for detailed analysis")
    print("2. Check failed examples CSV to understand common failure patterns")
    print("3. Focus repair efforts on policies with <100% accuracy")
    print("4. Consider manual review of policies with very low accuracy")
    print(f"{'='*70}")

if __name__ == "__main__":
    main()