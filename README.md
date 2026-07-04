# ClaimAssist: AI-Powered Vehicle Damage Assessment

A FastAPI + Chainlit prototype for automating vehicle damage assessment in insurance claims processing.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Claims Agent                             │
│                  (Chainlit Frontend)                        │
│   - Upload damage photos                                    │
│   - Review AI assessment                                    │
│   - Override if needed                                      │
│   - Approve or escalate                                     │
└────────────────────┬────────────────────────────────────────┘
                     │ HTTP API
┌────────────────────▼────────────────────────────────────────┐
│                    FastAPI Backend                          │
│   - Image upload & storage                                  │
│   - Gemini Vision API damage assessment                     │
│   - Confidence scoring & routing logic                      │
│   - Cost estimation heuristic                               │
│   - Audit logging for every decision                        │
└────────────────────────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                  Gemini Vision API                          │
│   - Analyze vehicle damage photos                           │
│   - Extract damage type, severity, location                 │
│   - Return confidence scores                                │
└─────────────────────────────────────────────────────────────┘
```

## Features

### MVP (Implemented)

- **Image Upload & Analysis** - Upload damage photos; Gemini Vision API analyzes and classifies
- **Damage Assessment** - Extracts: damage type, severity, vehicle area, confidence score
- **Confidence Scoring & Routing** - Confidence < 75% → escalate; >= 90% → fast track; between → review
- **Agent Override Workflow** - Agent can correct AI assessment; all overrides logged
- **Cost Estimation** - Heuristic-based repair cost range (severity × vehicle class)
- **Audit Trail** - Every decision logged for compliance and model improvement
- **Human-in-Loop Design** - Agent maintains control; AI is advisory only

### Phase 2 (Not Implemented)

- Historical claim lookup & comparison
- Fraud detection signals
- Policyholder self-service photo upload
- Predictive repair complexity scoring

## Setup

### Prerequisites

- Python 3.10+
- Gemini API key (for Gemini Vision)
- pip or uv package manager

### Installation

1. **Clone or navigate to the project directory:**

   ```bash
   cd app
   ```

2. **Create virtual environment:**

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Set environment variables:**
   ```bash
   export llm_api_key="your-api-key-here"
   export backend_url="http://localhost:8000"
   ```

### Running the Application

**Terminal 1: Start FastAPI Backend**

```bash
python -m backend
```

You should see:

```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Terminal 2: Start Chainlit Frontend**

```bash
chainlit run frontend.py --host 0.0.0.0 --port 8001
```

You should see:

```
Chainlit loaded successfully
App is available at http://localhost:8001
```

3. **Open browser:**
   Navigate to `http://localhost:8001` and start assessing claims.

## Usage Workflow

### 1. **Initial Claim View**

The app loads with claim context (vehicle, policy, accident details).

### 2. **Upload Damage Photo**

- Click the image upload button
- Select a photo of vehicle damage
- The Gemini Vision API analyzes it within 5-10 seconds

### 3. **Review Assessment**

The AI returns:

- **Damage Type** (scratch, dent, structural, paint, glass)
- **Severity** (minor, moderate, severe)
- **Vehicle Area** (bumper, door, fender, roof, etc.)
- **Confidence Score** (0-100%)
- **Recommended Action** (fast_track, agent_review, escalate_to_adjuster)

### 4. **Override if Needed**

If the assessment is wrong:

- Type "override" to correct the damage type, severity, or area
- Your correction is logged and sent to senior adjuster
- System learns from your feedback

### 5. **Generate Cost Estimate**

- Type "estimate" to get repair cost range
- Based on damage classification + vehicle specs
- Shows parts needed and estimated labor hours

### 6. **Approve or Escalate**

- Type "approve" to accept and send to authorization queue
- Type "escalate" to send to senior adjuster (if confidence < 75%)

## API Endpoints

### Backend (FastAPI)

**GET `/health`**

- Health check
- Response: `{"status": "ok", "service": "ClaimAssist Backend"}`

**GET `/claims/{claim_id}`**

- Retrieve claim context data
- Response: `{claim_id, policy_number, vehicle_make_model, vehicle_year, ...}`

**POST `/assess-damage?claim_id={claim_id}`**

- Upload image and get damage assessment
- Request: `multipart/form-data` with image file
- Response: `{damage_type, severity, vehicle_area, confidence_score, flagged_for_review, ...}`

**POST `/estimate-cost`**

- Generate cost estimate based on damage
- Query params: `damage_type`, `severity`, `vehicle_year`, `vehicle_make_model`
- Response: `{low_estimate, high_estimate, estimated_repair_time_hours, parts_likely_needed, ...}`

**POST `/override-assessment`**

- Log agent override of AI assessment
- Request: `{claim_id, original_assessment, override_assessment}`
- Response: `{status: "override_logged"}`

**GET `/claim-logs/{claim_id}`**

- Retrieve audit trail for a claim
- Response: `{claim_id, logs: [{timestamp, action, assessment, agent_override}, ...]}`

## Key Design Decisions

### 1. Agent-First, Not Policyholder-First (MVP)

**Why:** Focuses on the actual bottleneck—manual damage review (30-45 min/claim). Self-service complicates UX and validation. Start with agent control, then expand.

### 2. Confidence Thresholds & Escalation Logic

**Why:** Confidence < 75% automatically escalates to senior adjuster. This prevents errors and shows the system is designed for accuracy, not speed.

### 3. Heuristic Cost Estimation, Not ML

**Why:** Repair costs are rule-based (damage type × vehicle class × parts). No need for LLM; avoids hallucination risk. Simpler, faster, more predictable.

### 4. Every Override Logged

**Why:** Agent feedback is training data. Eventually, we'll fine-tune the model using these signals. This builds a virtuous cycle of improvement.

### 5. Human Accountability

**Why:** The agent decides, not the AI. All reasoning visible. Audit trail for appeals. This preserves trust and legal defensibility.

## Metrics to Track

- **Assessment Time** - Goal: < 8 min per claim (vs. 30-45 min baseline)
- **AI Accuracy** - Goal: >= 85% match vs. senior adjuster assessment
- **Override Rate** - Goal: 10-15% (high overrides = model drift)
- **Escalation Rate** - Goal: < 8% (low confidence assessments)
- **Claims Resolved < 5 Days** - Goal: 65% in 30 days, 85% in 90 days
- **Customer Satisfaction** - Goal: > 8/10 (maintain trust)

## File Structure

```
app/
├── backend.py              # FastAPI backend with Gemini Vision integration
├── frontend.py             # Chainlit frontend for claims agent
├── requirements.txt        # Python dependencies
├── README.md              # This file
├── uploads/               # Uploaded claim images (created at runtime)
└── logs/                  # Audit logs by claim (created at runtime)
```

## Troubleshooting

### "Connection refused" Error

- Ensure both backend and frontend are running
- Check ports: Backend should be 8000, Chainlit should be 8001
- If ports are in use: `lsof -i :8000` or `lsof -i :8001`

### "AssertionError: event_loop already created"

- This can happen with async/await in certain environments
- Workaround: Run in separate terminals or use `python -m` for both services

### No Assessment Results

- Ensure the image shows actual vehicle damage (not blank/text)
- Try a different image if Gemini can't classify
- Check backend logs for detailed error messages

## Next Steps for Production

1. **Database** - Replace mock MOCK_CLAIMS with real database (PostgreSQL + SQLAlchemy)
2. **Authentication** - Add user auth to verify claims agents
3. **File Storage** - Move from local `/uploads/` to S3 or cloud storage
4. **Model Fine-tuning** - After collecting 100+ agent overrides, fine-tune on your claims data
5. **A/B Testing** - Compare AI-assisted workflow vs. baseline for time/accuracy
6. **Error Handling** - Graceful fallback if Gemini API is down
7. **Rate Limiting** - Throttle uploads to prevent abuse
8. **Monitoring** - Track confidence scores and override rates over time

## Technical Stack

- **Backend**: FastAPI, Gemini SDK, Python 3.10+
- **Frontend**: Chainlit (built on Langchain)
- **AI Model**: Gemini Flash
- **Storage**: Local filesystem (demo), should migrate to S3
- **Logging**: JSONL audit logs per claim

---

**Author:** Sarah Alzmami
**Status:** MVP Prototype
