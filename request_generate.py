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
    
    def generate_multiple_actions(self, base_actions: List[str], count: int = None) -> List[str]:
        """Generate multiple related actions for a request"""
        if count is None:
            count = random.randint(1, 3)  # 1-3 actions per request
        
        actions = []
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
        selected_count = min(count, len(available_actions))
        actions = random.sample(available_actions, selected_count)
        
        return actions
    
    def generate_multiple_resources(self, base_resources: List[str], count: int = None) -> List[str]:
        """Generate multiple related resources for a request"""
        if count is None:
            count = random.randint(1, 2)  # 1-2 resources per request
        
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

    def generate_must_allow_requests(self, num_requests: int) -> List[Dict[str, Any]]:
        """Generate requests that must be allowed by the policy"""
        allowed_requests = []
        policy_elements = self.extract_policy_elements()
        
        if not policy_elements["actions"]:
            raise ValueError("No allowed actions found in policy")
        
        for i in range(num_requests):
            # Generate multiple allowed actions
            actions = self.generate_multiple_actions(policy_elements["actions"])
            
            # Generate multiple allowed resources
            resources = self.generate_multiple_resources(policy_elements["resources"])
            
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
        
        return allowed_requests
    
    def generate_multiple_denied_actions(self, denied_actions: List[str], count: int = None) -> List[str]:
        """Generate multiple denied actions for a request"""
        if count is None:
            count = random.randint(1, 2)  # 1-2 denied actions per request
        
        if not denied_actions:
            return ["lambda:InvokeFunction"]  # Fallback
        
        selected_count = min(count, len(denied_actions))
        return random.sample(denied_actions, selected_count)
    
    def generate_multiple_denied_resources(self, denied_resources: List[str], count: int = None) -> List[str]:
        """Generate multiple denied resources for a request"""
        if count is None:
            count = random.randint(1, 2)  # 1-2 denied resources per request
        
        if not denied_resources:
            return ["arn:aws:s3:::forbidden-bucket/file.txt"]  # Fallback
        
        selected_count = min(count, len(denied_resources))
        return random.sample(denied_resources, selected_count)

    def generate_must_deny_requests(self, num_requests: int) -> List[Dict[str, Any]]:
        """Generate requests that must be denied by the policy"""
        denied_requests = []
        policy_elements = self.extract_policy_elements()
        
        # Generate denied variations
        denied_actions = self.generate_denied_actions(policy_elements["actions"])
        denied_resources = self.generate_denied_resources(policy_elements["resources"])
        
        for i in range(num_requests):
            # Strategy: alternate between denied action and denied resource
            if i % 2 == 0 and denied_actions:
                # Use denied actions with allowed resources
                actions = self.generate_multiple_denied_actions(denied_actions)
                resources = self.generate_multiple_resources(policy_elements["resources"])
                
            else:
                # Use allowed actions with denied resources
                if denied_resources:
                    actions = self.generate_multiple_actions(policy_elements["actions"])
                    resources = self.generate_multiple_denied_resources(denied_resources)
                else:
                    # Fallback to denied actions
                    actions = self.generate_multiple_denied_actions(denied_actions)
                    resources = ["arn:aws:s3:::forbidden-bucket/file.txt"]
            
            request = {
                "id": f"deny_{uuid.uuid4().hex[:8]}",
                "Effect": "deny",
                "Action": actions,
                "Resource": resources
            }
            
            denied_requests.append(request)
        
        return denied_requests
    
    def generate_all_requests(self, num_allow: int = 3, num_deny: int = 2) -> Dict[str, Any]:
        """Generate complete set of must-allow and must-deny requests"""
        try:
            must_allow = self.generate_must_allow_requests(num_allow)
            must_deny = self.generate_must_deny_requests(num_deny)
            
            # Combine all requests
            all_requests = must_allow + must_deny
            
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
        print(f"✅ Generated requests saved to: {output_path}")
    except Exception as e:
        raise Exception(f"Failed to save requests to file: {e}")

def main():
    import argparse
    import os
    
    # Set up command line arguments
    parser = argparse.ArgumentParser(description='Generate IAM policy test requests')
    parser.add_argument('file_number', 
                       help='Policy file number (e.g., 0, 1, 2...)')
    parser.add_argument('--allow', '-a', 
                       type=int, default=3,
                       help='Number of allow requests to generate (default: 3)')
    parser.add_argument('--deny', '-d', 
                       type=int, default=2,
                       help='Number of deny requests to generate (default: 2)')
    
    args = parser.parse_args()
    
    # Set up file paths
    policy_file = f"policy/{args.file_number}"
    output_file = f"requests/{args.file_number}.json"
    
    # Create requests directory if it doesn't exist
    os.makedirs("requests", exist_ok=True)
    
    try:
        # Load policy from file
        print(f"Loading policy from: {policy_file}")
        policy = load_policy_from_file(policy_file)
        print(f"Policy loaded successfully")
        
        # Generate requests
        print(f"Generating {args.allow} allow and {args.deny} deny requests...")
        generator = RequestGenerator(policy)
        test_data = generator.generate_all_requests(num_allow=args.allow, num_deny=args.deny)
        
        if "error" in test_data:
            print(f" Error generating requests: {test_data['error']}")
            return 1
        
        # Save to output file
        save_requests_to_file(test_data, output_file)
        
        # Print summary
        total_requests = len(test_data.get("Requests", []))
        allow_count = sum(1 for req in test_data.get("Requests", []) if req.get("Effect") == "allow")
        deny_count = sum(1 for req in test_data.get("Requests", []) if req.get("Effect") == "deny")
        
        print(f"Summary:")
        print(f"   Total requests: {total_requests}")
        print(f"   Allow requests: {allow_count}")
        print(f"   Deny requests: {deny_count}")
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
        print("  python request_generator.py 5 --allow 4 --deny 3")
        print("\nThis will:")
        print("  - Read from policy/0 (or policy/5)")
        print("  - Save to requests/0.json (or requests/5.json)")
        sys.exit(1)
    
    sys.exit(main())