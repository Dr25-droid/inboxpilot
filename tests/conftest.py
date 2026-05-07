#!/usr/bin/env python

import pytest
import sys
from pathlib import Path

project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

def pytest_addoption(parser):
    """Add command-line options to pytest."""
    parser.addoption(
        "--agent-module",
        action="store",
        default="pilot",
        help="Specify which InboxPilot module to test (pilot, pilot_simple, pilot_review)"
    )

@pytest.fixture(scope="session")
def agent_module_name(request):
    """Return the agent module name from command line."""
    return request.config.getoption("--agent-module")
