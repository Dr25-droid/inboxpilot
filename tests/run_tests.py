#!/usr/bin/env python
import os
import subprocess
import sys
import argparse
from pathlib import Path

def main():
    langsmith_project = "InboxPilot: Response Evaluation"

    parser = argparse.ArgumentParser(description="Run tests for InboxPilot")
    parser.add_argument("--experiment-name", help="Name for the LangSmith experiment")
    parser.add_argument("--implementation", help="Run tests for a specific implementation")
    parser.add_argument("--all", action="store_true", help="Run tests for all implementations")
    args = parser.parse_args()

    base_pytest_options = ["-v", "--disable-warnings", "--langsmith-output"]

    # Only pilot_simple supports automated testing (no interrupt handling needed)
    implementations = ["pilot_simple"]

    if args.implementation:
        if args.implementation in implementations:
            implementations_to_test = [args.implementation]
        else:
            print(f"Error: Unknown implementation '{args.implementation}'")
            print(f"Available implementations: {', '.join(implementations)}")
            return 1
    elif args.all:
        implementations_to_test = implementations
    else:
        implementations_to_test = implementations

    for implementation in implementations_to_test:
        print(f"\nRunning tests for {implementation}...")

        os.environ["LANGSMITH_PROJECT"] = langsmith_project
        os.environ["LANGSMITH_TEST_SUITE"] = langsmith_project
        os.environ["LANGCHAIN_TRACING_V2"] = "true"

        pytest_options = base_pytest_options.copy()
        pytest_options.append(f"--agent-module={implementation}")

        test_files = ["test_response.py"]

        print(f"   Project: {langsmith_project}")
        print(f"\nTest results for {implementation} are being logged to LangSmith")
        for test_file in test_files:
            print(f"\nRunning {test_file} for {implementation}...")
            experiment_name = f"Test: {test_file.split('/')[-1]} | Agent: {implementation}"
            print(f"   Experiment: {experiment_name}")
            os.environ["LANGSMITH_EXPERIMENT"] = experiment_name

            cmd = ["python", "-m", "pytest", test_file] + pytest_options

            script_dir = Path(__file__).parent
            cwd = os.getcwd()
            os.chdir(script_dir)
            result = subprocess.run(cmd, capture_output=True, text=True)
            os.chdir(cwd)

            print(result.stdout)
            if result.stderr:
                print(result.stderr)

if __name__ == "__main__":
    sys.exit(main() or 0)
