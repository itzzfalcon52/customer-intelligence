import os
from pathlib import Path

from dotenv import load_dotenv
from openai import APIError, OpenAI

# Find .env beside this script, regardless of the terminal directory.
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(env_path)

required = ["NEBIUS_API_KEY", "NEBIUS_BASE_URL", "NEBIUS_MODEL"]
missing = [name for name in required if not os.getenv(name)]

if missing:
    raise SystemExit(f"Missing configuration: {', '.join(missing)}")

client = OpenAI(
    api_key=os.environ["NEBIUS_API_KEY"],
    base_url=os.environ["NEBIUS_BASE_URL"],
    timeout=60.0,
    max_retries=0,
)

try:
    response = client.chat.completions.create(
        model=os.environ["NEBIUS_MODEL"],
        messages=[
            {
                "role": "user",
                "content": "Explain customer churn in one short sentence.",
            }
        ],
        max_tokens=1024,
    )
except APIError as error:
    status = getattr(error, "status_code", None)
    raise SystemExit(
        f"Nebius request failed: {type(error).__name__}, HTTP status: {status}"
    ) from None

if not response.choices:
    raise SystemExit("Request succeeded, but returned no response choices.")

choice = response.choices[0]

print("Model:", response.model)
print("Response:", choice.message.content or "(No visible text returned)")
print("Finish reason:", choice.finish_reason)