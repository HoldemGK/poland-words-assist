"""
Local test runner for Polish Vocab Bot.
Loads environment variables from .env and triggers send_vocab_task locally.
"""
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def load_dotenv():
    root_dir = Path(__file__).parent.parent
    env_file = root_dir / ".env"
    if not env_file.exists():
        env_file = root_dir / ".env.example"
        print("Note: .env not found, falling back to reading .env.example")

    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    os.environ[k] = v
        print(f"Loaded environment variables from {env_file.name}")
    else:
        print("No environment configuration file found.")

if __name__ == "__main__":
    load_dotenv()
    from main import send_vocab_task

    class MockRequest:
        pass

    print("Executing send_vocab_task locally...")
    response, status_code = send_vocab_task(MockRequest())
    print(f"Result: {status_code} - {response}")
