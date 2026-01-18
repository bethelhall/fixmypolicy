# import json
# import random
# import uuid

# from typing import Dict, List, Any, Optional

# class RequestGenerator:
#     def __init__(self, policy: Dict[str, Any]):
#         self.policy = policy
#         self.service_actions = {
#             "s3": ["GetObject", "PutObject", "DeleteObject", "ListBucket", "GetBucketLocation", 
#                   "PutBucketPolicy", "GetBucketAcl", "CreateBucket", "DeleteBucket", "ListAllMyBuckets", 
#                   "GetObjectAcl", "PutObjectAcl", "GetBucketPolicy", "DeleteBucketPolicy", 
#                     "GetBucketCors", "PutBucketCors", "DeleteBucketCors", "GetBucketLogging", "PutBucketLogging",
#                     "GetBucketVersioning", "PutBucketVersioning", "GetBucketWebsite", "PutBucketWebsite",
#                     "DeleteBucketWebsite", "GetBucketTagging", "PutBucketTagging", "DeleteBucketTagging", 
#                     "GetBucketLifecycle", "PutBucketLifecycle", "DeleteBucketLifecycle",
#                     "GetObjectTagging", "PutObjectTagging", "DeleteObjectTagging",
#                     "GetObjectVersion", "ListObjectVersions", "RestoreObject"],
#             "athena": ["GetQueryExecution", "StartQueryExecution", "StopQueryExecution", 
#                       "GetWorkGroup", "GetDatabase", "BatchGetQueryExecution", "GetQueryResults",
#                       "GetQueryResultsStream", "GetTableMetadata", "CreateWorkGroup", "DeleteWorkGroup"],
#             "glue": ["GetTable", "GetDatabase", "GetPartitions", "CreateTable", "DeleteTable",
#                     "UpdateTable", "CreateDatabase", "DeleteDatabase", "UpdateDatabase", "GetJob",
#                     "StartJobRun", "GetJobRun", "BatchGetJobs", "GetCrawler", "StartCrawler", "GetCrawlers"],
#             "kms": ["CreateGrant", "DescribeKey", "Decrypt", "Encrypt", "GenerateDataKey",
#                    "DeleteAlias", "CreateKey", "ScheduleKeyDeletion", "CancelKeyDeletion", "ListKeys",
#                    "ListAliases", "UpdateKeyDescription", "EnableKey", "DisableKey",
#                    "ReEncrypt", "GenerateDataKeyWithoutPlaintext", "ListGrants", "RetireGrant", "RevokeGrant",
#                    "CreateAlias", "PutKeyPolicy", "GetKeyPolicy", "ListResourceTags"],
#             "ec2": ["DescribeInstances", "RunInstances", "TerminateInstances", "CreateSecurityGroup",
#                     "DeleteSecurityGroup", "AuthorizeSecurityGroupIngress", "RevokeSecurityGroupIngress",
#                     "CreateTags", "DeleteTags", "StartInstances", "StopInstances", "DescribeSecurityGroups",
#                     "DescribeVolumes", "CreateVolume", "DeleteVolume", "AttachVolume", "DetachVolume",
#                     "ModifyInstanceAttribute", "DescribeKeyPairs", "ImportKeyPair", "DeleteKeyPair"],
#             "iam": ["CreateUser", "DeleteUser", "AttachUserPolicy", "ListUsers", "GetUser", "CreateRole",
#                     "DeleteRole", "AttachRolePolicy", "ListRoles", "GetRole", "PutRolePolicy", "GetRolePolicy",
#                     "CreatePolicy", "DeletePolicy", "ListPolicies", "CreateAccessKey", "DeleteAccessKey",
#                     "ListAccessKeys", "UpdateAccessKey", "GetAccessKeyLastUsed",
#                     "CreateLoginProfile", "DeleteLoginProfile", "UpdateLoginProfile",
#                     "AddUserToGroup", "RemoveUserFromGroup", "ListGroupsForUser", "ListGroups",
#                     "CreateGroup", "DeleteGroup", "GetGroup", "ListAttachedUserPolicies",
#                     "ListAttachedRolePolicies", "ListAttachedGroupPolicies"],
#             "lambda": ["InvokeFunction", "CreateFunction", "DeleteFunction", "UpdateFunctionCode"],
#             "dynamodb": ["PutItem", "DeleteItem", "GetItem", "Scan", "Query", "CreateTable"],
#             "route53": ["ChangeResourceRecordSets", "ListHostedZones", "GetHostedZone"],
#             "rds": ["CreateDBInstance", "DeleteDBInstance", "DescribeDBInstances"],
#             "sns": ["Publish", "Subscribe", "CreateTopic", "DeleteTopic"],
#             "sqs": ["SendMessage", "ReceiveMessage", "DeleteMessage", "CreateQueue", 
#                     "DeleteQueue", "GetQueueAttributes", "SetQueueAttributes",
#                     "ListQueues", "PurgeQueue",
#                     "ChangeMessageVisibility", "GetQueueUrl", "ListDeadLetterSourceQueues",
#                     "AddPermission", "RemovePermission", "ListQueueTags", "TagQueue", "UntagQueue",
#                     "SendMessageBatch", "DeleteMessageBatch", "ChangeMessageVisibilityBatch",
#                     "GetQueueAttributes", "SetQueueAttributes", "GetQueueUrl", "ListQueues",
#                     "PurgeQueue", "ListDeadLetterSourceQueues", "AddPermission", "RemovePermission",
#                     "ListQueueTags", "TagQueue", "UntagQueue"
#                      ],
#             "cloudwatch": ["PutMetricData", "GetMetricData", "ListMetrics", "GetMetricStatistics", 
#                            "DescribeAlarms", "PutDashboard", "GetDashboard", "DeleteDashboards"],
#             "logs": ["CreateLogGroup", "CreateLogStream", "PutLogEvents", "DescribeLogStreams", 
#                      "DescribeLogGroups", "GetLogEvents", "FilterLogEvents", "DeleteLogGroup", "DeleteLogStream"],
#             "guardduty": ["CreateDetector", "GetDetector", "ListDetectors", "DeleteDetector",
#                             "CreateIPSet", "GetIPSet", "DeleteIPSet"],
#             "config": ["PutConfigRule", "GetComplianceDetailsByConfigRule", "DescribeConfigRules",
#                        "DeleteConfigRule"],
#             "cloudtrail": ["CreateTrail", "DeleteTrail", "GetTrailStatus", "StartLogging", "StopLogging"],
#             "cloudformation": ["CreateStack", "DeleteStack", "DescribeStacks", "UpdateStack"],
#             "cloudfront": ["CreateDistribution", "GetDistribution", "DeleteDistribution", "ListDistributions"],
#             "cloud9": ["CreateEnvironmentEC2", "DeleteEnvironment", "DescribeEnvironments"],
#             "codecommit": ["CreateRepository", "DeleteRepository", "GetRepository", "ListRepositories"],
#             "codebuild": ["StartBuild", "BatchGetBuilds", "StopBuild", "ListBuilds"],
#             "codepipeline": ["StartPipelineExecution", "GetPipeline", "ListPipelines"],
#             "codedeploy": ["CreateDeployment", "GetDeployment", "ListDeployments"],
#             "elasticbeanstalk": ["CreateApplication", "DeleteApplication", "DescribeApplications"],
#             "elasticloadbalancing": ["CreateLoadBalancer", "DeleteLoadBalancer", "DescribeLoadBalancers"],
#             "autoscaling": ["CreateAutoScalingGroup", "DeleteAutoScalingGroup", "DescribeAutoScalingGroups"],
#             "cloudsearch": ["CreateDomain", "DeleteDomain", "DescribeDomains"],
#             "es": ["CreateElasticsearchDomain", "DeleteElasticsearchDomain", "DescribeElasticsearchDomains"],
#             "kinesis": ["CreateStream", "DeleteStream", "DescribeStream", "PutRecord", "GetRecords"],
#             "redshift": ["CreateCluster", "DeleteCluster", "DescribeClusters"],
#             "ses": ["SendEmail", "SendRawEmail", "VerifyEmailIdentity", 
#                     "DeleteIdentity", "GetIdentityVerificationAttributes",
#                     "ListIdentities", "SetIdentityDkimEnabled", "GetIdentityDkimAttributes"],
#             "workspaces": ["CreateWorkspaces", "DeleteWorkspaces", "DescribeWorkspaces",
#                           "RebootWorkspaces", "StartWorkspaces", "StopWorkspaces",
#                           "ModifyWorkspaceProperties", "DescribeWorkspaceDirectories"], 
#             "sagemaker": ["CreateNotebookInstance", "DeleteNotebookInstance", "DescribeNotebookInstance",
#                             "StartNotebookInstance", "StopNotebookInstance", "ListNotebookInstances",
#                             "CreateTrainingJob", "DescribeTrainingJob", "ListTrainingJobs",
#                             "CreateModel", "DescribeModel", "ListModels",
#                             "CreateEndpointConfig", "DescribeEndpointConfig", "ListEndpointConfigs",
#                             "CreateEndpoint", "DescribeEndpoint", "ListEndpoints",
#                             "InvokeEndpoint"]
#         }
        
#         # Sample principals for generation
#         self.sample_principals = [
            
#             "arn:aws:iam::123456789012:user/alice",
#             "arn:aws:iam::123456789012:user/bob",
#             "arn:aws:iam::123456789012:role/service-role",
#             "arn:aws:iam::123456789012:role/admin-role",
#             "arn:aws:iam::987654321098:user/charlie",
#             "arn:aws:iam::555666777888:role/cross-account-role",
#             "arn:aws:iam::111222333444:user/david",
#             "arn:aws:iam::111222333444:role/developer-role",
#             "arn:aws:iam::999888777666:user/unauthorized",
#             "arn:aws:iam::123456789012:user/blocked-user",
#             "arn:aws:iam::123456789012:user/test-user",
#             "arn:aws:iam::123456789012:role/test-role",
#             "arn:aws:iam::123456789012:user/temp-user"
            
#         ]
        
#         self.sample_conditions = [
#             {"StringEquals": {"aws:RequestedRegion": "us-east-1"}},
#             {"StringEquals": {"aws:RequestedRegion": "us-west-2"}},
#             {"StringEquals": {"aws:RequestedRegion": "eu-west-1"}},
            
#             {"IpAddress": {"aws:SourceIp": "203.0.113.0/24"}},
#             {"StringLike": {"aws:userid": "AIDAI"}},
#             {"Bool": {"aws:SecureTransport": "true"}},
#             {"StringEquals": {"s3:ExistingObjectTag/Department": "Finance"}},
#             {"NumericLessThan": {"s3:max-keys": "10"}},
            
#         ]
#     def extract_policy_elements(self) -> Dict[str, List[str]]:
#         """Extract actions, resources, and principals from the policy"""
#         elements = {
#             "actions": [],
#             "resources": [],
#             "principals": [],
#             "conditions": [],
#             "has_principal": False,
#             "has_condition": False,
#             "has_action": False,
#             "has_resource": False
#         }
        
#         statements = self.policy.get("Statement", [])
#         for statement in statements:
#             # Changed: Extract from BOTH Allow and Deny statements
#             if statement.get("Effect") in ["Allow", "Deny"]:
#                 # Check and extract actions
#                 if "Action" in statement:
#                     elements["has_action"] = True
#                     actions = statement.get("Action", [])
#                     if isinstance(actions, str):
#                         elements["actions"].append(actions)
#                     elif isinstance(actions, list):
#                         elements["actions"].extend(actions)
                
#                 # Check and extract resources
#                 if "Resource" in statement:
#                     elements["has_resource"] = True
#                     resources = statement.get("Resource", [])
#                     if isinstance(resources, str):
#                         elements["resources"].append(resources)
#                     elif isinstance(resources, list):
#                         elements["resources"].extend(resources)
                
#                 # Check and extract principals
#                 if "Principal" in statement:
#                     elements["has_principal"] = True
#                     principal = statement.get("Principal")
#                     if isinstance(principal, str):
#                         elements["principals"].append(principal)
#                     elif isinstance(principal, list):
#                         elements["principals"].extend(principal)
#                     elif isinstance(principal, dict):
#                         for key, value in principal.items():
#                             if isinstance(value, str):
#                                 elements["principals"].append(value)
#                             elif isinstance(value, list):
#                                 elements["principals"].extend(value)
                
#                 # Check and extract conditions
#                 if "Condition" in statement:
#                     elements["has_condition"] = True
#                     condition = statement.get("Condition")
#                     if condition:
#                         elements["conditions"].append(condition)
        
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
#                     "arn:aws:s3:::admin-bucket/document.txt",
#                     "arn:aws:iam::123456789012:role/admin-role",
#                     "arn:aws:kms:us-east-1:123456789012:key/09348485-1234-5678-90ab-cdef12345678",
#                 ])
#             elif "arn:aws:s3:::" in resource:
#                 # For S3 resources, create variations
#                 if resource.endswith("/*"):
#                     bucket_name = resource.split(":::")[1].split("/")[0]
#                     denied_resources.update([
#                         f"arn:aws:s3:::different-{bucket_name}/file.txt",
#                         f"arn:aws:s3:::{bucket_name}-forbidden/file.txt",
#                         "arn:aws:s3:::completely-different-bucket/file.txt"
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
#                 # Simple resource names - make them specific
#                 denied_resources.update([
#                     f"forbidden-{resource}-specific",
#                     f"{resource}-forbidden-resource",
#                     f"authorized/{resource}/file.txt"
#                 ])
        
#         return list(denied_resources)
    
#     def generate_denied_principals(self, allowed_principals: List[str]) -> List[str]:
#         """Generate principals that should be denied"""
#         denied_principals = []
        
#         if not allowed_principals:
#             # If no principals in policy, return some denied ones
#             return self.sample_principals[:3]
        
#         # Generate variations of allowed principals that would be denied
#         for principal in allowed_principals:
#             if principal == "*":
#                 # If wildcard, create specific principals that might be denied
#                 denied_principals.extend([
#                     "arn:aws:iam::999888777666:user/unauthorized",
#                     "arn:aws:iam::123456789012:user/blocked-user",
#                     "arn:aws:iam::123456789012:role/forbidden-role",
#                     "arn:aws:iam::555666777888:role/cross-account-role",
#                     "arn:aws:iam::111222333444:user/temp-user",
#                     "arn:aws:iam::123456789012:user/test-user",
#                     "arn:aws:iam::123456789012:role/test-role"
#                 ])
#             elif "arn:aws:iam::" in principal:
#                 # Modify account ID or user/role name
#                 parts = principal.split(":")
#                 if len(parts) >= 6:
#                     # Change account ID
#                     modified_account = principal.replace(parts[4], np.random.randint(100000000000, 999999999999).__str__())
#                     denied_principals.append(modified_account)
                    
#                     # Change user/role name
#                     if "/" in parts[5]:
#                         resource_parts = parts[5].split("/")
#                         resource_parts[-1] = f"forbidden-{resource_parts[-1]}"
#                         modified_name = ":".join(parts[:5]) + ":" + "/".join(resource_parts)
#                         denied_principals.append(modified_name)
        
#         # Add some from sample if we don't have enough
#         while len(denied_principals) < 3:
#             for sample in self.sample_principals:
#                 if sample not in allowed_principals and sample not in denied_principals:
#                     denied_principals.append(sample)
#                     break
        
#         return denied_principals
    
#     def generate_denied_conditions(self, allowed_conditions: List[Dict]) -> List[Dict]:
#         """Generate conditions that should be denied"""
#         denied_conditions = []
        
#         if not allowed_conditions:
#             # If no conditions in policy, return some that would deny
#             return self.sample_conditions[:3]
        
#         # Generate conditions that would not match the allowed ones
#         for condition in allowed_conditions:
#             for operator, condition_block in condition.items():
#                 if operator == "StringEquals":
#                     for key, value in condition_block.items():
#                         # Create opposite condition
#                         denied_conditions.append({
#                             "StringEquals": {key: f"not-{value}"}
#                         })
#                 elif operator == "IpAddress":
#                     denied_conditions.append({
#                         "IpAddress": {"aws:SourceIp": "192.168.1.0/24"}
#                     })
#                 elif operator == "Bool":
#                     for key, value in condition_block.items():
#                         denied_conditions.append({
#                             "Bool": {key: str(not bool(value)).lower()}
#                         })
        
#         # Add some from sample conditions
#         for sample in self.sample_conditions:
#             if sample not in denied_conditions:
#                 denied_conditions.append(sample)
#                 if len(denied_conditions) >= 5:
#                     break
        
#         return denied_conditions
    
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
    
#     def expand_wildcard_principal(self, principal: str) -> str:
#         """Convert wildcard principals to specific principals"""
#         if principal == "*":
#             return random.choice(self.sample_principals)
#         elif principal.endswith("*"):
#             base = principal[:-1]
#             suffixes = ["user", "admin", "service"]
#             return base + random.choice(suffixes)
#         else:
#             return principal
    
#     def calculate_combinations(self, actions: List[str], resources: List[str]) -> int:
#         """Calculate the number of individual request combinations"""
#         return len(actions) * len(resources)
    
#     def generate_variable_actions(self, base_actions: List[str], target_count: int = None) -> List[str]:
#         """Generate a variable number of specific actions (no wildcards)"""
#         if target_count is None:
#             count = random.randint(1, 3)
#         else:
#             count = min(random.randint(1, min(3, target_count)), len(base_actions) if base_actions else 1)
        
#         available_actions = []
        
#         # Expand all base actions to get specific actions
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
#         """Generate a variable number of specific resources (no wildcards)"""
#         if target_count is None:
#             count = random.randint(1, 2)
#         else:
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
    
#     def generate_correctly_classified_requests(self, target_combinations: int, allow_ratio: float) -> List[Dict[str, Any]]:
#         """Generate correctly classified requests"""
#         requests = []
#         policy_elements = self.extract_policy_elements()
        
#         # Calculate correct allow/deny split
#         num_allow = int(target_combinations * allow_ratio)
#         num_deny = target_combinations - num_allow
        
#         # Generate correctly allowed requests
#         allow_requests = self.generate_must_allow_requests(num_allow, policy_elements)
#         requests.extend(allow_requests)
        
#         # Generate correctly denied requests
#         deny_requests = self.generate_must_deny_requests(num_deny, policy_elements)
#         requests.extend(deny_requests)
        
#         return requests
    
#     def generate_must_allow_requests(self, target_combinations: int, policy_elements: Dict) -> List[Dict[str, Any]]:
#         """Generate requests that must be allowed by the policy"""
#         allowed_requests = []
        
#         if not policy_elements["actions"]:
#             raise ValueError("No allowed actions found in policy")
        
#         remaining_combinations = target_combinations
#         request_count = 0
#         max_requests = target_combinations
        
#         while remaining_combinations > 0 and request_count < max_requests:
#             if remaining_combinations == 1:
#                 target_for_this_request = 1
#             else:
#                 max_for_this_request = min(remaining_combinations, 6)
#                 target_for_this_request = random.randint(1, max_for_this_request)
            
#             attempts = 0
#             while attempts < 10:
#                 actions = self.generate_variable_actions(policy_elements["actions"], target_for_this_request)
#                 resources = self.generate_variable_resources(policy_elements["resources"], target_for_this_request)
                
#                 combinations = self.calculate_combinations(actions, resources)
                
#                 if combinations <= remaining_combinations:
#                     break
                    
#                 attempts += 1
            
#             if combinations > remaining_combinations:
#                 actions = [self.generate_variable_actions(policy_elements["actions"], 1)[0]]
#                 resources = [self.generate_variable_resources(policy_elements["resources"], 1)[0]]
#                 combinations = 1
            
#             # Build request with only keys that exist in the policy
#             request = {
#                 "id": f"allow_{uuid.uuid4().hex[:8]}",
#                 "Effect": "allow"
#             }
            
#             # Only add Action if it exists in policy
#             if policy_elements["has_action"]:
#                 request["Action"] = actions
            
#             # Only add Resource if it exists in policy
#             if policy_elements["has_resource"]:
#                 request["Resource"] = resources
            
#             # Only add Principal if it exists in policy
#             if policy_elements["has_principal"]:
#                 if policy_elements["principals"]:
#                     request["Principal"] = self.expand_wildcard_principal(random.choice(policy_elements["principals"]))
#                 else:
#                     request["Principal"] = random.choice(self.sample_principals)

#             # Only add Condition if it exists in policy
#             if policy_elements["has_condition"]:
#                 if policy_elements["conditions"]:
#                     request["Condition"] = random.choice(policy_elements["conditions"])
#                 else:
#                     request["Condition"] = random.choice(self.sample_conditions)
#             allowed_requests.append(request)
#             remaining_combinations -= combinations
#             request_count += 1
        
#         return allowed_requests
    
#     def generate_must_deny_requests(self, target_combinations: int, policy_elements: Dict) -> List[Dict[str, Any]]:
#         """Generate requests that must be denied by the policy"""
#         denied_requests = []
        
#         denied_actions = self.generate_denied_actions(policy_elements["actions"])
#         denied_resources = self.generate_denied_resources(policy_elements["resources"])
#         denied_principals = self.generate_denied_principals(policy_elements["principals"])
#         denied_conditions = self.generate_denied_conditions(policy_elements["conditions"])
        
#         remaining_combinations = target_combinations
#         request_count = 0
#         max_requests = target_combinations
        
#         while remaining_combinations > 0 and request_count < max_requests:
#             if remaining_combinations == 1:
#                 target_for_this_request = 1
#             else:
#                 max_for_this_request = min(remaining_combinations, 6)
#                 target_for_this_request = random.randint(1, max_for_this_request)
            
#             attempts = 0
#             while attempts < 10:
#                 if request_count % 2 == 0 and denied_actions:
#                     actions = random.sample(denied_actions, min(1, len(denied_actions)))
#                     resources = self.generate_variable_resources(policy_elements["resources"], target_for_this_request)
#                 else:
#                     actions = self.generate_variable_actions(policy_elements["actions"], target_for_this_request)
#                     if denied_resources:
#                         resources = random.sample(denied_resources, min(1, len(denied_resources)))
#                     else:
#                         resources = ["arn:aws:s3:::forbidden-bucket/file.txt"]
                
#                 combinations = self.calculate_combinations(actions, resources)
                
#                 if combinations <= remaining_combinations:
#                     break
                    
#                 attempts += 1
            
#             if combinations > remaining_combinations:
#                 if denied_actions:
#                     actions = [denied_actions[0]]
#                     resources = self.generate_variable_resources(policy_elements["resources"], 1)
#                 else:
#                     actions = self.generate_variable_actions(policy_elements["actions"], 1)
#                     resources = ["arn:aws:s3:::forbidden-bucket/file.txt"]
#                 combinations = 1
            
#             # Build request with only keys that exist in the policy
#             request = {
#                 "id": f"deny_{uuid.uuid4().hex[:8]}",
#                 "Effect": "deny"
#             }
            
#             # Only add Action if it exists in policy
#             if policy_elements["has_action"]:
#                 request["Action"] = actions
            
#             # Only add Resource if it exists in policy  
#             if policy_elements["has_resource"]:
#                 request["Resource"] = resources
            
#             # Only add Principal if it exists in policy
#             if policy_elements["has_principal"]:
#                 request["Principal"] = random.choice(denied_principals)
#             # Only add Condition if it exists in policy
#             if policy_elements["has_condition"]:
#                 request["Condition"] = random.choice(denied_conditions)
                

#             denied_requests.append(request)
#             remaining_combinations -= combinations
#             request_count += 1
        
#         return denied_requests
#     # def misclassify_request(self, request: Dict[str, Any], policy_elements: Dict) -> Dict[str, Any]:
#     #     """Take a correctly classified request and modify it to be misclassified"""
#     #     misclassified_request = request.copy()
        
#     #     if request["Effect"] == "allow":
#     #         # This should be allowed but we'll make it denied by using denied principal/condition
#     #         denied_principals = self.generate_denied_principals(policy_elements["principals"])
#     #         denied_conditions = self.generate_denied_conditions(policy_elements["conditions"])
            
#     #         # Only modify Principal if it exists in the original policy
#     #         if policy_elements["has_principal"] and denied_principals:
#     #             misclassified_request["Principal"] = random.choice(denied_principals)
                
#     #         # Only modify Condition if it exists in the original policy
#     #         if policy_elements["has_condition"] and denied_conditions:
#     #             misclassified_request["Condition"] = random.choice(denied_conditions)
                
#     #     else:  # Effect == "deny"
#     #         # This should be denied but we'll make it allowed by using allowed principal/condition
            
#     #         # Only modify Principal if it exists in the original policy
#     #         if policy_elements["has_principal"] and policy_elements["principals"]:
#     #             misclassified_request["Principal"] = self.expand_wildcard_principal(random.choice(policy_elements["principals"]))
                
#     #         # Only modify Condition if it exists in the original policy
#     #         if policy_elements["has_condition"] and policy_elements["conditions"]:
#     #             misclassified_request["Condition"] = random.choice(policy_elements["conditions"])
        
#     #     return misclassified_request
    
#     def misclassify_request(self, request: Dict[str, Any], policy_elements: Dict) -> Dict[str, Any]:
#         """Take a correctly classified request and modify it to be misclassified"""
#         misclassified_request = request.copy()
        
#         if request["Effect"] == "allow":
#             # This should be allowed but we'll make it denied by using denied principal/condition
#             denied_principals = self.generate_denied_principals(policy_elements["principals"])
#             denied_conditions = self.generate_denied_conditions(policy_elements["conditions"])
            
#             if denied_principals:
#                 misclassified_request["Principal"] = random.choice(denied_principals)
#             if denied_conditions:
#                 misclassified_request["Condition"] = random.choice(denied_conditions)
                
#         else:  # Effect == "deny"
#             # This should be denied but we'll make it allowed by using allowed principal/condition
#             if policy_elements["principals"]:
#                 misclassified_request["Principal"] = self.expand_wildcard_principal(random.choice(policy_elements["principals"]))
#             else:
#                 misclassified_request["Principal"] = random.choice(self.sample_principals)
                
#             if policy_elements["conditions"]:
#                 misclassified_request["Condition"] = random.choice(policy_elements["conditions"])
#             else:
#                 misclassified_request["Condition"] = random.choice(self.sample_conditions)
        
#         return misclassified_request
    
#     def generate_all_requests(self, total_combinations: int, misclassified_percent: int = 70) -> Dict[str, Any]:
#         """Generate complete set of requests with specified misclassification percentage
        
#         Args:
#             total_combinations: Total number of individual request combinations to generate
#             misclassified_percent: Percentage of requests that should be misclassified (default 70)
#         """
#         try:
#             policy_elements = self.extract_policy_elements()
#             allow_ratio = 0.6 
            
#             # First, generate ALL requests correctly classified
#             all_correct_requests = self.generate_correctly_classified_requests(total_combinations, allow_ratio)
            
#             # Calculate how many to misclassify
#             num_to_misclassify = int(len(all_correct_requests) * misclassified_percent / 100.0)
            
#             # Randomly select which requests to misclassify
#             requests_to_misclassify = random.sample(all_correct_requests, num_to_misclassify)
            
#             # Create the final list
#             final_requests = []
            
#             for request in all_correct_requests:
#                 if request in requests_to_misclassify:
#                     # Misclassify this request
#                     misclassified_request = self.misclassify_request(request, policy_elements)
#                     final_requests.append(misclassified_request)
#                 else:
#                     # Keep as correctly classified
#                     final_requests.append(request)
            
#             # Shuffle to mix correct and misclassified
#             random.shuffle(final_requests)
            
#             return {
#                 "Requests": final_requests
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
#     import sys
    
#     # Show usage if wrong number of arguments
#     if len(sys.argv) != 4:
#         print("IAM Policy Request Generator")
#         print("\nUsage:")
#         print("  python request_generator.py <policy_number> <num_requests> <misclassified_percent>")
#         print("\nExamples:")
#         print("  python request_generator.py 0 25 70    # Policy 0, 25 requests, 70% misclassified")
#         print("  python request_generator.py 1 10 0     # Policy 1, 10 requests, 0% misclassified")
#         print("  python request_generator.py 2 50 100   # Policy 2, 50 requests, 100% misclassified")
#         print("\nArguments:")
#         print("  policy_number       : Policy file number (reads from original_policy/{N}.json)")
#         print("  num_requests        : Total number of requests to generate")
#         print("  misclassified_percent: Percentage to misclassify (0-100)")
#         print("\nMisclassification means:")
#         print("  - Intended ALLOW requests will be DENIED")
#         print("  - Intended DENY requests will be ALLOWED")
#         print("\nOutput:")
#         print("  - Saves to requests/request-{num_requests}/{policy_number}.json")
#         print("  - Fixed 60% allow / 40% deny ratio")
#         print("  - Each request includes Principal and Condition")
#         print("  - No wildcards in generated requests")
#         return 1
    
#     # Parse command line arguments
#     policy_number = sys.argv[1]
#     try:
#         num_requests = int(sys.argv[2])
#         misclassified_percent = int(sys.argv[3])
#     except ValueError:
#         print("Error: num_requests and misclassified_percent must be integers")
#         return 1
    
#     # Validate arguments
#     if num_requests <= 0:
#         print("Error: num_requests must be positive")
#         return 1
    
#     if not 0 <= misclassified_percent <= 100:
#         print("Error: misclassified_percent must be between 0 and 100")
#         return 1
    
#     # Set up file paths
#     policy_file = f"original_policy/{policy_number}.json"
#     output_file = f"requests/request-{num_requests}/{policy_number}.json"
    
#     # Create requests directory if it doesn't exist
#     os.makedirs(f"requests/request-{num_requests}", exist_ok=True)

#     try:
#         # Load policy from file
#         print(f"Loading policy from: {policy_file}")
#         policy = load_policy_from_file(policy_file)
#         print(f"Policy loaded successfully")
        
#         # Generate requests
#         print(f"Generating requests with exactly {num_requests} total combinations...")
#         print(f"  Allow ratio: 60.0%")
#         print(f"  Misclassified: {misclassified_percent}%")
#         print(f"  Correctly classified: {100-misclassified_percent}%")
        
#         generator = RequestGenerator(policy)
#         test_data = generator.generate_all_requests(num_requests, misclassified_percent)
        
#         if "error" in test_data:
#             print(f"Error generating requests: {test_data['error']}")
#             return 1
        
#         # Save to output file
#         save_requests_to_file(test_data, output_file)
        
#         # Calculate actual combinations and classification
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
#         print(f"   Misclassified: {misclassified_percent}%")
#         print(f"   Correctly classified: {100-misclassified_percent}%")
#         print(f"\nFeatures:")
#         print(f"   Each request includes Principal and Condition")
#         print(f"   No wildcards in generated requests")
#         print(f"   All IDs use standard allow_/deny_ format")
#         print(f"   Saved to: {output_file}")
        
#     except Exception as e:
#         print(f"Error: {e}")
#         return 1
    
#     return 0

# if __name__ == "__main__":
#     import sys
#     sys.exit(main())

import json
import random
import uuid
import hashlib
from typing import Dict, List, Any, Optional, Set

class RequestGenerator:
    def __init__(self, policy: Dict[str, Any]):
        self.policy = policy
        self.service_actions = {
            "s3": ["GetObject", "PutObject", "DeleteObject", "ListBucket", "GetBucketLocation", 
                  "PutBucketPolicy", "GetBucketAcl", "CreateBucket", "DeleteBucket", "ListAllMyBuckets", 
                  "GetObjectAcl", "PutObjectAcl", "GetBucketPolicy", "DeleteBucketPolicy", 
                    "GetBucketCors", "PutBucketCors", "DeleteBucketCors", "GetBucketLogging", "PutBucketLogging",
                    "GetBucketVersioning", "PutBucketVersioning", "GetBucketWebsite", "PutBucketWebsite",
                    "DeleteBucketWebsite", "GetBucketTagging", "PutBucketTagging", "DeleteBucketTagging", 
                    "GetBucketLifecycle", "PutBucketLifecycle", "DeleteBucketLifecycle",
                    "GetObjectTagging", "PutObjectTagging", "DeleteObjectTagging",
                    "GetObjectVersion", "ListObjectVersions", "RestoreObject"],
            "athena": ["GetQueryExecution", "StartQueryExecution", "StopQueryExecution", 
                      "GetWorkGroup", "GetDatabase", "BatchGetQueryExecution", "GetQueryResults",
                      "GetQueryResultsStream", "GetTableMetadata", "CreateWorkGroup", "DeleteWorkGroup"],
            "glue": ["GetTable", "GetDatabase", "GetPartitions", "CreateTable", "DeleteTable",
                    "UpdateTable", "CreateDatabase", "DeleteDatabase", "UpdateDatabase", "GetJob",
                    "StartJobRun", "GetJobRun", "BatchGetJobs", "GetCrawler", "StartCrawler", "GetCrawlers"],
            "kms": ["CreateGrant", "DescribeKey", "Decrypt", "Encrypt", "GenerateDataKey",
                   "DeleteAlias", "CreateKey", "ScheduleKeyDeletion", "CancelKeyDeletion", "ListKeys",
                   "ListAliases", "UpdateKeyDescription", "EnableKey", "DisableKey",
                   "ReEncrypt", "GenerateDataKeyWithoutPlaintext", "ListGrants", "RetireGrant", "RevokeGrant",
                   "CreateAlias", "PutKeyPolicy", "GetKeyPolicy", "ListResourceTags"],
            "ec2": ["DescribeInstances", "RunInstances", "TerminateInstances", "CreateSecurityGroup",
                    "DeleteSecurityGroup", "AuthorizeSecurityGroupIngress", "RevokeSecurityGroupIngress",
                    "CreateTags", "DeleteTags", "StartInstances", "StopInstances", "DescribeSecurityGroups",
                    "DescribeVolumes", "CreateVolume", "DeleteVolume", "AttachVolume", "DetachVolume",
                    "ModifyInstanceAttribute", "DescribeKeyPairs", "ImportKeyPair", "DeleteKeyPair"],
            "iam": ["CreateUser", "DeleteUser", "AttachUserPolicy", "ListUsers", "GetUser", "CreateRole",
                    "DeleteRole", "AttachRolePolicy", "ListRoles", "GetRole", "PutRolePolicy", "GetRolePolicy",
                    "CreatePolicy", "DeletePolicy", "ListPolicies", "CreateAccessKey", "DeleteAccessKey",
                    "ListAccessKeys", "UpdateAccessKey", "GetAccessKeyLastUsed",
                    "CreateLoginProfile", "DeleteLoginProfile", "UpdateLoginProfile",
                    "AddUserToGroup", "RemoveUserFromGroup", "ListGroupsForUser", "ListGroups",
                    "CreateGroup", "DeleteGroup", "GetGroup", "ListAttachedUserPolicies",
                    "ListAttachedRolePolicies", "ListAttachedGroupPolicies"],
            "lambda": ["InvokeFunction", "CreateFunction", "DeleteFunction", "UpdateFunctionCode"],
            "dynamodb": ["PutItem", "DeleteItem", "GetItem", "Scan", "Query", "CreateTable"],
            "route53": ["ChangeResourceRecordSets", "ListHostedZones", "GetHostedZone"],
            "rds": ["CreateDBInstance", "DeleteDBInstance", "DescribeDBInstances"],
            "sns": ["Publish", "Subscribe", "CreateTopic", "DeleteTopic"],
            "sqs": ["SendMessage", "ReceiveMessage", "DeleteMessage", "CreateQueue", 
                    "DeleteQueue", "GetQueueAttributes", "SetQueueAttributes",
                    "ListQueues", "PurgeQueue",
                    "ChangeMessageVisibility", "GetQueueUrl", "ListDeadLetterSourceQueues",
                    "AddPermission", "RemovePermission", "ListQueueTags", "TagQueue", "UntagQueue",
                    "SendMessageBatch", "DeleteMessageBatch", "ChangeMessageVisibilityBatch"],
            "cloudwatch": ["PutMetricData", "GetMetricData", "ListMetrics", "GetMetricStatistics", 
                           "DescribeAlarms", "PutDashboard", "GetDashboard", "DeleteDashboards"],
            "logs": ["CreateLogGroup", "CreateLogStream", "PutLogEvents", "DescribeLogStreams", 
                     "DescribeLogGroups", "GetLogEvents", "FilterLogEvents", "DeleteLogGroup", "DeleteLogStream"],
            "guardduty": ["CreateDetector", "GetDetector", "ListDetectors", "DeleteDetector",
                            "CreateIPSet", "GetIPSet", "DeleteIPSet"],
            "config": ["PutConfigRule", "GetComplianceDetailsByConfigRule", "DescribeConfigRules",
                       "DeleteConfigRule"],
            "cloudtrail": ["CreateTrail", "DeleteTrail", "GetTrailStatus", "StartLogging", "StopLogging"],
            "cloudformation": ["CreateStack", "DeleteStack", "DescribeStacks", "UpdateStack"],
            "cloudfront": ["CreateDistribution", "GetDistribution", "DeleteDistribution", "ListDistributions"],
            "cloud9": ["CreateEnvironmentEC2", "DeleteEnvironment", "DescribeEnvironments"],
            "codecommit": ["CreateRepository", "DeleteRepository", "GetRepository", "ListRepositories"],
            "codebuild": ["StartBuild", "BatchGetBuilds", "StopBuild", "ListBuilds"],
            "codepipeline": ["StartPipelineExecution", "GetPipeline", "ListPipelines"],
            "codedeploy": ["CreateDeployment", "GetDeployment", "ListDeployments"],
            "elasticbeanstalk": ["CreateApplication", "DeleteApplication", "DescribeApplications"],
            "elasticloadbalancing": ["CreateLoadBalancer", "DeleteLoadBalancer", "DescribeLoadBalancers"],
            "autoscaling": ["CreateAutoScalingGroup", "DeleteAutoScalingGroup", "DescribeAutoScalingGroups"],
            "cloudsearch": ["CreateDomain", "DeleteDomain", "DescribeDomains"],
            "es": ["CreateElasticsearchDomain", "DeleteElasticsearchDomain", "DescribeElasticsearchDomains"],
            "kinesis": ["CreateStream", "DeleteStream", "DescribeStream", "PutRecord", "GetRecords"],
            "redshift": ["CreateCluster", "DeleteCluster", "DescribeClusters"],
            "ses": ["SendEmail", "SendRawEmail", "VerifyEmailIdentity", 
                    "DeleteIdentity", "GetIdentityVerificationAttributes",
                    "ListIdentities", "SetIdentityDkimEnabled", "GetIdentityDkimAttributes"],
            "workspaces": ["CreateWorkspaces", "DeleteWorkspaces", "DescribeWorkspaces",
                          "RebootWorkspaces", "StartWorkspaces", "StopWorkspaces",
                          "ModifyWorkspaceProperties", "DescribeWorkspaceDirectories"], 
            "sagemaker": ["CreateNotebookInstance", "DeleteNotebookInstance", "DescribeNotebookInstance",
                            "StartNotebookInstance", "StopNotebookInstance", "ListNotebookInstances",
                            "CreateTrainingJob", "DescribeTrainingJob", "ListTrainingJobs",
                            "CreateModel", "DescribeModel", "ListModels",
                            "CreateEndpointConfig", "DescribeEndpointConfig", "ListEndpointConfigs",
                            "CreateEndpoint", "DescribeEndpoint", "ListEndpoints",
                            "InvokeEndpoint"]
        }
        
        # Sample principals for generation
        self.sample_principals = [
            "arn:aws:iam::123456789012:user/alice",
            "arn:aws:iam::123456789012:user/bob",
            "arn:aws:iam::123456789012:role/service-role",
            "arn:aws:iam::123456789012:role/admin-role",
            "arn:aws:iam::987654321098:user/charlie",
            "arn:aws:iam::555666777888:role/cross-account-role",
            "arn:aws:iam::111222333444:user/david",
            "arn:aws:iam::111222333444:role/developer-role",
            "arn:aws:iam::999888777666:user/unauthorized",
            "arn:aws:iam::123456789012:user/blocked-user",
            "arn:aws:iam::123456789012:user/test-user",
            "arn:aws:iam::123456789012:role/test-role",
            "arn:aws:iam::123456789012:user/temp-user"
        ]
        
        self.sample_conditions = [
            {"StringEquals": {"aws:RequestedRegion": "us-east-1"}},
            {"StringEquals": {"aws:RequestedRegion": "us-west-2"}},
            {"StringEquals": {"aws:RequestedRegion": "eu-west-1"}},
            {"IpAddress": {"aws:SourceIp": "203.0.113.0/24"}},
            {"StringLike": {"aws:userid": "AIDAI"}},
            {"Bool": {"aws:SecureTransport": "true"}},
            {"StringEquals": {"s3:ExistingObjectTag/Department": "Finance"}},
            {"NumericLessThan": {"s3:max-keys": "10"}},
        ]

    def _create_request_signature(self, request: Dict[str, Any]) -> str:
        """Create a unique signature for duplicate detection"""
        signature_parts = []
        
        # Include all relevant fields in sorted order
        for key in sorted(['Action', 'Resource', 'Principal', 'Condition', 'Effect']):
            if key in request:
                value = request[key]
                if isinstance(value, list):
                    signature_parts.append(f"{key}:{sorted(value)}")
                elif isinstance(value, dict):
                    signature_parts.append(f"{key}:{sorted(value.items())}")
                else:
                    signature_parts.append(f"{key}:{value}")
        
        signature_str = "|".join(signature_parts)
        return hashlib.md5(signature_str.encode()).hexdigest()
        
    def extract_policy_elements(self) -> Dict[str, List[str]]:
        """Extract actions, resources, and principals from the policy"""
        elements = {
            "actions": [],
            "resources": [],
            "principals": [],
            "conditions": [],
            "has_principal": False,
            "has_condition": False,
            "has_action": False,
            "has_resource": False
        }
        
        statements = self.policy.get("Statement", [])
        for statement in statements:
            # Changed: Extract from BOTH Allow and Deny statements
            if statement.get("Effect") in ["Allow", "Deny"]:
                # Check and extract actions
                if "Action" in statement:
                    elements["has_action"] = True
                    actions = statement.get("Action", [])
                    if isinstance(actions, str):
                        elements["actions"].append(actions)
                    elif isinstance(actions, list):
                        elements["actions"].extend(actions)
                
                # Check and extract resources
                if "Resource" in statement:
                    elements["has_resource"] = True
                    resources = statement.get("Resource", [])
                    if isinstance(resources, str):
                        elements["resources"].append(resources)
                    elif isinstance(resources, list):
                        elements["resources"].extend(resources)
                
                # Check and extract principals
                if "Principal" in statement:
                    elements["has_principal"] = True
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
                
                # Check and extract conditions
                if "Condition" in statement:
                    elements["has_condition"] = True
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
                    "arn:aws:s3:::admin-bucket/document.txt",
                    "arn:aws:iam::123456789012:role/admin-role",
                    "arn:aws:kms:us-east-1:123456789012:key/09348485-1234-5678-90ab-cdef12345678",
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
                    f"authorized/{resource}/file.txt"
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
                    "arn:aws:iam::123456789012:user/blocked-user",
                    "arn:aws:iam::123456789012:role/forbidden-role",
                    "arn:aws:iam::555666777888:role/cross-account-role",
                    "arn:aws:iam::111222333444:user/temp-user",
                    "arn:aws:iam::123456789012:user/test-user",
                    "arn:aws:iam::123456789012:role/test-role"
                ])
            elif "arn:aws:iam::" in principal:
                # Modify account ID or user/role name
                parts = principal.split(":")
                if len(parts) >= 6:
                    # Change account ID
                    modified_account = principal.replace(parts[4], str(random.randint(100000000000, 999999999999)))
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
    
    def generate_all_single_combinations(self, total_combinations: int, allow_ratio: float) -> List[Dict[str, Any]]:
        """Generate exactly the specified number of unique combinations using systematic enumeration"""
        
        policy_elements = self.extract_policy_elements()
        denied_actions = self.generate_denied_actions(policy_elements["actions"])
        denied_resources = self.generate_denied_resources(policy_elements["resources"])
        denied_principals = self.generate_denied_principals(policy_elements["principals"])
        denied_conditions = self.generate_denied_conditions(policy_elements["conditions"])
        
        num_allow = int(total_combinations * allow_ratio)
        num_deny = total_combinations - num_allow
        
        # Create comprehensive pools for each field
        all_allowed_actions = self._create_action_pool(policy_elements["actions"])
        all_allowed_resources = self._create_resource_pool(policy_elements["resources"])
        all_allowed_principals = self._create_principal_pool(policy_elements["principals"])
        all_allowed_conditions = self._create_condition_pool(policy_elements["conditions"])
        
        # Extend denied pools
        denied_actions.extend([f"ec2:DeniedAction{i}" for i in range(200)])
        denied_resources.extend([f"arn:aws:s3:::denied-bucket-{i}/file-{i}.txt" for i in range(200)])
        denied_principals.extend([f"arn:aws:iam::999888777666:user/denied-user-{i}" for i in range(200)])
        denied_conditions.extend([{"StringEquals": {"aws:RequestedRegion": f"denied-region-{i}"}} for i in range(200)])
        
        requests = []
        
        # Generate allow requests systematically
        allow_requests = self._generate_systematic_requests(
            "allow", num_allow, policy_elements,
            all_allowed_actions, all_allowed_resources, all_allowed_principals, all_allowed_conditions
        )
        requests.extend(allow_requests)
        
        # Generate deny requests systematically
        deny_requests = self._generate_systematic_requests(
            "deny", num_deny, policy_elements,
            denied_actions + all_allowed_actions,
            denied_resources + all_allowed_resources, 
            denied_principals + all_allowed_principals,
            denied_conditions + all_allowed_conditions
        )
        requests.extend(deny_requests)
        
        return requests
    
    def _create_action_pool(self, base_actions: List[str]) -> List[str]:
        """Create a large pool of unique actions"""
        actions = []
        for base_action in base_actions:
            if base_action.endswith("*"):
                service = base_action.split(":")[0]
                if service in self.service_actions:
                    for action in self.service_actions[service]:
                        actions.append(f"{service}:{action}")
            else:
                actions.append(base_action)
        
        # Add more actions to ensure we have enough unique ones
        for service, service_actions in self.service_actions.items():
            for action in service_actions:
                actions.append(f"{service}:{action}")
        
        return list(set(actions))
    
    def _create_resource_pool(self, base_resources: List[str]) -> List[str]:
        """Create a large pool of unique resources"""
        resources = []
        
        for base_resource in base_resources:
            if base_resource == "*":
                # Generate many unique resources
                resources.extend([f"arn:aws:s3:::bucket-{i}/file-{j}.txt" for i in range(50) for j in range(10)])
                resources.extend([f"arn:aws:athena:us-east-1:123456789012:workgroup/wg-{i}" for i in range(100)])
                resources.extend([f"arn:aws:glue:us-east-1:123456789012:table/db-{i}/table-{j}" for i in range(20) for j in range(25)])
            elif base_resource.endswith("/*"):
                base_path = base_resource[:-2]
                resources.extend([f"{base_path}/file-{i}-{j}.txt" for i in range(50) for j in range(20)])
            elif base_resource.endswith("*"):
                base_path = base_resource[:-1]
                resources.extend([f"{base_path}resource-{i}-{j}" for i in range(50) for j in range(20)])
            else:
                resources.append(base_resource)
        
        return list(set(resources))
    
    def _create_principal_pool(self, base_principals: List[str]) -> List[str]:
        """Create a large pool of unique principals"""
        principals = []
        
        for principal in base_principals:
            if principal == "*":
                principals.extend(self.sample_principals)
                principals.extend([f"arn:aws:iam::123456789012:user/user-{i}" for i in range(100)])
                principals.extend([f"arn:aws:iam::123456789012:role/role-{i}" for i in range(100)])
            else:
                principals.append(self.expand_wildcard_principal(principal))
        
        if not principals:
            principals = self.sample_principals + [f"arn:aws:iam::123456789012:user/user-{i}" for i in range(200)]
        
        return list(set(principals))
    
    def _create_condition_pool(self, base_conditions: List[Dict]) -> List[Dict]:
        """Create a large pool of unique conditions"""
        conditions = base_conditions + self.sample_conditions
        
        # Add many unique conditions
        conditions.extend([{"StringEquals": {"aws:RequestedRegion": f"region-{i}"}} for i in range(100)])
        conditions.extend([{"IpAddress": {"aws:SourceIp": f"10.{i}.0.0/24"}} for i in range(100)])
        conditions.extend([{"StringEquals": {"s3:ExistingObjectTag/Environment": f"env-{i}"}} for i in range(100)])
        conditions.extend([{"Bool": {"aws:SecureTransport": "true" if i % 2 == 0 else "false"}} for i in range(50)])
        
        return conditions
    
    def _generate_systematic_requests(self, effect: str, count: int, policy_elements: Dict,
                                    actions: List[str], resources: List[str], 
                                    principals: List[str], conditions: List[Dict]) -> List[Dict[str, Any]]:
        """Generate requests systematically to ensure uniqueness"""
        requests = []
        used_signatures = set()
        
        # Create iterators for systematic enumeration
        action_idx = 0
        resource_idx = 0 
        principal_idx = 0
        condition_idx = 0
        
        generated = 0
        max_iterations = count * 10  # Safety limit
        iteration = 0
        
        while generated < count and iteration < max_iterations:
            iteration += 1
            
            request = {
                "id": f"{effect}_{uuid.uuid4().hex[:8]}",
                "Effect": effect
            }
            
            # Systematically select values instead of random
            if policy_elements["has_action"] and actions:
                request["Action"] = actions[action_idx % len(actions)]
                action_idx += 1
            
            if policy_elements["has_resource"] and resources:
                request["Resource"] = resources[resource_idx % len(resources)]
                resource_idx += 1
            
            if policy_elements["has_principal"] and principals:
                request["Principal"] = principals[principal_idx % len(principals)]
                principal_idx += 1
            
            if policy_elements["has_condition"] and conditions:
                request["Condition"] = conditions[condition_idx % len(conditions)]
                condition_idx += 1
            
            # Check uniqueness
            signature = self._create_request_signature(request)
            if signature not in used_signatures:
                used_signatures.add(signature)
                requests.append(request)
                generated += 1
            else:
                # If we get a duplicate, advance all indices to try different combination
                action_idx += 1
                resource_idx += 2  
                principal_idx += 3
                condition_idx += 4
        
        if generated < count:
            print(f"Warning: Could only generate {generated} unique {effect} requests out of {count}")
        
        return requests
        
    def misclassify_request(self, request: Dict[str, Any], policy_elements: Dict) -> Dict[str, Any]:
        """Take a correctly classified request and modify it to be misclassified"""
        misclassified_request = request.copy()
        
        if request["Effect"] == "allow":
            # This should be allowed but we'll make it denied by using denied principal/condition
            denied_principals = self.generate_denied_principals(policy_elements["principals"])
            denied_conditions = self.generate_denied_conditions(policy_elements["conditions"])
            
            if denied_principals:
                misclassified_request["Principal"] = random.choice(denied_principals)
            if denied_conditions:
                misclassified_request["Condition"] = random.choice(denied_conditions)
                
        else:  # Effect == "deny"
            # This should be denied but we'll make it allowed by using allowed principal/condition
            if policy_elements["principals"]:
                misclassified_request["Principal"] = self.expand_wildcard_principal(random.choice(policy_elements["principals"]))
            else:
                misclassified_request["Principal"] = random.choice(self.sample_principals)
                
            if policy_elements["conditions"]:
                misclassified_request["Condition"] = random.choice(policy_elements["conditions"])
            else:
                misclassified_request["Condition"] = random.choice(self.sample_conditions)
        
        return misclassified_request
    
    def generate_all_requests(self, total_combinations: int, misclassified_percent: int = 70) -> Dict[str, Any]:
        """Generate complete set of requests with specified misclassification percentage
        
        Args:
            total_combinations: Total number of individual request combinations to generate
            misclassified_percent: Percentage of requests that should be misclassified (default 70)
        """
        try:
            policy_elements = self.extract_policy_elements()
            allow_ratio = 0.6 
            
            # Generate all requests as single combinations (1 action × 1 resource each)
            all_correct_requests = self.generate_all_single_combinations(total_combinations, allow_ratio)
            
            # Calculate how many to misclassify
            num_to_misclassify = int(len(all_correct_requests) * misclassified_percent / 100.0)
            
            # Randomly select which requests to misclassify
            requests_to_misclassify = random.sample(all_correct_requests, min(num_to_misclassify, len(all_correct_requests)))
            
            # Create the final list
            final_requests = []
            
            for request in all_correct_requests:
                if request in requests_to_misclassify:
                    # Misclassify this request
                    misclassified_request = self.misclassify_request(request, policy_elements)
                    final_requests.append(misclassified_request)
                else:
                    # Keep as correctly classified
                    final_requests.append(request)
            
            # Shuffle to mix correct and misclassified
            random.shuffle(final_requests)
            
            return {
                "Requests": final_requests
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
    import sys
    
    # Show usage if wrong number of arguments
    if len(sys.argv) != 4:
        print("IAM Policy Request Generator")
        print("\nUsage:")
        print("  python request_generator.py <policy_number> <num_requests> <misclassified_percent>")
        print("\nExamples:")
        print("  python request_generator.py 0 25 70    # Policy 0, 25 requests, 70% misclassified")
        print("  python request_generator.py 1 10 0     # Policy 1, 10 requests, 0% misclassified")
        print("  python request_generator.py 2 50 100   # Policy 2, 50 requests, 100% misclassified")
        print("\nArguments:")
        print("  policy_number       : Policy file number (reads from original_policy/{N}.json)")
        print("  num_requests        : Total number of requests to generate")
        print("  misclassified_percent: Percentage to misclassify (0-100)")
        print("\nMisclassification means:")
        print("  - Intended ALLOW requests will be DENIED")
        print("  - Intended DENY requests will be ALLOWED")
        print("\nOutput:")
        print("  - Saves to requests/request-{num_requests}/{policy_number}.json")
        print("  - Fixed 60% allow / 40% deny ratio")
        print("  - Each request includes Principal and Condition")
        print("  - No wildcards in generated requests")
        print("  - Each request has exactly 1 action × 1 resource = 1 combination")
        print("  - All requests are guaranteed unique")
        return 1
    
    # Parse command line arguments
    policy_number = sys.argv[1]
    try:
        num_requests = int(sys.argv[2])
        misclassified_percent = int(sys.argv[3])
    except ValueError:
        print("Error: num_requests and misclassified_percent must be integers")
        return 1
    
    # Validate arguments
    if num_requests <= 0:
        print("Error: num_requests must be positive")
        return 1
    
    if not 0 <= misclassified_percent <= 100:
        print("Error: misclassified_percent must be between 0 and 100")
        return 1
    
    # Set up file paths
    policy_file = f"original_policy/{policy_number}.json"
    output_file = f"requests/request-{num_requests}/{policy_number}.json"
    
    # Create requests directory if it doesn't exist
    os.makedirs(f"requests/request-{num_requests}", exist_ok=True)

    try:
        # Load policy from file
        print(f"Loading policy from: {policy_file}")
        policy = load_policy_from_file(policy_file)
        print(f"Policy loaded successfully")
        
        # Generate requests
        print(f"Generating exactly {num_requests} unique single-combination requests...")
        print(f"  Allow ratio: 60.0%")
        print(f"  Misclassified: {misclassified_percent}%")
        print(f"  Correctly classified: {100-misclassified_percent}%")
        print(f"  Each request: 1 action × 1 resource = 1 combination")
        
        generator = RequestGenerator(policy)
        test_data = generator.generate_all_requests(num_requests, misclassified_percent)
        
        if "error" in test_data:
            print(f"Error generating requests: {test_data['error']}")
            return 1
        
        # Save to output file
        save_requests_to_file(test_data, output_file)
        
        # Calculate actual combinations and classification
        requests = test_data.get("Requests", [])
        total_request_objects = len(requests)
        allow_objects = sum(1 for req in requests if req.get("Effect") == "allow")
        deny_objects = sum(1 for req in requests if req.get("Effect") == "deny")
        
        # Since each request now has exactly 1 action × 1 resource, total combinations = total requests
        total_combinations = total_request_objects
        allow_combinations = allow_objects
        deny_combinations = deny_objects
        
        print(f"\nSummary:")
        print(f"   Total request objects: {total_request_objects}")
        print(f"   Allow objects: {allow_objects}, Deny objects: {deny_objects}")
        print(f"   Total individual combinations: {total_combinations} (1:1 ratio)")
        print(f"   Allow combinations: {allow_combinations}")
        print(f"   Deny combinations: {deny_combinations}")
        if total_combinations > 0:
            print(f"   Actual allow ratio: {allow_combinations/total_combinations:.1%}")
        print(f"   Misclassified: {misclassified_percent}%")
        print(f"   Correctly classified: {100-misclassified_percent}%")
        print(f"\nFeatures:")
        print(f"   Each request includes Principal and Condition")
        print(f"   No wildcards in generated requests")
        print(f"   All IDs use standard allow_/deny_ format")
        print(f"   Each request has exactly 1 action and 1 resource")
        print(f"   All requests are guaranteed unique")
        print(f"   Saved to: {output_file}")
        
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())