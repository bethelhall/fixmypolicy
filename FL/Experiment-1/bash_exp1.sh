#!/bin/bash

# run_iterative_repair.sh
# 
# This script runs the iterative policy repair system with proper environment setup
# and dependency checking.

set -e  # Exit on any error

# Configuration with specific paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="iterative_policy_repair.py"
QUACKY_SRC_DIR="/home/bhall2/Documents/fixmypolicy/quacky/src"
VALIDATOR_SCRIPT="${QUACKY_SRC_DIR}/validate_requests.py"
BASE_EXPERIMENT_DIR="/home/bhall2/Documents/fixmypolicy/FL/Experiment-1"
POLICY_DIR="${BASE_EXPERIMENT_DIR}/original_policy"
REQUESTS_DIR="${BASE_EXPERIMENT_DIR}/requests/request-80"
RESULTS_DIR="${BASE_EXPERIMENT_DIR}/results/result-80"
LOGS_DIR="${BASE_EXPERIMENT_DIR}/logs/log-80"
TEMP_DIR="${BASE_EXPERIMENT_DIR}/temp_validation/val-80"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check Python version
check_python_version() {
    if command_exists python3; then
        python_version=$(python3 -c "import sys; print('.'.join(map(str, sys.version_info[:2])))")
        print_status "Python version: $python_version"
        
        # Check if version is >= 3.7
        if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 7) else 1)"; then
            return 0
        else
            print_error "Python 3.7+ is required. Current version: $python_version"
            return 1
        fi
    else
        print_error "Python 3 is not installed or not in PATH"
        return 1
    fi
}

# Function to check required files
check_required_files() {
    local missing_files=()
    
    # Check main script
    if [ ! -f "$PYTHON_SCRIPT" ]; then
        missing_files+=("$PYTHON_SCRIPT")
    fi
    
    # Check validator script
    if [ ! -f "$VALIDATOR_SCRIPT" ]; then
        missing_files+=("$VALIDATOR_SCRIPT")
    fi
    
    # Check required directories
    local required_dirs=("$POLICY_DIR" "$REQUESTS_DIR")
    for dir in "${required_dirs[@]}"; do
        if [ ! -d "$dir" ]; then
            missing_files+=("$dir/ (directory)")
        fi
    done
    
    # Check Quacky source directory
    if [ ! -d "$QUACKY_SRC_DIR" ]; then
        missing_files+=("$QUACKY_SRC_DIR/ (Quacky source directory)")
    fi
    
    if [ ${#missing_files[@]} -gt 0 ]; then
        print_error "Missing required files/directories:"
        for file in "${missing_files[@]}"; do
            echo "  - $file"
        done
        return 1
    fi
    
    return 0
}

# Function to check Python dependencies
check_python_dependencies() {
    print_status "Checking Python dependencies..."
    
    local required_packages=("anthropic" "pandas" "tqdm")
    local missing_packages=()
    
    for package in "${required_packages[@]}"; do
        if ! python3 -c "import ${package//-/_}" 2>/dev/null; then
            missing_packages+=("$package")
        fi
    done
    
    if [ ${#missing_packages[@]} -gt 0 ]; then
        print_warning "Missing Python packages: ${missing_packages[*]}"
        print_status "You can install them with: pip3 install ${missing_packages[*]}"
        print_warning "Continuing anyway - the script will fail if dependencies are missing"
    else
        print_success "All Python dependencies are available"
    fi
    
    return 0
}

# Function to create required directories
create_directories() {
    local dirs=("$RESULTS_DIR" "$LOGS_DIR" "${BASE_EXPERIMENT_DIR}/temp_validation" "${RESULTS_DIR}/Quacky_output")
    
    for dir in "${dirs[@]}"; do
        if [ ! -d "$dir" ]; then
            mkdir -p "$dir"
            print_status "Created directory: $dir"
        fi
    done
}

# Function to validate policy and request files
validate_input_files() {
    print_status "Validating input files..."
    
    local policy_count=0
    local request_count=0
    
    # Count policy files
    for i in {0..9}; do
        if [ -f "$POLICY_DIR/$i.json" ]; then
            ((policy_count++))
        fi
    done
    
    # Count request files
    for i in {0..9}; do
        if [ -f "$REQUESTS_DIR/$i.json" ]; then
            ((request_count++))
        fi
    done
    
    print_status "Found $policy_count policy files and $request_count request files"
    
    if [ $policy_count -eq 0 ] || [ $request_count -eq 0 ]; then
        print_error "No policy or request files found. Please ensure files are named 0.json through 9.json"
        return 1
    fi
    
    # Validate JSON format for existing files
    local invalid_files=()
    
    for i in {0..9}; do
        if [ -f "$POLICY_DIR/$i.json" ]; then
            if ! python3 -c "import json; json.load(open('$POLICY_DIR/$i.json'))" 2>/dev/null; then
                invalid_files+=("$POLICY_DIR/$i.json")
            fi
        fi
        
        if [ -f "$REQUESTS_DIR/$i.json" ]; then
            if ! python3 -c "import json; json.load(open('$REQUESTS_DIR/$i.json'))" 2>/dev/null; then
                invalid_files+=("$REQUESTS_DIR/$i.json")
            fi
        fi
    done
    
    if [ ${#invalid_files[@]} -gt 0 ]; then
        print_error "Invalid JSON files found:"
        for file in "${invalid_files[@]}"; do
            echo "  - $file"
        done
        return 1
    fi
    
    print_success "All input files are valid"
    return 0
}

# Function to check API key
check_api_key() {
    if ! grep -q "sk-ant-api03-" "$PYTHON_SCRIPT" 2>/dev/null; then
        print_warning "API key not found in script. Please ensure your Anthropic API key is set in $PYTHON_SCRIPT"
        print_warning "Or set it as an environment variable: export ANTHROPIC_API_KEY='your-key-here'"
    fi
}

# Function to run pre-flight checks
run_preflight_checks() {
    print_status "Running checks..."
    
    # Check Python
    if ! check_python_version; then
        return 1
    fi
    
    # Check required files
    if ! check_required_files; then
        return 1
    fi
    
    # Check dependencies
    if ! check_python_dependencies; then
        return 1
    fi
    
    # Create directories
    create_directories
    
    # Validate input files
    if ! validate_input_files; then
        return 1
    fi
    
    # Check API key
    check_api_key
    
    print_success "All pre-flight checks passed!"
    return 0
}

# Function to show progress monitoring tip
show_monitoring_tip() {
    echo
    print_status "Progress Monitoring Tips:"
    echo "  - Logs are saved in $LOGS_DIR directory"
    echo "  - Progress is tracked in $RESULTS_DIR/iterative_progress.json"
    echo "  - Results will be saved in $RESULTS_DIR directory"
    echo "  - You can resume if interrupted (progress is automatically saved)"
    echo "  - Each policy attempts up to 5 iterations to reach 100% accuracy"
    echo
}

# Function to show estimated time
show_time_estimate() {
    print_status "Time Estimates:"
    echo "  - Each iteration: ~30-60 seconds (LLM + SMT validation)"
    echo "  - Per policy: 1-5 iterations (up to 5 minutes per policy)"
    echo "  - Total estimated time: 10-50 minutes for 10 policies"
    echo "  - Progress will be shown with a progress bar"
    echo
}

# Function to clean up previous runs (optional)
cleanup_previous_runs() {
    if [ "$1" = "--clean" ]; then
        print_status "Cleaning up previous runs..."
        rm -rf "${RESULTS_DIR}/iterative_progress.json"
        rm -rf "${BASE_EXPERIMENT_DIR}/temp_validation/"
        rm -rf "${RESULTS_DIR}/repaired_*.json"
        rm -rf "${RESULTS_DIR}/iterative_repair_*.csv"
        print_status "Cleanup completed"
    fi
}

# Main function
main() {
    echo "=================================================="
    echo "    Iterative Policy Repair System"
    echo "=================================================="
    echo
    
    # Handle cleanup flag
    cleanup_previous_runs "$1"
    
    # Run pre-flight checks
    if ! run_preflight_checks; then
        print_error "Pre-flight checks failed. Please fix the issues above and try again."
        exit 1
    fi
    
    # Show monitoring and time information
    show_monitoring_tip
    show_time_estimate
    
    # Confirm before starting
    if [ "$1" != "--auto" ]; then
        echo -n "Ready to start iterative policy repair? (y/N): "
        read -r response
        if [[ ! "$response" =~ ^[Yy]$ ]]; then
            print_status "Operation cancelled by user"
            exit 0
        fi
    fi
    
    # Start the main process
    print_status "Starting iterative policy repair system..."
    print_status "Using paths:"
    echo "  - Policy directory: $POLICY_DIR"
    echo "  - Requests directory: $REQUESTS_DIR"
    echo "  - Results directory: $RESULTS_DIR"
    echo "  - Quacky source: $QUACKY_SRC_DIR"
    echo "  - Validator script: $VALIDATOR_SCRIPT"
    echo "  - Quacky output: ${RESULTS_DIR}/Quacky_output"
    echo "=================================================="
    
    # Run the Python script
    if python3 "$PYTHON_SCRIPT"; then
        echo
        echo "=================================================="
        print_success "Iterative policy repair completed successfully!"
        
        # Show results summary
        print_status "Results saved in $RESULTS_DIR:"
        echo "  - iterative_repair_summary_*.csv (high-level results)"
        echo "  - iterative_repair_details_*.csv (iteration-by-iteration details)"
        echo "  - repaired_*_final.json (successfully repaired policies)"
        echo "  - repaired_*_best.json (best attempts for failed policies)"
        
        echo
        print_status "Check $LOGS_DIR for detailed execution logs"
        
    else
        echo
        print_error "Iterative policy repair failed!"
        print_status "Check the logs in $LOGS_DIR for detailed error information"
        exit 1
    fi
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Options:"
    echo "  --clean    Clean up previous runs before starting"
    echo "  --auto     Run without user confirmation"
    echo "  --help     Show this help message"
    echo
    echo "Examples:"
    echo "  $0                    # Run with confirmation"
    echo "  $0 --auto            # Run automatically"
    echo "  $0 --clean --auto    # Clean and run automatically"
    echo
    echo "Required Python packages: anthropic, pandas, tqdm"
    echo "Install with: pip3 install anthropic pandas tqdm"
}

# Handle command line arguments
case "$1" in
    --help|-h)
        show_usage
        exit 0
        ;;
    *)
        main "$@"
        ;;
esac