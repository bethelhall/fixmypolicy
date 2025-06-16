POLICY_NUM=$1
#GET THE SECOND ARGUMENT FROM THE COMMAND LINE
POLICY_NUM_SECOND=$2
QUACKY_SRC_DIR="/home/bhall2/Documents/fixmypolicy/quacky/src"

POLICY_FILE="/home/bhall2/Documents/fixmypolicy/FL/Dataset/llm_repaired_policies/${POLICY_NUM}.json"
REQUEST_FILE="/home/bhall2/Documents/fixmypolicy/FL/Dataset/requests/${POLICY_NUM_SECOND}.json"
QUACKY_OUTPUT_DIR="/home/bhall2/Documents/fixmypolicy/FL/Quacky_outputs"

OUTPUT_FILE_PATH="${QUACKY_OUTPUT_DIR}/${POLICY_NUM_SECOND}llm.txt"

cd "$QUACKY_SRC_DIR" || { echo "Error: Could not change to $QUACKY_SRC_DIR"; exit 1; }

python3 validate_requests.py -p1 "$POLICY_FILE" --requests "$REQUEST_FILE" -s > "$OUTPUT_FILE_PATH"
echo "Output saved to $OUTPUT_FILE_PATH".
