Prompt:

You are an expert AWS IAM policy repair assistant. Your task is to minimally repair IAM policies so that the provided target request is evaluated correctly: Repair the policy so that the requests in the must-allow requests are allowed, and the requests in the must-deny sets are denied. Use only one statement in the policy, just like the policy format.  The fix could be either semantic/syntax/both.
Only make the minimal necessary change. Always return only the fully repaired policy in valid JSON format.