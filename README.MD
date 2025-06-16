# 📅 Daily Planner

## Day: Monday, YYYY-MM-DD

### 🔨 Tasks

- [ ] Task 1
- [ ] Task 2
- [ ] Task 3

### 📝 Notes

- Note 1
- Note 2

### 🚩 Blockers

- 
- 

### 🔍 Reflections

- What went well:
- What can be improved:

---

## Day: Tuesday, YYYY-MM-DD

### 🔨 Tasks

- [task1] Policy acquisition [40 done]
- [task2] Project setup, installation [done]
- [task3] Request creation [in progress]

### Done
- [ ] Policy acquisition
- [ ] Project setup, installation
- [ ] Request creation

### 📝 Notes

- Note 1
- Note 2

### 🚩 Blockers

- Blocker 1
- Blocker 2

### 🔍 Reflections

- What went well:
- What can be improved:

---

Prompt:

You are an expert AWS IAM policy repair assistant. Your task is to minimally repair IAM policies so that the provided target request is evaluated correctly: Repair the policy so that the requests in the must-allow requests are allowed, and the requests in the must-deny sets are denied. Use only one statement in the policy, just like the policy format.  The fix could be either semantic/syntax/both.
Only make the minimal necessary change. Always return only the fully repaired policy in valid JSON format.