"""
Baseline LLM-based AWS IAM Policy Repair (Requirements Only).

This script performs iterative policy repair using only the original policy
and requirements (no fault localization) as a baseline comparison.

Usage:
    python baseline_repair.py --policies ./policies --requests ./requests --output ./output
    python baseline_repair.py --model codellama --request-set 40
    python baseline_repair.py --model granite --max-iterations 5

Environment Variables:
    POLICY_DIR, REQUESTS_DIR, OUTPUT_DIR, QUACKY_SRC_DIR, LLM_MODEL
"""

import argparse
import os
import sys
import time
import json
import re
import shutil
import subprocess
import logging
from dataclasses import dataclass
from functools import wraps
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

import pandas as pd
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()
os.environ["TOKENIZERS_PARALLELISM"] = "false"

if os.environ.get("SET_CUDA_ALLOC_CONF", "0") == "1":
    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"


SUPPORTED_MODELS = {
    "codellama": "codellama/CodeLlama-7b-Instruct-hf",
    "granite": "ibm-granite/granite-3.3-8b-instruct",
    "deepseek": "deepseek-ai/deepseek-coder-7b-instruct-v1.5",
    "llama3": "meta-llama/Llama-3.2-3B-Instruct",
}

MODEL_DESCRIPTIONS = {
    "codellama": "CodeLLaMA-7B-Instruct - Trained for code synthesis and reasoning",
    "granite": "Granite-3.3-8B-Instruct - IBM model optimized for software engineering tasks",
    "deepseek": "DeepSeek-Coder-7B-Instruct - Finetuned for code completion and repair",
    "llama3": "Llama-3.2-3B-Instruct - Instruction-tuned text model (128K context)",
}

DEFAULT_MODEL = "codellama"


def get_model_identifier(model_name: str) -> str:
    """
    Resolve model name to HuggingFace identifier.
    
    Accepts either:
        - Short name: "codellama", "granite", "deepseek", "llama3"
        - Full HuggingFace identifier: "codellama/CodeLlama-7b-Instruct-hf"
    """
    if model_name.lower() in SUPPORTED_MODELS:
        return SUPPORTED_MODELS[model_name.lower()]
    if "/" in model_name:
        return model_name
    available = ", ".join(SUPPORTED_MODELS.keys())
    raise ValueError(
        f"Unknown model: '{model_name}'. "
        f"Available short names: {available}. "
        f"Or provide a full HuggingFace model identifier."
    )


@dataclass
class Config:
    """Configuration for the baseline repair pipeline."""
    
    # Directories
    policy_dir: str = ""
    requests_dir: str = ""
    output_dir: str = ""
    log_dir: str = ""
    temp_dir: str = ""
    quacky_src_dir: str = ""
    
    # Experiment parameters
    request_set: int = 10
    total_policies: int = 282
    max_iterations: int = 5
    max_attempts: int = 1
    retry_delay: float = 1.0
    target_accuracy: float = 100.0
    validation_timeout: int = 300
    
    llm_model: str = DEFAULT_MODEL
    
    # Generation hyperparameters
    temperature: float = 0.1
    top_p: float = 0.3
    top_k: int = 40
    repetition_penalty: float = 1.1
    max_new_tokens: int = 2048
    
    def __post_init__(self):
        """Apply environment variable defaults if paths not provided."""
        req = self.request_set
        
        if not self.policy_dir:
            self.policy_dir = os.environ.get("POLICY_DIR", "./policies")
        if not self.requests_dir:
            self.requests_dir = os.environ.get("REQUESTS_DIR", f"./requests/request-{req}")
        if not self.output_dir:
            self.output_dir = os.environ.get("OUTPUT_DIR", f"./results/result-{req}-baseline")
        if not self.log_dir:
            self.log_dir = os.environ.get("LOG_DIR", f"./logs/log-{req}-baseline")
        if not self.temp_dir:
            self.temp_dir = os.environ.get("TEMP_DIR", f"./temp/val-{req}-baseline")
        if not self.quacky_src_dir:
            self.quacky_src_dir = os.environ.get("QUACKY_SRC_DIR", "./quacky/src")
    
    @property
    def model_identifier(self) -> str:
        """Get the full HuggingFace model identifier."""
        return get_model_identifier(self.llm_model)
    
    @property
    def smt_validator_script(self) -> Path:
        """Path to the SMT validator script."""
        return Path(self.quacky_src_dir) / "validate_requests.py"
    
    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "Config":
        """Create Config from parsed command-line arguments."""
        return cls(
            policy_dir=args.policies or "",
            requests_dir=args.requests or "",
            output_dir=args.output or "",
            log_dir=args.log_dir or "",
            temp_dir=args.temp_dir or "",
            quacky_src_dir=args.quacky_src or "",
            request_set=args.request_set,
            total_policies=args.total_policies,
            max_iterations=args.max_iterations,
            max_attempts=args.max_attempts,
            retry_delay=args.retry_delay,
            target_accuracy=args.target_accuracy,
            llm_model=args.model,
            temperature=args.temperature,
            top_p=args.top_p,
            top_k=args.top_k,
            repetition_penalty=args.repetition_penalty,
            max_new_tokens=args.max_new_tokens,
        )


# Global config instance
CONFIG: Optional[Config] = None


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Baseline LLM-based AWS IAM policy repair (requirements only, no fault localization).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
    # Using short model names
    %(prog)s --model codellama --policies ./policies --requests ./requests
    %(prog)s --model granite --max-iterations 5
    %(prog)s --model deepseek --temperature 0.2
    %(prog)s --model llama3 --top-p 0.5

    # Using full HuggingFace identifier
    %(prog)s --model codellama/CodeLlama-7b-Instruct-hf

Supported Models:
{chr(10).join(f'  {k}: {v}' for k, v in MODEL_DESCRIPTIONS.items())}

Environment Variables:
    POLICY_DIR      Path to policy JSON files
    REQUESTS_DIR    Path to request JSON files
    OUTPUT_DIR      Path for output files
    LOG_DIR         Path for log files
    TEMP_DIR        Path for temporary files
    QUACKY_SRC_DIR  Path to Quacky source directory
    LLM_MODEL       Model to use (short name or HuggingFace identifier)
        """,
    )
    
    # Directory arguments
    dir_group = parser.add_argument_group("Directories")
    dir_group.add_argument("--policies", help="Policy JSON files directory")
    dir_group.add_argument("--requests", help="Request JSON files directory")
    dir_group.add_argument("--output", help="Output directory for results")
    dir_group.add_argument("--log-dir", help="Log files directory")
    dir_group.add_argument("--temp-dir", help="Temporary files directory")
    dir_group.add_argument("--quacky-src", help="Quacky source directory")
    
    # Experiment parameters
    exp_group = parser.add_argument_group("Experiment Parameters")
    exp_group.add_argument("--request-set", type=int, default=10,
                           help="Request set number (default: 10)")
    exp_group.add_argument("--total-policies", type=int, default=282,
                           help="Total number of policies to process (default: 282)")
    exp_group.add_argument("--max-iterations", type=int, default=5,
                           help="Maximum repair iterations per policy (default: 5)")
    exp_group.add_argument("--max-attempts", type=int, default=1,
                           help="Maximum retry attempts for LLM calls (default: 1)")
    exp_group.add_argument("--retry-delay", type=float, default=1.0,
                           help="Delay between retries in seconds (default: 1.0)")
    exp_group.add_argument("--target-accuracy", type=float, default=100.0,
                           help="Target accuracy percentage (default: 100.0)")
    
    # Model configuration
    model_group = parser.add_argument_group("Model Configuration")
    model_group.add_argument(
        "-m", "--model",
        default=os.environ.get("LLM_MODEL", DEFAULT_MODEL),
        help=f"Model to use. Short names: {', '.join(SUPPORTED_MODELS.keys())}. "
             f"Or full HuggingFace identifier. (default: {DEFAULT_MODEL})"
    )
    model_group.add_argument("--list-models", action="store_true",
                             help="List supported models and exit")
    
    # Generation hyperparameters
    gen_group = parser.add_argument_group("Generation Hyperparameters")
    gen_group.add_argument("--temperature", type=float, default=0.1,
                           help="Sampling temperature (default: 0.1)")
    gen_group.add_argument("--top-p", type=float, default=0.3,
                           help="Top-p (nucleus) sampling (default: 0.3)")
    gen_group.add_argument("--top-k", type=int, default=40,
                           help="Top-k sampling (default: 40)")
    gen_group.add_argument("--repetition-penalty", type=float, default=1.1,
                           help="Repetition penalty (default: 1.1)")
    gen_group.add_argument("--max-new-tokens", type=int, default=2048,
                           help="Maximum new tokens to generate (default: 2048)")
    
    # General options
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Handle --list-models
    if args.list_models:
        print("\nSupported Models (HuggingFace):")
        print("=" * 70)
        for short_name, full_name in SUPPORTED_MODELS.items():
            desc = MODEL_DESCRIPTIONS[short_name]
            print(f"\n  {short_name}")
            print(f"    HuggingFace: {full_name}")
            print(f"    Description: {desc}")
        print("\n" + "=" * 70)
        print("\nUsage: --model <short_name> or --model <full_identifier>")
        print("Example: --model codellama")
        print("Example: --model codellama/CodeLlama-7b-Instruct-hf")
        sys.exit(0)
    
    return args



def setup_logging(log_dir: str) -> str:
    """Configure logging with file and console handlers."""
    os.makedirs(log_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"baseline_repair_{timestamp}.log")
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return log_file


def retry(max_attempts: int = None, delay: float = None):
    """Decorator for retrying failed function calls."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            _max = max_attempts if max_attempts else (CONFIG.max_attempts if CONFIG else 1)
            _delay = delay if delay else (CONFIG.retry_delay if CONFIG else 1.0)
            
            for attempt in range(1, _max + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == _max:
                        raise
                    logging.warning(f"Attempt {attempt} failed: {e}. Retrying in {_delay}s...")
                    time.sleep(_delay)
        return wrapper
    return decorator


def load_json(path: str) -> Dict[str, Any]:
    """Load JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Dict[str, Any], path: str) -> None:
    """Save data to JSON file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


_hf_generator = None
_hf_tokenizer = None


def get_hf_generator():
    """Lazy-load the HuggingFace model and tokenizer."""
    global _hf_generator, _hf_tokenizer
    
    if _hf_generator is not None:
        return _hf_generator, _hf_tokenizer
    
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
    
    model_name = CONFIG.model_identifier
    logging.info(f"Loading HuggingFace model: {model_name}")
    
    _hf_tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    if _hf_tokenizer.pad_token is None:
        _hf_tokenizer.pad_token = _hf_tokenizer.eos_token
    
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        device_map="auto",
        torch_dtype=torch.float16,
    )
    
    if hasattr(model, 'gradient_checkpointing_enable'):
        model.gradient_checkpointing_enable()
    
    _hf_generator = pipeline(
        "text-generation",
        model=model,
        tokenizer=_hf_tokenizer,
        torch_dtype=torch.float16,
    )
    
    logging.info(f"Model loaded successfully: {model_name}")
    return _hf_generator, _hf_tokenizer


def call_llm(prompt: str, system_prompt: str = "") -> str:
    """Call the HuggingFace LLM with the given prompt."""
    import torch
    
    torch.cuda.empty_cache()
    
    generator, tokenizer = get_hf_generator()
    
    if system_prompt:
        full_prompt = f"<|system|>\n{system_prompt}\n<|user|>\n{prompt}"
    else:
        full_prompt = prompt
    
    outputs = generator(
        full_prompt,
        temperature=CONFIG.temperature,
        top_p=CONFIG.top_p,
        top_k=CONFIG.top_k,
        repetition_penalty=CONFIG.repetition_penalty,
        do_sample=True,
        max_new_tokens=CONFIG.max_new_tokens,
        return_full_text=False,
        eos_token_id=tokenizer.eos_token_id,
        pad_token_id=tokenizer.eos_token_id,
    )
    
    return outputs[0]["generated_text"]


def create_repair_prompt(
    policy: Dict,
    requirements: Dict,
    iteration: int,
    previous_accuracy: float,
) -> str:
    """Create repair prompt for the LLM."""
    return f"""You are an AWS IAM policy expert. You must use security best practices to repair the following policy so that the provided test sets are allowed and denied. 
        CURRENT POLICY:
        {json.dumps(policy, indent=2)}

        REQUIREMENTS to SATISFY:
        {json.dumps(requirements, indent=2)}

        REPAIR STATUS:
        Iteration: {iteration}/{CONFIG.max_iterations}
        Previous Accuracy: {previous_accuracy:.1f}%

        Return ONLY the complete corrected policy as valid JSON. No explanations, no markdown formatting.

        CORRECTED POLICY:"""


def create_system_prompt() -> str:
    """Create system prompt for policy repair."""
    return """You are an expert AWS IAM policy engineer.

CRITICAL OUTPUT REQUIREMENTS:
- You MUST return a complete, valid JSON policy
- Start your response immediately with { and end with }
- Do NOT include any explanations, comments, or text before or after the JSON
- Do NOT use markdown formatting or code blocks
- The JSON must be syntactically correct and complete

Return ONLY the JSON policy, nothing else."""


# =============================================================================
# JSON Extraction
# =============================================================================

def extract_policy(text: str) -> Dict[str, Any]:
    """Extract and validate JSON policy from LLM response."""
    text = text.strip()
    
    # Remove markdown formatting
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    
    # Find JSON boundaries
    start = text.find("{")
    end = text.rfind("}")
    
    if start == -1 or end == -1:
        logging.error(f"No JSON found in LLM output: {text[:200]}...")
        raise ValueError("No JSON found in LLM output")
    
    json_text = text[start:end + 1]
    
    try:
        policy = json.loads(json_text)
        
        if not isinstance(policy, dict):
            raise ValueError("Response is not a JSON object")
        if "Statement" not in policy:
            raise ValueError("Missing 'Statement' field in policy")
        if not isinstance(policy["Statement"], list):
            raise ValueError("'Statement' field must be an array")
        if "Version" not in policy:
            policy["Version"] = "2012-10-17"
        
        return policy
    
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON at line {e.lineno}, column {e.colno}: {e.msg}")
        logging.error(f"JSON text: {json_text[:500]}...")
        raise ValueError(f"Invalid JSON in LLM output: {e}")




def run_smt_validator(policy_file: str, requests_file: str, policy_idx: int = None) -> Dict[str, Any]:
    """Run SMT validator and return accuracy metrics."""
    original_dir = os.getcwd()
    
    try:
        os.chdir(CONFIG.quacky_src_dir)
        
        cmd = [
            "python3", "validate_requests.py",
            "-p1", str(policy_file),
            "--requests", str(requests_file),
            "-s",
        ]
        
        logging.debug(f"Running validation: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=CONFIG.validation_timeout,
        )
        
        os.chdir(original_dir)
        
        if result.returncode != 0:
            raise RuntimeError(f"Validation failed: {result.stderr}")
        
        accuracy = 0.0
        total_requests = correct = incorrect = 0
        
        for line in result.stdout.splitlines():
            line = line.strip()
            if "Overall Accuracy:" in line:
                match = re.search(r'(\d+\.?\d*)\s*%', line)
                if match:
                    accuracy = float(match.group(1))
            elif "Total Individual Requests:" in line:
                match = re.search(r'(\d+)', line)
                if match:
                    total_requests = int(match.group(1))
            elif "Correct Classifications:" in line:
                match = re.search(r'(\d+)', line)
                if match:
                    correct = int(match.group(1))
            elif "Incorrect Classifications:" in line:
                match = re.search(r'(\d+)', line)
                if match:
                    incorrect = int(match.group(1))
        
        logging.info(f"Validation: {accuracy:.1f}% accuracy ({correct}/{total_requests} correct)")
        
        return {
            "accuracy": accuracy,
            "total_requests": total_requests,
            "correct": correct,
            "incorrect": incorrect,
            "raw": result.stdout,
        }
    
    except subprocess.TimeoutExpired:
        os.chdir(original_dir)
        raise RuntimeError("SMT validator timed out")
    except Exception as e:
        os.chdir(original_dir)
        raise



@retry()
def repair_policy(
    policy: Dict,
    requirements: Dict,
    iteration: int,
    previous_accuracy: float,
    policy_idx: int = None,
) -> Dict:
    """Repair policy using LLM."""
    prompt = create_repair_prompt(policy, requirements, iteration, previous_accuracy)
    system_prompt = create_system_prompt()
    
    logging.info(f"{'=' * 60}")
    logging.info(f"Repair iteration {iteration}/{CONFIG.max_iterations}")
    logging.info(f"Previous accuracy: {previous_accuracy:.1f}%")
    logging.info(f"{'=' * 60}")
    
    response = call_llm(prompt, system_prompt)
    
    # Save raw LLM output for debugging
    if policy_idx is not None:
        raw_output_file = os.path.join(
            CONFIG.temp_dir, f"raw_llm_output_policy_{policy_idx:03d}_iter_{iteration}.txt"
        )
        os.makedirs(CONFIG.temp_dir, exist_ok=True)
        with open(raw_output_file, "w", encoding="utf-8") as f:
            f.write(response)
    
    logging.info(f"Response length: {len(response)} chars")
    
    return extract_policy(response)



def process_policy(idx: int, baseline_accuracy: float) -> Dict[str, Any]:
    """Process a single policy with iterative repair."""
    cycle_start = time.time()
    
    policy_file = os.path.join(CONFIG.policy_dir, f"{idx}.json")
    req_file = os.path.join(CONFIG.requests_dir, f"{idx}.json")
    
    if not os.path.exists(policy_file) or not os.path.exists(req_file):
        raise FileNotFoundError(f"Missing files for policy {idx}")
    
    policy = load_json(policy_file)
    requirements = load_json(req_file)
    
    logging.info(f"Processing policy {idx} (baseline: {baseline_accuracy:.1f}%)")
    
    if baseline_accuracy >= CONFIG.target_accuracy:
        output_file = os.path.join(CONFIG.output_dir, f"repaired_{idx}_already_perfect.json")
        save_json(policy, output_file)
        return {
            "index": idx,
            "status": "already_perfect",
            "baseline_accuracy": baseline_accuracy,
            "final_accuracy": baseline_accuracy,
            "iterations_used": 0,
            "iteration_accuracies": [baseline_accuracy],
            "cycle_duration_seconds": 0,
        }
    
    iteration_accuracies = [baseline_accuracy]
    current_policy = policy.copy()
    current_accuracy = baseline_accuracy
    
    for iteration in range(1, CONFIG.max_iterations + 1):
        logging.info(f"Policy {idx} - Iteration {iteration}/{CONFIG.max_iterations}")
        
        try:
            repaired = repair_policy(
                current_policy, requirements, iteration,
                previous_accuracy=current_accuracy,
                policy_idx=idx,
            )
            
            tmp_policy = os.path.join(CONFIG.temp_dir, f"policy_{idx}_iter_{iteration}.json")
            save_json(repaired, tmp_policy)
            
            result = run_smt_validator(tmp_policy, req_file, policy_idx=idx)
            accuracy = result["accuracy"]
            iteration_accuracies.append(accuracy)
            
            if accuracy >= CONFIG.target_accuracy:
                final_path = os.path.join(CONFIG.output_dir, f"repaired_{idx}_final.json")
                save_json(repaired, final_path)
                cycle_time = time.time() - cycle_start
                
                return {
                    "index": idx,
                    "status": "success",
                    "baseline_accuracy": baseline_accuracy,
                    "final_accuracy": accuracy,
                    "iterations_used": iteration,
                    "iteration_accuracies": iteration_accuracies,
                    "cycle_duration_seconds": cycle_time,
                }
            
            if accuracy >= current_accuracy:
                current_policy = repaired.copy()
                current_accuracy = accuracy
        
        except Exception as e:
            logging.error(f"Iteration {iteration} failed for policy {idx}: {e}")
    
    cycle_time = time.time() - cycle_start
    final_accuracy = max(iteration_accuracies)
    
    best_iter = iteration_accuracies.index(final_accuracy)
    if best_iter > 0:
        best_file = os.path.join(CONFIG.temp_dir, f"policy_{idx}_iter_{best_iter}.json")
        if os.path.exists(best_file):
            final_path = os.path.join(CONFIG.output_dir, f"repaired_{idx}_best.json")
            shutil.copy2(best_file, final_path)
    
    return {
        "index": idx,
        "status": "failed",
        "baseline_accuracy": baseline_accuracy,
        "final_accuracy": final_accuracy,
        "iterations_used": CONFIG.max_iterations,
        "iteration_accuracies": iteration_accuracies,
        "cycle_duration_seconds": cycle_time,
    }

def main():
    """Main entry point for baseline policy repair."""
    global CONFIG
    
    args = parse_arguments()
    CONFIG = Config.from_args(args)
    
    log_file = setup_logging(CONFIG.log_dir)
    
    logging.info("=" * 60)
    logging.info("Baseline Policy Repair System (Requirements Only)")
    logging.info("=" * 60)
    logging.info(f"Configuration:")
    logging.info(f"  Policies: {CONFIG.policy_dir}")
    logging.info(f"  Requests: {CONFIG.requests_dir}")
    logging.info(f"  Output: {CONFIG.output_dir}")
    logging.info(f"  Model: {CONFIG.model_identifier}")
    logging.info(f"  Max iterations: {CONFIG.max_iterations}")
    logging.info(f"  Target accuracy: {CONFIG.target_accuracy}%")
    logging.info(f"  Hyperparameters:")
    logging.info(f"    temperature={CONFIG.temperature}, top_p={CONFIG.top_p}, "
                 f"top_k={CONFIG.top_k}, repetition_penalty={CONFIG.repetition_penalty}")
    
    if not os.path.isdir(CONFIG.policy_dir):
        logging.error(f"Policy directory not found: {CONFIG.policy_dir}")
        sys.exit(1)
    if not os.path.isdir(CONFIG.requests_dir):
        logging.error(f"Requests directory not found: {CONFIG.requests_dir}")
        sys.exit(1)
    if not CONFIG.smt_validator_script.exists():
        logging.error(f"SMT validator not found: {CONFIG.smt_validator_script}")
        sys.exit(1)
    
    os.makedirs(CONFIG.output_dir, exist_ok=True)
    os.makedirs(CONFIG.temp_dir, exist_ok=True)
    
    results = []
    
    for idx in tqdm(range(CONFIG.total_policies), desc="Processing policies"):
        try:
            policy_file = os.path.join(CONFIG.policy_dir, f"{idx}.json")
            req_file = os.path.join(CONFIG.requests_dir, f"{idx}.json")
            
            if not os.path.exists(policy_file) or not os.path.exists(req_file):
                logging.warning(f"Skipping policy {idx}: files not found")
                continue
            
            baseline = run_smt_validator(policy_file, req_file, policy_idx=idx)
            baseline_accuracy = baseline["accuracy"]
            
            result = process_policy(idx, baseline_accuracy)
            results.append(result)
            
            logging.info(f"Policy {idx}: {result['baseline_accuracy']:.1f}% -> {result['final_accuracy']:.1f}% ({result['status']})")
        
        except Exception as e:
            logging.error(f"Policy {idx} failed: {e}")
            results.append({
                "index": idx,
                "status": "error",
                "baseline_accuracy": 0.0,
                "final_accuracy": 0.0,
                "iterations_used": 0,
                "iteration_accuracies": [],
                "error": str(e),
            })
    
    df = pd.DataFrame(results)
    summary_file = os.path.join(CONFIG.output_dir, "baseline_repair_summary.csv")
    df.to_csv(summary_file, index=False)
    logging.info(f"Results saved to: {summary_file}")
    
    successful = len([r for r in results if r.get("status") in ["success", "already_perfect"]])
    improved = len([r for r in results if r.get("status") == "success"])
    failed = len([r for r in results if r.get("status") in ["failed", "error"]])
    
    print(f"\n{'=' * 60}")
    print("BASELINE REPAIR SUMMARY")
    print(f"{'=' * 60}")
    print(f"Total policies: {len(results)}")
    print(f"Successfully repaired: {improved}")
    print(f"Already perfect: {successful - improved}")
    print(f"Failed: {failed}")
    
    if results:
        avg_baseline = sum(r.get("baseline_accuracy", 0) for r in results) / len(results)
        avg_final = sum(r.get("final_accuracy", 0) for r in results) / len(results)
        print(f"Average baseline: {avg_baseline:.1f}%")
        print(f"Average final: {avg_final:.1f}%")
        print(f"Improvement: {avg_final - avg_baseline:.1f} percentage points")
    
    print(f"\nResults saved to: {CONFIG.output_dir}")


if __name__ == "__main__":
    main()