
# import json
# import random
# import uuid
# from typing import Dict, List, Any, Optional

# class RequestGenerator:
#     def __init__(self, policy: Dict[str, Any]):
#         self.policy = policy
#         # More comprehensive action lists per service
#         self.service_actions = {
#             "s3": ["GetObject", "PutObject", "DeleteObject", "ListBucket", "GetBucketLocation", 
#                   "PutBucketPolicy", "GetBucketAcl", "CreateBucket", "DeleteBucket"],
#             "athena": ["GetQueryExecution", "StartQueryExecution", "StopQueryExecution", 
#                       "GetWorkGroup", "GetDatabase", "BatchGetQueryExecution", "GetQueryResults",
#                       "GetQueryResultsStream", "GetTableMetadata", "CreateWorkGroup", "DeleteWorkGroup"],
#             "glue": ["GetTable", "GetDatabase", "GetPartitions", "CreateTable", "DeleteTable",
#                     "UpdateTable", "CreateDatabase", "DeleteDatabase"],
#             "kms": ["CreateGrant", "DescribeKey", "Decrypt", "Encrypt", "GenerateDataKey",
#                    "DeleteAlias", "CreateKey", "ScheduleKeyDeletion"],
#             "ec2": ["DescribeInstances", "RunInstances", "TerminateInstances", "CreateSecurityGroup"],
#             "iam": ["CreateUser", "DeleteUser", "AttachUserPolicy", "ListUsers"],
#             "lambda": ["InvokeFunction", "CreateFunction", "DeleteFunction", "UpdateFunctionCode"],
#             "dynamodb": ["PutItem", "DeleteItem", "GetItem", "Scan", "Query", "CreateTable"]
#         }    
    
#     def extract_policy_elements(self) -> Dict[str, List[str]]:
#         """Extract actions, resources, and principals from the policy"""
#         elements = {
#             "actions": [],
#             "resources": [],
#             "principals": []
#         }
        
#         statements = self.policy.get("Statement", [])
#         for statement in statements:
#             if statement.get("Effect") == "Allow":
#                 # Extract actions
#                 actions = statement.get("Action", [])
#                 if isinstance(actions, str):
#                     elements["actions"].append(actions)
#                 elif isinstance(actions, list):
#                     elements["actions"].extend(actions)
                
#                 # Extract resources
#                 resources = statement.get("Resource", [])
#                 if isinstance(resources, str):
#                     elements["resources"].append(resources)
#                 elif isinstance(resources, list):
#                     elements["resources"].extend(resources)
                
#                 # Extract principals
#                 principal = statement.get("Principal")
#                 if isinstance(principal, str):
#                     elements["principals"].append(principal)
#                 elif isinstance(principal, list):
#                     elements["principals"].extend(principal)
        
#         return elements
    
#     def generate_denied_actions(self, allowed_actions: List[str]) -> List[str]:
#         """Generate actions that should be denied"""
#         denied_actions = set()
        
#         # Get all services that have allowed actions
#         allowed_services = set()
#         for action in allowed_actions:
#             if ":" in action:
#                 service = action.split(":", 1)[0]
#                 allowed_services.add(service)
        
#         # For each service, find actions that aren't allowed
#         for service in allowed_services:
#             if service in self.service_actions:
#                 service_allowed = set()
                
#                 # Check what's actually allowed for this service
#                 for action in allowed_actions:
#                     if action.startswith(f"{service}:"):
#                         if action.endswith("*"):
#                             # Wildcard - all actions for this service are allowed
#                             service_allowed.update(self.service_actions[service])
#                         else:
#                             operation = action.split(":", 1)[1]
#                             service_allowed.add(operation)
                
#                 # Find actions that aren't allowed
#                 for action in self.service_actions[service]:
#                     if action not in service_allowed:
#                         denied_actions.add(f"{service}:{action}")
        
#         # Add actions from services not in the policy at all
#         other_services = ["ec2", "iam", "lambda", "dynamodb", "rds", "sns", "sqs"]
#         for service in other_services:
#             if service not in allowed_services and service in self.service_actions:
#                 for action in self.service_actions[service][:2]:  # Just add a few
#                     denied_actions.add(f"{service}:{action}")
        
#         return list(denied_actions)
    
#     def generate_denied_resources(self, allowed_resources: List[str]) -> List[str]:
#         """Generate resources that should be denied"""
#         denied_resources = set()
        
#         for resource in allowed_resources:
#             if resource == "*":
#                 # If wildcard, create specific resources that might be sensitive
#                 denied_resources.update([
#                     "arn:aws:s3:::forbidden-bucket/*",
#                     "arn:aws:iam::123456789012:role/admin-role",
#                     "arn:aws:kms:us-east-1:123456789012:key/forbidden-key"
#                 ])
#             elif "arn:aws:s3:::" in resource:
#                 # For S3 resources, create variations
#                 if resource.endswith("/*"):
#                     bucket_name = resource.split(":::")[1].split("/")[0]
#                     denied_resources.update([
#                         f"arn:aws:s3:::different-{bucket_name}/*",
#                         f"arn:aws:s3:::{bucket_name}-forbidden/*",
#                         "arn:aws:s3:::completely-different-bucket/*"
#                     ])
#                 else:
#                     # Specific file
#                     parts = resource.split("/")
#                     if len(parts) > 1:
#                         bucket_part = "/".join(parts[:-1])
#                         file_part = parts[-1]
#                         denied_resources.update([
#                             f"{bucket_part}/forbidden-{file_part}",
#                             f"{bucket_part.replace(':::', ':::forbidden-')}/{file_part}"
#                         ])
#             else:
#                 # Simple resource names
#                 denied_resources.update([
#                     f"forbidden-{resource}",
#                     f"{resource}-forbidden",
#                     f"unauthorized/{resource}"
#                 ])
        
#         return list(denied_resources)
    
#     def expand_wildcard_action(self, action: str) -> str:
#         """Convert wildcard actions to specific actions"""
#         if not action.endswith("*"):
#             return action
            
#         service = action.split(":")[0]
#         if service in self.service_actions:
#             return f"{service}:{random.choice(self.service_actions[service])}"
#         else:
#             return action.replace("*", "GetObject")  # Default fallback
    
#     def expand_wildcard_resource(self, resource: str) -> str:
#         """Convert wildcard resources to specific resources"""
#         if resource == "*":
#             # Return a specific resource
#             return random.choice([
#                 "arn:aws:s3:::my-bucket/document.txt",
#                 "arn:aws:athena:us-east-1:123456789012:workgroup/primary",
#                 "arn:aws:glue:us-east-1:123456789012:table/my-database/my-table"
#             ])
#         elif resource.endswith("/*"):
#             base_path = resource[:-2]
#             suffixes = ["/document.txt", "/data/file.json", "/logs/app.log", "/temp/upload.tmp"]
#             return base_path + random.choice(suffixes)
#         elif resource.endswith("*"):
#             base_path = resource[:-1]
#             suffixes = ["file1", "document", "data123"]
#             return base_path + random.choice(suffixes)
#         else:
#             return resource
    
#     def calculate_combinations(self, actions: List[str], resources: List[str]) -> int:
#         """Calculate the number of individual request combinations"""
#         return len(actions) * len(resources)
    
#     def generate_variable_actions(self, base_actions: List[str], target_count: int = None) -> List[str]:
#         """Generate a variable number of actions, considering target combination count"""
#         if target_count is None:
#             count = random.randint(1, 3)  # 1-3 actions per request
#         else:
#             # Adjust action count based on remaining target combinations
#             count = min(random.randint(1, min(3, target_count)), len(base_actions) if base_actions else 1)
        
#         available_actions = []
        
#         # Expand all base actions to get a pool of specific actions
#         for base_action in base_actions:
#             if base_action.endswith("*"):
#                 service = base_action.split(":")[0]
#                 if service in self.service_actions:
#                     for action in self.service_actions[service]:
#                         available_actions.append(f"{service}:{action}")
#             else:
#                 available_actions.append(base_action)
        
#         # Remove duplicates and select random actions
#         available_actions = list(set(available_actions))
#         if not available_actions:
#             return ["s3:GetObject"]
            
#         selected_count = min(count, len(available_actions))
#         actions = random.sample(available_actions, selected_count)
        
#         return actions
    
#     def generate_variable_resources(self, base_resources: List[str], target_count: int = None) -> List[str]:
#         """Generate a variable number of resources, considering target combination count"""
#         if target_count is None:
#             count = random.randint(1, 2)  # 1-2 resources per request
#         else:
#             # Adjust resource count based on remaining target combinations
#             count = min(random.randint(1, min(3, target_count)), 3)
        
#         resources = []
        
#         for _ in range(count):
#             if base_resources:
#                 base_resource = random.choice(base_resources)
#                 expanded_resource = self.expand_wildcard_resource(base_resource)
#                 resources.append(expanded_resource)
#             else:
#                 resources.append("arn:aws:s3:::my-bucket/specific-file.txt")
        
#         # Remove duplicates while preserving order
#         seen = set()
#         unique_resources = []
#         for resource in resources:
#             if resource not in seen:
#                 seen.add(resource)
#                 unique_resources.append(resource)
        
#         return unique_resources
    


#     def generate_must_allow_requests(self, target_combinations: int) -> List[Dict[str, Any]]:
#         """Generate requests that must be allowed by the policy with exact combination count"""
#         allowed_requests = []
#         policy_elements = self.extract_policy_elements()
        
#         if not policy_elements["actions"]:
#             raise ValueError("No allowed actions found in policy")
        
#         remaining_combinations = target_combinations
#         request_count = 0
#         max_requests = target_combinations  # Prevent infinite loop
        
#         while remaining_combinations > 0 and request_count < max_requests:
#             # Determine how many combinations this request should have
#             if remaining_combinations == 1:
#                 # Last request - must be exactly 1 combination
#                 target_for_this_request = 1
#             else:
#                 # Random between 1 and remaining (but not too large)
#                 max_for_this_request = min(remaining_combinations, 6)  # Cap at 6 to avoid huge requests
#                 target_for_this_request = random.randint(1, max_for_this_request)
            
#             # Generate actions and resources to hit the target
#             attempts = 0
#             while attempts < 10:  # Prevent infinite loop
#                 actions = self.generate_variable_actions(policy_elements["actions"], target_for_this_request)
#                 resources = self.generate_variable_resources(policy_elements["resources"], target_for_this_request)
                
#                 combinations = self.calculate_combinations(actions, resources)
                
#                 if combinations <= remaining_combinations:
#                     break
                    
#                 attempts += 1
            
#             # If we couldn't hit the target exactly, adjust
#             if combinations > remaining_combinations:
#                 # Fall back to single action/resource
#                 actions = [self.generate_variable_actions(policy_elements["actions"], 1)[0]]
#                 resources = [self.generate_variable_resources(policy_elements["resources"], 1)[0]]
#                 combinations = 1
            
#             # Select allowed principal
#             principal = None
#             if policy_elements["principals"]:
#                 principal = random.choice(policy_elements["principals"])
            
#             request = {
#                 "id": f"allow_{uuid.uuid4().hex[:8]}",
#                 "Effect": "allow",
#                 "Action": actions,
#                 "Resource": resources
#             }
            
#             if principal:
#                 request["Principal"] = principal
            
#             allowed_requests.append(request)
#             remaining_combinations -= combinations
#             request_count += 1
        
#         return allowed_requests
    
#     def generate_variable_denied_actions(self, denied_actions: List[str], target_count: int = None) -> List[str]:
#         """Generate a variable number of denied actions"""
#         if target_count is None:
#             count = random.randint(1, 2)  # 1-2 denied actions per request
#         else:
#             count = min(random.randint(1, min(3, target_count)), len(denied_actions) if denied_actions else 1)
        
#         if not denied_actions:
#             return ["lambda:InvokeFunction"]  # Fallback
        
#         selected_count = min(count, len(denied_actions))
#         return random.sample(denied_actions, selected_count)
    
#     def generate_variable_denied_resources(self, denied_resources: List[str], target_count: int = None) -> List[str]:
#         """Generate a variable number of denied resources"""
#         if target_count is None:
#             count = random.randint(1, 2)  # 1-2 denied resources per request
#         else:
#             count = min(random.randint(1, min(3, target_count)), len(denied_resources) if denied_resources else 1)
        
#         if not denied_resources:
#             return ["arn:aws:s3:::forbidden-bucket/file.txt"]  # Fallback
        
#         selected_count = min(count, len(denied_resources))
#         return random.sample(denied_resources, selected_count)

#     def generate_must_deny_requests(self, target_combinations: int) -> List[Dict[str, Any]]:
#         """Generate requests that must be denied by the policy with exact combination count"""
#         denied_requests = []
#         policy_elements = self.extract_policy_elements()
        
#         # Generate denied variations
#         denied_actions = self.generate_denied_actions(policy_elements["actions"])
#         denied_resources = self.generate_denied_resources(policy_elements["resources"])
        
#         remaining_combinations = target_combinations
#         request_count = 0
#         max_requests = target_combinations  # Prevent infinite loop
        
#         while remaining_combinations > 0 and request_count < max_requests:
#             # Determine how many combinations this request should have
#             if remaining_combinations == 1:
#                 # Last request - must be exactly 1 combination
#                 target_for_this_request = 1
#             else:
#                 # Random between 1 and remaining (but not too large)
#                 max_for_this_request = min(remaining_combinations, 6)  # Cap at 6 to avoid huge requests
#                 target_for_this_request = random.randint(1, max_for_this_request)
            
#             # Strategy: alternate between denied action and denied resource
#             attempts = 0
#             while attempts < 10:  # Prevent infinite loop
#                 if request_count % 2 == 0 and denied_actions:
#                     # Use denied actions with allowed resources
#                     actions = self.generate_variable_denied_actions(denied_actions, target_for_this_request)
#                     resources = self.generate_variable_resources(policy_elements["resources"], target_for_this_request)
#                 else:
#                     # Use allowed actions with denied resources
#                     if denied_resources:
#                         actions = self.generate_variable_actions(policy_elements["actions"], target_for_this_request)
#                         resources = self.generate_variable_denied_resources(denied_resources, target_for_this_request)
#                     else:
#                         # Fallback to denied actions
#                         actions = self.generate_variable_denied_actions(denied_actions, target_for_this_request)
#                         resources = ["arn:aws:s3:::forbidden-bucket/file.txt"]
                
#                 combinations = self.calculate_combinations(actions, resources)
                
#                 if combinations <= remaining_combinations:
#                     break
                    
#                 attempts += 1
            
#             # If we couldn't hit the target exactly, adjust
#             if combinations > remaining_combinations:
#                 # Fall back to single action/resource
#                 if denied_actions:
#                     actions = [denied_actions[0]]
#                     resources = self.generate_variable_resources(policy_elements["resources"], 1)
#                 else:
#                     actions = self.generate_variable_actions(policy_elements["actions"], 1)
#                     resources = ["arn:aws:s3:::forbidden-bucket/file.txt"]
#                 combinations = 1
            
#             request = {
#                 "id": f"deny_{uuid.uuid4().hex[:8]}",
#                 "Effect": "deny",
#                 "Action": actions,
#                 "Resource": resources
#             }
            
#             denied_requests.append(request)
#             remaining_combinations -= combinations
#             request_count += 1
        
#         return denied_requests
    
#     def generate_all_requests(self, total_combinations: int, allow_ratio: float = 0.6) -> Dict[str, Any]:
#         """Generate complete set of must-allow and must-deny requests with exact combination count
        
#         Args:
#             total_combinations: Total number of individual request combinations to generate
#             allow_ratio: Ratio of allow combinations (default 0.6 = 60% allow, 40% deny)
#         """
#         try:
#             # Calculate number of allow and deny combinations
#             num_allow_combinations = int(total_combinations * allow_ratio)
#             num_deny_combinations = total_combinations - num_allow_combinations
            
#             # Ensure at least one of each type if total > 1
#             if total_combinations > 1:
#                 if num_allow_combinations == 0:
#                     num_allow_combinations = 1
#                     num_deny_combinations = total_combinations - 1
#                 elif num_deny_combinations == 0:
#                     num_deny_combinations = 1
#                     num_allow_combinations = total_combinations - 1
            
#             must_allow = self.generate_must_allow_requests(num_allow_combinations)
#             must_deny = self.generate_must_deny_requests(num_deny_combinations)
            
#             # Combine all requests - allows first, then denies
#             all_requests = must_allow + must_deny
            
#             # Don't shuffle - keep allows before denies
            
#             return {
#                 "Requests": all_requests
#             }
#         except Exception as e:
#             return {
#                 "error": f"Failed to generate requests: {str(e)}"
#             }

# def load_policy_from_file(file_path: str) -> Dict[str, Any]:
#     """Load IAM policy from JSON file"""
#     try:
#         with open(file_path, 'r') as file:
#             policy = json.load(file)
#         return policy
#     except FileNotFoundError:
#         raise FileNotFoundError(f"Policy file not found: {file_path}")
#     except json.JSONDecodeError as e:
#         raise ValueError(f"Invalid JSON in policy file: {e}")

# def save_requests_to_file(requests: Dict[str, Any], output_path: str) -> None:
#     """Save generated requests to JSON file"""
#     try:
#         with open(output_path, 'w') as file:
#             json.dump(requests, file, indent=2)
#         print(f"Generated requests saved to: {output_path}")
#     except Exception as e:
#         raise Exception(f"Failed to save requests to file: {e}")

# def main():
#     import argparse
#     import os
    
#     # Set up command line arguments
#     parser = argparse.ArgumentParser(description='Generate IAM policy test requests')
#     parser.add_argument('file_number', 
#                        help='Policy file number (e.g., 0, 1, 2...)')
#     parser.add_argument('--requests', '-r', 
#                        type=int, default=5,
#                        help='Total number of requests to generate (default: 5)')
#     parser.add_argument('--allow-ratio', 
#                        type=float, default=0.6,
#                        help='Ratio of allow requests (0.0-1.0, default: 0.6)')
    
#     args = parser.parse_args()
    
#     # Validate allow_ratio
#     if not 0.0 <= args.allow_ratio <= 1.0:
#         print("Error: --allow-ratio must be between 0.0 and 1.0")
#         return 1
    
#     # Set up file paths
#     policy_file = f"original_policy/{args.file_number}.json"
#     output_file = f"requests/request-{args.requests}/{args.file_number}.json"
    
#     # Create requests directory if it doesn't exist
#     os.makedirs(f"requests/request-{args.requests}", exist_ok=True)

#     try:
#         # Load policy from file
#         print(f"Loading policy from: {policy_file}")
#         policy = load_policy_from_file(policy_file)
#         print(f"Policy loaded successfully")
        
#         # Generate requests
#         print(f"Generating requests with exactly {args.requests} total combinations ({args.allow_ratio:.1%} allow ratio)...")
#         generator = RequestGenerator(policy)
#         test_data = generator.generate_all_requests(args.requests, args.allow_ratio)
        
#         if "error" in test_data:
#             print(f"Error generating requests: {test_data['error']}")
#             return 1
        
#         # Save to output file
#         save_requests_to_file(test_data, output_file)
        
#         # Calculate actual combinations
#         total_request_objects = len(test_data.get("Requests", []))
#         allow_objects = sum(1 for req in test_data.get("Requests", []) if req.get("Effect") == "allow")
#         deny_objects = sum(1 for req in test_data.get("Requests", []) if req.get("Effect") == "deny")
        
#         # Calculate total combinations
#         total_combinations = 0
#         allow_combinations = 0
#         deny_combinations = 0
        
#         for req in test_data.get("Requests", []):
#             actions = req.get("Action", [])
#             resources = req.get("Resource", [])
#             if not isinstance(actions, list):
#                 actions = [actions]
#             if not isinstance(resources, list):
#                 resources = [resources]
            
#             combinations = len(actions) * len(resources)
#             total_combinations += combinations
            
#             if req.get("Effect") == "allow":
#                 allow_combinations += combinations
#             else:
#                 deny_combinations += combinations
        
#         print(f"\nSummary:")
#         print(f"   Total request objects: {total_request_objects}")
#         print(f"   Allow objects: {allow_objects}, Deny objects: {deny_objects}")
#         print(f"   Total individual combinations: {total_combinations}")
#         print(f"   Allow combinations: {allow_combinations}")
#         print(f"   Deny combinations: {deny_combinations}")
#         print(f"   Actual allow ratio: {allow_combinations/total_combinations:.1%}")
#         print(f"   Saved to: {output_file}")
        
#     except Exception as e:
#         print(f"Error: {e}")
#         return 1
    
#     return 0

# if __name__ == "__main__":
#     import sys
    
#     # Show usage if no arguments
#     if len(sys.argv) == 1:
#         print("IAM Policy Request Generator")
#         print("\nUsage:")
#         print("  python request_generator.py 0")
#         print("  python request_generator.py 5 --requests 10")
#         print("  python request_generator.py 3 --requests 8 --allow-ratio 0.7")
#         print("\nOptions:")
#         print("  --requests, -r    Total number of requests to generate (default: 5)")
#         print("  --allow-ratio     Ratio of allow requests 0.0-1.0 (default: 0.6)")
#         print("\nThis will:")
#         print("  - Read from original_policy/{file_number}.json")
#         print("  - Save to requests/{file_number}.json")
#         print("  - Generate request objects with multiple actions/resources")
#         print("  - Total Cartesian product of all combinations equals specified number")
#         print("  - Split combinations between allow/deny based on ratio")
#         sys.exit(1)
    
#     sys.exit(main())                                                                                                                                                                                                              
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
        
        # Sample principals for generation
        self.sample_principals = [
            "arn:aws:iam::123456789012:user/alice",
            "arn:aws:iam::123456789012:user/bob",
            "arn:aws:iam::123456789012:role/service-role",
            "arn:aws:iam::123456789012:role/admin-role",
            "arn:aws:iam::987654321098:user/charlie",
            "arn:aws:iam::555666777888:role/cross-account-role"
        ]
        
        # Sample conditions for generation
        self.sample_conditions = [
            {"StringEquals": {"aws:RequestedRegion": "us-east-1"}},
            {"StringEquals": {"aws:RequestedRegion": "us-west-2"}},
            {"DateGreaterThan": {"aws:CurrentTime": "2024-01-01T00:00:00Z"}},
            {"DateLessThan": {"aws:CurrentTime": "2025-12-31T23:59:59Z"}},
            {"IpAddress": {"aws:SourceIp": "203.0.113.0/24"}},
            {"StringLike": {"aws:userid": "AIDAI"}},
            {"Bool": {"aws:SecureTransport": "true"}},
            {"StringEquals": {"s3:ExistingObjectTag/Department": "Finance"}},
            {"NumericLessThan": {"s3:max-keys": "10"}}
        ]
    
    def extract_policy_elements(self) -> Dict[str, List[str]]:
        """Extract actions, resources, and principals from the policy"""
        elements = {
            "actions": [],
            "resources": [],
            "principals": [],
            "conditions": []
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
                elif isinstance(principal, dict):
                    for key, value in principal.items():
                        if isinstance(value, str):
                            elements["principals"].append(value)
                        elif isinstance(value, list):
                            elements["principals"].extend(value)
                
                # Extract conditions
                condition = statement.get("Condition")
                if condition:
                    elements["conditions"].append(condition)
        
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
                    "arn:aws:s3:::forbidden-bucket/document.txt",
                    "arn:aws:iam::123456789012:role/admin-role",
                    "arn:aws:kms:us-east-1:123456789012:key/forbidden-key"
                ])
            elif "arn:aws:s3:::" in resource:
                # For S3 resources, create variations
                if resource.endswith("/*"):
                    bucket_name = resource.split(":::")[1].split("/")[0]
                    denied_resources.update([
                        f"arn:aws:s3:::different-{bucket_name}/file.txt",
                        f"arn:aws:s3:::{bucket_name}-forbidden/file.txt",
                        "arn:aws:s3:::completely-different-bucket/file.txt"
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
                # Simple resource names - make them specific
                denied_resources.update([
                    f"forbidden-{resource}-specific",
                    f"{resource}-forbidden-resource",
                    f"unauthorized/{resource}/file.txt"
                ])
        
        return list(denied_resources)
    
    def generate_denied_principals(self, allowed_principals: List[str]) -> List[str]:
        """Generate principals that should be denied"""
        denied_principals = []
        
        if not allowed_principals:
            # If no principals in policy, return some denied ones
            return self.sample_principals[:3]
        
        # Generate variations of allowed principals that would be denied
        for principal in allowed_principals:
            if principal == "*":
                # If wildcard, create specific principals that might be denied
                denied_principals.extend([
                    "arn:aws:iam::999888777666:user/unauthorized",
                    "arn:aws:iam::123456789012:user/blocked-user"
                ])
            elif "arn:aws:iam::" in principal:
                # Modify account ID or user/role name
                parts = principal.split(":")
                if len(parts) >= 6:
                    # Change account ID
                    modified_account = principal.replace(parts[4], "999888777666")
                    denied_principals.append(modified_account)
                    
                    # Change user/role name
                    if "/" in parts[5]:
                        resource_parts = parts[5].split("/")
                        resource_parts[-1] = f"forbidden-{resource_parts[-1]}"
                        modified_name = ":".join(parts[:5]) + ":" + "/".join(resource_parts)
                        denied_principals.append(modified_name)
        
        # Add some from sample if we don't have enough
        while len(denied_principals) < 3:
            for sample in self.sample_principals:
                if sample not in allowed_principals and sample not in denied_principals:
                    denied_principals.append(sample)
                    break
        
        return denied_principals
    
    def generate_denied_conditions(self, allowed_conditions: List[Dict]) -> List[Dict]:
        """Generate conditions that should be denied"""
        denied_conditions = []
        
        if not allowed_conditions:
            # If no conditions in policy, return some that would deny
            return self.sample_conditions[:3]
        
        # Generate conditions that would not match the allowed ones
        for condition in allowed_conditions:
            for operator, condition_block in condition.items():
                if operator == "StringEquals":
                    for key, value in condition_block.items():
                        # Create opposite condition
                        denied_conditions.append({
                            "StringEquals": {key: f"not-{value}"}
                        })
                elif operator == "IpAddress":
                    denied_conditions.append({
                        "IpAddress": {"aws:SourceIp": "192.168.1.0/24"}
                    })
                elif operator == "Bool":
                    for key, value in condition_block.items():
                        denied_conditions.append({
                            "Bool": {key: str(not bool(value)).lower()}
                        })
        
        # Add some from sample conditions
        for sample in self.sample_conditions:
            if sample not in denied_conditions:
                denied_conditions.append(sample)
                if len(denied_conditions) >= 5:
                    break
        
        return denied_conditions
    
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
    
    def expand_wildcard_principal(self, principal: str) -> str:
        """Convert wildcard principals to specific principals"""
        if principal == "*":
            return random.choice(self.sample_principals)
        elif principal.endswith("*"):
            base = principal[:-1]
            suffixes = ["user", "admin", "service"]
            return base + random.choice(suffixes)
        else:
            return principal
    
    def calculate_combinations(self, actions: List[str], resources: List[str]) -> int:
        """Calculate the number of individual request combinations"""
        return len(actions) * len(resources)
    
    def generate_variable_actions(self, base_actions: List[str], target_count: int = None) -> List[str]:
        """Generate a variable number of specific actions (no wildcards)"""
        if target_count is None:
            count = random.randint(1, 3)
        else:
            count = min(random.randint(1, min(3, target_count)), len(base_actions) if base_actions else 1)
        
        available_actions = []
        
        # Expand all base actions to get specific actions
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
        """Generate a variable number of specific resources (no wildcards)"""
        if target_count is None:
            count = random.randint(1, 2)
        else:
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
    
    def generate_correctly_classified_requests(self, target_combinations: int, allow_ratio: float) -> List[Dict[str, Any]]:
        """Generate 30% correctly classified requests"""
        requests = []
        policy_elements = self.extract_policy_elements()
        
        # Calculate correct allow/deny split
        num_allow = int(target_combinations * allow_ratio)
        num_deny = target_combinations - num_allow
        
        # Generate correctly allowed requests
        allow_requests = self.generate_must_allow_requests(num_allow, policy_elements)
        requests.extend(allow_requests)
        
        # Generate correctly denied requests
        deny_requests = self.generate_must_deny_requests(num_deny, policy_elements)
        requests.extend(deny_requests)
        
        return requests
    
    def generate_misclassified_requests(self, target_combinations: int, allow_ratio: float) -> List[Dict[str, Any]]:
        """Generate 70% misclassified requests (intended allow will be denied, intended deny will be allowed)"""
        requests = []
        policy_elements = self.extract_policy_elements()
        
        # Calculate split - but flip the logic
        num_intended_allow = int(target_combinations * allow_ratio)  # These will actually be denied
        num_intended_deny = target_combinations - num_intended_allow  # These will actually be allowed
        
        # Generate requests intended to be allowed but will be denied
        misclassified_allow = self.generate_misclassified_allow_requests(num_intended_allow, policy_elements)
        requests.extend(misclassified_allow)
        
        # Generate requests intended to be denied but will be allowed
        misclassified_deny = self.generate_misclassified_deny_requests(num_intended_deny, policy_elements)
        requests.extend(misclassified_deny)
        
        return requests
    
    def generate_must_allow_requests(self, target_combinations: int, policy_elements: Dict) -> List[Dict[str, Any]]:
        """Generate requests that must be allowed by the policy"""
        allowed_requests = []
        
        if not policy_elements["actions"]:
            raise ValueError("No allowed actions found in policy")
        
        remaining_combinations = target_combinations
        request_count = 0
        max_requests = target_combinations
        
        while remaining_combinations > 0 and request_count < max_requests:
            if remaining_combinations == 1:
                target_for_this_request = 1
            else:
                max_for_this_request = min(remaining_combinations, 6)
                target_for_this_request = random.randint(1, max_for_this_request)
            
            attempts = 0
            while attempts < 10:
                actions = self.generate_variable_actions(policy_elements["actions"], target_for_this_request)
                resources = self.generate_variable_resources(policy_elements["resources"], target_for_this_request)
                
                combinations = self.calculate_combinations(actions, resources)
                
                if combinations <= remaining_combinations:
                    break
                    
                attempts += 1
            
            if combinations > remaining_combinations:
                actions = [self.generate_variable_actions(policy_elements["actions"], 1)[0]]
                resources = [self.generate_variable_resources(policy_elements["resources"], 1)[0]]
                combinations = 1
            
            # Add principal and condition
            principal = None
            if policy_elements["principals"]:
                principal = self.expand_wildcard_principal(random.choice(policy_elements["principals"]))
            else:
                principal = random.choice(self.sample_principals)
            
            condition = None
            if policy_elements["conditions"]:
                condition = random.choice(policy_elements["conditions"])
            else:
                condition = random.choice(self.sample_conditions)
            
            request = {
                "id": f"allow_{uuid.uuid4().hex[:8]}",
                "Effect": "allow",
                "Action": actions,
                "Resource": resources,
                "Principal": principal,
                "Condition": condition
            }
            
            allowed_requests.append(request)
            remaining_combinations -= combinations
            request_count += 1
        
        return allowed_requests
    
    def generate_must_deny_requests(self, target_combinations: int, policy_elements: Dict) -> List[Dict[str, Any]]:
        """Generate requests that must be denied by the policy"""
        denied_requests = []
        
        denied_actions = self.generate_denied_actions(policy_elements["actions"])
        denied_resources = self.generate_denied_resources(policy_elements["resources"])
        denied_principals = self.generate_denied_principals(policy_elements["principals"])
        denied_conditions = self.generate_denied_conditions(policy_elements["conditions"])
        
        remaining_combinations = target_combinations
        request_count = 0
        max_requests = target_combinations
        
        while remaining_combinations > 0 and request_count < max_requests:
            if remaining_combinations == 1:
                target_for_this_request = 1
            else:
                max_for_this_request = min(remaining_combinations, 6)
                target_for_this_request = random.randint(1, max_for_this_request)
            
            attempts = 0
            while attempts < 10:
                if request_count % 2 == 0 and denied_actions:
                    actions = random.sample(denied_actions, min(1, len(denied_actions)))
                    resources = self.generate_variable_resources(policy_elements["resources"], target_for_this_request)
                else:
                    actions = self.generate_variable_actions(policy_elements["actions"], target_for_this_request)
                    if denied_resources:
                        resources = random.sample(denied_resources, min(1, len(denied_resources)))
                    else:
                        resources = ["arn:aws:s3:::forbidden-bucket/file.txt"]
                
                combinations = self.calculate_combinations(actions, resources)
                
                if combinations <= remaining_combinations:
                    break
                    
                attempts += 1
            
            if combinations > remaining_combinations:
                if denied_actions:
                    actions = [denied_actions[0]]
                    resources = self.generate_variable_resources(policy_elements["resources"], 1)
                else:
                    actions = self.generate_variable_actions(policy_elements["actions"], 1)
                    resources = ["arn:aws:s3:::forbidden-bucket/file.txt"]
                combinations = 1
            
            # Add denied principal and condition
            principal = random.choice(denied_principals) if denied_principals else random.choice(self.sample_principals)
            condition = random.choice(denied_conditions) if denied_conditions else random.choice(self.sample_conditions)
            
            request = {
                "id": f"deny_{uuid.uuid4().hex[:8]}",
                "Effect": "deny",
                "Action": actions,
                "Resource": resources,
                "Principal": principal,
                "Condition": condition
            }
            
            denied_requests.append(request)
            remaining_combinations -= combinations
            request_count += 1
        
        return denied_requests
    
    def generate_misclassified_allow_requests(self, target_combinations: int, policy_elements: Dict) -> List[Dict[str, Any]]:
        """Generate requests that appear to be allowed but will be denied"""
        requests = []
        
        denied_principals = self.generate_denied_principals(policy_elements["principals"])
        denied_conditions = self.generate_denied_conditions(policy_elements["conditions"])
        
        remaining_combinations = target_combinations
        request_count = 0
        
        while remaining_combinations > 0 and request_count < target_combinations:
            if remaining_combinations == 1:
                target_for_this_request = 1
            else:
                max_for_this_request = min(remaining_combinations, 6)
                target_for_this_request = random.randint(1, max_for_this_request)
            
            # Use allowed actions and resources but denied principal/condition
            actions = self.generate_variable_actions(policy_elements["actions"], target_for_this_request)
            resources = self.generate_variable_resources(policy_elements["resources"], target_for_this_request)
            
            combinations = self.calculate_combinations(actions, resources)
            
            if combinations > remaining_combinations:
                actions = [self.generate_variable_actions(policy_elements["actions"], 1)[0]]
                resources = [self.generate_variable_resources(policy_elements["resources"], 1)[0]]
                combinations = 1
            
            # Use denied principal or condition to make it fail
            principal = random.choice(denied_principals) if denied_principals else random.choice(self.sample_principals)
            condition = random.choice(denied_conditions) if denied_conditions else random.choice(self.sample_conditions)
            
            request = {
                "id": f"allow_{uuid.uuid4().hex[:8]}",
                "Effect": "allow",  # Intended to be allowed
                "Action": actions,
                "Resource": resources,
                "Principal": principal,
                "Condition": condition
            }
            
            requests.append(request)
            remaining_combinations -= combinations
            request_count += 1
        
        return requests
    
    def generate_misclassified_deny_requests(self, target_combinations: int, policy_elements: Dict) -> List[Dict[str, Any]]:
        """Generate requests that appear to be denied but will be allowed"""
        requests = []
        
        remaining_combinations = target_combinations
        request_count = 0
        
        while remaining_combinations > 0 and request_count < target_combinations:
            if remaining_combinations == 1:
                target_for_this_request = 1
            else:
                max_for_this_request = min(remaining_combinations, 6)
                target_for_this_request = random.randint(1, max_for_this_request)
            
            # Use allowed actions, resources, principals, and conditions so it gets allowed
            actions = self.generate_variable_actions(policy_elements["actions"], target_for_this_request)
            resources = self.generate_variable_resources(policy_elements["resources"], target_for_this_request)
            
            combinations = self.calculate_combinations(actions, resources)
            
            if combinations > remaining_combinations:
                actions = [self.generate_variable_actions(policy_elements["actions"], 1)[0]]
                resources = [self.generate_variable_resources(policy_elements["resources"], 1)[0]]
                combinations = 1
            
            # Use allowed principal and condition so it actually gets allowed
            principal = None
            if policy_elements["principals"]:
                principal = self.expand_wildcard_principal(random.choice(policy_elements["principals"]))
            else:
                principal = random.choice(self.sample_principals)
            
            condition = None
            if policy_elements["conditions"]:
                condition = random.choice(policy_elements["conditions"])
            else:
                condition = random.choice(self.sample_conditions)
            
            request = {
                "id": f"deny_{uuid.uuid4().hex[:8]}",
                "Effect": "deny",  # Intended to be denied
                "Action": actions,
                "Resource": resources,
                "Principal": principal,
                "Condition": condition
            }
            
            requests.append(request)
            remaining_combinations -= combinations
            request_count += 1
        
        return requests
    
    def generate_all_requests(self, total_combinations: int, allow_ratio: float = 0.6, correct_ratio: float = 0.3) -> Dict[str, Any]:
        """Generate complete set of requests with specified correct/misclassified ratio
        
        Args:
            total_combinations: Total number of individual request combinations to generate
            allow_ratio: Ratio of allow combinations (default 0.6 = 60% allow, 40% deny)
            correct_ratio: Ratio of correctly classified requests (default 0.3 = 30% correct, 70% misclassified)
        """
        try:
            # Calculate correct and misclassified combinations
            num_correct_combinations = int(total_combinations * correct_ratio)
            num_misclassified_combinations = total_combinations - num_correct_combinations
            
            # Generate correctly classified requests (30%)
            correct_requests = self.generate_correctly_classified_requests(num_correct_combinations, allow_ratio)
            
            # Generate misclassified requests (70%)
            misclassified_requests = self.generate_misclassified_requests(num_misclassified_combinations, allow_ratio)
            
            # Combine all requests
            all_requests = correct_requests + misclassified_requests
            
            # Shuffle to mix correct and misclassified
            random.shuffle(all_requests)
            
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
    parser = argparse.ArgumentParser(description='Generate IAM policy test requests with misclassification')
    parser.add_argument('file_number', 
                       help='Policy file number (e.g., 0, 1, 2...)')
    parser.add_argument('--requests', '-r', 
                       type=int, default=5,
                       help='Total number of requests to generate (default: 5)')
    parser.add_argument('--allow-ratio', 
                       type=float, default=0.6,
                       help='Ratio of allow requests (0.0-1.0, default: 0.6)')
    parser.add_argument('--correct-ratio',
                       type=float, default=0.3,
                       help='Ratio of correctly classified requests (0.0-1.0, default: 0.3)')
    
    args = parser.parse_args()
    
    # Validate ratios
    if not 0.0 <= args.allow_ratio <= 1.0:
        print("Error: --allow-ratio must be between 0.0 and 1.0")
        return 1
    
    if not 0.0 <= args.correct_ratio <= 1.0:
        print("Error: --correct-ratio must be between 0.0 and 1.0")
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
        print(f"Generating requests with exactly {args.requests} total combinations...")
        print(f"  Allow ratio: {args.allow_ratio:.1%}")
        print(f"  Correct classification ratio: {args.correct_ratio:.1%}")
        print(f"  Misclassified ratio: {1-args.correct_ratio:.1%}")
        
        generator = RequestGenerator(policy)
        test_data = generator.generate_all_requests(args.requests, args.allow_ratio, args.correct_ratio)
        
        if "error" in test_data:
            print(f"Error generating requests: {test_data['error']}")
            return 1
        
        # Save to output file
        save_requests_to_file(test_data, output_file)
        
        # Calculate actual combinations and classification
        total_request_objects = len(test_data.get("Requests", []))
        allow_objects = sum(1 for req in test_data.get("Requests", []) if req.get("Effect") == "allow")
        deny_objects = sum(1 for req in test_data.get("Requests", []) if req.get("Effect") == "deny")
        
        correct_objects = sum(1 for req in test_data.get("Requests", []) 
                            if req.get("Effect") == "allow")
        deny_objects = sum(1 for req in test_data.get("Requests", []) 
                         if req.get("Effect") == "deny")
        
        # Since we can't distinguish by ID anymore, we'll track by generation method
        # This is just for display purposes - the actual classification is in the logic
        
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
        print(f"   Correct classification ratio: {args.correct_ratio:.1%} (as configured)")
        print(f"   Misclassified ratio: {1-args.correct_ratio:.1%} (as configured)")
        print(f"   Each request includes Principal and Condition")
        print(f"   No wildcards in generated requests")
        print(f"   All IDs use standard allow_/deny_ format")
        print(f"   Saved to: {output_file}")
        
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    import sys
    
    # Show usage if no arguments
    if len(sys.argv) == 1:
        print("Enhanced IAM Policy Request Generator with Misclassification")
        print("\nUsage:")
        print("  python request_generator.py 0")
        print("  python request_generator.py 5 --requests 10")
        print("  python request_generator.py 3 --requests 8 --allow-ratio 0.7 --correct-ratio 0.2")
        print("\nOptions:")
        print("  --requests, -r      Total number of requests to generate (default: 5)")
        print("  --allow-ratio       Ratio of allow requests 0.0-1.0 (default: 0.6)")
        print("  --correct-ratio     Ratio of correctly classified requests 0.0-1.0 (default: 0.3)")
        print("\nFeatures:")
        print("  - Each request includes Principal and Condition")
        print("  - No wildcards in generated requests")
        print("  - 30% correctly classified (by default)")
        print("  - 70% misclassified (intended allow will be denied, intended deny will be allowed)")
        print("  - Total combinations of all requests equals specified number")
        print("\nRequest Types:")
        print("  - allow_XXXXXXXX: Correctly classified allow requests (will be allowed)")
        print("  - deny_XXXXXXXX: Correctly classified deny requests (will be denied)")
        print("  - misallow_XXXXXXXX: Misclassified requests (intended allow, will be denied)")
        print("  - misdeny_XXXXXXXX: Misclassified requests (intended deny, will be allowed)")
        print("\nThis will:")
        print("  - Read from original_policy/{file_number}.json")
        print("  - Save to requests/request-{requests}/{file_number}.json")
        print("  - Generate request objects with multiple actions/resources")
        print("  - Include realistic principals and conditions")
        print("  - Create intentional misclassification for testing")
        print("\nExamples:")
        print("  python request_generator.py 0                           # 5 requests, 60% allow, 30% correct")
        print("  python request_generator.py 1 --requests 20             # 20 requests with defaults")
        print("  python request_generator.py 2 --correct-ratio 0.1       # Only 10% correctly classified")
        print("  python request_generator.py 3 --allow-ratio 0.8 --requests 50  # 80% allow ratio, 50 requests")
        sys.exit(1)
    
    sys.exit(main())