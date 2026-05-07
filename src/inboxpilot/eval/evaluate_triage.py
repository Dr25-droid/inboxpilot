from langsmith import Client
import os
import matplotlib.pyplot as plt
from datetime import datetime

from inboxpilot.eval.email_dataset import examples_triage
from inboxpilot.pilot_simple import email_assistant

client = Client()

dataset_name = "InboxPilot: Email Triage Dataset"

if not client.has_dataset(dataset_name=dataset_name):
    dataset = client.create_dataset(
        dataset_name=dataset_name,
        description="A dataset of emails and their triage classifications."
    )
    client.create_examples(dataset_id=dataset.id, examples=examples_triage)

def target_email_assistant(inputs: dict) -> dict:
    """Process an email through the triage workflow."""
    try:
        response = email_assistant.invoke({"email_input": inputs["email_input"]})
        if "classification_decision" in response:
            return {"classification_decision": response["classification_decision"]}
        return {"classification_decision": "unknown"}
    except Exception as e:
        print(f"Error in triage evaluation: {e}")
        return {"classification_decision": "unknown"}

feedback_key = "classification"

def classification_evaluator(outputs: dict, reference_outputs: dict) -> bool:
    """Check if the classification matches the expected answer."""
    return outputs["classification_decision"].lower() == reference_outputs["classification"].lower()

experiment_results = client.evaluate(
    target_email_assistant,
    data=dataset_name,
    evaluators=[classification_evaluator],
    experiment_prefix="InboxPilot triage",
    max_concurrency=2,
)

df = experiment_results.to_pandas()
score = df["feedback.classification_evaluator"].mean() if "feedback.classification_evaluator" in df.columns else 0.0

plt.figure(figsize=(8, 5))
plt.bar(["InboxPilot"], [score], color=["#5DA5DA"], width=0.4)
plt.xlabel("Agent")
plt.ylabel("Average Score")
plt.title(f"Email Triage Performance — {feedback_key.capitalize()} Score")
plt.text(0, score + 0.02, f"{score:.2f}", ha="center", fontweight="bold")
plt.ylim(0, 1.1)
plt.grid(axis="y", linestyle="--", alpha=0.7)

os.makedirs("eval/results", exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
plot_path = f"eval/results/triage_comparison_{timestamp}.png"
plt.savefig(plot_path)
plt.close()

print(f"\nEvaluation saved to: {plot_path}")
print(f"Triage Score: {score:.2f}")
