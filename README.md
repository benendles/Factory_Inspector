# 🏭 Factory Inspector

**AI-Powered Industrial Inspection and Predictive Maintenance**

Factory Inspector is an AI-assisted industrial inspection platform built for the **AMD Developer Hackathon**. It uses AI agents, simulated sensor data, equipment identification, and workflow automation to investigate factory anomalies, recommend maintenance actions, and verify whether simulated maintenance resolves detected problems.

The goal is to demonstrate how AI agents can help factory teams detect equipment problems, investigate incidents, coordinate maintenance, and escalate unresolved issues.

> **⚠️ Safety Notice:** Factory Inspector is a hackathon prototype, not a certified industrial safety system. Sensor readings and maintenance outcomes may be simulated. It must not be used as the sole basis for decisions involving real equipment. Safety certification remains disabled (`safety_certified = false`).

---

## 🚀 Key Features

- **Sensor Anomaly Detection:** Analyze temperature, vibration, pressure, and moisture readings.
- **AI-Assisted Inspection:** Support visual inspection when image evidence is provided.
- **Equipment Identification:** Match machine identifiers against an equipment registry.
- **Incident Management:** Generate incidents when simulated sensor evidence indicates anomalies.
- **Maintenance Recommendations:** Generate proposed actions for human review.
- **Human-in-the-Loop Approval:** Pause the workflow until the required human approval is received.
- **Physical Identity Verification:** Require confirmation that the physical machine matches its registry record before asset-specific maintenance can proceed.
- **Post-Maintenance Verification:** Evaluate fresh simulated evidence after maintenance.
- **Automatic Escalation:** Escalate unresolved anomalies instead of incorrectly declaring success.
- **Stateful AI Workflows:** Use LangGraph to coordinate the inspection and maintenance process.

---

## 🧠 How It Works

The Factory Inspector workflow follows these stages:

1. **Receive Evidence** — Obtain sensor readings and optional machine images.
2. **Analyze Sensors** — Identify readings that exceed configured demo thresholds.
3. **Inspect Visual Evidence** — Analyze an image when one is available.
4. **Identify Equipment** — Compare machine identifiers with registry records.
5. **Verify Physical Identity** — Require audit-backed human confirmation of the physical asset.
6. **Create an Incident** — Record the detected anomaly when an incident is necessary.
7. **Investigate the Incident** — Analyze available evidence and prepare proposed maintenance actions.
8. **Request Human Approval** — Pause before proceeding with the maintenance workflow.
9. **Simulate Maintenance** — Proceed only when the required safeguards and approval checks pass.
10. **Verify the Outcome** — Evaluate fresh simulated sensor evidence after maintenance.
11. **Resolve or Escalate** — Mark the workflow resolved when appropriate, or escalate if the anomaly persists.

### Workflow Safety Rules

- A registry match does not prove the identity of the physical machine.
- Rejected physical identity verification must block asset-specific maintenance approval and execution.
- Human approval is separate from physical identity verification.
- A workflow must not report successful resolution when the simulated anomaly persists.
- The prototype does not certify equipment as safe.

---

## 🛠️ Technology Stack

| Technology | Purpose |
|---|---|
| Python | Backend development |
| FastAPI | REST API |
| LangGraph | Stateful agent workflow orchestration |
| AMD Token Factory | Hosted AI model access |
| Evolus API | AI agent and workflow integration |
| SQLAlchemy | Database interaction |
| SQL Database | Persistent records and identity verification audits |
| Swagger UI | Interactive API testing |

---

## 📁 Project Structure

The main backend components include:

```text
Factory_Inspector/
└── backend/
    ├── app/
    │   ├── agents/
    │   │   ├── graph.py
    │   │   ├── nodes.py
    │   │   └── state.py
    │   │
    │   ├── api/
    │   │   └── routes/
    │   │       └── simulator.py
    │   │
    │   ├── database/
    │   │   ├── models.py
    │   │   ├── repositories.py
    │   │   ├── identity_verification_repository.py
    │   │   └── session.py
    │   │
    │   ├── services/
    │   │   ├── amd_token_factory.py
    │   │   └── factory_workflow_service.py
    │   │
    │   └── simulator/
    │       └── scenarios.py
    │
    └── tests/
        └── test_amd_client.py
```

This tree highlights the main components. Your actual repository may contain additional files.

---

## ⚙️ Installation

### 1. Clone or Open the Project

Open the project directory in Cursor or your preferred editor.

From your terminal:

```bash
cd Factory_Inspector/backend
```

### 2. Create a Virtual Environment

On macOS or Linux:

```bash
python3 -m venv .venv
```

Activate it:

```bash
source .venv/bin/activate
```

### 3. Install Dependencies

If the project contains a `requirements.txt` file:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If the dependency file is missing, restore it from the project's actual dependencies before running the application.

---

## 🔑 Environment Configuration

Create a `.env` file using the environment variable names expected by the application.

Example template:

```dotenv
# AMD Token Factory
RADEON_API_KEY=your_amd_api_key

# Evolus
EVOLUS_API_KEY=your_evolus_api_key

# Database
DATABASE_URL=your_database_connection_string
```

**Important:** These are example configuration names. Check the application's settings and service files to confirm the exact variable names used by your implementation.

Never commit API keys, passwords, or database credentials to GitHub.

Ensure `.env` is included in `.gitignore`.

---

## ▶️ Running the Backend

From the `backend/` directory, activate your virtual environment and run:

```bash
uvicorn app.main:app --reload
```

If your FastAPI application uses a different entry-point module, replace `app.main:app` with the correct import path.

Once the server starts, open:

**Swagger UI:**

```text
http://127.0.0.1:8000/docs
```

**OpenAPI schema:**

```text
http://127.0.0.1:8000/openapi.json
```

Use Swagger UI to inspect available endpoints and test the simulator.

---

## 🧪 Available Simulation Scenarios

Factory Inspector currently supports five demo scenarios.

| Scenario | Example Readings | Expected Behavior |
|---|---|---|
| `normal_operation` | Temperature: 55°C, vibration: 2 | No injected critical anomaly |
| `overheating` | Temperature: 95°C, vibration: 2.5 | Detect a temperature anomaly |
| `excessive_vibration` | Temperature: 55°C, vibration: 8.2 | Detect excessive vibration |
| `critical_failure` | Temperature: 95°C, vibration: 8.2, pressure: 9 | Exercise multiple critical anomalies |
| `persistent_anomaly` | Temperature: 95°C, vibration: 8.2 | Simulate an issue that remains after maintenance and should escalate |

These values are simulated examples, not universal industrial safety thresholds or measurements from real equipment.

The scenario definitions are maintained in:

```text
backend/app/simulator/scenarios.py
```

---

## 🔐 Equipment Identity and Approval

Factory Inspector separates equipment registry matching from physical identity confirmation.

### Registry Matching

The system searches for a matching equipment record using available identifiers.

A successful registry match identifies a candidate record; it does not establish that the physical equipment has that identity.

### Physical Identity Verification

A human must confirm the physical identity through the audit-backed verification workflow before asset-specific maintenance can be approved.

### Rejected Identity

If physical identity is rejected:

- The workflow status becomes `identity_rejected`.
- `approval_required` must be `false`.
- `pending_approval` must be an empty list.
- The physical identity must remain unconfirmed.
- Asset-specific maintenance approval and execution must be blocked.
- The workflow must remain unresolved.

### Human Approval

Even after physical identity is confirmed, maintenance requires its own approval decision.

A reviewer name or approver label alone is not authentication. A production deployment would need proper authentication, authorization, and audit controls.

---

## 🔎 Post-Maintenance Verification

After simulated maintenance, Factory Inspector evaluates fresh simulated evidence to determine whether the anomaly remains.

Possible outcomes include:

- **Resolved:** The simulated evidence no longer indicates the targeted anomaly.
- **Escalation required:** The anomaly persists and requires further investigation.

The `persistent_anomaly` scenario is intended to demonstrate escalation when simulated maintenance does not resolve the problem.

The application must not declare a real machine safe based solely on simulated readings.

---

## 🧪 Running Tests

From the `backend/` directory, activate the virtual environment.

Test the AMD client:

```bash
python -m tests.test_amd_client
```

Run the available test suite:

```bash
python -m pytest
```

If `pytest` is not installed:

```bash
pip install pytest
```

Tests that call external services may require valid API credentials and network access.

---

## ⚠️ Current Limitations

- Sensor readings and maintenance outcomes can be simulated.
- Visual inspection requires valid image evidence and the appropriate model configuration.
- The demo registry must not be treated as an authoritative inventory of real factory equipment.
- The workflow service currently uses an in-memory LangGraph checkpointer and in-memory workflow cache.
- Active workflow state may be lost when the backend restarts.
- API credentials and database settings must be configured locally.
- Production deployment requires durable workflow persistence, authentication, authorization, monitoring, secret management, and stronger operational controls.
- The project is not a certified industrial safety system.

---

## 🔮 Future Improvements

Potential next steps include:

- Persistent LangGraph checkpoints.
- Integration with real industrial IoT sensors.
- Live camera-based anomaly detection.
- More comprehensive equipment registry integration.
- Authenticated technician and supervisor accounts.
- Role-based approval permissions.
- Durable incident and maintenance history.
- Notifications for critical incidents.
- A dashboard for inspection results and workflow status.
- Automated regression tests for identity rejection and approval bypass attempts.
- Deployment and monitoring suitable for a controlled demonstration environment.

---

## 🏆 About the Project

Factory Inspector is an AI-assisted industrial inspection and maintenance workflow prototype developed for the **AMD Developer Hackathon**.

It demonstrates how AI agents and stateful workflows can help investigate equipment anomalies while keeping identity verification, human approval, and escalation central to the process.

**Safety certification:** `false`

**Project status:** Active hackathon prototype.