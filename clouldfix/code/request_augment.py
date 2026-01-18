"""
SMT-based Request Validation and Augmentation Module.

This module identifies misclassified AWS IAM policy requests using SMT validation
and augments them with similar resource variations to improve test coverage.

Usage:
    python smt_request_augmenter.py --quacky-src /path/to/quacky/src \\
                                    --policies /path/to/policies \\
                                    --requests /path/to/requests \\
                                    --output /path/to/output

    Or set environment variables:
        QUACKY_SRC_DIR, POLICY_DIR, REQUESTS_DIR, OUTPUT_DIR
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Config:
    """
    Configuration settings for the validation pipeline.
    
    Paths can be provided via:
        1. Direct instantiation
        2. Command-line arguments
        3. Environment variables
        4. Defaults (current directory structure)
    """
    
    quacky_src_dir: str = ""
    policy_dir: str = ""
    requests_dir: str = ""
    output_dir: str = ""
    temp_dir: str = "./temp"
    requests_subdir: str = "request-10"
    validation_timeout: int = 300
    
    def __post_init__(self):
        """Apply environment variable defaults if paths not provided."""
        if not self.quacky_src_dir:
            self.quacky_src_dir = os.environ.get("QUACKY_SRC_DIR", "./quacky/src")
        if not self.policy_dir:
            self.policy_dir = os.environ.get("POLICY_DIR", "./policies")
        if not self.requests_dir:
            self.requests_dir = os.environ.get("REQUESTS_DIR", "./requests")
        if not self.output_dir:
            self.output_dir = os.environ.get("OUTPUT_DIR", "./output")
    
    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "Config":
        """Create Config from parsed command-line arguments."""
        return cls(
            quacky_src_dir=args.quacky_src or "",
            policy_dir=args.policies or "",
            requests_dir=args.requests or "",
            output_dir=args.output or "",
            temp_dir=args.temp_dir,
            requests_subdir=args.requests_subdir,
            validation_timeout=args.timeout,
        )


@dataclass
class ValidationResult:
    """Results from SMT validation."""
    
    accuracy: float = 0.0
    total_requests: int = 0
    correct: int = 0
    incorrect: int = 0
    misclassified_requests: list = field(default_factory=list)
    raw_output: str = ""


@dataclass
class MisclassifiedRequest:
    """Details of a misclassified request."""
    
    request_id: str
    action: str
    resource: str
    principal: Optional[str]
    condition: Optional[str]
    expected: str
    actual: str


@dataclass
class ProcessingResult:
    """Results from processing a single policy."""
    
    policy_idx: int
    accuracy: float = 0.0
    total_requests: int = 0
    misclassified_count: int = 0
    misclassified_ids: list = field(default_factory=list)
    output_file: str = ""
    error: Optional[str] = None



def setup_logging(level: int = logging.INFO) -> None:
    """Configure logging with consistent formatting."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )



class SMTValidator:
    """Handles SMT-based policy validation using Quacky."""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    def validate(
        self,
        policy_file: str,
        requests_file: str,
        policy_idx: Optional[int] = None,
    ) -> ValidationResult:
        """
        Run SMT validator and extract results.
        
        Args:
            policy_file: Path to the policy JSON file.
            requests_file: Path to the requests JSON file.
            policy_idx: Optional policy index for organizing output.
            
        Returns:
            ValidationResult containing accuracy metrics and misclassified requests.
            
        Raises:
            ValidationError: If validation fails or times out.
        """
        original_dir = os.getcwd()
        
        try:
            os.chdir(self.config.quacky_src_dir)
            output_path = self._prepare_output_path(original_dir, policy_idx)
            
            cmd = self._build_command(original_dir, policy_file, requests_file)
            self.logger.info(f"Running SMT validation: {' '.join(cmd)}")
            
            output_content = self._execute_validation(cmd, output_path)
            
            return self._parse_results(output_content)
            
        except subprocess.TimeoutExpired:
            raise ValidationError("SMT validator timed out")
        except Exception as e:
            self.logger.error(f"Error running SMT validator: {e}")
            raise
        finally:
            os.chdir(original_dir)
    
    def _prepare_output_path(self, base_dir: str, policy_idx: Optional[int]) -> str:
        """Prepare the output file path for validation results."""
        if policy_idx is not None:
            output_dir = Path(base_dir) / self.config.output_dir / "Quacky_output" / f"policy_{policy_idx:03d}"
            output_dir.mkdir(parents=True, exist_ok=True)
            return str(output_dir / f"policy_{policy_idx:03d}_accuracy_validation.txt")
        
        output_dir = Path(base_dir) / self.config.output_dir / "Quacky_output"
        output_dir.mkdir(parents=True, exist_ok=True)
        return str(output_dir / f"temp_accuracy_{os.getpid()}_{int(time.time())}.txt")
    
    def _build_command(self, base_dir: str, policy_file: str, requests_file: str) -> list:
        """Build the validation command."""
        return [
            sys.executable,
            "validate_requests.py",
            "-p1", os.path.abspath(os.path.join(base_dir, policy_file)),
            "--requests", os.path.abspath(os.path.join(base_dir, requests_file)),
            "-s",
        ]
    
    def _execute_validation(self, cmd: list, output_path: str) -> str:
        """Execute the validation subprocess and return output."""
        with open(output_path, "w") as output_file:
            result = subprocess.run(
                cmd,
                stdout=output_file,
                stderr=subprocess.PIPE,
                text=True,
                timeout=self.config.validation_timeout,
            )
        
        if result.returncode != 0:
            raise ValidationError(f"SMT validation failed: {result.stderr}")
        
        with open(output_path, "r") as f:
            content = f.read()
        
        # Clean up temporary file
        Path(output_path).unlink(missing_ok=True)
        
        return content
    
    def _parse_results(self, output_content: str) -> ValidationResult:
        """Parse validation output into structured results."""
        result = ValidationResult(raw_output=output_content)
        
        self._parse_accuracy_metrics(output_content, result)
        result.misclassified_requests = self._extract_misclassified(output_content)
        
        self.logger.info(
            f"SMT Validation Results - Accuracy: {result.accuracy}%, "
            f"Total: {result.total_requests}, Misclassified: {len(result.misclassified_requests)}"
        )
        
        return result
    
    def _parse_accuracy_metrics(self, content: str, result: ValidationResult) -> None:
        """Extract accuracy metrics from output content."""
        lines = content.split("\n")
        in_analysis = False
        
        for i, line in enumerate(lines):
            line = line.strip()
            
            if "INDIVIDUAL REQUEST ANALYSIS" in line:
                in_analysis = True
                continue
            
            if not in_analysis:
                continue
            
            # Check for section end
            if line.startswith("=") and len(line) > 10:
                remaining = "".join(lines[i:i+5])
                if "Results saved" in remaining or "saved to HOME" in remaining:
                    break
            
            # Parse metrics
            if line.startswith("Total Individual Requests:"):
                if match := re.search(r"(\d+)", line):
                    result.total_requests = int(match.group(1))
            elif line.startswith("Correct Classifications:"):
                if match := re.search(r"(\d+)", line):
                    result.correct = int(match.group(1))
            elif line.startswith("Incorrect Classifications:"):
                if match := re.search(r"(\d+)", line):
                    result.incorrect = int(match.group(1))
            elif line.startswith("Overall Accuracy:"):
                if match := re.search(r"(\d+\.?\d*)%", line):
                    result.accuracy = float(match.group(1))
    
    def _extract_misclassified(self, content: str) -> list:
        """Extract misclassified request details from output."""
        misclassified = []
        current_request = {}
        
        for line in content.split("\n"):
            line = line.strip()
            
            if "Validating individual request:" in line:
                if match := re.search(r"Validating individual request: (\w+)_combo_\d+", line):
                    current_request = {"id": match.group(1)}
            
            elif line.startswith("Action:") and current_request:
                self._parse_request_details(line, current_request)
            
            elif "INCORRECT:" in line and current_request:
                if match := re.search(r"Expected=(\w+), Got=(\w+)", line):
                    misclassified.append({
                        "request_id": current_request.get("id", "unknown"),
                        "action": current_request.get("action", "unknown"),
                        "resource": current_request.get("resource", "unknown"),
                        "principal": current_request.get("principal"),
                        "condition": current_request.get("condition"),
                        "expected": match.group(1),
                        "actual": match.group(2),
                    })
            
            elif "CORRECT:" in line or "Processing request object:" in line:
                current_request = {}
        
        self.logger.info(f"Extracted {len(misclassified)} misclassified requests")
        return misclassified
    
    def _parse_request_details(self, line: str, request: dict) -> None:
        """Parse request details from a comma-separated line."""
        field_map = {
            "Action": "action",
            "Resource": "resource",
            "Principal": "principal",
            "Condition": "condition",
        }
        
        for part in line.split(", "):
            for prefix, key in field_map.items():
                if part.startswith(f"{prefix}:"):
                    value = part.split(": ", 1)[1].strip()
                    request[key] = None if value == "None" else value
                    break


class ValidationError(Exception):
    """Raised when SMT validation fails."""
    pass


# =============================================================================
# Resource Augmentation
# =============================================================================

class ResourceAugmenter:
    """Generates similar AWS resource variations for augmentation."""
    
    # Resource type patterns and their variation generators
    RESOURCE_PATTERNS = {
        ("iam::", "role/"): "_augment_iam_role",
        ("iam::", "user/"): "_augment_iam_user",
        ("kms:", "key/"): "_augment_kms_key",
        ("s3:::",): "_augment_s3",
        ("lambda:", "function:"): "_augment_lambda",
        ("ec2:", "instance/"): "_augment_ec2_instance",
        ("rds:", "db:"): "_augment_rds",
        ("athena:", "workgroup/"): "_augment_athena",
        ("glue:", "table/"): "_augment_glue_table",
        ("dynamodb:", "table/"): "_augment_dynamodb",
        ("logs:", "log-group:"): "_augment_cloudwatch_logs",
        ("sqs:", "queue/"): "_augment_sqs",
        ("sns:", "topic/"): "_augment_sns",
        ("apigateway:", "restapi/"): "_augment_api_gateway",
        ("cloudfront:", "distribution/"): "_augment_cloudfront",
    }
    
    ENVIRONMENT_SUFFIXES = ["-dev", "-staging", "-prod"]
    
    def generate_variations(self, resource: str) -> list:
        """
        Generate similar resource variations based on resource type.
        
        Args:
            resource: Original AWS resource ARN.
            
        Returns:
            List of resource variations including the original.
        """
        variations = [resource]
        
        for patterns, method_name in self.RESOURCE_PATTERNS.items():
            if all(p in resource for p in patterns):
                method = getattr(self, method_name)
                variations.extend(method(resource))
                break
        
        return variations
    
    def _augment_iam_role(self, resource: str) -> list:
        """Generate IAM role variations."""
        base_arn, role_name = resource.split("role/")
        return [f"{base_arn}role/{role_name}{suffix}" for suffix in self.ENVIRONMENT_SUFFIXES]
    
    def _augment_iam_user(self, resource: str) -> list:
        """Generate IAM user variations."""
        base_arn, user_name = resource.split("user/")
        suffixes = ["-service", "-admin", "-dev"]
        return [f"{base_arn}user/{user_name}{suffix}" for suffix in suffixes]
    
    def _augment_kms_key(self, resource: str) -> list:
        """Generate KMS key variations."""
        base_arn, key_id = resource.split("key/")
        return [f"{base_arn}key/{chr(ord('a') + i)}{key_id[1:]}" for i in range(3)]
    
    def _augment_s3(self, resource: str) -> list:
        """Generate S3 bucket variations."""
        bucket_part = resource.split("s3:::")[1]
        bucket_name, path = (bucket_part.split("/", 1) + [""])[:2]
        
        suffixes = ["-dev", "-staging", "-prod", "-backup", "-archive"]
        variations = []
        
        for suffix in suffixes:
            new_resource = f"arn:aws:s3:::{bucket_name}{suffix}"
            if path:
                new_resource += f"/{path}"
            variations.append(new_resource)
        
        return variations
    
    def _augment_lambda(self, resource: str) -> list:
        """Generate Lambda function variations."""
        base_arn, func_part = resource.split("function:")
        func_name = func_part.split(":")[0]  # Remove version/alias
        
        suffixes = ["-dev", "-staging", "-prod", "-v2", "-v3"]
        return [f"{base_arn}function:{func_name}{suffix}" for suffix in suffixes]
    
    def _augment_ec2_instance(self, resource: str) -> list:
        """Generate EC2 instance variations."""
        base_arn, instance_id = resource.split("instance/")
        variations = []
        
        for i in range(1, 5):
            new_id = f"i-{instance_id[2:8]}{i:06x}{instance_id[14:]}"
            variations.append(f"{base_arn}instance/{new_id}")
        
        return variations
    
    def _augment_rds(self, resource: str) -> list:
        """Generate RDS database variations."""
        base_arn, db_name = resource.split("db:")
        suffixes = ["-replica", "-backup", "-read-replica", "-test"]
        return [f"{base_arn}db:{db_name}{suffix}" for suffix in suffixes]
    
    def _augment_athena(self, resource: str) -> list:
        """Generate Athena workgroup variations."""
        base_arn, workgroup = resource.split("workgroup/")
        suffixes = ["-cost-control", "-analytics", "-dev"]
        return [f"{base_arn}workgroup/{workgroup}{suffix}" for suffix in suffixes]
    
    def _augment_glue_table(self, resource: str) -> list:
        """Generate Glue table variations."""
        base_arn, table_path = resource.split("table/")
        parts = table_path.split("/")
        database = parts[0]
        table = parts[1] if len(parts) > 1 else "default_table"
        
        suffixes = ["_dev", "_staging", "_prod"]
        return [f"{base_arn}table/{database}{suffix}/{table}" for suffix in suffixes]
    
    def _augment_dynamodb(self, resource: str) -> list:
        """Generate DynamoDB table variations."""
        base_arn, table_name = resource.split("table/")
        return [f"{base_arn}table/{table_name}{suffix}" for suffix in self.ENVIRONMENT_SUFFIXES]
    
    def _augment_cloudwatch_logs(self, resource: str) -> list:
        """Generate CloudWatch Log Group variations."""
        base_arn, log_group = resource.split("log-group:")
        log_group = log_group.rstrip(":*")
        return [f"{base_arn}log-group:{log_group}{suffix}" for suffix in self.ENVIRONMENT_SUFFIXES]
    
    def _augment_sqs(self, resource: str) -> list:
        """Generate SQS queue variations."""
        base_arn, queue_name = resource.split("queue/")
        suffixes = ["-dev", "-staging", "-prod", "-fifo"]
        return [f"{base_arn}queue/{queue_name}{suffix}" for suffix in suffixes]
    
    def _augment_sns(self, resource: str) -> list:
        """Generate SNS topic variations."""
        base_arn, topic_name = resource.split("topic/")
        suffixes = ["-notifications", "-alerts", "-dev"]
        return [f"{base_arn}topic/{topic_name}{suffix}" for suffix in suffixes]
    
    def _augment_api_gateway(self, resource: str) -> list:
        """Generate API Gateway REST API variations."""
        base_arn, api_id = resource.split("restapi/")
        return [f"{base_arn}restapi/{api_id}{suffix}" for suffix in self.ENVIRONMENT_SUFFIXES]
    
    def _augment_cloudfront(self, resource: str) -> list:
        """Generate CloudFront distribution variations."""
        base_arn, dist_id = resource.split("distribution/")
        suffixes = ["-test", "-staging", "-prod"]
        return [f"{base_arn}distribution/{dist_id}{suffix}" for suffix in suffixes]


# =============================================================================
# Request Processor
# =============================================================================

class RequestProcessor:
    """Orchestrates validation and augmentation of policy requests."""
    
    def __init__(self, config: Config):
        self.config = config
        self.validator = SMTValidator(config)
        self.augmenter = ResourceAugmenter()
        self.logger = logging.getLogger(__name__)
    
    def process(
        self,
        policy_file: str,
        requests_file: str,
        output_file: str,
    ) -> dict:
        """
        Validate requests and augment misclassified ones.
        
        Args:
            policy_file: Path to policy JSON.
            requests_file: Path to requests JSON.
            output_file: Path for augmented output.
            
        Returns:
            Dictionary with processing results.
        """
        with open(requests_file, "r") as f:
            requests_data = json.load(f)
        
        requests = requests_data.get("Requests", [])
        
        print("=== RUNNING SMT VALIDATOR ===")
        validation = self.validator.validate(policy_file, requests_file)
        
        misclassified_ids = [req["request_id"] for req in validation.misclassified_requests]
        
        self._print_validation_summary(validation, misclassified_ids)
        
        if not misclassified_ids:
            print("No misclassified requests found. No augmentation needed.")
            with open(output_file, "w") as f:
                json.dump(requests_data, f, indent=2)
            return self._build_result(requests, [], output_file)
        
        print(f"\n=== AUGMENTING {len(misclassified_ids)} MISCLASSIFIED REQUESTS ===")
        augmented = self._augment_requests(requests, misclassified_ids)
        
        with open(output_file, "w") as f:
            json.dump({"Requests": augmented}, f, indent=2)
        
        print(f"\nAugmented requests saved to: {output_file}")
        
        return self._build_result(requests, misclassified_ids, output_file, augmented)
    
    def _print_validation_summary(self, validation: ValidationResult, misclassified_ids: list) -> None:
        """Print validation results summary."""
        print(f"SMT Validation Results:")
        print(f"  Accuracy: {validation.accuracy:.1f}%")
        print(f"  Total requests: {validation.total_requests}")
        print(f"  Correct: {validation.correct}")
        print(f"  Incorrect: {validation.incorrect}")
        print(f"  Misclassified request IDs: {misclassified_ids}")
    
    def _augment_requests(self, requests: list, misclassified_ids: list) -> list:
        """Augment misclassified requests with resource variations."""
        augmented = []
        
        for request in requests:
            if request["id"] not in misclassified_ids:
                augmented.append(request)
                continue
            
            print(f"\nAugmenting request: {request['id']}")
            print(f"Original resources: {request['Resource']}")
            
            # Generate variations for each resource
            all_resources = []
            for resource in request["Resource"]:
                all_resources.extend(self.augmenter.generate_variations(resource))
            
            # Deduplicate while preserving order
            unique_resources = list(dict.fromkeys(all_resources))
            
            augmented_request = request.copy()
            augmented_request["Resource"] = unique_resources
            augmented.append(augmented_request)
            
            added_count = len(unique_resources) - len(request["Resource"])
            print(f"Augmented resources: {unique_resources}")
            print(f"Added {added_count} new resources")
        
        return augmented
    
    def _build_result(
        self,
        requests: list,
        misclassified_ids: list,
        output_file: str,
        augmented: list = None,
    ) -> dict:
        """Build the result dictionary."""
        result = {
            "total_requests": len(requests),
            "misclassified_count": len(misclassified_ids),
            "misclassified_ids": misclassified_ids,
            "output_file": output_file,
        }
        if augmented:
            result["augmented_requests"] = augmented
        return result


# =============================================================================
# Batch Processor
# =============================================================================

class BatchProcessor:
    """Processes multiple policies in batch mode."""
    
    def __init__(self, config: Config):
        self.config = config
        self.processor = RequestProcessor(config)
        self.logger = logging.getLogger(__name__)
    
    def run(self) -> None:
        """Execute batch processing on all policies."""
        self._validate_directories()
        
        policy_files = self._discover_policies()
        print(f"Found {len(policy_files)} policy files")
        
        results = self._process_all_policies(policy_files)
        
        self._print_summary(results)
        self._save_summary(results)
    
    def _validate_directories(self) -> None:
        """Verify all required directories exist."""
        Path(self.config.output_dir).mkdir(parents=True, exist_ok=True)
        Path(self.config.temp_dir).mkdir(parents=True, exist_ok=True)
        
        required_dirs = [
            (self.config.policy_dir, "Policy directory"),
            (self.config.requests_dir, "Requests directory"),
            (self.config.quacky_src_dir, "Quacky source directory"),
        ]
        
        for path, name in required_dirs:
            if not os.path.exists(path):
                raise FileNotFoundError(f"{name} not found: {path}")
        
        requests_subdir = Path(self.config.requests_dir) / self.config.requests_subdir
        if not requests_subdir.exists():
            raise FileNotFoundError(f"Requests subdirectory not found: {requests_subdir}")
    
    def _discover_policies(self) -> list:
        """Find all policy files in sequence."""
        policies = []
        idx = 0
        
        while True:
            policy_path = Path(self.config.policy_dir) / f"{idx}.json"
            if policy_path.exists():
                policies.append((idx, str(policy_path)))
                idx += 1
            else:
                break
        
        return policies
    
    def _process_all_policies(self, policy_files: list) -> list:
        """Process each policy and collect results."""
        results = []
        requests_path = Path(self.config.requests_dir) / self.config.requests_subdir
        
        for idx, policy_file in policy_files:
            print(f"\n{'=' * 80}")
            print(f"PROCESSING POLICY {idx}")
            print(f"{'=' * 80}")
            
            requests_file = requests_path / f"{idx}.json"
            output_file = Path(self.config.output_dir) / f"{idx}.json"
            
            if not requests_file.exists():
                print(f"Warning: Request file not found for policy {idx}: {requests_file}")
                continue
            
            result = self._process_single_policy(
                idx, policy_file, str(requests_file), str(output_file)
            )
            results.append(result)
        
        return results
    
    def _process_single_policy(
        self,
        idx: int,
        policy_file: str,
        requests_file: str,
        output_file: str,
    ) -> ProcessingResult:
        """Process a single policy and return results."""
        try:
            result = self.processor.process(policy_file, requests_file, output_file)
            
            print(f"Policy {idx} completed:")
            print(f"  Misclassified: {result['misclassified_count']}/{result['total_requests']}")
            print(f"  Output: {result['output_file']}")
            
            return ProcessingResult(
                policy_idx=idx,
                accuracy=result.get("accuracy", 0),
                total_requests=result["total_requests"],
                misclassified_count=result["misclassified_count"],
                misclassified_ids=result["misclassified_ids"],
                output_file=result["output_file"],
            )
            
        except Exception as e:
            self.logger.error(f"Error processing policy {idx}: {e}")
            return ProcessingResult(policy_idx=idx, error=str(e))
    
    def _print_summary(self, results: list) -> None:
        """Print final processing summary."""
        print(f"\n{'=' * 80}")
        print("FINAL SUMMARY")
        print(f"{'=' * 80}")
        
        successful = [r for r in results if r.error is None]
        failed = [r for r in results if r.error is not None]
        
        total_misclassified = sum(r.misclassified_count for r in successful)
        total_requests = sum(r.total_requests for r in successful)
        
        print(f"Total policies processed: {len(successful)}")
        print(f"Total errors: {len(failed)}")
        print(f"Total requests processed: {total_requests}")
        print(f"Total misclassified requests: {total_misclassified}")
        
        if total_requests > 0:
            rate = (total_misclassified / total_requests) * 100
            print(f"Overall misclassification rate: {rate:.2f}%")
        
        print(f"\nPER-POLICY RESULTS:")
        for result in results:
            if result.error:
                print(f"  Policy {result.policy_idx}: ERROR - {result.error}")
            else:
                print(f"  Policy {result.policy_idx}: {result.misclassified_count}/{result.total_requests} misclassified")
    
    def _save_summary(self, results: list) -> None:
        """Save processing summary to JSON file."""
        summary_data = []
        
        for r in results:
            entry = {
                "policy_idx": r.policy_idx,
                "accuracy": r.accuracy,
                "total_requests": r.total_requests,
                "misclassified_count": r.misclassified_count,
                "misclassified_ids": r.misclassified_ids,
                "output_file": r.output_file,
            }
            if r.error:
                entry["error"] = r.error
            summary_data.append(entry)
        
        summary_file = Path(self.config.output_dir) / "processing_summary.json"
        with open(summary_file, "w") as f:
            json.dump(summary_data, f, indent=2)
        
        print(f"\nSummary saved to: {summary_file}")


# =============================================================================
# Entry Point
# =============================================================================

def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="SMT-based request validation and augmentation for AWS IAM policies.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s --quacky-src ./quacky/src --policies ./policies --requests ./requests --output ./output
    
Environment Variables:
    QUACKY_SRC_DIR  Path to Quacky source directory
    POLICY_DIR      Path to policy files
    REQUESTS_DIR    Path to request files  
    OUTPUT_DIR      Path for output files
        """,
    )
    
    parser.add_argument(
        "--quacky-src",
        help="Path to Quacky source directory (or set QUACKY_SRC_DIR)",
    )
    parser.add_argument(
        "--policies",
        help="Path to policy JSON files directory (or set POLICY_DIR)",
    )
    parser.add_argument(
        "--requests",
        help="Path to request JSON files directory (or set REQUESTS_DIR)",
    )
    parser.add_argument(
        "--output",
        help="Path for augmented output files (or set OUTPUT_DIR)",
    )
    parser.add_argument(
        "--temp-dir",
        default="./temp",
        help="Path for temporary files (default: ./temp)",
    )
    parser.add_argument(
        "--requests-subdir",
        default="request-10",
        help="Subdirectory within requests dir (default: request-10)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Validation timeout in seconds (default: 300)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    
    return parser.parse_args()


def main() -> None:
    """Main entry point for batch processing."""
    args = parse_arguments()
    
    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(log_level)
    
    config = Config.from_args(args)
    
    # Log effective configuration
    logging.info(f"Configuration:")
    logging.info(f"  Quacky source: {config.quacky_src_dir}")
    logging.info(f"  Policies: {config.policy_dir}")
    logging.info(f"  Requests: {config.requests_dir}")
    logging.info(f"  Output: {config.output_dir}")
    
    processor = BatchProcessor(config)
    processor.run()


if __name__ == "__main__":
    main()