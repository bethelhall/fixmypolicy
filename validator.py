from frontend import validate_args
from translator import call_translator
from utilities import bit_string
from re2smt.re2smt import re2smt
from z3 import Solver, sat
import argparse as ap
import json
import csv
import os
from pathlib import Path


def validate_requests(args):
    # 1) Translate policy into SMT constraints
    call_translator(args)
    smt_file = f"{args.output}_1.smt2"
    base_smt = []
    with open(smt_file) as f:
        for line in f:
            if line.strip() not in ("(check-sat)", "(get-model)"):
                base_smt.append(line)
    base_smt = ''.join(base_smt)

    # 2) Load requests
    if not args.requests:
        print("Error: No requests given to validate")
        return
    with open(args.requests) as f:
        data = json.load(f)

    all_individual_results = []
    
    for req in data.get("Requests", []):
        req_id = req.get("id", "unknown")
        print(f"Processing request object: {req_id}")
        
        actions    = req.get("Action")
        resources  = req.get("Resource")
        effect    = req.get("Effect").lower()
        principals = req.get("Principal")
        condition  = req.get("Condition")

        actions   = actions if isinstance(actions, list) else [actions]
        resources = resources if isinstance(resources, list) else [resources]
        principals = principals if isinstance(principals, list) else ([principals] if principals else [None])

        # Generate all combinations for this request object
        combination_id = 1
        for action in actions:
            for resource in resources:
                for principal in principals:
                    # Create individual request ID
                    individual_req_id = f"{req_id}_combo_{combination_id}"
                    combination_id += 1
                    
                    print(f"  Validating individual request: {individual_req_id}")
                    print(f"    Action: {action}, Resource: {resource}, Principal: {principal}")
                    
                    solver = Solver()
                    smt_parts = [base_smt]

                    # assert action & resource
                    a = (action.lower())
                    r = (resource)
                    smt_parts.append(f'(assert (= action "{a}"))\n')
                    smt_parts.append(f'(assert (= resource "{r}"))\n')

                    # assert principal
                    if principal:
                        smt_parts.append(f'(assert (= principal "{principal}"))\n')

                    # assert conditions
                    if condition:
                        for key, val in condition.items():
                            k = key.replace(':', '.')
                            vals = val if isinstance(val, list) else [val]
                            clauses = []
                            for v in vals:
                                if isinstance(v, int):
                                    clauses.append(f"(= {k} {v})")
                                elif isinstance(v, str) and "Ip" not in key:
                                    ev = v
                                    clauses.append(f'(= {k} "{ev}")')
                                elif isinstance(v, str):
                                    addr, pref = bit_string(v)
                                    re_expr = re2smt(addr[:pref])
                                    clauses.append(f"(str.in.re {k} {re_expr})")
                            if clauses:
                                if len(clauses) > 1:
                                    smt_parts.append(f"(assert (or {' '.join(clauses)}))\n")
                                else:
                                    smt_parts.append(f"(assert {clauses[0]})\n")

                    smt_parts.append("(check-sat)")
                    full_smt = ''.join(smt_parts).replace('\x00', '\x01')

                    try:
                        solver.from_string(full_smt)
                        solver_result = solver.check()
                        print(f"    Solver result: {solver_result}")                    
                        
                        # Determine actual result
                        actual_result = 'allow' if solver_result == sat else 'deny'
                        
                        # Check if the result matches expectation
                        is_correct = ((solver_result == sat and effect == 'allow') or 
                                    (solver_result != sat and effect == 'deny'))
                        
                        # Store individual result
                        individual_result = {
                            'request_object_id': req_id,
                            'individual_request_id': individual_req_id,
                            'action': action,
                            'resource': resource,
                            'principal': principal if principal else 'None',
                            'condition': str(condition) if condition else 'None',
                            'expected_effect': effect,
                            'actual_result': actual_result,
                            'solver_result': str(solver_result),
                            'is_correct': is_correct
                        }
                        
                        all_individual_results.append(individual_result)
                        
                        status = "✓ CORRECT" if is_correct else "✗ INCORRECT"
                        print(f"    {status}: Expected={effect}, Got={actual_result}")
                        
                    except Exception as e:
                        print(f"    Exception during solving: {e}")
                        individual_result = {
                            'request_object_id': req_id,
                            'individual_request_id': individual_req_id,
                            'action': action,
                            'resource': resource,
                            'principal': principal if principal else 'None',
                            'condition': str(condition) if condition else 'None',
                            'expected_effect': effect,
                            'actual_result': 'error',
                            'solver_result': 'error',
                            'is_correct': False
                        }
                        all_individual_results.append(individual_result)

    # Analyze and save results
    summary_stats = analyze_individual_results(all_individual_results)
    save_individual_results_to_csv(all_individual_results, summary_stats, args)
    
    return all_individual_results


def analyze_individual_results(all_results):
    """Analyze individual request results"""
    total_individual_requests = len(all_results)
    correct_count = sum(1 for r in all_results if r['is_correct'])
    incorrect_count = total_individual_requests - correct_count
    
    # Count by expected vs actual
    correct_allow = sum(1 for r in all_results if r['expected_effect'] == 'allow' and r['actual_result'] == 'allow')
    correct_deny = sum(1 for r in all_results if r['expected_effect'] == 'deny' and r['actual_result'] == 'deny')
    misclassified_allow_to_deny = sum(1 for r in all_results if r['expected_effect'] == 'allow' and r['actual_result'] == 'deny')
    misclassified_deny_to_allow = sum(1 for r in all_results if r['expected_effect'] == 'deny' and r['actual_result'] == 'allow')
    errors = sum(1 for r in all_results if r['actual_result'] == 'error')
    
    # Count by request object ID prefix
    allow_prefix_correct = 0
    allow_prefix_incorrect = 0
    deny_prefix_correct = 0
    deny_prefix_incorrect = 0
    
    for r in all_results:
        req_obj_id = r['request_object_id']
        if req_obj_id.startswith('allow_'):
            if r['actual_result'] == 'allow':
                allow_prefix_correct += 1
            else:
                allow_prefix_incorrect += 1
        elif req_obj_id.startswith('deny_'):
            if r['actual_result'] == 'deny':
                deny_prefix_correct += 1
            else:
                deny_prefix_incorrect += 1
    
    accuracy = (correct_count / total_individual_requests * 100) if total_individual_requests > 0 else 0
    
    print("\n" + "="*60)
    print("INDIVIDUAL REQUEST ANALYSIS")
    print("="*60)
    print(f"Total Individual Requests: {total_individual_requests}")
    print(f"Correct Classifications: {correct_count}")
    print(f"Incorrect Classifications: {incorrect_count}")
    print(f"Errors: {errors}")
    print(f"Overall Accuracy: {accuracy:.1f}%")
    print()
    print("Expected vs Actual:")
    print(f"  Expected Allow → Got Allow: {correct_allow}")
    print(f"  Expected Allow → Got Deny: {misclassified_allow_to_deny}")
    print(f"  Expected Deny → Got Deny: {correct_deny}")
    print(f"  Expected Deny → Got Allow: {misclassified_deny_to_allow}")
    print()
    print("By Request Object ID Prefix:")
    print(f"  'allow_' prefix → Correctly Allowed: {allow_prefix_correct}")
    print(f"  'allow_' prefix → Incorrectly Denied: {allow_prefix_incorrect}")
    print(f"  'deny_' prefix → Correctly Denied: {deny_prefix_correct}")
    print(f"  'deny_' prefix → Incorrectly Allowed: {deny_prefix_incorrect}")
    print("="*60)
    
    return {
        'total_individual_requests': total_individual_requests,
        'correct_count': correct_count,
        'incorrect_count': incorrect_count,
        'errors': errors,
        'accuracy': accuracy,
        'correct_allow': correct_allow,
        'correct_deny': correct_deny,
        'misclassified_allow_to_deny': misclassified_allow_to_deny,
        'misclassified_deny_to_allow': misclassified_deny_to_allow,
        'allow_prefix_correct': allow_prefix_correct,
        'allow_prefix_incorrect': allow_prefix_incorrect,
        'deny_prefix_correct': deny_prefix_correct,
        'deny_prefix_incorrect': deny_prefix_incorrect
    }


def save_individual_results_to_csv(all_results, summary_stats, args):
    """Save individual results to CSV files in home directory"""
    
    # Get home directory
    home_dir = "/home/bhall2/Documents/fixmypolicy/FL/Quacky_outputs/"
    home_dir = Path(home_dir)
    if not home_dir.exists():
        print(f"Error: Home directory {home_dir} does not exist.")
        return
    
    # Create filename based on output argument or default
    base_filename = os.path.basename(args.output) if args.output else "policy_validation"
    
    # Save detailed individual results to home directory
    detailed_csv_path = home_dir / f"{base_filename}_individual_results.csv"
    with open(detailed_csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['request_object_id', 'individual_request_id', 'action', 'resource', 
                     'principal', 'condition', 'expected_effect', 'actual_result', 
                     'solver_result', 'is_correct']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for result in all_results:
            writer.writerow(result)
    
    # Save summary statistics to home directory
    summary_csv_path = home_dir / f"{base_filename}_individual_summary.csv"
    with open(summary_csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Metric', 'Value'])
        writer.writerow(['Total Individual Requests', summary_stats['total_individual_requests']])
        writer.writerow(['Correct Classifications', summary_stats['correct_count']])
        writer.writerow(['Incorrect Classifications', summary_stats['incorrect_count']])
        writer.writerow(['Errors', summary_stats['errors']])
        writer.writerow(['Accuracy (%)', f"{summary_stats['accuracy']:.1f}"])
        writer.writerow(['', ''])  # Empty row
        writer.writerow(['Expected vs Actual', ''])
        writer.writerow(['Expected Allow → Got Allow', summary_stats['correct_allow']])
        writer.writerow(['Expected Allow → Got Deny', summary_stats['misclassified_allow_to_deny']])
        writer.writerow(['Expected Deny → Got Deny', summary_stats['correct_deny']])
        writer.writerow(['Expected Deny → Got Allow', summary_stats['misclassified_deny_to_allow']])
        writer.writerow(['', ''])  # Empty row
        writer.writerow(['By Request Object ID Prefix', ''])
        writer.writerow(['allow_ prefix → Correctly Allowed', summary_stats['allow_prefix_correct']])
        writer.writerow(['allow_ prefix → Incorrectly Denied', summary_stats['allow_prefix_incorrect']])
        writer.writerow(['deny_ prefix → Correctly Denied', summary_stats['deny_prefix_correct']])
        writer.writerow(['deny_ prefix → Incorrectly Allowed', summary_stats['deny_prefix_incorrect']])
    
    print(f"\nResults saved to HOME directory:")
    print(f"  Individual results: {detailed_csv_path}")
    print(f"  Summary statistics: {summary_csv_path}")


if __name__ == '__main__':
    parser = ap.ArgumentParser(description = 'Validate requests against AWS policy using SMT formulas')
    parser.add_argument('-p1' , '--policy1'         , help = 'policy 1 (AWS)'               , required = False)
    parser.add_argument('-p2' , '--policy2'         , help = 'policy 2 (AWS)'               , required = False)
    parser.add_argument('-rd' , '--role-definitions', help = 'role definitions (Azure)'     , required = False)
    parser.add_argument('-ra1', '--role-assignment1', help = 'role assignment 1 (Azure)'    , required = False)
    parser.add_argument('-ra2', '--role-assignment2', help = 'role assignment 2 (Azure)'    , required = False)
    parser.add_argument('-r'  , '--roles'           , help = 'roles (GCP)'                  , required = False)
    parser.add_argument('-rb1', '--role-binding1'   , help = 'role binding 1 (GCP)'         , required = False)
    parser.add_argument('-rb2', '--role-binding2'   , help = 'role binding 2 (GCP)'         , required = False)
    # parser.add_argument('-d'  , '--domain'          , help = 'domain file (not supported)'  , required = False)
    parser.add_argument('-o'  , '--output'          , help = 'output file'                  , required = False, default='output')
    parser.add_argument('-s'  , '--smt-lib'         , help = 'use SMT-LIB syntax'           , required = False, action = 'store_true')
    parser.add_argument('-e'  , '--enc'             , help = 'use action encoding'          , required = False, action = 'store_true')
    parser.add_argument('-c'  , '--constraints'     , help = 'use resource type constraints', required = False, action = 'store_true')
    parser.add_argument('-rq' , '--requests'        , help = 'check if requests in a json-formatted list are accepted by the policy', required = False)

    args = parser.parse_args()

    call_translator(args)
    validate_requests(args)