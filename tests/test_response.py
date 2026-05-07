#!/usr/bin/env python

import uuid
import importlib
import sys
import pytest
from typing import Dict, List, Any, Tuple
from pydantic import BaseModel, Field
from langchain.chat_models import init_chat_model

from langsmith import testing as t

from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from inboxpilot.utils import extract_tool_calls, format_messages_string
from inboxpilot.eval.prompts import RESPONSE_CRITERIA_SYSTEM_PROMPT

from dotenv import load_dotenv
load_dotenv(".env", override=True)

if "inboxpilot.eval.email_dataset" in sys.modules:
    importlib.reload(sys.modules["inboxpilot.eval.email_dataset"])
from inboxpilot.eval.email_dataset import email_inputs, email_names, response_criteria_list, triage_outputs_list, expected_tool_calls

class CriteriaGrade(BaseModel):
    """Score the response against specific criteria."""
    grade: bool = Field(description="Does the response meet the provided criteria?")
    justification: str = Field(description="The justification for the grade and score, including specific examples from the response.")

criteria_eval_llm = init_chat_model("openai:gpt-4o")
criteria_eval_structured_llm = criteria_eval_llm.with_structured_output(CriteriaGrade)

AGENT_MODULE = None
agent_module = None

@pytest.fixture(autouse=True, scope="function")
def set_agent_module(agent_module_name):
    """Set the global AGENT_MODULE for each test function."""
    global AGENT_MODULE, agent_module
    AGENT_MODULE = agent_module_name
    print(f"Using agent module: {AGENT_MODULE}")

    if f"inboxpilot.{AGENT_MODULE}" in sys.modules:
        importlib.reload(sys.modules[f"inboxpilot.{AGENT_MODULE}"])

    agent_module = importlib.import_module(f"inboxpilot.{AGENT_MODULE}")
    return AGENT_MODULE

def setup_assistant() -> Tuple[Any, Dict[str, Any], InMemoryStore]:
    """Setup the InboxPilot assistant and create thread configuration."""
    checkpointer = MemorySaver()
    store = InMemoryStore()

    thread_id = uuid.uuid4()
    thread_config = {"configurable": {"thread_id": thread_id}}

    if AGENT_MODULE == "pilot":
        email_assistant = agent_module.overall_workflow.compile(checkpointer=checkpointer, store=store)
    elif AGENT_MODULE in ["pilot_review"]:
        email_assistant = agent_module.overall_workflow.compile(checkpointer=checkpointer)
    else:
        email_assistant = agent_module.overall_workflow.compile(checkpointer=checkpointer)
        store = None

    return email_assistant, thread_config, store

def extract_values(state: Any) -> Dict[str, Any]:
    """Extract values from state object regardless of type."""
    if hasattr(state, "values"):
        return state.values
    return state

def run_initial_stream(email_assistant: Any, email_input: Dict, thread_config: Dict) -> List[Dict]:
    """Run the initial stream and return collected messages."""
    messages = []
    for chunk in email_assistant.stream({"email_input": email_input}, config=thread_config):
        messages.append(chunk)
    return messages

def run_stream_with_command(email_assistant: Any, command: Command, thread_config: Dict) -> List[Dict]:
    """Run stream with a command and return collected messages."""
    messages = []
    for chunk in email_assistant.stream(command, config=thread_config):
        messages.append(chunk)
    return messages

def is_module_compatible(required_modules: List[str]) -> bool:
    """Check if current module is compatible with test."""
    return AGENT_MODULE in required_modules

def create_response_test_cases():
    """Create test cases for emails that require a response."""
    test_cases = []
    for email_input, email_name, criteria, triage_output, expected_calls in zip(
        email_inputs, email_names, response_criteria_list, triage_outputs_list, expected_tool_calls
    ):
        if triage_output == "respond":
            test_cases.append((email_input, email_name, criteria, expected_calls))

    print(f"Created {len(test_cases)} test cases for emails requiring responses")
    return test_cases

@pytest.mark.langsmith(output_keys=["expected_calls"])
@pytest.mark.parametrize("email_input,email_name,criteria,expected_calls", create_response_test_cases())
def test_email_dataset_tool_calls(email_input, email_name, criteria, expected_calls):
    """Test if email processing contains expected tool calls."""
    t.log_inputs({"module": AGENT_MODULE, "test": "test_email_dataset_tool_calls"})

    print(f"Processing {email_name}...")

    email_assistant, thread_config, _ = setup_assistant()

    if AGENT_MODULE == "pilot_simple":
        result = email_assistant.invoke({"email_input": email_input}, config=thread_config)
    else:
        raise ValueError(f"Unsupported agent module: {AGENT_MODULE}. Use 'pilot_simple' for automated testing.")

    state = email_assistant.get_state(thread_config)
    values = extract_values(state)

    extracted_tool_calls = extract_tool_calls(values["messages"])

    missing_calls = [call for call in expected_calls if call.lower() not in extracted_tool_calls]
    extra_calls = [call for call in extracted_tool_calls if call.lower() not in [c.lower() for c in expected_calls]]

    all_messages_str = format_messages_string(values["messages"])
    t.log_outputs({
        "extracted_tool_calls": extracted_tool_calls,
        "missing_calls": missing_calls,
        "extra_calls": extra_calls,
        "response": all_messages_str,
    })

    assert len(missing_calls) == 0

@pytest.mark.langsmith(output_keys=["criteria"])
@pytest.mark.parametrize("email_input,email_name,criteria,expected_calls", create_response_test_cases())
def test_response_criteria_evaluation(email_input, email_name, criteria, expected_calls):
    """Test if a response meets the specified criteria."""
    t.log_inputs({"module": AGENT_MODULE, "test": "test_response_criteria_evaluation"})

    print(f"Processing {email_name}...")

    email_assistant, thread_config, _ = setup_assistant()

    if AGENT_MODULE == "pilot_simple":
        result = email_assistant.invoke({"email_input": email_input}, config=thread_config)
    else:
        raise ValueError(f"Unsupported agent module: {AGENT_MODULE}. Use 'pilot_simple' for automated testing.")

    state = email_assistant.get_state(thread_config)
    values = extract_values(state)

    all_messages_str = format_messages_string(values["messages"])

    eval_result = criteria_eval_structured_llm.invoke([
        {"role": "system", "content": RESPONSE_CRITERIA_SYSTEM_PROMPT},
        {"role": "user", "content": f"\n\n Response criteria: {criteria} \n\n Assistant's response: \n\n {all_messages_str} \n\n Evaluate whether the assistant's response meets the criteria and provide justification for your evaluation."}
    ])

    t.log_outputs({
        "justification": eval_result.justification,
        "response": all_messages_str,
    })

    assert eval_result.grade
