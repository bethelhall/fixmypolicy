"""
LLM-based AWS IAM Policy Repair with Fault Localization.

This script performs iterative policy repair using LLMs guided by SMT-based
fault localization to achieve target accuracy on policy test suites.

Usage:
    python policy_repair.py --policies ./policies --requests ./requests --output ./output

    Or set environment variables:
        POLICY_DIR, REQUESTS_DIR, OUTPUT_DIR, QUACKY_SRC_DIR, etc.
"""

import argparse
import re
import subprocess
import shutil
from functools import wraps
from datetime import datetime, timedelta
from dataclasses import dataclass
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Optional
import pandas as pd
from tqdm import tqdm
import os
import sys
import time
import json
import logging

from dotenv import load_dotenv
load_dotenv()

os.environ["TOKENIZERS_PARALLELISM"] = "false"


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
    # Check if it's a short name
    if model_name.lower() in SUPPORTED_MODELS:
        return SUPPORTED_MODELS[model_name.lower()]
    
    # Check if it's already a full identifier (contains '/')
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
    """
    Configuration for the policy repair pipeline.
    
    Values are resolved in order: CLI args > environment variables > defaults.
    """
    # Directories
    policy_dir: str = ""
    requests_dir: str = ""
    output_dir: str = ""
    log_dir: str = ""
    temp_dir: str = ""
    quacky_src_dir: str = ""
    fault_localization_dir: str = ""
    
    # Experiment parameters
    request_set: int = 10
    total_policies: int = 282
    max_iterations: int = 5
    max_attempts: int = 1
    retry_delay: int = 1
    target_accuracy: float = 100.0
    validation_timeout: int = 300
    
    # Model configuration
    llm_model: str = DEFAULT_MODEL
    ollama_model: str = "gpt-oss"
    
    # Generation hyperparameters
    temperature: float = 0.1
    top_p: float = 0.3
    top_k: int = 40
    repetition_penalty: float = 1.1
    max_new_tokens: int = 4800
    
    @property
    def model_identifier(self) -> str:
        """Get the full HuggingFace model identifier."""
        return get_model_identifier(self.llm_model)
    
    def __post_init__(self):
        """Apply environment variable defaults if paths not provided."""
        req = self.request_set
        
        if not self.policy_dir:
            self.policy_dir = os.environ.get("POLICY_DIR", "./policies")
        if not self.requests_dir:
            self.requests_dir = os.environ.get("REQUESTS_DIR", "./requests")
        if not self.output_dir:
            self.output_dir = os.environ.get("OUTPUT_DIR", f"./results/result-{req}")
        if not self.log_dir:
            self.log_dir = os.environ.get("LOG_DIR", f"./logs/log-{req}")
        if not self.temp_dir:
            self.temp_dir = os.environ.get("TEMP_DIR", f"./temp/val-{req}")
        if not self.quacky_src_dir:
            self.quacky_src_dir = os.environ.get("QUACKY_SRC_DIR", "./quacky/src")
        if not self.fault_localization_dir:
            self.fault_localization_dir = os.environ.get(
                "FAULT_LOCALIZATION_DIR", 
                f"./results/result-{req}-ollama/Quacky_output"
            )
    
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
            fault_localization_dir=args.fault_loc_dir or "",
            request_set=args.request_set,
            total_policies=args.total_policies,
            max_iterations=args.max_iterations,
            max_attempts=args.max_attempts,
            retry_delay=args.retry_delay,
            target_accuracy=args.target_accuracy,
            llm_model=args.model,
            ollama_model=args.ollama_model,
            temperature=args.temperature,
            top_p=args.top_p,
            top_k=args.top_k,
            repetition_penalty=args.repetition_penalty,
            max_new_tokens=args.max_new_tokens,
        )


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    
    # Build model choices help text
    model_choices_help = "Model to use. Options:\n"
    for short_name, desc in MODEL_DESCRIPTIONS.items():
        model_choices_help += f"  {short_name}: {desc}\n"
    model_choices_help += "Or provide a full HuggingFace model identifier."
    
    parser = argparse.ArgumentParser(
        description="LLM-based AWS IAM policy repair with fault localization.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
    # Using short model names
    %(prog)s --model codellama --policies ./policies --requests ./requests
    %(prog)s --model granite --max-iterations 5
    %(prog)s --model deepseek --temperature 0.2
    %(prog)s --model llama3 --top-p 0.5
    
    # Using full HuggingFace identifier
    %(prog)s --model codellama/CodeLlama-7b-Instruct-hf --policies ./policies

Supported Models:
{chr(10).join(f'  {k}: {v}' for k, v in MODEL_DESCRIPTIONS.items())}

Environment Variables:
    POLICY_DIR              Path to policy JSON files
    REQUESTS_DIR            Path to request JSON files
    OUTPUT_DIR              Path for output files
    LOG_DIR                 Path for log files
    TEMP_DIR                Path for temporary files
    QUACKY_SRC_DIR          Path to Quacky source directory
    FAULT_LOCALIZATION_DIR  Path for fault localization outputs
    LLM_MODEL               Model to use (short name or HuggingFace identifier)
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
    dir_group.add_argument("--fault-loc-dir", help="Fault localization output directory")
    
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
    exp_group.add_argument("--retry-delay", type=int, default=1,
                           help="Delay between retries in seconds (default: 1)")
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
    model_group.add_argument("--ollama-model", default="gpt-oss",
                             help="Ollama model name (if using Ollama backend)")
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
    gen_group.add_argument("--max-new-tokens", type=int, default=4800,
                           help="Maximum new tokens to generate (default: 4800)")
    
    # General options
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Handle --list-models
    if args.list_models:
        print("\nSupported Models:")
        print("=" * 70)
        for short_name, full_name in SUPPORTED_MODELS.items():
            desc = MODEL_DESCRIPTIONS[short_name]
            print(f"\n  {short_name}")
            print(f"    HuggingFace: {full_name}")
            print(f"    Description: {desc}")
        print("\n" + "=" * 70)
        print("\nUsage: --model <short_name> or --model <full_huggingface_identifier>")
        print("Example: --model codellama")
        print("Example: --model codellama/CodeLlama-7b-Instruct-hf")
        sys.exit(0)
    
    return args


# Global config instance (initialized in main)
CONFIG: Optional[Config] = None


# =============================================================================
# Logging Setup
# =============================================================================

def setup_logging(config: Config) -> str:
    """Configure logging with file and console handlers."""
    os.makedirs(config.log_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(config.log_dir, f"policy_repair_{timestamp}.log")
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(),
        ],
    )
    return log_file


def retry(max_attempts: int = None, delay: int = None):
    """Decorator for retrying failed function calls."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            _max_attempts = max_attempts if max_attempts else (CONFIG.max_attempts if CONFIG else 1)
            _delay = delay if delay else (CONFIG.retry_delay if CONFIG else 1)
            
            attempts = 0
            while attempts < _max_attempts:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    attempts += 1
                    if attempts == _max_attempts:
                        raise
                    logging.warning(f"Attempt {attempts} failed: {e}. Retrying in {_delay}s...")
                    time.sleep(_delay)
        return wrapper
    return decorator


# =============================================================================
# Model Loading (Lazy Initialization)
# =============================================================================

_model = None
_tokenizer = None
_generator = None


def get_model_and_tokenizer():
    """Lazy-load the model and tokenizer."""
    global _model, _tokenizer, _generator
    
    if _generator is not None:
        return _generator
    
    from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
    import torch
    
    os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'expandable_segments:True'
    
    model_name = CONFIG.model_identifier if CONFIG else SUPPORTED_MODELS[DEFAULT_MODEL]
    
    logging.info(f"Loading model: {model_name}")
    
    _tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    
    if _tokenizer.pad_token is None:
        _tokenizer.pad_token = _tokenizer.eos_token
    
    _model = AutoModelForCausalLM.from_pretrained(
        model_name,
        device_map="auto",
        torch_dtype=torch.float16,
    )
    
    if hasattr(_model, 'gradient_checkpointing_enable'):
        _model.gradient_checkpointing_enable()
    
    _generator = pipeline("text-generation", model=_model, tokenizer=_tokenizer)
    
    logging.info(f"Model loaded successfully: {model_name}")
    
    return _generator


def call_ollama(prompt: str, system_prompt: str = "") -> str:
    """Call the LLM with the given prompt."""
    import torch
    
    try:
        torch.cuda.empty_cache()
        
        generator = get_model_and_tokenizer()
        tokenizer = _tokenizer
        
        if system_prompt:
            full_prompt = f"<|system|>\n{system_prompt}\n<|user|>\n{prompt}"
        else:
            full_prompt = prompt
        
        outputs = generator(
            full_prompt,
            temperature=CONFIG.temperature if CONFIG else 0.1,
            top_p=CONFIG.top_p if CONFIG else 0.3,
            top_k=CONFIG.top_k if CONFIG else 40,
            repetition_penalty=CONFIG.repetition_penalty if CONFIG else 1.1,
            do_sample=True,
            eos_token_id=tokenizer.eos_token_id,
            return_full_text=False,
            max_new_tokens=CONFIG.max_new_tokens if CONFIG else 4800,
            pad_token_id=tokenizer.eos_token_id,
        )
        
        return outputs[0]["generated_text"]
    
    except Exception as e:
        if "CUDA out of memory" in str(e):
            logging.error(f"CUDA out of memory: {e}")
            import torch
            torch.cuda.empty_cache()
        else:
            logging.error(f"Model generation error: {e}")
        raise


# =============================================================================
# SMT Timing Parser
# =============================================================================

def parse_smt_timing_from_output(output_content: str) -> dict:
    """Parse SMT solver timing information from validator output."""
    smt_data = {
        'total_solver_calls': 0,
        'total_solver_time': 0.0,
        'individual_call_times': [],
        'average_call_time': 0.0,
        'min_call_time': 0.0,
        'max_call_time': 0.0,
    }
    
    try:
        lines = output_content.split('\n')
        call_times = []
        
        for line in lines:
            if 'Solver time:' in line:
                time_match = re.search(r'Solver time:\s*([\d.]+)\s*seconds', line)
                if time_match:
                    call_times.append(float(time_match.group(1)))
            
            if 'Total Solver Calls:' in line:
                calls_match = re.search(r'Total Solver Calls:\s*(\d+)', line)
                if calls_match:
                    smt_data['total_solver_calls'] = int(calls_match.group(1))
        
        if call_times:
            smt_data['individual_call_times'] = call_times
            smt_data['total_solver_time'] = sum(call_times)
            smt_data['average_call_time'] = smt_data['total_solver_time'] / len(call_times)
            smt_data['min_call_time'] = min(call_times)
            smt_data['max_call_time'] = max(call_times)
    
    except Exception as e:
        logging.warning(f"Error parsing SMT timing data: {e}")
    
    return smt_data


# =============================================================================
# Prompt Creation
# =============================================================================

def create_simple_repair_prompt(
    original_policy: dict,
    requirements: dict,
    fault_localization_report: str,
    iteration: int = 1,
    previous_accuracy: float = 0.0,
) -> str:
    """Create repair prompt for the LLM."""
    return f"""You are an AWS IAM policy expert. You must use security best practices to repair the following policy so that the provided tests sets are allowed and denied. 

        CURRENT POLICY:    
        {json.dumps(original_policy, indent=2)}

        REQUIREMENTS to SATISFY:
        {json.dumps(requirements, indent=2)}

        REPAIR STATUS:
        Iteration: {iteration}
        Previous Accuracy: {previous_accuracy:.1f}%

        Your Task IS TO LOOK AT THIS FAULT LOCALIZATION REPORT TO CHECK WHICH REQUIREMENTS ARE BEING INCORRECTLY ALLOWED/DENIED AND FIX the policy accordingly:
        {fault_localization_report}

        Return ONLY the complete corrected policy as valid JSON. No explanations, no markdown formatting.

        CORRECTED POLICY:"""


def create_simple_system_prompt() -> str:
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
# JSON Extraction and Validation
# =============================================================================

def extract_and_validate_json(response_text: str) -> dict:
    """Extract and validate JSON from LLM response."""
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
    
    json_text = text[start_idx:end_idx + 1]
    
    try:
        parsed_json = json.loads(json_text)
        
        if not isinstance(parsed_json, dict):
            raise ValueError("Response is not a JSON object")
        if "Statement" not in parsed_json:
            raise ValueError("Missing 'Statement' field in policy")
        if not isinstance(parsed_json["Statement"], list):
            raise ValueError("'Statement' field must be an array")
        if "Version" not in parsed_json:
            parsed_json["Version"] = "2012-10-17"
        
        return parsed_json
    
    except json.JSONDecodeError as e:
        logging.error(f"LLM generated invalid JSON at line {e.lineno}, column {e.colno}: {e.msg}")
        logging.error(f"=== EXTRACTED JSON ===\n{json_text}\n=== END ===")
        raise ValueError(f"LLM generated invalid JSON: {e}")


def extract_failing_requests(validator_output: str, original_reqs: dict) -> dict:
    """Parse SMT validator output and return only the failing requests."""
    failing_ids = set()
    
    for line in validator_output.splitlines():
        if line.startswith("Request:"):
            parts = line.split()
            if len(parts) >= 2:
                failing_ids.add(parts[1].strip())
    
    failing_reqs = [r for r in original_reqs.get("Requests", []) if r.get("id") in failing_ids]
    return {"Requests": failing_reqs}


# =============================================================================
# Policy Repair
# =============================================================================

@retry()
def repair_policy_simple(
    policy: dict,
    requirements: dict,
    fault_localization_report: str,
    iteration: int = 1,
    policy_idx: int = None,
    previous_accuracy: float = 0.0,
) -> dict:
    """Repair policy using LLM with fault localization guidance."""
    prompt = create_simple_repair_prompt(
        policy, requirements, fault_localization_report, iteration, previous_accuracy
    )
    system_prompt = create_simple_system_prompt()
    
    logging.info(f"{'=' * 80}")
    logging.info(f"Iterative Repair - ITERATION {iteration}")
    logging.info(f"{'=' * 80}")
    logging.info(f"System prompt length: {len(system_prompt)} chars")
    logging.info(f"User prompt length: {len(prompt)} chars")
    
    response_text = call_ollama(prompt, system_prompt)
    
    # Save raw LLM output
    if CONFIG and policy_idx is not None:
        raw_output_file = os.path.join(CONFIG.temp_dir, f"raw_llm_output_policy_{policy_idx:03d}_iter_{iteration}.txt")
        os.makedirs(CONFIG.temp_dir, exist_ok=True)
        with open(raw_output_file, 'w', encoding='utf-8') as f:
            f.write(response_text)
    
    logging.info(f"Response length: {len(response_text)} chars")
    
    if not response_text:
        raise ValueError("Empty response from LLM")
    
    repaired_policy = extract_and_validate_json(response_text)
    
    original_statements = policy.get('Statement', [])
    repaired_statements = repaired_policy.get('Statement', [])
    logging.info(f"Statements: {len(original_statements)} -> {len(repaired_statements)}")
    
    return repaired_policy


# =============================================================================
# SMT Validator
# =============================================================================

def run_smt_validator(policy_file: str, requests_file: str, policy_idx: int = None) -> dict:
    """Run SMT validator and return accuracy metrics."""
    original_dir = os.getcwd()
    
    try:
        os.chdir(CONFIG.quacky_src_dir)
        
        # Prepare output path
        if policy_idx is not None:
            policy_dir = os.path.join(CONFIG.output_dir, "Quacky_output", f"policy_{policy_idx:03d}")
            os.makedirs(policy_dir, exist_ok=True)
            output_path = os.path.join(policy_dir, f"policy_{policy_idx:03d}_accuracy_validation.txt")
        else:
            output_dir = os.path.join(CONFIG.output_dir, "Quacky_output")
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f"temp_accuracy_{os.getpid()}_{int(time.time())}.txt")
        
        cmd = [
            sys.executable, 'validate_requests.py',
            '-p1', policy_file,
            '--requests', requests_file,
            '-s',
        ]
        
        logging.debug(f"Running validation: {' '.join(cmd)}")
        
        with open(output_path, 'w') as f:
            result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, text=True,
                                    timeout=CONFIG.validation_timeout)
        
        if result.returncode != 0:
            raise Exception(f"Validation failed: {result.stderr}")
        
        with open(output_path, 'r') as f:
            output_content = f.read()
        
        os.chdir(original_dir)
        
        # Parse results
        accuracy = 0.0
        total_requests = correct_count = incorrect_count = 0
        misclassified_allow_to_deny = misclassified_deny_to_allow = 0
        
        in_analysis = False
        for line in output_content.splitlines():
            line = line.strip()
            
            if "INDIVIDUAL REQUEST ANALYSIS" in line:
                in_analysis = True
                continue
            if not in_analysis:
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
        
        smt_timing = parse_smt_timing_from_output(output_content)
        
        logging.info(f"Validation: {accuracy:.1f}% accuracy, {total_requests} requests")
        
        if os.path.exists(output_path):
            os.unlink(output_path)
        
        return {
            'accuracy': accuracy,
            'total_requests': total_requests,
            'correct': correct_count,
            'incorrect': incorrect_count,
            'misclassified_allow_to_deny': misclassified_allow_to_deny,
            'misclassified_deny_to_allow': misclassified_deny_to_allow,
            'raw_output': output_content,
            'output_file': output_path,
            'smt_timing': smt_timing,
            'total_solver_calls': smt_timing.get('total_solver_calls', 0),
            'total_solver_time': smt_timing.get('total_solver_time', 0.0),
            'average_solver_time': smt_timing.get('average_call_time', 0.0),
            'min_solver_time': smt_timing.get('min_call_time', 0.0),
            'max_solver_time': smt_timing.get('max_call_time', 0.0),
        }
    
    except subprocess.TimeoutExpired:
        os.chdir(original_dir)
        raise Exception("SMT validator timed out")
    except Exception as e:
        os.chdir(original_dir)
        raise


# =============================================================================
# File I/O Utilities
# =============================================================================

def load_json_file(path: str) -> dict:
    """Load JSON file."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json_file(data: dict, path: str) -> None:
    """Save data to JSON file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


# =============================================================================
# Fault Localization
# =============================================================================

def load_fault_localization_report(policy_idx: int, iteration: int) -> str:
    """Load fault localization report for a specific policy and iteration."""
    policy_iter_dir = os.path.join(
        CONFIG.fault_localization_dir, f"policy_{policy_idx:03d}", f"iteration_{iteration}"
    )
    main_report = os.path.join(policy_iter_dir, "fault_localization_report.txt")
    
    if os.path.exists(main_report):
        try:
            with open(main_report, 'r', encoding='utf-8') as f:
                report = f.read().strip()
            logging.info(f"Loaded FL report for policy {policy_idx} iter {iteration}: {len(report)} chars")
            return report
        except Exception as e:
            logging.error(f"Error reading FL report: {e}")
    
    # Fallback locations
    fallbacks = [
        os.path.join(CONFIG.fault_localization_dir, f"policy_{policy_idx:03d}_iter_{iteration}_llm_report.txt"),
        os.path.join(CONFIG.fault_localization_dir, f"{policy_idx}_iter_{iteration}_llm_report.txt"),
        os.path.join(CONFIG.fault_localization_dir, f"policy_{policy_idx:03d}_llm_report.txt"),
    ]
    
    for path in fallbacks:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read().strip()
            except Exception:
                continue
    
    logging.warning(f"No FL report found for policy {policy_idx} iteration {iteration}")
    return ""


def save_policy_for_fault_localization(policy: dict, policy_idx: int, iteration: int) -> str:
    """Save repaired policy for fault localization analysis."""
    policy_file = os.path.join(CONFIG.temp_dir, f"repaired_policy_{policy_idx}_iter_{iteration}.json")
    os.makedirs(CONFIG.temp_dir, exist_ok=True)
    
    with open(policy_file, 'w', encoding='utf-8') as f:
        json.dump(policy, f, indent=2)
    
    return policy_file


def run_fault_localization(
    policy_file: str,
    requests_file: str,
    policy_idx: int,
    iteration: int,
) -> str:
    """Run fault localization on a policy and return the report path."""
    original_dir = os.getcwd()
    
    try:
        os.chdir(CONFIG.quacky_src_dir)
        
        policy_iter_dir = os.path.join(
            CONFIG.fault_localization_dir, f"policy_{policy_idx:03d}", f"iteration_{iteration}"
        )
        os.makedirs(policy_iter_dir, exist_ok=True)
        
        output_base = os.path.join(policy_iter_dir, f"fault_analysis_{policy_idx:03d}_iter_{iteration}")
        
        cmd = [
            sys.executable, 'validate_requests.py',
            '-p1', policy_file,
            '--requests', requests_file,
            '-s',
            '--identify-faulty',
            '--output', output_base,
        ]
        
        logging.info(f"Running fault localization for policy {policy_idx} iter {iteration}")
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        # Save stdout/stderr for debugging
        with open(os.path.join(policy_iter_dir, f"stdout_{policy_idx:03d}_iter_{iteration}.txt"), 'w') as f:
            f.write(result.stdout)
        with open(os.path.join(policy_iter_dir, f"stderr_{policy_idx:03d}_iter_{iteration}.txt"), 'w') as f:
            f.write(result.stderr)
        
        if result.returncode != 0:
            logging.error(f"Fault localization failed: {result.stderr}")
            return ""
        
        target_report = os.path.join(policy_iter_dir, "fault_localization_report.txt")
        
        # Look for LLM report in validator output
        base_filename = os.path.basename(output_base)
        validator_output_dir = Path(CONFIG.fault_localization_dir)
        expected_report = validator_output_dir / f"{base_filename}_llm_report.txt"
        
        if expected_report.exists():
            shutil.copy2(expected_report, target_report)
            return target_report
        
        # Try to find any llm_report.txt file
        if validator_output_dir.exists():
            llm_reports = list(validator_output_dir.glob("*_llm_report.txt"))
            if llm_reports:
                shutil.copy2(llm_reports[0], target_report)
                return target_report
        
        return ""
    
    except subprocess.TimeoutExpired:
        logging.error("Fault localization timed out")
        return ""
    except Exception as e:
        logging.error(f"Error in fault localization: {e}")
        return ""
    finally:
        os.chdir(original_dir)


# =============================================================================
# Policy Processing
# =============================================================================

def process_policy_simple(idx: int, baseline_accuracy: float = 0.0) -> dict:
    """Process a single policy with iterative repair."""
    cycle_start = time.time()
    
    policy_file = os.path.join(CONFIG.policy_dir, f"{idx}.json")
    req_file = os.path.join(CONFIG.requests_dir, f"{idx}.json")
    
    if not os.path.exists(policy_file) or not os.path.exists(req_file):
        raise FileNotFoundError(f"Missing files for policy {idx}")
    
    original_policy = load_json_file(policy_file)
    requirements = load_json_file(req_file)
    
    logging.info(f"Processing policy {idx} (baseline: {baseline_accuracy:.1f}%)")
    
    if baseline_accuracy >= CONFIG.target_accuracy:
        output_file = os.path.join(CONFIG.output_dir, f"repaired_{idx}_already_perfect.json")
        save_json_file(original_policy, output_file)
        return {
            'index': idx,
            'status': 'already_perfect',
            'baseline_accuracy': baseline_accuracy,
            'final_accuracy': baseline_accuracy,
            'iterations_used': 0,
            'iteration_accuracies': [baseline_accuracy],
            'iteration_results': [],
            'final_policy_file': output_file,
            'cycle_duration_seconds': 0,
            'cycle_duration_formatted': "00:00:00",
        }
    
    iteration_results = []
    current_policy = original_policy.copy()
    current_accuracy = baseline_accuracy
    final_accuracy = baseline_accuracy
    iteration_accuracies = [baseline_accuracy]
    
    for iteration in range(1, CONFIG.max_iterations + 1):
        iter_start = time.time()
        logging.info(f"Policy {idx} - Iteration {iteration}/{CONFIG.max_iterations}")
        
        try:
            fl_report = load_fault_localization_report(idx, iteration)
            
            repaired_policy = repair_policy_simple(
                current_policy, requirements, fl_report, iteration,
                policy_idx=idx,
                previous_accuracy=current_accuracy,
            )
            
            temp_policy_file = os.path.join(CONFIG.temp_dir, f"policy_{idx}_iter_{iteration}.json")
            save_json_file(repaired_policy, temp_policy_file)
            
            validation = run_smt_validator(temp_policy_file, req_file, policy_idx=idx)
            accuracy = validation['accuracy']
            iteration_accuracies.append(accuracy)
            final_accuracy = accuracy
            
            iteration_results.append({
                'policy_idx': idx,
                'iteration': iteration,
                'accuracy': accuracy,
                'baseline_accuracy': baseline_accuracy,
                'total_requests': validation['total_requests'],
                'correct': validation['correct'],
                'incorrect': validation['incorrect'],
                'misclassified_allow_to_deny': validation['misclassified_allow_to_deny'],
                'misclassified_deny_to_allow': validation['misclassified_deny_to_allow'],
                'policy_file': temp_policy_file,
                'iteration_duration_seconds': time.time() - iter_start,
                'total_solver_calls': validation.get('total_solver_calls', 0),
                'total_solver_time': validation.get('total_solver_time', 0.0),
                'average_solver_time': validation.get('average_solver_time', 0.0),
                'min_solver_time': validation.get('min_solver_time', 0.0),
                'max_solver_time': validation.get('max_solver_time', 0.0),
            })
            
            if accuracy >= CONFIG.target_accuracy:
                output_file = os.path.join(CONFIG.output_dir, f"repaired_{idx}_final.json")
                save_json_file(repaired_policy, output_file)
                cycle_time = time.time() - cycle_start
                return {
                    'index': idx,
                    'status': 'success',
                    'baseline_accuracy': baseline_accuracy,
                    'final_accuracy': accuracy,
                    'iterations_used': iteration,
                    'iteration_accuracies': iteration_accuracies,
                    'iteration_results': iteration_results,
                    'final_policy_file': output_file,
                    'cycle_duration_seconds': cycle_time,
                    'cycle_duration_formatted': str(timedelta(seconds=int(cycle_time))),
                }
            
            # Extract failing requests for next iteration
            failing = extract_failing_requests(validation['raw_output'], load_json_file(req_file))
            if failing["Requests"]:
                logging.info(f"Iteration {iteration}: {len(failing['Requests'])} failing requests")
                requirements = failing
            
            # Pre-generate fault localization for next iteration
            if iteration < CONFIG.max_iterations:
                logging.info(f"Generating FL for iteration {iteration + 1}...")
                fl_policy = save_policy_for_fault_localization(repaired_policy, idx, iteration)
                run_fault_localization(fl_policy, req_file, idx, iteration + 1)
            
            if current_accuracy <= accuracy:
                current_policy = repaired_policy.copy()
                current_accuracy = accuracy
        
        except Exception as e:
            logging.error(f"Iteration {iteration} failed for policy {idx}: {e}")
    
    # Loop completed without success
    cycle_time = time.time() - cycle_start
    best_iter = max(iteration_results, key=lambda r: r['accuracy'], default=None)
    
    if best_iter and best_iter['policy_file'] and os.path.exists(best_iter['policy_file']):
        output_file = os.path.join(CONFIG.output_dir, f"repaired_{idx}_best.json")
        shutil.copy2(best_iter['policy_file'], output_file)
    else:
        output_file = os.path.join(CONFIG.output_dir, f"repaired_{idx}_original.json")
        save_json_file(original_policy, output_file)
    
    return {
        'index': idx,
        'status': 'failed',
        'baseline_accuracy': baseline_accuracy,
        'final_accuracy': final_accuracy,
        'iterations_used': CONFIG.max_iterations,
        'iteration_accuracies': iteration_accuracies,
        'iteration_results': iteration_results,
        'final_policy_file': output_file,
        'cycle_duration_seconds': cycle_time,
        'cycle_duration_formatted': str(timedelta(seconds=int(cycle_time))),
    }


# =============================================================================
# Progress Tracking
# =============================================================================

class ProgressTracker:
    """Track progress of policy repair across runs."""
    
    def __init__(self, progress_file: str):
        self.progress_file = progress_file
        self.progress = self._load()
    
    def _load(self) -> dict:
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "last_processed": -1,
            "completed": [],
            "failed": [],
            "policy_iterations": {},
            "baseline_completed": [],
            "baseline_accuracies": {},
        }
    
    def save(self) -> None:
        os.makedirs(os.path.dirname(self.progress_file), exist_ok=True)
        with open(self.progress_file, 'w') as f:
            json.dump(self.progress, f, indent=2)
    
    def mark_baseline_completed(self, idx: int, accuracy: float = None) -> None:
        if idx not in self.progress["baseline_completed"]:
            self.progress["baseline_completed"].append(idx)
        if accuracy is not None:
            self.progress["baseline_accuracies"][str(idx)] = accuracy
        self.save()
    
    def get_baseline_accuracy(self, idx: int) -> float:
        return self.progress["baseline_accuracies"].get(str(idx), 0.0)
    
    def is_baseline_done(self, idx: int) -> bool:
        return idx in self.progress.get("baseline_completed", [])
    
    def is_done(self, idx: int) -> bool:
        return idx in self.progress.get("completed", [])
    
    def mark_completed(
        self,
        idx: int,
        baseline_accuracy: float,
        final_accuracy: float,
        iterations_used: int,
        iteration_accuracies: list,
        cycle_duration: float = 0.0,
    ) -> None:
        self.progress["last_processed"] = idx
        if idx not in self.progress["completed"]:
            self.progress["completed"].append(idx)
        if idx in self.progress["failed"]:
            self.progress["failed"].remove(idx)
        
        self.progress["baseline_accuracies"][str(idx)] = baseline_accuracy
        
        repair_accuracies = iteration_accuracies[1:] if len(iteration_accuracies) > 1 else []
        avg_accuracy = sum(repair_accuracies) / len(repair_accuracies) if repair_accuracies else final_accuracy
        
        self.progress["policy_iterations"][str(idx)] = {
            "status": "completed",
            "baseline_accuracy": baseline_accuracy,
            "final_accuracy": final_accuracy,
            "improvement": final_accuracy - baseline_accuracy,
            "iterations_used": iterations_used,
            "iteration_accuracies": iteration_accuracies,
            "average_accuracy": avg_accuracy,
            "cycle_duration_seconds": cycle_duration,
            "cycle_duration_formatted": str(timedelta(seconds=int(cycle_duration))) if cycle_duration > 0 else "00:00:00",
        }
        self.save()
    
    def mark_failed(
        self,
        idx: int,
        baseline_accuracy: float,
        final_accuracy: float,
        iterations_used: int,
        iteration_accuracies: list,
        cycle_duration: float = 0.0,
    ) -> None:
        if idx not in self.progress["failed"]:
            self.progress["failed"].append(idx)
        
        self.progress["baseline_accuracies"][str(idx)] = baseline_accuracy
        
        repair_accuracies = iteration_accuracies[1:] if len(iteration_accuracies) > 1 else []
        avg_accuracy = sum(repair_accuracies) / len(repair_accuracies) if repair_accuracies else final_accuracy
        
        self.progress["policy_iterations"][str(idx)] = {
            "status": "failed",
            "baseline_accuracy": baseline_accuracy,
            "final_accuracy": final_accuracy,
            "improvement": final_accuracy - baseline_accuracy,
            "iterations_used": iterations_used,
            "iteration_accuracies": iteration_accuracies,
            "average_accuracy": avg_accuracy,
            "cycle_duration_seconds": cycle_duration,
            "cycle_duration_formatted": str(timedelta(seconds=int(cycle_duration))) if cycle_duration > 0 else "00:00:00",
        }
        self.save()


# =============================================================================
# Baseline Validation
# =============================================================================

def run_baseline_validation(idx: int) -> dict:
    """Run baseline validation on the original policy."""
    policy_file = os.path.join(CONFIG.policy_dir, f"{idx}.json")
    req_file = os.path.join(CONFIG.requests_dir, f"{idx}.json")
    
    if not os.path.exists(policy_file) or not os.path.exists(req_file):
        raise FileNotFoundError(f"Missing files for policy {idx}")
    
    logging.info(f"Baseline validation for policy {idx}...")
    
    try:
        validation = run_smt_validator(policy_file, req_file, policy_idx=idx)
        
        return {
            'policy_idx': idx,
            'validation_type': 'baseline',
            'accuracy': validation['accuracy'],
            'total_requests': validation['total_requests'],
            'correct': validation['correct'],
            'incorrect': validation['incorrect'],
            'misclassified_allow_to_deny': validation['misclassified_allow_to_deny'],
            'misclassified_deny_to_allow': validation['misclassified_deny_to_allow'],
            'output_file': validation['output_file'],
            'total_solver_calls': validation.get('total_solver_calls', 0),
            'total_solver_time': validation.get('total_solver_time', 0.0),
            'average_solver_time': validation.get('average_solver_time', 0.0),
            'min_solver_time': validation.get('min_solver_time', 0.0),
            'max_solver_time': validation.get('max_solver_time', 0.0),
        }
    
    except Exception as e:
        logging.error(f"Baseline validation failed for policy {idx}: {e}")
        return {
            'policy_idx': idx,
            'validation_type': 'baseline',
            'accuracy': 0.0,
            'total_solver_calls': 0,
            'total_solver_time': 0.0,
            'error': str(e),
        }


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Main entry point for policy repair."""
    global CONFIG
    
    args = parse_arguments()
    CONFIG = Config.from_args(args)
    
    log_file = setup_logging(CONFIG)
    
    logging.info("=" * 60)
    logging.info("LLM-based Policy Repair System")
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
    
    # Validate directories
    for directory in [CONFIG.policy_dir, CONFIG.requests_dir]:
        if not os.path.isdir(directory):
            logging.error(f"Directory not found: {directory}")
            sys.exit(1)
    
    if not CONFIG.smt_validator_script.exists():
        logging.error(f"SMT validator not found: {CONFIG.smt_validator_script}")
        sys.exit(1)
    
    # Create output directories
    for directory in [CONFIG.output_dir, CONFIG.temp_dir, CONFIG.fault_localization_dir,
                      os.path.join(CONFIG.output_dir, "Quacky_output")]:
        os.makedirs(directory, exist_ok=True)
    
    tracker = ProgressTracker(os.path.join(CONFIG.output_dir, "repair_progress.json"))
    total = CONFIG.total_policies
    
    # Step 1: Baseline validation
    print("\n" + "=" * 60)
    print("STEP 1: BASELINE VALIDATION")
    print("=" * 60)
    
    baseline_results = []
    baseline_to_process = [i for i in range(total) if not tracker.is_baseline_done(i)]
    
    if baseline_to_process:
        for idx in tqdm(baseline_to_process, desc="Baseline validation"):
            try:
                result = run_baseline_validation(idx)
                baseline_results.append(result)
                tracker.mark_baseline_completed(idx, result.get('accuracy', 0.0))
            except Exception as e:
                logging.error(f"Baseline failed for policy {idx}: {e}")
                baseline_results.append({'policy_idx': idx, 'validation_type': 'baseline', 'accuracy': 0.0, 'error': str(e)})
                tracker.mark_baseline_completed(idx, 0.0)
    else:
        logging.info("Baseline validations already completed.")
        for i in range(total):
            baseline_results.append({
                'policy_idx': i,
                'validation_type': 'baseline',
                'accuracy': tracker.get_baseline_accuracy(i),
            })
    
    # Save baseline results
    if baseline_results:
        baseline_df = pd.DataFrame(baseline_results)
        baseline_df.to_csv(os.path.join(CONFIG.output_dir, "baseline_results.csv"), index=False)
    
    # Print baseline summary
    successful = [r for r in baseline_results if r.get('accuracy', 0) > 0 and 'error' not in r]
    perfect = [r for r in baseline_results if r.get('accuracy', 0) >= CONFIG.target_accuracy]
    
    if successful:
        avg_accuracy = sum(r['accuracy'] for r in successful) / len(successful)
        print(f"Baseline average accuracy: {avg_accuracy:.1f}%")
        print(f"Already perfect: {len(perfect)}")
    
    # Step 2: Policy repair
    print("\n" + "=" * 60)
    print("STEP 2: POLICY REPAIR")
    print("=" * 60)
    
    baseline_map = {r['policy_idx']: r.get('accuracy', 0.0) for r in baseline_results}
    to_process = [i for i in range(total) if not tracker.is_done(i)]
    
    all_results = []
    all_iteration_data = baseline_results.copy()
    
    for idx in tqdm(to_process, desc="Repairing policies"):
        baseline_acc = baseline_map.get(idx, 0.0)
        
        # Generate initial fault localization
        try:
            policy_file = os.path.join(CONFIG.policy_dir, f"{idx}.json")
            req_file = os.path.join(CONFIG.requests_dir, f"{idx}.json")
            
            initial_fl = run_fault_localization(policy_file, req_file, idx, 1)
            if not initial_fl:
                # Create empty report
                fl_dir = os.path.join(CONFIG.fault_localization_dir, f"policy_{idx:03d}", "iteration_1")
                os.makedirs(fl_dir, exist_ok=True)
                with open(os.path.join(fl_dir, "fault_localization_report.txt"), 'w') as f:
                    f.write("No fault localization available.\n")
        except Exception as e:
            logging.error(f"Initial FL failed for policy {idx}: {e}")
        
        # Process policy
        try:
            result = process_policy_simple(idx, baseline_acc)
            
            if result['status'] in ['success', 'already_perfect']:
                tracker.mark_completed(
                    idx, result['baseline_accuracy'], result['final_accuracy'],
                    result['iterations_used'], result['iteration_accuracies'],
                    result.get('cycle_duration_seconds', 0.0)
                )
            else:
                tracker.mark_failed(
                    idx, result['baseline_accuracy'], result['final_accuracy'],
                    result['iterations_used'], result.get('iteration_accuracies', []),
                    result.get('cycle_duration_seconds', 0.0)
                )
            
            all_results.append(result)
            all_iteration_data.extend(result.get('iteration_results', []))
        
        except Exception as e:
            logging.error(f"Policy {idx} failed: {e}", exc_info=True)
            tracker.mark_failed(idx, baseline_acc, 0.0, 0, [])
            all_results.append({
                'index': idx,
                'status': 'error',
                'baseline_accuracy': baseline_acc,
                'final_accuracy': 0.0,
                'iterations_used': 0,
                'iteration_accuracies': [],
                'iteration_results': [],
                'error': str(e),
            })
    
    # Save results
    if all_results:
        pd.DataFrame(all_results).to_csv(os.path.join(CONFIG.output_dir, "repair_summary.csv"), index=False)
    if all_iteration_data:
        pd.DataFrame(all_iteration_data).to_csv(os.path.join(CONFIG.output_dir, "repair_details.csv"), index=False)
    
    # Final summary
    successful = len([r for r in all_results if r.get('status') in ['success', 'already_perfect']])
    improved = len([r for r in all_results if r.get('status') == 'success'])
    failed = len([r for r in all_results if r.get('status') in ['failed', 'error']])
    
    print(f"\n{'=' * 60}")
    print("FINAL SUMMARY")
    print(f"{'=' * 60}")
    print(f"Total policies: {len(all_results)}")
    print(f"Successfully repaired: {improved}")
    print(f"Already perfect: {successful - improved}")
    print(f"Failed: {failed}")
    
    if all_results:
        avg_baseline = sum(r.get('baseline_accuracy', 0) for r in all_results) / len(all_results)
        avg_final = sum(r.get('final_accuracy', 0) for r in all_results) / len(all_results)
        print(f"Average baseline: {avg_baseline:.1f}%")
        print(f"Average final: {avg_final:.1f}%")
        print(f"Improvement: {avg_final - avg_baseline:.1f} percentage points")
    
    print(f"\nResults saved to: {CONFIG.output_dir}")


if __name__ == "__main__":
    main()