import json
import random
import pandas as pd

def generate_labeled_requests(policy_json, num_allow=3, num_deny=2):
    policy = json.loads(policy_json)
    statements = policy.get("Statement", [])
    requests = []

    # Helper functions to extract and normalize values
    def get_action(stmt):
        action = stmt.get("Action", "s3:getobject")
        return random.choice(action) if isinstance(action, list) else action

    def get_resource(stmt):
        resource = stmt.get("Resource", "arn:aws:s3:::example-bucket/my-object")
        if "*" in resource:
            return resource.replace("*", f"object-{random.randint(1, 100)}")
        return resource

    def get_principal(stmt):
        principal = stmt.get("Principal", "arn:aws:iam::123456789:user/example-user")
        if isinstance(principal, dict):
            return list(principal.values())[0]
        return principal

    def get_condition(stmt):
        cond_block = stmt.get("Condition", {})
        flattened = {}
        for operator, conds in cond_block.items():
            for key, val in conds.items():
                flattened[key] = (val + 1) if isinstance(val, (int, float)) else val
        return flattened or {"s3:MaxKeys": 101}

    # Generate allowed requests
    for _ in range(num_allow):
        stmt = random.choice(statements)
        requests.append({
            "Effect": "allow",
            "Principal": get_principal(stmt),
            "Action": get_action(stmt),
            "Resource": get_resource(stmt),
            "Condition": get_condition(stmt),
            "ExpectedDecision": "Allow"
        })

    # Generate denied (misclassified) requests
    for _ in range(num_deny):
        stmt = random.choice(statements)
        action = get_action(stmt)
        resource = get_resource(stmt)
        # Randomly perturb action or resource
        if random.random() < 0.5:
            action = action + ".Invalid"
        else:
            resource = "arn:aws:s3:::invalid-bucket/unknown-object"
        requests.append({
            "Effect": "allow",
            "Principal": get_principal(stmt),
            "Action": action,
            "Resource": resource,
            "Condition": get_condition(stmt),
            "ExpectedDecision": "Deny"
        })

    random.shuffle(requests)
    return {"Requests": requests}

def initailize_request():
    """
    Initialize the request generation process.
    This function can be expanded to include more complex initialization logic if needed.
    """
    print("Request generation initialized.")
# Example policy
policy_input = '''
{
    "Statement": [
        {
            "Action": ["s3:GetObject", "s3:ListBucket"],
            "Effect": "Allow",
            "Principal": "arn:aws:iam::123456789:user/alice",
            "Resource": "arn:aws:s3:::my-bucket/*",
            "Condition": {
                "NumericLessThanEquals": {
                    "s3:MaxKeys": 100
                }
            }
        }
    ]
}
'''

generated = generate_labeled_requests(policy_input)
print("Generated Requests:")
df = pd.DataFrame(generated["Requests"])
print(df.to_string(index=False))
print("\nTotal Requests Generated:", len(generated["Requests"]))
# The code generates labeled requests based on a given IAM policy JSON.
