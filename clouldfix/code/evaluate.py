# import os
# import sys
# import time
# import json
# import logging
# import re
# import subprocess
# import pandas as pd
# from tqdm import tqdm

# # Configuration
# TOTAL_POLICIES = 282
# POLICY_DIR = "/home/bhall2/fixmypolicy/FL/Experiment-2/results/result-10-fl-repair"
# REQUIREMENTS_DIR = "/home/bhall2/fixmypolicy/FL/Experiment-2/requests/req_extended"
# OUTPUT_DIR = "/home/bhall2/fixmypolicy/FL/Experiment-2/results/accuracy_results-fl"
# QUACKY_SRC_DIR = "/home/bhall2/fixmypolicy/quacky/src"

# def setup_logging():
#     """Configure logging"""
#     logging.basicConfig(
#         level=logging.INFO,
#         format='%(asctime)s - %(levelname)s - %(message)s',
#         handlers=[logging.StreamHandler()]
#     )

# def run_smt_validator(policy_file: str, requests_file: str, policy_idx: int = None) -> dict:
#     """Run SMT validator and extract accuracy"""
#     try:
#         original_dir = os.getcwd()
#         os.chdir(QUACKY_SRC_DIR)
        
#         if policy_idx is not None:
#             policy_specific_dir = os.path.join(OUTPUT_DIR, "Quacky_output", f"policy_{policy_idx:03d}")
#             os.makedirs(policy_specific_dir, exist_ok=True)
#             accuracy_output_path = os.path.join(policy_specific_dir, f"policy_{policy_idx:03d}_accuracy_validation.txt")
#         else:
#             quacky_output_dir = os.path.join(OUTPUT_DIR, "Quacky_output")
#             os.makedirs(quacky_output_dir, exist_ok=True)
#             timestamp = int(time.time())
#             pid = os.getpid()
#             accuracy_output_path = os.path.join(quacky_output_dir, f"temp_accuracy_{pid}_{timestamp}.txt")
        
#         # Run SMT validator
#         cmd_accuracy = [
#             'python3', 'validate_requests.py',
#             '-p1', policy_file,
#             '--requests', requests_file,
#             '-s'
#         ]
        
#         logging.debug(f"Running accuracy validation: {' '.join(cmd_accuracy)}")
        
#         with open(accuracy_output_path, 'w') as output_file:
#             result = subprocess.run(cmd_accuracy, stdout=output_file, stderr=subprocess.PIPE, text=True, timeout=300)
        
#         os.chdir(original_dir)
        
#         if result.returncode != 0:
#             logging.error(f"Accuracy validation failed: {result.stderr}")
#             raise Exception(f"Accuracy validation failed: {result.stderr}")
        
#         with open(accuracy_output_path, 'r') as f:
#             accuracy_output_content = f.read()
        
#         # Parse accuracy results
#         accuracy, total_requests, correct_count, incorrect_count = parse_accuracy_results(accuracy_output_content)
        
#         logging.info(f"Validation completed - Accuracy: {accuracy}%, Total: {total_requests}, Correct: {correct_count}, Incorrect: {incorrect_count}")
        
#         # Clean up temporary files
#         if os.path.exists(accuracy_output_path):
#             os.unlink(accuracy_output_path)
        
#         return {
#             'accuracy': accuracy,
#             'total_requests': total_requests,
#             'correct': correct_count,
#             'incorrect': incorrect_count,
#             'raw_output': accuracy_output_content
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

# def parse_accuracy_results(output_content: str) -> tuple:
#     """Parse accuracy results from SMT validator output"""
#     lines = output_content.split('\n')
#     accuracy = 0.0
#     total_requests = 0
#     correct_count = 0
#     incorrect_count = 0
    
#     in_analysis_section = False
#     for i, line in enumerate(lines):
#         line = line.strip()
        
#         if "INDIVIDUAL REQUEST ANALYSIS" in line:
#             in_analysis_section = True
#             continue
#         elif line.startswith("=") and in_analysis_section and len(line) > 10:
#             if any(phrase in ''.join(lines[i:i+5]) for phrase in ["Results saved", "saved to HOME"]):
#                 break
        
#         if in_analysis_section:
#             if line.startswith("Total Individual Requests:"):
#                 total_match = re.search(r'(\d+)', line)
#                 if total_match:
#                     total_requests = int(total_match.group(1))
#             elif line.startswith("Correct Classifications:"):
#                 correct_match = re.search(r'(\d+)', line)
#                 if correct_match:
#                     correct_count = int(correct_match.group(1))
#             elif line.startswith("Incorrect Classifications:"):
#                 incorrect_match = re.search(r'(\d+)', line)
#                 if incorrect_match:
#                     incorrect_count = int(incorrect_match.group(1))
#             elif line.startswith("Overall Accuracy:"):
#                 accuracy_match = re.search(r'(\d+\.?\d*)%', line)
#                 if accuracy_match:
#                     accuracy = float(accuracy_match.group(1))
    
#     return accuracy, total_requests, correct_count, incorrect_count

# def find_policy_file(idx: int) -> str:
#     """Find policy file - either 'final' or 'best'"""
#     # Try 'final' first, then 'best'
#     for suffix in ['final', 'best', 'original', 'already_perfect']:
#         candidate_file = os.path.join(POLICY_DIR, f"repaired_{idx}_{suffix}.json")
#         if os.path.exists(candidate_file):
#             logging.debug(f"Found policy file: repaired_{idx}_{suffix}.json")
#             return candidate_file
#     # If neither exists, use 0.json, 1.json 
#         else:
#             candidate_file = os.path.join(POLICY_DIR, f"{idx}.json")
#             if os.path.exists(candidate_file):
#                 logging.debug(f"Found policy file: {idx}.json")
#                 return candidate_file
    
#     raise FileNotFoundError(f"Neither repaired_{idx}_final.json nor repaired_{idx}_best.json found in {POLICY_DIR}")

# def run_baseline_validation(idx: int) -> dict:
#     """Run baseline validation on the repaired policy"""
#     try:
#         policy_file = find_policy_file(idx)
#         policy_filename = os.path.basename(policy_file)
#     except FileNotFoundError as e:
#         logging.error(str(e))
#         return {
#             'policy_idx': idx,
#             'policy_file': f"repaired_{idx}_*.json (not found)",
#             'accuracy': 0.0,
#             'total_requests': 0,
#             'correct': 0,
#             'incorrect': 0,
#             'error': str(e)
#         }
    
#     req_file = os.path.join(REQUIREMENTS_DIR, f"{idx}.json")
    
#     if not os.path.exists(req_file):
#         error_msg = f"Request file not found: {req_file}"
#         logging.error(error_msg)
#         return {
#             'policy_idx': idx,
#             'policy_file': policy_filename,
#             'accuracy': 0.0,
#             'total_requests': 0,
#             'correct': 0,
#             'incorrect': 0,
#             'error': error_msg
#         }
    
#     logging.info(f"Running validation for policy {idx} using {policy_filename}...")
    
#     try:
#         validation_results = run_smt_validator(policy_file, req_file, policy_idx=idx)
        
#         baseline_result = {
#             'policy_idx': idx,
#             'policy_file': policy_filename,
#             'accuracy': validation_results['accuracy'],
#             'total_requests': validation_results['total_requests'],
#             'correct': validation_results['correct'],
#             'incorrect': validation_results['incorrect']
#         }
        
#         logging.info(f"Validation for policy {idx}: {validation_results['accuracy']:.1f}% accuracy using {policy_filename}")
        
#         return baseline_result
        
#     except Exception as e:
#         logging.error(f"Validation failed for policy {idx}: {e}")
#         return {
#             'policy_idx': idx,
#             'policy_file': policy_filename,
#             'accuracy': 0.0,
#             'total_requests': 0,
#             'correct': 0,
#             'incorrect': 0,
#             'error': str(e)
#         }

# def main():
#     """Main function - Calculate accuracy for all policies"""
#     setup_logging()
    
#     print("=" * 60)
#     print("Policy Accuracy Calculator")
#     print("=" * 60)
    
#     # Ensure required directories exist
#     for directory in [POLICY_DIR, REQUIREMENTS_DIR]:
#         if not os.path.isdir(directory):
#             logging.error(f"Directory '{directory}' not found.")
#             print(f"Directory '{directory}' not found. Exiting.")
#             sys.exit(1)
    
#     # Create output directories
#     os.makedirs(OUTPUT_DIR, exist_ok=True)
#     os.makedirs(os.path.join(OUTPUT_DIR, "Quacky_output"), exist_ok=True)
    
#     total = TOTAL_POLICIES
    
#     print(f"\nCalculating accuracy for {total} policies...")
#     print("=" * 60)
    
#     baseline_results = []
    
#     # Process all policies
#     for idx in tqdm(range(total), desc="Calculating accuracy"):
#         try:
#             baseline_result = run_baseline_validation(idx)
#             baseline_results.append(baseline_result)
            
#             if 'error' not in baseline_result:
#                 accuracy = baseline_result.get('accuracy', 0.0)
#                 total_req = baseline_result.get('total_requests', 0)
#                 policy_file = baseline_result.get('policy_file', 'unknown')
#                 print(f"Policy {idx}: {accuracy:.1f}% ({baseline_result['correct']}/{total_req}) - {policy_file}")
#             else:
#                 print(f"Policy {idx}: ERROR - {baseline_result['error']}")
                
#         except Exception as e:
#             logging.error(f"Baseline validation failed for policy {idx}: {e}")
#             baseline_results.append({
#                 'policy_idx': idx,
#                 'accuracy': 0.0,
#                 'total_requests': 0,
#                 'correct': 0,
#                 'incorrect': 0,
#                 'error': str(e)
#             })
#             print(f"Policy {idx}: ERROR - {str(e)}")
    
#     # Save results
#     if baseline_results:
#         baseline_csv = os.path.join(OUTPUT_DIR, "accuracy_results.csv")
#         baseline_df = pd.DataFrame(baseline_results)
#         baseline_df.to_csv(baseline_csv, index=False)
#         logging.info(f"Results saved to {baseline_csv}")
    
#     # Print summary
#     print(f"\n{'='*60}")
#     print("ACCURACY SUMMARY")
#     print(f"{'='*60}")
    
#     successful_results = [r for r in baseline_results if r.get('accuracy', 0) > 0 and 'error' not in r]
#     failed_results = [r for r in baseline_results if 'error' in r]
#     perfect_results = [r for r in baseline_results if r.get('accuracy', 0) >= 100.0]
    
#     if successful_results:
#         avg_accuracy = sum(r['accuracy'] for r in successful_results) / len(successful_results)
#         total_requests = sum(r['total_requests'] for r in successful_results)
#         total_correct = sum(r['correct'] for r in successful_results)
        
#         print(f"Successfully processed policies: {len(successful_results)}")
#         print(f"Failed validations: {len(failed_results)}")
#         print(f"Perfect accuracy policies: {len(perfect_results)}")
#         print(f"Average accuracy: {avg_accuracy:.1f}%")
#         print(f"Total requests: {total_requests}")
#         print(f"Total correct: {total_correct}")
        
#         if perfect_results:
#             perfect_indices = [r['policy_idx'] for r in perfect_results]
#             print(f"Perfect policies: {perfect_indices}")
    
#     print(f"Results saved to: {baseline_csv}")
#     print(f"{'='*60}")

# if __name__ == "__main__":
#     main()

import os
import sys
import time
import json
import logging
import re
import subprocess
import pandas as pd
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor, as_completed

TOTAL_POLICIES = 282
POLICY_DIR = "/home/bhall2/fixmypolicy/FL/Experiment-2/results/result-fl-repair-generalize"
REQUIREMENTS_DIR = "/home/bhall2/fixmypolicy/FL/Experiment-2/requests/req_extended_v3"

OUTPUT_DIR = "/home/bhall2/fixmypolicy/FL/Experiment-2/results/accuracy_results-fl"
QUACKY_SRC_DIR = "/home/bhall2/fixmypolicy/quacky/src"
MAX_WORKERS = 8

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )

def run_smt_validator(policy_file: str, requests_file: str, policy_idx: int = None) -> dict:
    """Run SMT validator and extract accuracy (with single-request fallback)."""
    try:
        original_dir = os.getcwd()
        os.chdir(QUACKY_SRC_DIR)

        if policy_idx is not None:
            policy_specific_dir = os.path.join(OUTPUT_DIR, "Quacky_output", f"policy_{policy_idx:03d}")
            os.makedirs(policy_specific_dir, exist_ok=True)
            accuracy_output_path = os.path.join(
                policy_specific_dir, f"policy_{policy_idx:03d}_accuracy_validation.txt"
            )
        else:
            quacky_output_dir = os.path.join(OUTPUT_DIR, "Quacky_output")
            os.makedirs(quacky_output_dir, exist_ok=True)
            timestamp = int(time.time())
            pid = os.getpid()
            accuracy_output_path = os.path.join(
                quacky_output_dir, f"temp_accuracy_{pid}_{timestamp}.txt"
            )

        # Run validator
        cmd_accuracy = [
            sys.executable,
            "validate_requests.py",
            "-p1",
            policy_file,
            "--requests",
            requests_file,
            "-s",
        ]
        with open(accuracy_output_path, "w") as output_file:
            result = subprocess.run(
                cmd_accuracy,
                stdout=output_file,
                stderr=subprocess.PIPE,
                text=True,
                timeout=1200,
            )

        os.chdir(original_dir)

        if result.returncode != 0:
            raise Exception(f"Accuracy validation failed: {result.stderr}")

        with open(accuracy_output_path, "r") as f:
            accuracy_output_content = f.read()

        # Parse accuracy
        accuracy, total_requests, correct_count, incorrect_count = parse_accuracy_results(
            accuracy_output_content
        )

        logging.info(
            f"Validation completed - Acc: {accuracy:.1f}%, Total: {total_requests}, "
            f"Correct: {correct_count}, Incorrect: {incorrect_count}"
        )

        return {
            "accuracy": accuracy,
            "total_requests": total_requests,
            "correct": correct_count,
            "incorrect": incorrect_count,
            "raw_output": accuracy_output_content,
        }

    except subprocess.TimeoutExpired:
        os.chdir(original_dir)
        logging.error("SMT validator timed out")
        raise Exception("SMT validator timed out")
    except Exception as e:
        try:
            os.chdir(original_dir)
        except:
            pass
        logging.error(f"Error running SMT validator: {e}")
        raise

def parse_accuracy_results(output_content: str) -> tuple:
    """Parse accuracy results from SMT validator output (with single-request fallback)."""
    lines = output_content.split("\n")
    accuracy = 0.0
    total_requests = 0
    correct_count = 0
    incorrect_count = 0

    in_analysis_section = False
    for i, line in enumerate(lines):
        line = line.strip()

        if "INDIVIDUAL REQUEST ANALYSIS" in line:
            in_analysis_section = True
            continue

        if in_analysis_section:
            if line.startswith("Total Individual Requests:"):
                total_match = re.search(r"(\d+)", line)
                if total_match:
                    total_requests = int(total_match.group(1))
            elif line.startswith("Correct Classifications:"):
                correct_match = re.search(r"(\d+)", line)
                if correct_match:
                    correct_count = int(correct_match.group(1))
            elif line.startswith("Incorrect Classifications:"):
                incorrect_match = re.search(r"(\d+)", line)
                if incorrect_match:
                    incorrect_count = int(incorrect_match.group(1))
            elif line.startswith("Overall Accuracy:"):
                accuracy_match = re.search(r"(\d+\.?\d*)%", line)
                if accuracy_match:
                    accuracy = float(accuracy_match.group(1))

    # ---- Fallback: single request case ----
    if total_requests == 0:
        m = re.search(r"Overall Accuracy:\s*(\d+\.?\d*)%", output_content)
        if m:
            accuracy = float(m.group(1))
            total_requests = 1
            correct_count = 1 if accuracy == 100.0 else 0
            incorrect_count = 0 if accuracy == 100.0 else 1

    return accuracy, total_requests, correct_count, incorrect_count

def find_policy_file(idx: int) -> str:
    """Find best available repaired policy file."""
    for suffix in ["final", "best", "original", "already_perfect"]:
        candidate_file = os.path.join(POLICY_DIR, f"repaired_{idx}_{suffix}.json")
        if os.path.exists(candidate_file):
            return candidate_file
    candidate_file = os.path.join(POLICY_DIR, f"{idx}.json")
    if os.path.exists(candidate_file):
        return candidate_file
    raise FileNotFoundError(f"No repaired or original policy file found for {idx} in {POLICY_DIR}")


def run_baseline_validation(idx: int) -> dict:
    """Run baseline validation for one policy index."""
    try:
        policy_file = find_policy_file(idx)
        policy_filename = os.path.basename(policy_file)
    except FileNotFoundError as e:
        return {
            "policy_idx": idx,
            "policy_file": "not found",
            "accuracy": 0.0,
            "total_requests": 0,
            "correct": 0,
            "incorrect": 0,
            "error": str(e),
        }

    req_file = os.path.join(REQUIREMENTS_DIR, f"{idx}_variants.json")
    if not os.path.exists(req_file):
        error_msg = f"Request file not found: {req_file}"
        return {
            "policy_idx": idx,
            "policy_file": policy_filename,
            "accuracy": 0.0,
            "total_requests": 0,
            "correct": 0,
            "incorrect": 0,
            "error": error_msg,
        }

    try:
        validation_results = run_smt_validator(policy_file, req_file, policy_idx=idx)
        return {
            "policy_idx": idx,
            "policy_file": policy_filename,
            "accuracy": validation_results["accuracy"],
            "total_requests": validation_results["total_requests"],
            "correct": validation_results["correct"],
            "incorrect": validation_results["incorrect"],
        }
    except Exception as e:
        return {
            "policy_idx": idx,
            "policy_file": policy_filename,
            "accuracy": 0.0,
            "total_requests": 0,
            "correct": 0,
            "incorrect": 0,
            "error": str(e),
        }
def main():
    setup_logging()

    for directory in [POLICY_DIR, REQUIREMENTS_DIR]:
        if not os.path.isdir(directory):
            print(f"Directory '{directory}' not found. Exiting.")
            sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(os.path.join(OUTPUT_DIR, "Quacky_output"), exist_ok=True)

    # ---- Filter only 'final' policy files ----
    available_indices = []
    for i in range(TOTAL_POLICIES):
        candidate = os.path.join(POLICY_DIR, f"repaired_{i}_final.json")
        if os.path.exists(candidate):
            available_indices.append(i)

    if not available_indices:
        print("No 'final' policy files found — nothing to evaluate.")
        sys.exit(0)

    print(f"\nEvaluating {len(available_indices)} 'final' policies sequentially...")
    print("=" * 60)

    baseline_results = []

    # ---- Sequential evaluation ----
    for idx in tqdm(available_indices, desc="Validating policies"):
        try:
            result = run_baseline_validation(idx)
            baseline_results.append(result)

            if "error" not in result:
                print(
                    f"Policy {idx}: {result['accuracy']:.1f}% "
                    f"({result['correct']}/{result['total_requests']})"
                )
            else:
                print(f"Policy {idx}: ERROR - {result['error']}")
        except Exception as e:
            baseline_results.append(
                {
                    "policy_idx": idx,
                    "accuracy": 0.0,
                    "total_requests": 0,
                    "correct": 0,
                    "incorrect": 0,
                    "error": str(e),
                }
            )
            print(f"Policy {idx}: ERROR - {str(e)}")

    # Save results
    baseline_csv = os.path.join(OUTPUT_DIR, "accuracy_results_final_only.csv")
    pd.DataFrame(baseline_results).to_csv(baseline_csv, index=False)
    logging.info(f"Results saved to {baseline_csv}")

    print(f"\n{'='*60}")
    print("ACCURACY SUMMARY (FINAL FILES ONLY)")
    print(f"{'='*60}")

    successful_results = [r for r in baseline_results if r.get("accuracy", 0) > 0 and "error" not in r]
    perfect_results = [r for r in baseline_results if r.get("accuracy", 0) >= 100.0]

    if successful_results:
        avg_accuracy = sum(r["accuracy"] for r in successful_results) / len(successful_results)
        print(f"Successfully processed policies: {len(successful_results)}")
        print(f"Perfect accuracy policies: {len(perfect_results)}")
        print(f"Average accuracy: {avg_accuracy:.1f}%")
        print(f"Results saved to: {baseline_csv}")

    print(f"{'='*60}")

if __name__ == "__main__":
    main()
