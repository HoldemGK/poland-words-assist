# Polish Vocab Bot 🇵🇱

Automated Polish vocabulary drill system for Telegram channels powered by Google Cloud Run Functions (2nd Gen), OpenAI GPT-4o-mini, ElevenLabs TTS, and Cloud Scheduler.

---

## 🏗 System  Architecture

```text
 [Cloud Scheduler (Cron: 0 9,12,15,18,21 * * *)]
                   │ (OIDC Auth via Service Account)
                   ▼
 [Cloud Run Function (2nd gen) - Python 3.11]
         │
         ├─► 1. Telegram Bot API: getChat() -> extract pinned_message text
         ├─► 2. Parse & pick random 2-3 words from Polish vocab list
         ├─► 3. OpenAI API (gpt-4o-mini): generate A2/B1 sentence + RU translation (Structured Outputs)
         ├─► 4. ElevenLabs API (eleven_multilingual_v2): synthesize ONLY Polish sentence to MP3
         └─► 5. Telegram Bot API: sendVoice() + formatted caption with hidden spoilers
```

---

## 📁 Repository Structure

```text
poland-words-assist/
├── .env.example                     # Unified variables (.env) for local testing and HCP Terraform
├── .gitignore                       # Git ignore rules for Python, Terraform, and secrets
├── README.md                        # Project documentation
├── antigravity_artifacts.md         # Reference architectural specification
├── src/                             # Cloud Function application source
│   ├── main.py                      # Main entrypoint (functions-framework HTTP handler)
│   └── requirements.txt             # Python runtime dependencies
├── terraform/                       # Terraform infrastructure as code (HCP Cloud backend)
│   ├── main.tf                      # Cloud Run Function, Secret Manager, Cloud Scheduler, IAM
│   ├── variables.tf                 # Terraform input variables
│   └── outputs.tf                   # Outputs (Function URI, Scheduler job name)
├── scripts/                         # Helper scripts
│   └── run_local.py                 # Local test runner using .env
└── tests/                           # Unit tests
    └── test_vocab.py                # Tests for parsing, schema, and handler execution
```

---

## ⚙️ Configuration & Prerequisites

### 1. Telegram Bot Setup
1. Create a bot using [@BotFather](https://t.me/BotFather) and copy `TELEGRAM_BOT_TOKEN`.
2. Add the bot as an **Administrator** to your target Telegram channel with permission to post messages.
3. Pin a message in the channel containing your Polish vocabulary list (e.g., lines with `1. słowo - перевод`, `- słowo`, etc.).
4. Get your channel `@username` or numerical ID (`TELEGRAM_CHAT_ID`).

### 2. OpenAI & ElevenLabs
- **OpenAI API Key**: With access to `gpt-4o-mini`.
- **ElevenLabs API Key**: With access to `eleven_multilingual_v2`.
- **ElevenLabs Voice ID**: Default is `pNInz6obpgDQGcFmaJgB` (Adam) or any custom Polish-friendly voice.

---

## 💻 Local Development & Testing

### Setting Up Virtual Environment
```bash
# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\activate       # Windows
# source .venv/bin/activate    # Linux / macOS

# Install dependencies
pip install -r src/requirements.txt
```

### Running Unit Tests
```bash
python -m unittest discover -s tests
```

### Running Locally with Real APIs
1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Fill in your real API keys and channel ID.
3. Run the local test runner:
   ```bash
   python scripts/run_local.py
   ```

---

## ☁️ Deployment via HCP Terraform (Remote Execution)

Since the project uses HCP Terraform (`app.terraform.io` / `portal.cloud.hashicorp.com`) as the backend, **no local `terraform apply` is needed**. Runs, plans, and state management execute automatically in HCP Terraform.

### 1. Workspace Configuration
- **Organization**: `gkllc`
- **Project**: `fabe8953-8918-4dc5-8d5f-7b72742c42d9` (`poland-words-assist`)
- **Workspace**: `poland-words-assist`

### 2. Configure Variables in HCP Terraform
Configure your workspace variables or variable sets in the HCP Terraform console (or link via `.env`):
- `project_id` = GCP project ID (`polan-words-assist`)
- `region` = GCP Region (e.g., `europe-west1`)
- `time_zone` = Time zone for scheduler (e.g., `Europe/Warsaw`)
- `telegram_bot_token` (sensitive) = Telegram Bot Token
- `telegram_chat_id` = Channel username or ID
- `openai_api_key` (sensitive) = OpenAI API Key
- `elevenlabs_api_key` (sensitive) = ElevenLabs API Key
- `elevenlabs_voice_id` = Voice ID (e.g., `pNInz6obpgDQGcFmaJgB`)

### 3. Remote Execution Workflow
- **VCS-Driven (Recommended):** Connect your GitHub repository to the `poland-words-assist` workspace in HCP Terraform. Every push triggers speculative plans and automated applies in the cloud.
- **CLI-Driven (Optional):** If running from your terminal, authenticate once and run speculative plans remotely:
  ```bash
  terraform login
  cd terraform
  terraform init
  terraform plan
  ```
  *(The plan runs remotely on HCP Terraform infrastructure).*

Terraform will automatically:
- Enable required Google Cloud APIs (`cloudfunctions`, `run`, `cloudscheduler`, `secretmanager`, etc.)
- Create dedicated Service Accounts with least-privilege IAM roles
- Store API tokens securely in **Google Cloud Secret Manager**
- Package and upload `src/` to a Cloud Storage bucket
- Deploy the **Cloud Run Function (2nd Gen)**
- Schedule automated runs via **Cloud Scheduler** (every 3 hours between 9:00 and 21:00 Warsaw time)

---

## 🧪 Triggering Cloud Function Manually

Once deployed, you can trigger the function manually using Cloud Scheduler or gcloud:

```bash
# Trigger via Cloud Scheduler
gcloud scheduler jobs run polish-vocab-3h-cron --location=europe-west1

# Or view Cloud Run Function logs
gcloud functions logs read polish-vocab-generator --gen2 --region=europe-west1 --limit=50
```

---

## 🛡 Security & Best Practices

- **Zero Hardcoded Secrets**: Secrets are provisioned through Google Cloud Secret Manager and mounted as environment variables at runtime.
- **Strict OIDC Authentication**: Cloud Scheduler invokes the Cloud Run Function using a dedicated Service Account with OIDC token authentication; unauthorized public invocations are blocked.
- **Robust Failure Fallback**: If ElevenLabs TTS quota is exceeded or fails, the bot automatically falls back to delivering formatted HTML text messages so users never miss a vocabulary update.
- **HTML Injection Safety**: All dynamic strings (word, sentence, translation) are escaped before composing Telegram HTML payloads to prevent entity parsing errors.
