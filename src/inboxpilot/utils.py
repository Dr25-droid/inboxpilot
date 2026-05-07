from typing import List, Any
import json
import html2text

def format_email_markdown(subject, author, to, email_thread, email_id=None):
    """Format email details into a markdown string for display."""
    id_section = f"\n**ID**: {email_id}" if email_id else ""

    return f"""

**Subject**: {subject}
**From**: {author}
**To**: {to}{id_section}

{email_thread}

---
"""

def format_gmail_markdown(subject, author, to, email_thread, email_id=None):
    """Format Gmail email details into markdown, converting HTML body to text."""
    id_section = f"\n**ID**: {email_id}" if email_id else ""

    if email_thread and (email_thread.strip().startswith("<!DOCTYPE") or
                          email_thread.strip().startswith("<html") or
                          "<body" in email_thread):
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0
        email_thread = h.handle(email_thread)

    return f"""

**Subject**: {subject}
**From**: {author}
**To**: {to}{id_section}

{email_thread}

---
"""

def format_for_display(tool_call):
    """Format a tool call for display in Agent Inbox."""
    display = ""

    if tool_call["name"] == "write_email":
        display += f"""# Email Draft

**To**: {tool_call["args"].get("to")}
**Subject**: {tool_call["args"].get("subject")}

{tool_call["args"].get("content")}
"""
    elif tool_call["name"] == "schedule_meeting":
        display += f"""# Calendar Invite

**Meeting**: {tool_call["args"].get("subject")}
**Attendees**: {', '.join(tool_call["args"].get("attendees"))}
**Duration**: {tool_call["args"].get("duration_minutes")} minutes
**Day**: {tool_call["args"].get("preferred_day")}
"""
    elif tool_call["name"] == "Question":
        display += f"""# Question for User

{tool_call["args"].get("content")}
"""
    else:
        display += f"""# Tool Call: {tool_call["name"]}

Arguments:"""
        if isinstance(tool_call["args"], dict):
            display += f"\n{json.dumps(tool_call['args'], indent=2)}\n"
        else:
            display += f"\n{tool_call['args']}\n"
    return display

def parse_email(email_input: dict) -> tuple:
    """Parse standard email input dict into (author, to, subject, email_thread)."""
    return (
        email_input["author"],
        email_input["to"],
        email_input["subject"],
        email_input["email_thread"],
    )

def parse_gmail(email_input: dict) -> tuple:
    """Parse Gmail email input dict into (author, to, subject, body, email_id)."""
    return (
        email_input["from"],
        email_input["to"],
        email_input["subject"],
        email_input["body"],
        email_input["id"],
    )

def extract_message_content(message) -> str:
    """Extract clean string content from a message object."""
    content = message.content

    if isinstance(content, str) and '<Recursion on AIMessage with id=' in content:
        return "[Recursive content]"

    if isinstance(content, str):
        return content

    elif isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict) and 'text' in item:
                text_parts.append(item['text'])
        return "\n".join(text_parts)

    return str(content)

def format_few_shot_examples(examples):
    """Format vector store examples into a readable string."""
    formatted = []
    for example in examples:
        email_part = example.value.split('Original routing:')[0].strip()
        original_routing = example.value.split('Original routing:')[1].split('Correct routing:')[0].strip()
        correct_routing = example.value.split('Correct routing:')[1].strip()

        formatted_example = f"""Example:
Email: {email_part}
Original Classification: {original_routing}
Correct Classification: {correct_routing}
---"""
        formatted.append(formatted_example)

    return "\n".join(formatted)

def extract_tool_calls(messages: List[Any]) -> List[str]:
    """Extract tool call names from messages."""
    tool_call_names = []
    for message in messages:
        if isinstance(message, dict) and message.get("tool_calls"):
            tool_call_names.extend([call["name"].lower() for call in message["tool_calls"]])
        elif hasattr(message, "tool_calls") and message.tool_calls:
            tool_call_names.extend([call["name"].lower() for call in message.tool_calls])

    return tool_call_names

def format_messages_string(messages: List[Any]) -> str:
    """Format messages into a single string for analysis."""
    return '\n'.join(message.pretty_repr() for message in messages)
