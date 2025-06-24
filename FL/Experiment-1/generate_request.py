
import json
import random
import uuid
from typing import Dict, List, Any, Optional

class RequestGenerator:
    def __init__(self, policy: Dict[str, Any]):
        self.policy = policy
        # More comprehensive action lists per service
        self.service_actions = {
            "s3": ["GetObject", "PutObject", "DeleteObject", "ListBucket", "GetBucketLocation", 
                  "PutBucketPolicy", "GetBucketAcl", "CreateBucket", "DeleteBucket"],
            "athena": ["GetQueryExecution", "StartQueryExecution", "StopQueryExecution", 
                      "GetWorkGroup", "GetDatabase", "BatchGetQueryExecution", "GetQueryResults",
                      "GetQueryResultsStream", "GetTableMetadata", "CreateWorkGroup", "DeleteWorkGroup"],
            "glue": ["GetTable", "GetDatabase", "GetPartitions", "CreateTable", "DeleteTable",
                    "UpdateTable", "CreateDatabase", "DeleteDatabase"],
            "kms": ["CreateGrant", "DescribeKey", "Decrypt", "Encrypt", "GenerateDataKey",
                   "DeleteAlias", "CreateKey", "ScheduleKeyDeletion"],
            "ec2": ["DescribeInstances", "RunInstances", "TerminateInstances", "CreateSecurityGroup"],
            "iam": ["CreateUser", "DeleteUser", "AttachUserPolicy", "ListUsers"],
            "lambda": ["InvokeFunction", "CreateFunction", "DeleteFunction", "UpdateFunctionCode"],
            "dynamodb": ["PutItem", "DeleteItem", "GetItem", "Scan", "Query", "CreateTable"]
        }
    
    def extract_policy_elements(self) -> Dict[str, List[str]]:
        """Extract actions, resources, and principals from the policy"""
        elements = {
            "actions": [],
            "resources": [],
            "principals": []
        }
        
        statements = self.policy.get("Statement", [])
        for statement in statements:
            if statement.get("Effect") == "Allow":
                # Extract actions
                actions = statement.get("Action", [])
                if isinstance(actions, str):
                    elements["actions"].append(actions)
                elif isinstance(actions, list):
                    elements["actions"].extend(actions)
                
                # Extract resources
                resources = statement.get("Resource", [])
                if isinstance(resources, str):
                    elements["resources"].append(resources)
                elif isinstance(resources, list):
                    elements["resources"].extend(resources)
                
                # Extract principals
                principal = statement.get("Principal")
                if isinstance(principal, str):
                    elements["principals"].append(principal)
                elif isinstance(principal, list):
                    elements["principals"].extend(principal)
        
        return elements
    
    def generate_denied_actions(self, allowed_actions: List[str]) -> List[str]:
        """Generate actions that should be denied"""
        denied_actions = set()
        
        # Get all services that have allowed actions
        allowed_services = set()
        for action in allowed_actions:
            if ":" in action:
                service = action.split(":", 1)[0]
                allowed_services.add(service)
        
        # For each service, find actions that aren't allowed
        for service in allowed_services:
            if service in self.service_actions:
                service_allowed = set()
                
                # Check what's actually allowed for this service
                for action in allowed_actions:
                    if action.startswith(f"{service}:"):
                        if action.endswith("*"):
                            # Wildcard - all actions for this service are allowed
                            service_allowed.update(self.service_actions[service])
                        else:
                            operation = action.split(":", 1)[1]
                            service_allowed.add(operation)
                
                # Find actions that aren't allowed
                for action in self.service_actions[service]:
                    if action not in service_allowed:
                        denied_actions.add(f"{service}:{action}")
        
        # Add actions from services not in the policy at all
        other_services = ["ec2", "iam", "lambda", "dynamodb", "rds", "sns", "sqs"]
        for service in other_services:
            if service not in allowed_services and service in self.service_actions:
                for action in self.service_actions[service][:2]:  # Just add a few
                    denied_actions.add(f"{service}:{action}")
        
        return list(denied_actions)
    
    def generate_denied_resources(self, allowed_resources: List[str]) -> List[str]:
        """Generate resources that should be denied"""
        denied_resources = set()
        
        for resource in allowed_resources:
            if resource == "*":
                # If wildcard, create specific resources that might be sensitive
                denied_resources.update([
                    "arn:aws:s3:::forbidden-bucket/*",
                    "arn:aws:iam::123456789012:role/admin-role",
                    "arn:aws:kms:us-east-1:123456789012:key/forbidden-key"
                ])
            elif "arn:aws:s3:::" in resource:
                # For S3 resources, create variations
                if resource.endswith("/*"):
                    bucket_name = resource.split(":::")[1].split("/")[0]
                    denied_resources.update([
                        f"arn:aws:s3:::different-{bucket_name}/*",
                        f"arn:aws:s3:::{bucket_name}-forbidden/*",
                        "arn:aws:s3:::completely-different-bucket/*"
                    ])
                else:
                    # Specific file
                    parts = resource.split("/")
                    if len(parts) > 1:
                        bucket_part = "/".join(parts[:-1])
                        file_part = parts[-1]
                        denied_resources.update([
                            f"{bucket_part}/forbidden-{file_part}",
                            f"{bucket_part.replace(':::', ':::forbidden-')}/{file_part}"
                        ])
            else:
                # Simple resource names
                denied_resources.update([
                    f"forbidden-{resource}",
                    f"{resource}-forbidden",
                    f"unauthorized/{resource}"
                ])
        
        return list(denied_resources)
    
    def expand_wildcard_action(self, action: str) -> str:
        """Convert wildcard actions to specific actions"""
        if not action.endswith("*"):
            return action
            
        service = action.split(":")[0]
        if service in self.service_actions:
            return f"{service}:{random.choice(self.service_actions[service])}"
        else:
            return action.replace("*", "GetObject")  # Default fallback
    
    def expand_wildcard_resource(self, resource: str) -> str:
        """Convert wildcard resources to specific resources"""
        if resource == "*":
            # Return a specific resource
            return random.choice([
                "arn:aws:s3:::my-bucket/document.txt",
                "arn:aws:athena:us-east-1:123456789012:workgroup/primary",
                "arn:aws:glue:us-east-1:123456789012:table/my-database/my-table"
            ])
        elif resource.endswith("/*"):
            base_path = resource[:-2]
            suffixes = ["/document.txt", "/data/file.json", "/logs/app.log", "/temp/upload.tmp"]
            return base_path + random.choice(suffixes)
        elif resource.endswith("*"):
            base_path = resource[:-1]
            suffixes = ["file1", "document", "data123"]
            return base_path + random.choice(suffixes)
        else:
            return resource
    
    def calculate_combinations(self, actions: List[str], resources: List[str]) -> int:
        """Calculate the number of individual request combinations"""
        return len(actions) * len(resources)
    
    def generate_variable_actions(self, base_actions: List[str], target_count: int = None) -> List[str]:
        """Generate a variable number of actions, considering target combination count"""
        if target_count is None:
            count = random.randint(1, 3)  # 1-3 actions per request
        else:
            # Adjust action count based on remaining target combinations
            count = min(random.randint(1, min(3, target_count)), len(base_actions) if base_actions else 1)
        
        available_actions = []
        
        # Expand all base actions to get a pool of specific actions
        for base_action in base_actions:
            if base_action.endswith("*"):
                service = base_action.split(":")[0]
                if service in self.service_actions:
                    for action in self.service_actions[service]:
                        available_actions.append(f"{service}:{action}")
            else:
                available_actions.append(base_action)
        
        # Remove duplicates and select random actions
        available_actions = list(set(available_actions))
        if not available_actions:
            return ["s3:GetObject"]
            
        selected_count = min(count, len(available_actions))
        actions = random.sample(available_actions, selected_count)
        
        return actions
    
    def generate_variable_resources(self, base_resources: List[str], target_count: int = None) -> List[str]:
        """Generate a variable number of resources, considering target combination count"""
        if target_count is None:
            count = random.randint(1, 2)  # 1-2 resources per request
        else:
            # Adjust resource count based on remaining target combinations
            count = min(random.randint(1, min(3, target_count)), 3)
        
        resources = []
        
        for _ in range(count):
            if base_resources:
                base_resource = random.choice(base_resources)
                expanded_resource = self.expand_wildcard_resource(base_resource)
                resources.append(expanded_resource)
            else:
                resources.append("arn:aws:s3:::my-bucket/specific-file.txt")
        
        # Remove duplicates while preserving order
        seen = set()
        unique_resources = []
        for resource in resources:
            if resource not in seen:
                seen.add(resource)
                unique_resources.append(resource)
        
        return unique_resources
    


    def generate_must_allow_requests(self, target_combinations: int) -> List[Dict[str, Any]]:
        """Generate requests that must be allowed by the policy with exact combination count"""
        allowed_requests = []
        policy_elements = self.extract_policy_elements()
        
        if not policy_elements["actions"]:
            raise ValueError("No allowed actions found in policy")
        
        remaining_combinations = target_combinations
        request_count = 0
        max_requests = target_combinations  # Prevent infinite loop
        
        while remaining_combinations > 0 and request_count < max_requests:
            # Determine how many combinations this request should have
            if remaining_combinations == 1:
                # Last request - must be exactly 1 combination
                target_for_this_request = 1
            else:
                # Random between 1 and remaining (but not too large)
                max_for_this_request = min(remaining_combinations, 6)  # Cap at 6 to avoid huge requests
                target_for_this_request = random.randint(1, max_for_this_request)
            
            # Generate actions and resources to hit the target
            attempts = 0
            while attempts < 10:  # Prevent infinite loop
                actions = self.generate_variable_actions(policy_elements["actions"], target_for_this_request)
                resources = self.generate_variable_resources(policy_elements["resources"], target_for_this_request)
                
                combinations = self.calculate_combinations(actions, resources)
                
                if combinations <= remaining_combinations:
                    break
                    
                attempts += 1
            
            # If we couldn't hit the target exactly, adjust
            if combinations > remaining_combinations:
                # Fall back to single action/resource
                actions = [self.generate_variable_actions(policy_elements["actions"], 1)[0]]
                resources = [self.generate_variable_resources(policy_elements["resources"], 1)[0]]
                combinations = 1
            
            # Select allowed principal
            principal = None
            if policy_elements["principals"]:
                principal = random.choice(policy_elements["principals"])
            
            request = {
                "id": f"allow_{uuid.uuid4().hex[:8]}",
                "Effect": "allow",
                "Action": actions,
                "Resource": resources
            }
            
            if principal:
                request["Principal"] = principal
            
            allowed_requests.append(request)
            remaining_combinations -= combinations
            request_count += 1
        
        return allowed_requests
    
    def generate_variable_denied_actions(self, denied_actions: List[str], target_count: int = None) -> List[str]:
        """Generate a variable number of denied actions"""
        if target_count is None:
            count = random.randint(1, 2)  # 1-2 denied actions per request
        else:
            count = min(random.randint(1, min(3, target_count)), len(denied_actions) if denied_actions else 1)
        
        if not denied_actions:
            return ["lambda:InvokeFunction"]  # Fallback
        
        selected_count = min(count, len(denied_actions))
        return random.sample(denied_actions, selected_count)
    
    def generate_variable_denied_resources(self, denied_resources: List[str], target_count: int = None) -> List[str]:
        """Generate a variable number of denied resources"""
        if target_count is None:
            count = random.randint(1, 2)  # 1-2 denied resources per request
        else:
            count = min(random.randint(1, min(3, target_count)), len(denied_resources) if denied_resources else 1)
        
        if not denied_resources:
            return ["arn:aws:s3:::forbidden-bucket/file.txt"]  # Fallback
        
        selected_count = min(count, len(denied_resources))
        return random.sample(denied_resources, selected_count)

    def generate_must_deny_requests(self, target_combinations: int) -> List[Dict[str, Any]]:
        """Generate requests that must be denied by the policy with exact combination count"""
        denied_requests = []
        policy_elements = self.extract_policy_elements()
        
        # Generate denied variations
        denied_actions = self.generate_denied_actions(policy_elements["actions"])
        denied_resources = self.generate_denied_resources(policy_elements["resources"])
        
        remaining_combinations = target_combinations
        request_count = 0
        max_requests = target_combinations  # Prevent infinite loop
        
        while remaining_combinations > 0 and request_count < max_requests:
            # Determine how many combinations this request should have
            if remaining_combinations == 1:
                # Last request - must be exactly 1 combination
                target_for_this_request = 1
            else:
                # Random between 1 and remaining (but not too large)
                max_for_this_request = min(remaining_combinations, 6)  # Cap at 6 to avoid huge requests
                target_for_this_request = random.randint(1, max_for_this_request)
            
            # Strategy: alternate between denied action and denied resource
            attempts = 0
            while attempts < 10:  # Prevent infinite loop
                if request_count % 2 == 0 and denied_actions:
                    # Use denied actions with allowed resources
                    actions = self.generate_variable_denied_actions(denied_actions, target_for_this_request)
                    resources = self.generate_variable_resources(policy_elements["resources"], target_for_this_request)
                else:
                    # Use allowed actions with denied resources
                    if denied_resources:
                        actions = self.generate_variable_actions(policy_elements["actions"], target_for_this_request)
                        resources = self.generate_variable_denied_resources(denied_resources, target_for_this_request)
                    else:
                        # Fallback to denied actions
                        actions = self.generate_variable_denied_actions(denied_actions, target_for_this_request)
                        resources = ["arn:aws:s3:::forbidden-bucket/file.txt"]
                
                combinations = self.calculate_combinations(actions, resources)
                
                if combinations <= remaining_combinations:
                    break
                    
                attempts += 1
            
            # If we couldn't hit the target exactly, adjust
            if combinations > remaining_combinations:
                # Fall back to single action/resource
                if denied_actions:
                    actions = [denied_actions[0]]
                    resources = self.generate_variable_resources(policy_elements["resources"], 1)
                else:
                    actions = self.generate_variable_actions(policy_elements["actions"], 1)
                    resources = ["arn:aws:s3:::forbidden-bucket/file.txt"]
                combinations = 1
            
            request = {
                "id": f"deny_{uuid.uuid4().hex[:8]}",
                "Effect": "deny",
                "Action": actions,
                "Resource": resources
            }
            
            denied_requests.append(request)
            remaining_combinations -= combinations
            request_count += 1
        
        return denied_requests
    
    def generate_all_requests(self, total_combinations: int, allow_ratio: float = 0.6) -> Dict[str, Any]:
        """Generate complete set of must-allow and must-deny requests with exact combination count
        
        Args:
            total_combinations: Total number of individual request combinations to generate
            allow_ratio: Ratio of allow combinations (default 0.6 = 60% allow, 40% deny)
        """
        try:
            # Calculate number of allow and deny combinations
            num_allow_combinations = int(total_combinations * allow_ratio)
            num_deny_combinations = total_combinations - num_allow_combinations
            
            # Ensure at least one of each type if total > 1
            if total_combinations > 1:
                if num_allow_combinations == 0:
                    num_allow_combinations = 1
                    num_deny_combinations = total_combinations - 1
                elif num_deny_combinations == 0:
                    num_deny_combinations = 1
                    num_allow_combinations = total_combinations - 1
            
            must_allow = self.generate_must_allow_requests(num_allow_combinations)
            must_deny = self.generate_must_deny_requests(num_deny_combinations)
            
            # Combine all requests - allows first, then denies
            all_requests = must_allow + must_deny
            
            # Don't shuffle - keep allows before denies
            
            return {
                "Requests": all_requests
            }
        except Exception as e:
            return {
                "error": f"Failed to generate requests: {str(e)}"
            }

def load_policy_from_file(file_path: str) -> Dict[str, Any]:
    """Load IAM policy from JSON file"""
    try:
        with open(file_path, 'r') as file:
            policy = json.load(file)
        return policy
    except FileNotFoundError:
        raise FileNotFoundError(f"Policy file not found: {file_path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in policy file: {e}")

def save_requests_to_file(requests: Dict[str, Any], output_path: str) -> None:
    """Save generated requests to JSON file"""
    try:
        with open(output_path, 'w') as file:
            json.dump(requests, file, indent=2)
        print(f"Generated requests saved to: {output_path}")
    except Exception as e:
        raise Exception(f"Failed to save requests to file: {e}")

def main():
    import argparse
    import os
    
    # Set up command line arguments
    parser = argparse.ArgumentParser(description='Generate IAM policy test requests')
    parser.add_argument('file_number', 
                       help='Policy file number (e.g., 0, 1, 2...)')
    parser.add_argument('--requests', '-r', 
                       type=int, default=5,
                       help='Total number of requests to generate (default: 5)')
    parser.add_argument('--allow-ratio', 
                       type=float, default=0.6,
                       help='Ratio of allow requests (0.0-1.0, default: 0.6)')
    
    args = parser.parse_args()
    
    # Validate allow_ratio
    if not 0.0 <= args.allow_ratio <= 1.0:
        print("Error: --allow-ratio must be between 0.0 and 1.0")
        return 1
    
    # Set up file paths
    policy_file = f"original_policy/{args.file_number}.json"
    output_file = f"requests/request-{args.requests}/{args.file_number}.json"
    
    # Create requests directory if it doesn't exist
    os.makedirs(f"requests/request-{args.requests}", exist_ok=True)

    try:
        # Load policy from file
        print(f"Loading policy from: {policy_file}")
        policy = load_policy_from_file(policy_file)
        print(f"Policy loaded successfully")
        
        # Generate requests
        print(f"Generating requests with exactly {args.requests} total combinations ({args.allow_ratio:.1%} allow ratio)...")
        generator = RequestGenerator(policy)
        test_data = generator.generate_all_requests(args.requests, args.allow_ratio)
        
        if "error" in test_data:
            print(f"Error generating requests: {test_data['error']}")
            return 1
        
        # Save to output file
        save_requests_to_file(test_data, output_file)
        
        # Calculate actual combinations
        total_request_objects = len(test_data.get("Requests", []))
        allow_objects = sum(1 for req in test_data.get("Requests", []) if req.get("Effect") == "allow")
        deny_objects = sum(1 for req in test_data.get("Requests", []) if req.get("Effect") == "deny")
        
        # Calculate total combinations
        total_combinations = 0
        allow_combinations = 0
        deny_combinations = 0
        
        for req in test_data.get("Requests", []):
            actions = req.get("Action", [])
            resources = req.get("Resource", [])
            if not isinstance(actions, list):
                actions = [actions]
            if not isinstance(resources, list):
                resources = [resources]
            
            combinations = len(actions) * len(resources)
            total_combinations += combinations
            
            if req.get("Effect") == "allow":
                allow_combinations += combinations
            else:
                deny_combinations += combinations
        
        print(f"\nSummary:")
        print(f"   Total request objects: {total_request_objects}")
        print(f"   Allow objects: {allow_objects}, Deny objects: {deny_objects}")
        print(f"   Total individual combinations: {total_combinations}")
        print(f"   Allow combinations: {allow_combinations}")
        print(f"   Deny combinations: {deny_combinations}")
        print(f"   Actual allow ratio: {allow_combinations/total_combinations:.1%}")
        print(f"   Saved to: {output_file}")
        
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    import sys
    
    # Show usage if no arguments
    if len(sys.argv) == 1:
        print("IAM Policy Request Generator")
        print("\nUsage:")
        print("  python request_generator.py 0")
        print("  python request_generator.py 5 --requests 10")
        print("  python request_generator.py 3 --requests 8 --allow-ratio 0.7")
        print("\nOptions:")
        print("  --requests, -r    Total number of requests to generate (default: 5)")
        print("  --allow-ratio     Ratio of allow requests 0.0-1.0 (default: 0.6)")
        print("\nThis will:")
        print("  - Read from original_policy/{file_number}.json")
        print("  - Save to requests/{file_number}.json")
        print("  - Generate request objects with multiple actions/resources")
        print("  - Total Cartesian product of all combinations equals specified number")
        print("  - Split combinations between allow/deny based on ratio")
        sys.exit(1)
    
    sys.exit(main())                                                                                                                                                                                                              