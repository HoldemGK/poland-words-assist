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
├── .env.example                     # Unified variables (.env) for local testing and Terraform
├── .gitignore                       # Git ignore rules for Python, Terraform, and secrets
├── README.md                        # Project documentation
├── antigravity_artifacts.md         # Reference architectural specification
├── src/                             # Cloud Function application source
│   ├── main.py                      # Main entrypoint (functions-framework HTTP handler)
│   └── requirements.txt             # Python runtime dependencies
├── terraform/                       # Terraform infrastructure as code (Google Cloud Storage GCS backend)
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

## ☁️ Deployment via Terraform (GCS Backend)

State management is stored in a dedicated Google Cloud Storage bucket (`polan-words-assist-static/tf-state-prd`).

### 1. Backend Configuration
Configured in `terraform/backend.tf`:
- **Bucket**: `polan-words-assist-static`
- **Prefix / Folder**: `tf-state-prd`

### 2. Environment Variables & Credentials
Ensure your terminal has Google Cloud authentication and variables configured:
```bash
# Authenticate with Google Cloud
gcloud auth application-default login

# Export your variables or supply them via terraform.tfvars / .env:
export TF_VAR_project_id="polan-words-assist"
export TF_VAR_telegram_bot_token="<your-token>"
export TF_VAR_telegram_chat_id="<your-chat-id>"
export TF_VAR_openai_api_key="<your-openai-key>"
export TF_VAR_elevenlabs_api_key="<your-elevenlabs-key>"
```

### 3. Deploying Infrastructure
Navigate to the `terraform/` directory:
```bash
cd terraform

# Initialize with GCS backend (use -migrate-state if migrating existing state)
terraform init

# Review execution plan
terraform plan

# Apply changes
terraform apply
```

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


To configure GitHub Actions to deploy resources to Google Cloud using your service account, using static JSON service account keys is no longer recommended as they present a significant security risk (they do not expire and can be leaked easily).

Instead, the modern and secure best practice is to configure Workload Identity Federation (WIF). Workload Identity Federation allows GitHub Actions to authenticate directly with Google Cloud using short-lived, OpenID Connect (OIDC) tokens, eliminating the need to store or rotate JSON keys.

Here is the complete set of gcloud commands to configure Workload Identity Federation on the Google Cloud side.

Step 1: Set Up Variables
Before running the commands, define the variables for your setup (replace <GITHUB_ORGANIZATION_OR_USER> and <GITHUB_REPO> with your actual repository details):

# Variables
PROJECT_ID="polan-words-assist"
POOL_NAME="github-pool"
PROVIDER_NAME="github-provider"
SERVICE_ACCOUNT_EMAIL="tf-cloud@polan-words-assist.iam.gserviceaccount.com"
GITHUB_REPO="<GITHUB_ORGANIZATION_OR_USER>/<GITHUB_REPO>" # e.g., "my-org/my-repo"
# Variables
PROJECT_ID="polan-words-assist"
POOL_NAME="github-pool"
PROVIDER_NAME="github-provider"
SERVICE_ACCOUNT_EMAIL="tf-cloud@polan-words-assist.iam.gserviceaccount.com"
GITHUB_REPO="<GITHUB_ORGANIZATION_OR_USER>/<GITHUB_REPO>" # e.g., "my-org/my-repo"
Generated code may be subject to license restrictions not shown here. Use code with care. Learn more 

Step 2: Enable the Required APIs
Enable the IAM Credentials and Workload Credentials APIs in your project:

gcloud services enable iamcredentials.googleapis.com \
    --project="${PROJECT_ID}"


Step 3: Create the Workload Identity Pool
Create a pool that will manage the identities coming from GitHub:

gcloud iam workload-identity-pools create "${POOL_NAME}" \
    --project="${PROJECT_ID}" \
    --location="global" \
    --display-name="GitHub Actions Pool"

Step 4: Create the Workload Identity Provider
Create the OIDC provider inside the pool. This maps GitHub's claims (such as repository, actor, etc.) to Google Cloud IAM attributes:

gcloud iam workload-identity-pools providers create-oidc github-actions --project="${PROJECT_ID}" --location="global" --workload-identity-pool=github-actions --display-name="GitHub Provider" --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository" --issuer-uri="https://token.actions.githubusercontent.com" --attribute-condition="assertion.repository_owner == 'HoldemGK'"

Step 5: Grant the GitHub Repo Permission to Impersonate the Service Account
Authorize your specific GitHub repository to impersonate your service account tf-cloud using the Workload Identity Pool. This restricts access to only your specified repository:

# Retrieve the full unique ID of your Workload Identity Pool
POOL_ID=$(gcloud iam workload-identity-pools describe "${POOL_NAME}" \
    --project="${PROJECT_ID}" \
    --location="global" \
    --format="value(name)")
# Grant the Workload Identity User role to your  repository
gcloud iam service-accounts add-iam-policy-binding "${SERVICE_ACCOUNT_EMAIL}" \
    --project="${PROJECT_ID}" \
    --role="roles/iam.workloadIdentityUser" \
    --member="principalSet://iam.googleapis.com/${POOL_ID}/attribute.repository/${GITHUB_REPO}"

Step 6: GitHub Actions Workflow Integration
On the GitHub side, you do not need to paste any JSON keys into your repository secrets. Instead, you only need to reference your project settings using the official Google Authentication Action (google-github-actions/auth)