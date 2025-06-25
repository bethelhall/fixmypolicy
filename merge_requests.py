import json
import os
import uuid
from pathlib import Path

def merge_request_files():
    """Merge every 5 request files into one, with proper allow/deny IDs"""
    
    # Define the available file numbers (excluding the skipped ones)
    skip_files = {15, 25, 45, 55, 65, 75, 85, 95}
    available_files = [i for i in range(100) if i not in skip_files]
    
    # Input and output directories
    input_dir = Path("/home/bhall2/Documents/fixmypolicy/FL/Dataset/requests/version2")
    output_dir = Path.home() / "merged_requests"
    output_dir.mkdir(exist_ok=True)
    
    # Group files into sets of 5
    file_groups = []
    for i in range(0, len(available_files), 5):
        group = available_files[i:i+5]
        if len(group) == 5:  # Only process complete groups of 5
            file_groups.append(group)
    
    print(f"Found {len(file_groups)} complete groups of 5 files")
    
    # Process each group
    for group_idx, file_numbers in enumerate(file_groups):
        print(f"\nProcessing group {group_idx + 1}: files {file_numbers}")
        
        merged_requests = []
        
        for req_idx, file_num in enumerate(file_numbers):
            input_file = input_dir / f"{file_num:02d}.json"
            
            try:
                with open(input_file, 'r') as f:
                    data = json.load(f)
                
                # Get the first request from this file
                requests = data.get("Requests", [])
                if requests:
                    original_request = requests[0].copy()
                    
                    # Assign new ID based on position in group
                    if req_idx < 3:  # First 3 are "allow"
                        new_id = f"allow_{uuid.uuid4().hex[:8]}"
                        original_request["Effect"] = "allow"
                    else:  # Last 2 are "deny"  
                        new_id = f"deny_{uuid.uuid4().hex[:8]}"
                        original_request["Effect"] = "deny"
                    
                    original_request["id"] = new_id
                    merged_requests.append(original_request)
                    
                    print(f"  Added {input_file.name} as {new_id} with effect '{original_request['Effect']}'")
                else:
                    print(f"  WARNING: No requests found in {input_file.name}")
                    
            except FileNotFoundError:
                print(f"  ERROR: File not found: {input_file}")
            except json.JSONDecodeError:
                print(f"  ERROR: Invalid JSON in {input_file}")
            except Exception as e:
                print(f"  ERROR processing {input_file}: {e}")
        
        # Save merged file
        if merged_requests:
            output_file = output_dir / f"merged_group_{group_idx + 1:02d}.json"
            
            merged_data = {
                "Requests": merged_requests
            }
            
            with open(output_file, 'w') as f:
                json.dump(merged_data, f, indent=2)
            
            print(f"  Saved merged file: {output_file}")
            print(f"  Total requests in merged file: {len(merged_requests)}")
        else:
            print(f"  WARNING: No valid requests found for group {group_idx + 1}")
    
    print(f"\nMerging complete! Output files saved to: {output_dir}")
    return output_dir

def list_available_files():
    """List all available request files to verify"""
    input_dir = Path("/home/bhall2/Documents/fixmypolicy/FL/Dataset/requests/version2")
    skip_files = {15, 25, 45, 55, 65, 75, 85, 95} # these files are non-existent
    
    print("Available request files:")
    available = []
    for i in range(100):
        if i not in skip_files:
            file_path = input_dir / f"{i:02d}.json"
            if file_path.exists():
                available.append(i)
                print(f"  {i:02d}.json ✓")
            else:
                print(f"  {i:02d}.json ✗ (missing)")
    
    print(f"\nTotal available files: {len(available)}")
    print(f"Groups of 5 possible: {len(available) // 5}")
    return available

if __name__ == "__main__":
    print("="*50)
    print("REQUEST FILE MERGER")
    print("="*50)
    
    # First, list available files
    available = list_available_files()
    
    print("\n" + "="*50)
    
    # Proceed with merging
    if len(available) >= 5:
        output_dir = merge_request_files()
        
        print(f"\n" + "="*50)
        print("SUMMARY")
        print("="*50)
        print(f"Merged files saved to: {output_dir}")
        print("Each merged file contains:")
        print("  - 5 requests total")
        print("  - First 3 requests: Effect='allow', ID starts with 'allow_'")
        print("  - Last 2 requests: Effect='deny', ID starts with 'deny_'")
    else:
        print("ERROR: Not enough files available for merging")