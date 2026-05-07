"""pilot.py — Main InboxPilot agent with human approval and persistent memory.

Full production assistant:
- Triage: classifies email as IGNORE / NOTIFY / RESPOND
- Review: pauses for human approval before sending drafts
- Memory: learns from every approval, edit, and rejection
"""
from typing import Literal

from langchain.chat_models import init_chat_model

from langgraph.graph import StateGraph, START, END
from langgraph.store.base import BaseStore
from langgraph.types import interrupt, Command

from inboxpilot.tools import get_tools, get_tools_by_name
from inboxpilot.tools.prompt_templates import HITL_MEMORY_TOOLS_PROMPT
from inboxpilot.prompts import (
    triage_system_prompt, triage_user_prompt, agent_system_prompt_with_memory,
    get_background, default_triage_instructions,
    default_response_preferences, default_cal_preferences,
    MEMORY_UPDATE_INSTRUCTIONS, MEMORY_UPDATE_INSTRUCTIONS_REINFORCEMENT,
)
from inboxpilot.schemas import State, RouterSchema, StateInput, UserPreferences
from inboxpilot.utils import parse_email, format_for_display, format_email_markdown
from dotenv import load_dotenv

load_dotenv(".env")

tools = get_tools(["write_email", "schedule_meeting", "check_calendar_availability", "Question", "Done"])
tools_by_name = get_tools_by_name(tools)

llm = init_chat_model("openai:gpt-4.1", temperature=0.0)
llm_router = llm.with_structured_output(RouterSchema)

llm = init_chat_model("openai:gpt-4.1", temperature=0.0)
llm_with_tools = llm.bind_tools(tools, tool_choice="required")

def get_memory(store, namespace, default_content=None):
    """Retrieve memory from the store, seeding with defaults on first access."""
    user_preferences = store.get(namespace, "user_preferences")
    if user_preferences:
        return user_preferences.value
    store.put(namespace, "user_preferences", default_content)
    return default_content

def update_memory(store, namespace, messages):
    """Update a memory namespace using LLM-powered selective editing."""
    user_preferences = store.get(namespace, "user_preferences")
    llm_mem = init_chat_model("openai:gpt-4.1", temperature=0.0).with_structured_output(UserPreferences)
    result = llm_mem.invoke(
        [{"role": "system", "content": MEMORY_UPDATE_INSTRUCTIONS.format(
            current_profile=user_preferences.value, namespace=namespace
        )}] + messages
    )
    store.put(namespace, "user_preferences", result.user_preferences)

def triage_router(state: State, store: BaseStore) -> Command[Literal["triage_interrupt_handler", "response_agent", "__end__"]]:
    """Classify email using triage preferences from memory."""
    author, to, subject, email_thread = parse_email(state["email_input"])
    user_prompt = triage_user_prompt.format(
        author=author, to=to, subject=subject, email_thread=email_thread
    )
    email_markdown = format_email_markdown(subject, author, to, email_thread)

    triage_instructions = get_memory(store, ("inboxpilot", "triage_preferences"), default_triage_instructions)

    system_prompt = triage_system_prompt.format(
        background=get_background(),
        triage_instructions=triage_instructions,
    )

    result = llm_router.invoke([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ])
    classification = result.classification

    if classification == "respond":
        print("📧 Classification: RESPOND")
        goto = "response_agent"
        update = {
            "classification_decision": result.classification,
            "messages": [{"role": "user", "content": f"Respond to the email: {email_markdown}"}],
        }
    elif classification == "ignore":
        print("🚫 Classification: IGNORE")
        goto = END
        update = {"classification_decision": classification}
    elif classification == "notify":
        print("🔔 Classification: NOTIFY")
        goto = "triage_interrupt_handler"
        update = {"classification_decision": classification}
    else:
        raise ValueError(f"Invalid classification: {classification}")

    return Command(goto=goto, update=update)

def triage_interrupt_handler(state: State, store: BaseStore) -> Command[Literal["response_agent", "__end__"]]:
    """Show NOTIFY emails to user; update triage memory based on their decision."""
    author, to, subject, email_thread = parse_email(state["email_input"])
    email_markdown = format_email_markdown(subject, author, to, email_thread)

    messages = [{"role": "user", "content": f"Email to notify user about: {email_markdown}"}]

    request = {
        "action_request": {
            "action": f"InboxPilot: {state['classification_decision']}",
            "args": {}
        },
        "config": {
            "allow_ignore": True,
            "allow_respond": True,
            "allow_edit": False,
            "allow_accept": False,
        },
        "description": email_markdown,
    }

    response = interrupt([request])[0]

    if response["type"] == "response":
        user_input = response["args"]
        messages.append({"role": "user", "content": f"User wants to reply to the email. Use this feedback to respond: {user_input}"})
        update_memory(store, ("inboxpilot", "triage_preferences"), [{"role": "user", "content": "The user decided to respond to the email, so update the triage preferences to capture this."}] + messages)
        goto = "response_agent"
    elif response["type"] == "ignore":
        messages.append({"role": "user", "content": "The user decided to ignore the email even though it was classified as notify. Update triage preferences to capture this."})
        update_memory(store, ("inboxpilot", "triage_preferences"), messages)
        goto = END
    else:
        raise ValueError(f"Invalid response: {response}")

    return Command(goto=goto, update={"messages": messages})

def llm_call(state: State, store: BaseStore):
    """LLM decides which tool to call, reading response and calendar preferences from memory."""
    cal_preferences = get_memory(store, ("inboxpilot", "cal_preferences"), default_cal_preferences)
    response_preferences = get_memory(store, ("inboxpilot", "response_preferences"), default_response_preferences)

    return {
        "messages": [
            llm_with_tools.invoke(
                [{"role": "system", "content": agent_system_prompt_with_memory.format(
                    tools_prompt=HITL_MEMORY_TOOLS_PROMPT,
                    background=get_background(),
                    response_preferences=response_preferences,
                    cal_preferences=cal_preferences
                )}]
                + state["messages"]
            )
        ]
    }

def interrupt_handler(state: State, store: BaseStore) -> Command[Literal["llm_call", "__end__"]]:
    """Pause for human review; update memory based on every approval, edit, or rejection."""
    result = []
    goto = "llm_call"

    for tool_call in state["messages"][-1].tool_calls:
        hitl_tools = ["write_email", "schedule_meeting", "Question"]

        if tool_call["name"] not in hitl_tools:
            tool = tools_by_name[tool_call["name"]]
            observation = tool.invoke(tool_call["args"])
            result.append({"role": "tool", "content": observation, "tool_call_id": tool_call["id"]})
            continue

        email_input = state["email_input"]
        author, to, subject, email_thread = parse_email(email_input)
        original_email_markdown = format_email_markdown(subject, author, to, email_thread)

        tool_display = format_for_display(tool_call)
        description = original_email_markdown + tool_display

        if tool_call["name"] == "write_email":
            config = {"allow_ignore": True, "allow_respond": True, "allow_edit": True, "allow_accept": True}
        elif tool_call["name"] == "schedule_meeting":
            config = {"allow_ignore": True, "allow_respond": True, "allow_edit": True, "allow_accept": True}
        elif tool_call["name"] == "Question":
            config = {"allow_ignore": True, "allow_respond": True, "allow_edit": False, "allow_accept": False}
        else:
            raise ValueError(f"Invalid tool call: {tool_call['name']}")

        request = {
            "action_request": {"action": tool_call["name"], "args": tool_call["args"]},
            "config": config,
            "description": description,
        }

        response = interrupt([request])[0]

        if response["type"] == "accept":
            tool = tools_by_name[tool_call["name"]]
            observation = tool.invoke(tool_call["args"])
            result.append({"role": "tool", "content": observation, "tool_call_id": tool_call["id"]})

        elif response["type"] == "edit":
            tool = tools_by_name[tool_call["name"]]
            initial_tool_call = tool_call["args"]
            edited_args = response["args"]["args"]
            ai_message = state["messages"][-1]
            current_id = tool_call["id"]
            updated_tool_calls = [tc for tc in ai_message.tool_calls if tc["id"] != current_id] + [
                {"type": "tool_call", "name": tool_call["name"], "args": edited_args, "id": current_id}
            ]
            result.append(ai_message.model_copy(update={"tool_calls": updated_tool_calls}))

            if tool_call["name"] == "write_email":
                observation = tool.invoke(edited_args)
                result.append({"role": "tool", "content": observation, "tool_call_id": current_id})
                update_memory(store, ("inboxpilot", "response_preferences"), [{"role": "user", "content": f"User edited the email response. Initial: {initial_tool_call}. Edited: {edited_args}. {MEMORY_UPDATE_INSTRUCTIONS_REINFORCEMENT}"}])
            elif tool_call["name"] == "schedule_meeting":
                observation = tool.invoke(edited_args)
                result.append({"role": "tool", "content": observation, "tool_call_id": current_id})
                update_memory(store, ("inboxpilot", "cal_preferences"), [{"role": "user", "content": f"User edited the calendar invitation. Initial: {initial_tool_call}. Edited: {edited_args}. {MEMORY_UPDATE_INSTRUCTIONS_REINFORCEMENT}"}])
            else:
                raise ValueError(f"Invalid tool call: {tool_call['name']}")

        elif response["type"] == "ignore":
            if tool_call["name"] == "write_email":
                result.append({"role": "tool", "content": "User ignored this email draft. Ignore this email and end the workflow.", "tool_call_id": tool_call["id"]})
                goto = END
                update_memory(store, ("inboxpilot", "triage_preferences"), state["messages"] + result + [{"role": "user", "content": f"The user ignored the email draft. Update triage preferences to ensure emails of this type are not classified as respond. {MEMORY_UPDATE_INSTRUCTIONS_REINFORCEMENT}"}])
            elif tool_call["name"] == "schedule_meeting":
                result.append({"role": "tool", "content": "User ignored this calendar meeting draft. Ignore this email and end the workflow.", "tool_call_id": tool_call["id"]})
                goto = END
                update_memory(store, ("inboxpilot", "triage_preferences"), state["messages"] + result + [{"role": "user", "content": f"The user ignored the calendar meeting draft. Update triage preferences to ensure emails of this type are not classified as respond. {MEMORY_UPDATE_INSTRUCTIONS_REINFORCEMENT}"}])
            elif tool_call["name"] == "Question":
                result.append({"role": "tool", "content": "User ignored this question. Ignore this email and end the workflow.", "tool_call_id": tool_call["id"]})
                goto = END
                update_memory(store, ("inboxpilot", "triage_preferences"), state["messages"] + result + [{"role": "user", "content": f"The user ignored the Question. Update triage preferences to ensure emails of this type are not classified as respond. {MEMORY_UPDATE_INSTRUCTIONS_REINFORCEMENT}"}])
            else:
                raise ValueError(f"Invalid tool call: {tool_call['name']}")

        elif response["type"] == "response":
            user_feedback = response["args"]
            if tool_call["name"] == "write_email":
                result.append({"role": "tool", "content": f"User gave feedback, which can we incorporate into the email. Feedback: {user_feedback}", "tool_call_id": tool_call["id"]})
                update_memory(store, ("inboxpilot", "response_preferences"), state["messages"] + result + [{"role": "user", "content": f"User gave feedback. Update response preferences. {MEMORY_UPDATE_INSTRUCTIONS_REINFORCEMENT}"}])
            elif tool_call["name"] == "schedule_meeting":
                result.append({"role": "tool", "content": f"User gave feedback, which can we incorporate into the meeting request. Feedback: {user_feedback}", "tool_call_id": tool_call["id"]})
                update_memory(store, ("inboxpilot", "cal_preferences"), state["messages"] + result + [{"role": "user", "content": f"User gave feedback. Update calendar preferences. {MEMORY_UPDATE_INSTRUCTIONS_REINFORCEMENT}"}])
            elif tool_call["name"] == "Question":
                result.append({"role": "tool", "content": f"User answered the question, which can we can use for any follow up actions. Feedback: {user_feedback}", "tool_call_id": tool_call["id"]})
            else:
                raise ValueError(f"Invalid tool call: {tool_call['name']}")

    return Command(goto=goto, update={"messages": result})

def should_continue(state: State, store: BaseStore) -> Literal["interrupt_handler", "__end__"]:
    """Route to human review or end when Done is called."""
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        for tool_call in last_message.tool_calls:
            if tool_call["name"] == "Done":
                return END
            else:
                return "interrupt_handler"

agent_builder = StateGraph(State)
agent_builder.add_node("llm_call", llm_call)
agent_builder.add_node("interrupt_handler", interrupt_handler)
agent_builder.add_edge(START, "llm_call")
agent_builder.add_conditional_edges(
    "llm_call", should_continue,
    {"interrupt_handler": "interrupt_handler", END: END},
)
response_agent = agent_builder.compile()

overall_workflow = (
    StateGraph(State, input=StateInput)
    .add_node(triage_router)
    .add_node(triage_interrupt_handler)
    .add_node("response_agent", response_agent)
    .add_edge(START, "triage_router")
)

email_assistant = overall_workflow.compile()
