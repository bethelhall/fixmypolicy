import json
import re
import itertools
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass
from enum import Enum

class Effect(Enum):
    ALLOW = "Allow"
    DENY = "Deny"

@dataclass
class Request:
    action: str
    resource: str
    principal: Optional[str] = None
    condition_context: Optional[Dict[str, Any]] = None
    
    def to_dict(self):
        return {
            "Action": self.action,
            "Resource": self.resource,
            "Principal": self.principal,
            "ConditionContext": self.condition_context
        }

@dataclass
class PolicyStatement:
    effect: Effect
    actions: List[str]
    resources: List[str]
    conditions: Optional[Dict[str, Any]] = None
    principals: Optional[List[str]] = None

class IAMPolicyAnalyzer:
    def __init__(self, policy: Dict[str, Any]):
        self.policy = policy
        self.statements = self._parse_statements()
    
    def _parse_statements(self) -> List[PolicyStatement]:
        statements = []
        for stmt in self.policy.get("Statement", []):
            effect = Effect.ALLOW if stmt.get("Effect") == "Allow" else Effect.DENY
            
            # Handle actions
            actions = stmt.get("Action", [])
            if isinstance(actions, str):
                actions = [actions]
            elif isinstance(actions, list):
                actions = [action for action in actions if action]
            
            # Handle resources
            resources = stmt.get("Resource", [])
            if isinstance(resources, str):
                resources = [resources]
                
            elif isinstance(resources, list):
                resources = [res for res in resources if res] 
            
            # Handle conditions
            conditions = stmt.get("Condition")
            
            # Handle principals
            principals = stmt.get("Principal")
            if isinstance(principals, str):
                principals = [principals]
            elif isinstance(principals, dict):
                # Flatten principal dict
                principal_list = []
                for key, values in principals.items():
                    if isinstance(values, str):
                        principal_list.append(values)
                    elif isinstance(values, list):
                        principal_list.extend(values)
                principals = principal_list
            
            statements.append(PolicyStatement(
                effect=effect,
                actions=actions,
                resources=resources,
                conditions=conditions,
                principals=principals
            ))
        
        return statements
    
    def _match_pattern(self, pattern: str, value: str) -> bool:
        """Check if a pattern matches a value (supports wildcards)"""
        if pattern == "*":
            return True
        
        # Convert IAM wildcard pattern to regex
        regex_pattern = pattern.replace("*", ".*").replace("?", ".")
        regex_pattern = f"^{regex_pattern}$"
        
        return bool(re.match(regex_pattern, value, re.IGNORECASE))
    
    def _evaluate_condition(self, condition: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """Evaluate IAM policy conditions"""
        if not condition or not context:
            return True
        
        for condition_operator, condition_block in condition.items():
            for condition_key, condition_values in condition_block.items():
                context_value = context.get(condition_key)
                
                if isinstance(condition_values, str):
                    condition_values = [condition_values]
                
                if condition_operator == "StringEquals":
                    if context_value not in condition_values:
                        return False
                elif condition_operator == "StringLike":
                    if not any(self._match_pattern(cv, str(context_value)) for cv in condition_values):
                        return False
                elif condition_operator == "IpAddress":
                    # Simplified IP check
                    if context_value not in condition_values:
                        return False
                # Add more condition operators as needed
        
        return True
    
    def evaluate_request(self, request: Request) -> bool:
        """Evaluate if a request should be allowed by the policy"""
        explicit_deny = False
        explicit_allow = False
        
        for stmt in self.statements:
            # Check if action matches
            action_matches = any(self._match_pattern(action, request.action) for action in stmt.actions)
            if not action_matches:
                continue
            
            # Check if resource matches
            resource_matches = any(self._match_pattern(resource, request.resource) for resource in stmt.resources)
            if not resource_matches:
                continue
            
            # Check conditions
            if stmt.conditions and not self._evaluate_condition(stmt.conditions, request.condition_context or {}):
                continue
            
            # Check principals (if specified)
            if stmt.principals and request.principal:
                principal_matches = any(self._match_pattern(principal, request.principal) for principal in stmt.principals)
                if not principal_matches:
                    continue
            
            # Apply effect
            if stmt.effect == Effect.DENY:
                explicit_deny = True
            elif stmt.effect == Effect.ALLOW:
                explicit_allow = True
        
        # IAM evaluation logic: explicit deny overrides everything, then explicit allow
        if explicit_deny:
            return False
        return explicit_allow

class RequestGenerator:
    def __init__(self, analyzer: IAMPolicyAnalyzer):
        self.analyzer = analyzer
        
        # Common AWS services and actions
        self.common_services = [
            "s3", "ec2", "lambda", "iam", "cloudwatch", "logs", "sns", "sqs", 
            "dynamodb", "rds", "ecs", "eks", "apigateway", "cloudformation"
        ]
        
        self.common_actions = {
            "s3": ["GetObject", "PutObject", "DeleteObject", "ListBucket", "CreateBucket"],
            "ec2": ["DescribeInstances", "RunInstances", "TerminateInstances", "CreateTags"],
            "lambda": ["InvokeFunction", "CreateFunction", "DeleteFunction", "GetFunction"],
            "iam": ["CreateRole", "DeleteRole", "PassRole", "GetRole", "AttachRolePolicy"],
            "cloudwatch": ["ListMetrics", "GetMetricStatistics", "PutMetricData"],
            "logs": ["CreateLogGroup", "CreateLogStream", "PutLogEvents"],
        }
        
        self.resource_patterns = [
            "arn:aws:s3:::bucket-name/*",
            "arn:aws:s3:::bucket-name",
            "arn:aws:ec2:us-east-1:123456789012:instance/*",
            "arn:aws:lambda:us-east-1:123456789012:function:*",
            "arn:aws:iam::123456789012:role/*",
            "*"
        ]
    
    def _extract_policy_elements(self) -> Dict[str, List[str]]:
        """Extract actions and resources from the policy"""
        policy_actions = set()
        policy_resources = set()
        
        for stmt in self.analyzer.statements:
            policy_actions.update(stmt.actions)
            policy_resources.update(stmt.resources)
        
        return {
            "actions": list(policy_actions),
            "resources": list(policy_resources)
        }
    
    def _generate_concrete_actions(self, action_pattern: str) -> List[str]:
        """Convert wildcard action patterns to concrete actions (no wildcards)"""
        concrete_actions = []
        
        if action_pattern == "*":
            # Generate common concrete actions
            concrete_actions.extend([
                "s3:GetObject",
                "s3:PutObject", 
                "s3:DeleteObject",
                "ec2:DescribeInstances",
                "ec2:RunInstances",
                "lambda:InvokeFunction",
                "iam:CreateRole"
            ])
        elif "*" in action_pattern:
            if action_pattern.endswith("*"):
                # Remove the wildcard and create concrete variations
                base = action_pattern[:-1]
                if ":" in base:
                    service, action_base = base.split(":", 1)
                    service_actions = self.common_actions.get(service, ["Object", "Item", "Resource"])
                    for suffix in service_actions:
                        concrete_actions.append(f"{service}:{action_base}{suffix}")
                else:
                    concrete_actions.append(f"{base}Object")
            elif action_pattern.startswith("*"):
                # Handle prefix wildcards
                suffix = action_pattern[1:]
                concrete_actions.extend([
                    f"Get{suffix}",
                    f"Put{suffix}",
                    f"Delete{suffix}"
                ])
        else:
            # Already concrete
            concrete_actions.append(action_pattern)
        
        # Filter out any remaining wildcards
        return [action for action in concrete_actions if "*" not in action and "?" not in action]
    
    def _generate_concrete_resources(self, resource_pattern: str) -> List[str]:
        """Convert wildcard resource patterns to concrete resources (no wildcards)"""
        concrete_resources = []
        
        if resource_pattern == "*":
            # Generate common concrete resources
            concrete_resources.extend([
                "arn:aws:s3:::test-bucket/file.txt",
                "arn:aws:s3:::prod-bucket",
                "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
                "arn:aws:lambda:us-east-1:123456789012:function:test-function",
                "arn:aws:iam::123456789012:role/test-role"
            ])
        elif "*" in resource_pattern:
            if resource_pattern.endswith("/*"):
                # Replace /* with specific items
                base = resource_pattern[:-2]
                concrete_resources.extend([
                    f"{base}/file1.txt",
                    f"{base}/file2.json",
                    f"{base}/folder/subfolder/item.data"
                ])
            elif resource_pattern.endswith("*"):
                # Replace trailing * with specific endings
                base = resource_pattern[:-1]
                concrete_resources.extend([
                    f"{base}123",
                    f"{base}test",
                    f"{base}prod"
                ])
            else:
                # Handle wildcards in middle
                if "/*/" in resource_pattern:
                    concrete_resources.append(resource_pattern.replace("/*/", "/specific-item/"))
                else:
                    concrete_resources.append(resource_pattern.replace("*", "concrete-value"))
        else:
            # Already concrete
            concrete_resources.append(resource_pattern)
        
        # Filter out any remaining wildcards
        return [resource for resource in concrete_resources if "*" not in resource and "?" not in resource]
    
    def generate_misclassified_requests(self, count: int = 20) -> Dict[str, List[Request]]:
        """Generate requests that might be misclassified due to policy ambiguities"""
        policy_elements = self._extract_policy_elements()
        misclassified_requests = []
        
        # Generate concrete requests from wildcard patterns in the policy
        for stmt in self.analyzer.statements:
            if len(misclassified_requests) >= count:
                break
                
            for action in stmt.actions:
                if len(misclassified_requests) >= count:
                    break
                    
                # Convert wildcard actions to concrete actions that might be problematic
                concrete_actions = self._generate_concrete_actions(action)
                
                for concrete_action in concrete_actions:
                    if len(misclassified_requests) >= count:
                        break
                        
                    for resource in stmt.resources:
                        if len(misclassified_requests) >= count:
                            break
                            
                        # Convert wildcard resources to concrete resources
                        concrete_resources = self._generate_concrete_resources(resource)
                        
                        for concrete_resource in concrete_resources:
                            if len(misclassified_requests) >= count:
                                break
                                
                            request = Request(concrete_action, concrete_resource)
                            misclassified_requests.append(request)
        
        # Add edge cases
        edge_cases = self._generate_edge_cases()
        if len(misclassified_requests) < count:
            remaining = count - len(misclassified_requests)
            misclassified_requests.extend(edge_cases[:remaining])
        
        return {
            "misclassified_requests": misclassified_requests[:count]
        }
    
    def _generate_edge_cases(self) -> List[Request]:
        """Generate edge cases that might reveal policy weaknesses (no wildcards in requests)"""
        edge_cases = []
        
        # Test with special characters in concrete actions/resources
        edge_cases.extend([
            Request("s3:GetObject", "arn:aws:s3:::bucket/file-with-special-chars!@#.txt"),
            Request("s3:PutObject", "arn:aws:s3:::bucket/path/with/../../traversal/file.txt"),
            Request("ec2:DescribeInstances", "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"),
        ])
        
        # Test with very long but concrete strings
        long_resource_name = "A" * 100
        edge_cases.append(Request("s3:GetObject", f"arn:aws:s3:::bucket/{long_resource_name}.txt"))
        
        # Test with case variations
        edge_cases.extend([
            Request("S3:GETOBJECT", "arn:aws:s3:::bucket/file.txt"),
            Request("s3:getobject", "arn:aws:s3:::bucket/file.txt"),
        ])
        
        # Test with service typos (concrete actions only)
        edge_cases.extend([
            Request("s2:GetObject", "arn:aws:s3:::bucket/file.txt"),
            Request("ec3:DescribeInstances", "arn:aws:ec2:us-east-1:123456789012:instance/i-123"),
        ])
        
        return edge_cases
    
    def generate_correctly_classified_requests(self, count: int = 20) -> Dict[str, List[Request]]:
        """Generate requests that will be correctly classified by the policy"""
        policy_elements = self._extract_policy_elements()
        allowed_requests = []
        denied_requests = []
        
        # Generate allowed requests (should match policy allow statements)
        for stmt in self.analyzer.statements:
            if stmt.effect == Effect.ALLOW and len(allowed_requests) < count // 2:
                for action in stmt.actions[:3]:  # Limit to avoid too many
                    for resource in stmt.resources[:3]:
                        if '*' in action or '*' in resource:
                            # Generate concrete examples for wildcards
                            concrete_action = self._concretize_wildcard(action)
                            concrete_resource = self._concretize_wildcard(resource)
                            allowed_requests.append(Request(concrete_action, concrete_resource))
                        else:
                            allowed_requests.append(Request(action, resource))
        
        # Generate denied requests (should not match any allow statements)
        denied_count = 0
        for service in self.common_services:
            if denied_count >= count // 2:
                break
            for action_name in self.common_actions.get(service, ["TestAction"]):
                action = f"{service}:{action_name}"
                resource = f"arn:aws:{service}:us-east-1:123456789012:resource/unauthorized"
                
                request = Request(action, resource)
                if not self.analyzer.evaluate_request(request):
                    denied_requests.append(request)
                    denied_count += 1
                    if denied_count >= count // 2:
                        break
        
        return {
            "correctly_allowed": allowed_requests[:count//2],
            "correctly_denied": denied_requests[:count//2]
        }
    
    def _concretize_wildcard(self, pattern: str) -> str:
        """Convert wildcard patterns to concrete examples"""
        if pattern == "*":
            return "s3:GetObject"
        
        if pattern.endswith("*"):
            base = pattern[:-1]
            if ":" in base:
                return f"{base}Object"
            else:
                return f"{base}example"
        
        return pattern
    
    def generate_comprehensive_test_suite(self, count: int = 50) -> Dict[str, Any]:
        """Generate a comprehensive test suite"""
        correctly_classified = self.generate_correctly_classified_requests(count // 2)
        misclassified = self.generate_misclassified_requests(count // 2)
        
        # Test each request against the policy
        test_results = {}
        
        for category, requests in {**correctly_classified, **misclassified}.items():
            test_results[category] = []
            for request in requests:
                result = self.analyzer.evaluate_request(request)
                test_results[category].append({
                    "request": request.to_dict(),
                    "policy_decision": "ALLOW" if result else "DENY",
                    "expected": self._get_expected_result(category, request),
                    "is_misclassified": self._is_misclassified(category, result)
                })
        
        return test_results
    
    def _get_expected_result(self, category: str, request: Request) -> str:
        """Determine expected result based on category"""
        if category in ["correctly_allowed", "false_negatives"]:
            return "ALLOW"
        else:
            return "DENY"
    
    def _is_misclassified(self, category: str, actual_result: bool) -> bool:
        """Check if the result represents a misclassification"""
        if category == "false_positives":
            return actual_result  # Should be denied but was allowed
        elif category == "false_negatives":
            return not actual_result  # Should be allowed but was denied
        else:
            return False  # Correctly classified categories

# Example usage
def main():
    # Example policy with potential misclassification issues
    example_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["s3:Get*", "s3:List*"],  # Overly broad wildcard
                "Resource": ["arn:aws:s3:::my-bucket/*", "arn:aws:s3:::my-bucket"]
            },
            {
                "Effect": "Allow",
                "Action": "ec2:Describe*",  # Another broad wildcard
                "Resource": "*"
            },
            {
                "Effect": "Deny",
                "Action": "s3:Delete*",
                "Resource": "*"
            }
        ]
    }
    
    # Create analyzer and generator
    analyzer = IAMPolicyAnalyzer(example_policy)
    generator = RequestGenerator(analyzer)
    
    # Generate test requests
    print("=== POLICY ANALYSIS ===")
    print(json.dumps(example_policy, indent=2))
    
    print("\n=== POTENTIALLY MISCLASSIFIED REQUESTS ===")
    misclassified = generator.generate_misclassified_requests(20)
    
    for category, requests in misclassified.items():
        print(f"\n{category.upper().replace('_', ' ')}:")
        for i, request in enumerate(requests[:5]):  # Show first 5
            result = analyzer.evaluate_request(request)
            status = "ALLOW" if result else "DENY"
            print(f"  {i+1}. {request.action} on {request.resource} -> {status}")
            
            # Explain why this might be a misclassification
            if category == "false_positives" and result:
                print(f"     ⚠️  This should probably be DENIED but is ALLOWED")
            elif category == "false_negatives" and not result:
                print(f"     ⚠️  This should probably be ALLOWED but is DENIED")
    
    # Generate and save comprehensive test suite
    print("\n=== GENERATING COMPREHENSIVE TEST SUITE ===")
    test_suite = generator.generate_comprehensive_test_suite(40)
    
    # Save to file
    with open("iam_policy_test_suite.json", "w") as f:
        json.dump(test_suite, f, indent=2, default=str)
    
    print("Test suite saved to 'iam_policy_test_suite.json'")
    
    # Summary statistics
    total_tests = sum(len(requests) for requests in test_suite.values())
    misclassified_count = sum(
        sum(1 for test in tests if test.get("is_misclassified", False))
        for tests in test_suite.values()
    )
    
    print(f"\nGenerated {total_tests} test cases across {len(test_suite)} categories")
    print(f"Found {misclassified_count} potentially misclassified requests")

if __name__ == "__main__":
    main()