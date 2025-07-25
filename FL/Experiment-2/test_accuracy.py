"""
final_policy_validation.py
Validates the final repaired policies to ensure accuracy calculations are correct.
This script checks all the repaired_X_best.json, repaired_X_final.json, and other output files.
"""

import os
import sys
import json
import logging
import subprocess
import tempfile
import time
from pathlib import Path
import pandas as pd
from datetime import datetime

# Configuration - Update these paths to match your setup
REQUIREMENTS_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-2/requests/request-10"
OUTPUT_DIR = "/home/bhall2/Documents/fixmypolicy/FL/Experiment-2/results/result-10-ollama/"
QUACKY_SRC_DIR = "/home/bhall2/Documents/fixmypolicy/quacky/src"
SMT_VALIDATOR_SCRIPT = "/home/bhall2/Documents/fixmypolicy/quacky/src/validate_requests.py"


def setup_logging():
    """Configure logging for validation"""
    log_file = os.path.join(OUTPUT_DIR, f'final_validation_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return log_file

def run_smt_validator(policy_file: str, requests_file: str) -> dict:
    """Run the SMT validator and return parsed results"""
    try:
        original_dir = os.getcwd()
        os.chdir(QUACKY_SRC_DIR)
        
        # Create temporary output file
        timestamp = int(time.time())
        pid = os.getpid()
        output_file_path = os.path.join(OUTPUT_DIR, f"temp_final_validation_{pid}_{timestamp}.txt")
        
        cmd = [
            'python3', 'validate_requests.py',
            '-p1', policy_file,
            '--requests', requests_file,
            '-s'
        ]
        
        logging.debug(f"Running SMT validator: {' '.join(cmd)}")
        
        with open(output_file_path, 'w') as output_file:
            result = subprocess.run(cmd, stdout=output_file, stderr=subprocess.PIPE, text=True, timeout=300)
        
        os.chdir(original_dir)
        
        if result.returncode != 0:
            logging.error(f"SMT validator failed: {result.stderr}")
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
                # Check if we've reached the end of analysis section
                if any(phrase in ''.join(output_lines[i:i+5]) for phrase in ["Results saved", "saved to HOME"]):
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
        
        # Clean up temporary file
        if os.path.exists(output_file_path):
            os.unlink(output_file_path)
        
        return {
            'accuracy': accuracy,
            'total_requests': total_requests,
            'correct': correct_count,
            'incorrect': incorrect_count,
            'misclassified_allow_to_deny': misclassified_allow_to_deny,
            'misclassified_deny_to_allow': misclassified_deny_to_allow,
            'raw_output': output_content
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

def find_repaired_policies(output_dir: str) -> dict:
    """Find all repaired policy files in the output directory"""
    repaired_files = {}
    
    # Look for various patterns of repaired files
    patterns = [
        "repaired_*_best.json"
    ]
    
    for pattern in patterns:
        import glob
        files = glob.glob(os.path.join(output_dir, pattern))
        for file_path in files:
            filename = os.path.basename(file_path)
            # Extract policy index and type
            import re
            match = re.match(r'repaired_(\d+)_(.+)\.json', filename)
            if match:
                policy_idx = int(match.group(1))
                file_type = match.group(2)
                
                if policy_idx not in repaired_files:
                    repaired_files[policy_idx] = {}
                
                repaired_files[policy_idx][file_type] = file_path
    
    return repaired_files

def load_json_file(file_path: str) -> dict:
    """Load and validate JSON file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except Exception as e:
        logging.error(f"Error loading JSON file {file_path}: {e}")
        raise

def validate_final_policies():
    """Main function to validate all final repaired policies"""
    log_file = setup_logging()
    logging.info("Starting final validation of repaired policies")
    
    print("=" * 80)
    print("FINAL VALIDATION OF REPAIRED POLICIES")
    print("=" * 80)
    
    # Check if required directories exist
    if not os.path.exists(OUTPUT_DIR):
        logging.error(f"Output directory not found: {OUTPUT_DIR}")
        print(f"Error: Output directory not found: {OUTPUT_DIR}")
        return
    
    if not os.path.exists(REQUIREMENTS_DIR):
        logging.error(f"Requirements directory not found: {REQUIREMENTS_DIR}")
        print(f"Error: Requirements directory not found: {REQUIREMENTS_DIR}")
        return
    
    if not os.path.exists(SMT_VALIDATOR_SCRIPT):
        logging.error(f"SMT validator script not found: {SMT_VALIDATOR_SCRIPT}")
        print(f"Error: SMT validator script not found: {SMT_VALIDATOR_SCRIPT}")
        return
    
    # Find all repaired policy files
    repaired_files = find_repaired_policies(OUTPUT_DIR)
    
    if not repaired_files:
        logging.warning("No repaired policy files found")
        print("Warning: No repaired policy files found in output directory")
        return
    
    print(f"Found repaired policies for {len(repaired_files)} policy indices")
    
    # Show what files were found
    for policy_idx in sorted(repaired_files.keys()):
        file_types = list(repaired_files[policy_idx].keys())
        print(f"  Policy {policy_idx}: {', '.join(file_types)}")
    
    print("\nStarting validation...")
    
    validation_results = []
    
    # Validate each repaired policy
    for policy_idx in sorted(repaired_files.keys()):
        policy_files = repaired_files[policy_idx]
        requirements_file = os.path.join(REQUIREMENTS_DIR, f"{policy_idx}.json")
        
        if not os.path.exists(requirements_file):
            logging.warning(f"Requirements file not found for policy {policy_idx}: {requirements_file}")
            continue
        
        print(f"\nValidating policy {policy_idx}...")
        
        for file_type, policy_file in policy_files.items():
            print(f"  Validating {file_type} policy...")
            
            try:
                # Load and validate the policy file structure
                policy_data = load_json_file(policy_file)
                
                # Basic structure validation
                if not isinstance(policy_data, dict):
                    raise ValueError("Policy is not a JSON object")
                
                if "Statement" not in policy_data:
                    raise ValueError("Policy missing 'Statement' field")
                
                if not isinstance(policy_data["Statement"], list):
                    raise ValueError("'Statement' field must be an array")
                
                # Run SMT validation
                validation_result = run_smt_validator(policy_file, requirements_file)
                
                result_record = {
                    'policy_idx': policy_idx,
                    'file_type': file_type,
                    'policy_file': os.path.basename(policy_file),
                    'accuracy': validation_result['accuracy'],
                    'total_requests': validation_result['total_requests'],
                    'correct': validation_result['correct'],
                    'incorrect': validation_result['incorrect'],
                    'misclassified_allow_to_deny': validation_result['misclassified_allow_to_deny'],
                    'misclassified_deny_to_allow': validation_result['misclassified_deny_to_allow'],
                    'validation_status': 'success'
                }
                
                validation_results.append(result_record)
                
                accuracy = validation_result['accuracy']
                print(f"    ✓ {file_type}: {accuracy:.1f}% accuracy ({validation_result['correct']}/{validation_result['total_requests']} correct)")
                
                if accuracy == 100.0:
                    print(f"    🎯 Perfect accuracy achieved!")
                elif accuracy >= 95.0:
                    print(f"    🟢 High accuracy")
                elif accuracy >= 80.0:
                    print(f"    🟡 Moderate accuracy")
                else:
                    print(f"    🔴 Low accuracy")
                
            except Exception as e:
                logging.error(f"Validation failed for policy {policy_idx} ({file_type}): {e}")
                
                result_record = {
                    'policy_idx': policy_idx,
                    'file_type': file_type,
                    'policy_file': os.path.basename(policy_file),
                    'accuracy': 0.0,
                    'total_requests': 0,
                    'correct': 0,
                    'incorrect': 0,
                    'misclassified_allow_to_deny': 0,
                    'misclassified_deny_to_allow': 0,
                    'validation_status': 'error',
                    'error': str(e)
                }
                
                validation_results.append(result_record)
                print(f"    {file_type}: Validation failed - {e}")
    
    # Save results
    if validation_results:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        results_file = os.path.join(OUTPUT_DIR, f"final_validation_results_{timestamp}.csv")
        
        df = pd.DataFrame(validation_results)
        df.to_csv(results_file, index=False)
        
        logging.info(f"Final validation results saved to {results_file}")
        print(f"\nResults saved to: {results_file}")
    
    # Print summary
    print("\n" + "=" * 80)
    print("FINAL VALIDATION SUMMARY")
    print("=" * 80)
    
    if validation_results:
        successful_validations = [r for r in validation_results if r['validation_status'] == 'success']
        failed_validations = [r for r in validation_results if r['validation_status'] == 'error']
        
        print(f"Total validations performed: {len(validation_results)}")
        print(f"Successful validations: {len(successful_validations)}")
        print(f"Failed validations: {len(failed_validations)}")
        
        if successful_validations:
            # Group by policy index to find best results
            policy_best_accuracy = {}
            for result in successful_validations:
                policy_idx = result['policy_idx']
                accuracy = result['accuracy']
                file_type = result['file_type']
                
                if policy_idx not in policy_best_accuracy:
                    policy_best_accuracy[policy_idx] = {'accuracy': accuracy, 'file_type': file_type}
                elif accuracy > policy_best_accuracy[policy_idx]['accuracy']:
                    policy_best_accuracy[policy_idx] = {'accuracy': accuracy, 'file_type': file_type}
            
            perfect_policies = sum(1 for p in policy_best_accuracy.values() if p['accuracy'] == 100.0)
            high_accuracy_policies = sum(1 for p in policy_best_accuracy.values() if p['accuracy'] >= 95.0)
            avg_best_accuracy = sum(p['accuracy'] for p in policy_best_accuracy.values()) / len(policy_best_accuracy)
            
            print(f"\nPOLICY-LEVEL SUMMARY (best result per policy):")
            print(f"Policies with perfect accuracy (100%): {perfect_policies}")
            print(f"Policies with high accuracy (≥95%): {high_accuracy_policies}")
            print(f"Average best accuracy: {avg_best_accuracy:.1f}%")
            
            print(f"\nDETAILED RESULTS BY POLICY:")
            for policy_idx in sorted(policy_best_accuracy.keys()):
                best = policy_best_accuracy[policy_idx]
                accuracy = best['accuracy']
                file_type = best['file_type']
                
                # Find all results for this policy
                policy_results = [r for r in successful_validations if r['policy_idx'] == policy_idx]
                
                if accuracy == 100.0:
                    status_icon = "🎯"
                elif accuracy >= 95.0:
                    status_icon = "🟢"
                elif accuracy >= 80.0:
                    status_icon = "🟡"
                else:
                    status_icon = "🔴"

                print(f"  Policy {policy_idx}: {status_icon} {accuracy:.1f}% (best: {file_type})")
                
                # Show all file types for this policy
                for result in policy_results:
                    if result['file_type'] != file_type:  # Don't repeat the best one
                        print(f"    - {result['file_type']}: {result['accuracy']:.1f}%")
        
        if failed_validations:
            print(f"\nFAILED VALIDATIONS:")
            for result in failed_validations:
                print(f"  Policy {result['policy_idx']} ({result['file_type']}): {result.get('error', 'Unknown error')}")
    
    print("=" * 80)
    print(f"Log file: {log_file}")
    print("=" * 80)

if __name__ == "__main__":
    validate_final_policies()

