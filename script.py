import os

directory = "./Dataset/faulty_policy"

for i in range(41, 100):
    filename = f"{i}.json"
    filepath = os.path.join(directory, filename)
    with open(filepath, "w") as file:
        file.write("")
        
print(f"Created empty file: {filepath}")
# This script creates empty JSON files numbered from 18 to 40 in the specified directory.
# The files are named "18.json", "19.json", ..., "40.json".
# The directory is "./Dataset/faulty_policy", and the script uses a loop to create each file.
    
    
if __name__ == "__main__":
    print("Empty JSON files created successfully.")