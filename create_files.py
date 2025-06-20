import os

directory = "./FL/Dataset/llm_repaired_policies_v2"

# def create_directory(directory):
#     os.makedirs(directory, exist_ok=True)

#     if not os.path.exists(directory):
#         os.makedirs(directory)
#         print(f"Created directory: {directory}")
#     for i in range(0, 10):
#         for j in range(0, 6):
#                 filename = f"{i}{j}.json"
#                 filepath = os.path.join(directory, filename)
#                 with open(filepath, 'w') as file:
#                     file.write('')
#                 print(f"Created empty file: {filepath}")
#         else:
#             print(f"Directory already exists: {directory}")
#     # Create the directory and files
#     print("Directory and files created successfully.")

def create_files():
    os.makedirs(directory, exist_ok=True)

    if not os.path.exists(directory):
        os.makedirs(directory)
        print(f"Created directory: {directory}")
    for i in range(1, 9):
        filename = f"{i}.json"
        filepath = os.path.join(directory, filename)
        with open(filepath, 'w') as file:
            file.write('')
        print(f"Created empty file: {filepath}")

if __name__ == "__main__":
   create_files()
