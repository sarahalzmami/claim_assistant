"""
FastAPI backend for ClaimAssist - AI-powered vehicle damage assessment
Handles image uploads, Claude Vision API calls, and assessment logic
"""
import json
import base64
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import  asdict

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import google.generativeai as genai
from type import ClaimContext, CostEstimate, DamageAssessment

from settings import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="ClaimAssist Backend",
    description="AI-powered vehicle damage assessment for claims agents",
    version="0.1.0",
)

# Enable CORS for Chainlit
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Google Generative AI client
genai.configure(api_key=settings.llm_api_key)
model = genai.GenerativeModel("gemini-3-flash-preview")

# Storage paths
UPLOAD_DIR = Path("./uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
LOG_DIR = Path("./logs")
LOG_DIR.mkdir(exist_ok=True)

# Mock claims database for demo
MOCK_CLAIMS = {
    "CLM-2024-001": ClaimContext(
        claim_id="CLM-2024-001",
        policy_number="POL-987654",
        vehicle_make_model="Toyota Camry",
        vehicle_year=2021,
        accident_date="2024-06-25",
        reported_by="John Smith",
        damage_description="Rear-end collision at traffic light",
    ),
    "CLM-2024-002": ClaimContext(
        claim_id="CLM-2024-002",
        policy_number="POL-987655",
        vehicle_make_model="Honda Civic",
        vehicle_year=2022,
        accident_date="2024-06-26",
        reported_by="Sarah Johnson",
        damage_description="Side-swipe in parking lot",
    ),
}


def encode_image_to_base64(image_path: str) -> str:
    """Convert image file to base64 for Claude API"""
    try:
        if not Path(image_path).exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        with open(image_path, "rb") as image_file:
            return base64.standard_b64encode(image_file.read()).decode("utf-8")
    except Exception as e:
        logger.error(f"Error encoding image: {str(e)}")
        raise


def assess_damage_with_vision(image_path: str) -> dict:
    """
    Use Google Gemini Vision API to analyze vehicle damage in the image
    Returns structured assessment with confidence scores
    """
    try:
        # Encode image to base64
        image_data = encode_image_to_base64(image_path)

        # Determine image media type
        file_ext = Path(image_path).suffix.lower()
        media_type_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        media_type = media_type_map.get(file_ext, "image/jpeg")

        # Create image part for Gemini
        image_part = {"mime_type": media_type, "data": image_data}

        # Call Gemini Vision API with structured prompt
        response = model.generate_content(
            [
                image_part,
                """You are an expert vehicle damage assessor for an insurance company. Analyze this vehicle damage image and provide a structured assessment.

IMPORTANT: Respond ONLY with valid JSON, no preamble or markdown.

Return this exact JSON structure:
{
  "damage_type": "scratch|dent|structural|paint|glass|multiple",
  "severity": "minor|moderate|severe",
  "vehicle_area": "bumper|door|fender|roof|windshield|hood|side-panel|other",
  "description": "detailed technical description of damage",
  "confidence_score": 0-100,
  "is_drivable": true|false,
  "recommended_parts": ["part1", "part2"],
  "notes": "any additional observations"
}

Confidence score should reflect how certain you are about the assessment.
Be conservative: if you're not sure, lower the confidence score.
If the image doesn't show a vehicle or is unclear, set confidence_score to 0.""",
            ]
        )

        # Parse response
        response_text = response.text.strip()

        # Try to extract JSON if response includes text before/after
        try:
            # First try parsing directly
            assessment_raw = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to find JSON in response
            import re

            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if json_match:
                assessment_raw = json.loads(json_match.group())
            else:
                raise ValueError("Could not extract JSON from model response")

        # Calculate confidence level
        confidence = assessment_raw.get("confidence_score", 0)
        if confidence >= 90:
            confidence_level = "high"
        elif confidence >= 75:
            confidence_level = "medium"
        else:
            confidence_level = "low"

        # Create structured response
        assessment = DamageAssessment(
            damage_type=assessment_raw.get("damage_type", "unknown"),
            severity=assessment_raw.get("severity", "unknown"),
            vehicle_area=assessment_raw.get("vehicle_area", "unknown"),
            description=assessment_raw.get("description", ""),
            confidence_score=confidence,
            confidence_level=confidence_level,
            flagged_for_review=confidence < 75,
            recommended_action=(
                "escalate_to_adjuster"
                if confidence < 75
                else ("fast_track" if confidence >= 90 else "agent_review")
            ),
        )

        logger.info(
            f"Damage assessment: {assessment.damage_type} ({assessment.severity}) - Confidence: {assessment.confidence_score}%"
        )
        return asdict(assessment)

    except Exception as e:
        logger.error(f"Error in damage assessment: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Assessment failed: {str(e)}")


def estimate_repair_cost(
    damage_type: str, severity: str, vehicle_year: int, vehicle_make_model: str
) -> dict:
    """
    Estimate repair costs based on damage classification
    Uses simple heuristic: severity tier × vehicle class + parts lookup
    """
    # Base costs by severity (labor + typical parts for that severity)
    severity_base = {"minor": 300, "moderate": 800, "severe": 2000}

    # Vehicle value tier (impacts labor rate)
    vehicle_value_tier = 1.0  # baseline
    if vehicle_year >= 2020:
        vehicle_value_tier = 1.2
    if "luxury" in vehicle_make_model.lower() or any(
        x in vehicle_make_model.lower() for x in ["bmw", "audi", "mercedes", "lexus"]
    ):
        vehicle_value_tier = 1.5

    # Damage-specific multipliers
    damage_multiplier = {
        "scratch": 0.8,
        "paint": 1.0,
        "dent": 1.2,
        "glass": 1.5,
        "structural": 2.5,
        "multiple": 2.0,
    }

    base_cost = severity_base.get(severity, 500)
    multiplier = damage_multiplier.get(damage_type, 1.0)

    estimated_cost = base_cost * multiplier * vehicle_value_tier

    # Add 15% uncertainty range
    low_estimate = estimated_cost * 0.85
    high_estimate = estimated_cost * 1.15

    # Estimate labor hours (0.5-16 hours depending on severity/type)
    labor_hours = {"minor": 1, "moderate": 4, "severe": 8}.get(severity, 2)

    # Parts likely needed
    parts_map = {
        "scratch": ["Touch-up paint", "Clear coat"],
        "paint": ["Paint materials", "Clear coat", "Primer"],
        "dent": ["PDR tools (no parts if using paintless dent removal)"],
        "glass": ["Replacement windshield/window", "Adhesive", "Trim"],
        "structural": [
            "Frame straightening or replacement",
            "Suspension components",
            "Alignment",
        ],
        "multiple": ["Multiple replacement parts", "Paint", "Suspension work"],
    }

    estimate = CostEstimate(
        low_estimate=round(low_estimate),
        high_estimate=round(high_estimate),
        estimated_repair_time_hours=labor_hours,
        parts_likely_needed=parts_map.get(damage_type, ["Assessment-based parts TBD"]),
        labor_estimate=round(estimated_cost * 0.4),  # Labor typically 40% of total
    )

    return asdict(estimate)


def log_claim_action(
    claim_id: str, action: str, assessment: dict, override: Optional[dict] = None
):
    """Log all claim assessment actions for audit trail"""
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "claim_id": claim_id,
        "action": action,
        "assessment": assessment,
        "agent_override": override,
    }

    log_file = LOG_DIR / f"claim_{claim_id}_audit.jsonl"
    with open(log_file, "a") as f:
        f.write(json.dumps(log_entry) + "\n")

    logger.info(f"Logged action for claim {claim_id}: {action}")


# ============================================================================
# API ENDPOINTS
# ============================================================================


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "ClaimAssist Backend"}


@app.get("/claims/{claim_id}")
async def get_claim(claim_id: str):
    """Retrieve claim context data"""
    claim = MOCK_CLAIMS.get(claim_id)
    if not claim:
        # Return a default claim for demo
        claim = MOCK_CLAIMS["CLM-2024-001"]

    return asdict(claim)


@app.post("/assess-damage")
async def assess_damage(file: UploadFile = File(...), claim_id: str = "CLM-2024-001"):
    """
    Upload image and get AI damage assessment

    Returns:
    - damage_type, severity, vehicle_area
    - confidence_score and confidence_level
    - flagged_for_review if confidence < 75%
    - recommended_action (fast_track, agent_review, escalate_to_adjuster)
    """
    try:
        # Validate file
        if not file or not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")

        # Check file type
        allowed_types = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in allowed_types:
            raise HTTPException(
                status_code=400, detail=f"Invalid file type. Allowed: {allowed_types}"
            )

        # Save uploaded file
        file_path = (
            UPLOAD_DIR / f"{claim_id}_{int(datetime.now().timestamp())}_{file.filename}"
        )
        content = await file.read()

        if not content:
            raise HTTPException(status_code=400, detail="File is empty")

        with open(file_path, "wb") as f:
            f.write(content)

        logger.info(
            f"Image uploaded for claim {claim_id}: {file.filename} ({len(content)} bytes)"
        )

        # Get assessment from Claude Vision
        assessment = assess_damage_with_vision(str(file_path))

        # Log the action
        log_claim_action(claim_id, "damage_assessed", assessment)

        return JSONResponse(content=assessment)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in damage assessment endpoint: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Assessment failed: {str(e)}")


@app.post("/estimate-cost")
async def estimate_cost(
    damage_type: str, severity: str, vehicle_year: int, vehicle_make_model: str
):
    """
    Generate cost estimate based on damage classification

    Inputs from damage assessment + claim context
    Returns low/high estimates, parts needed, labor hours
    """
    try:
        estimate = estimate_repair_cost(
            damage_type=damage_type,
            severity=severity,
            vehicle_year=vehicle_year,
            vehicle_make_model=vehicle_make_model,
        )

        return JSONResponse(content=estimate)

    except Exception as e:
        logger.error(f"Error in cost estimation: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/override-assessment")
async def override_assessment(
    claim_id: str, original_assessment: dict, override_assessment: dict
):
    """
    Agent override of AI assessment - logs for audit trail and feedback

    This is critical: every override is training data for model improvement
    """
    try:
        log_claim_action(
            claim_id=claim_id,
            action="assessment_overridden_by_agent",
            assessment=original_assessment,
            override=override_assessment,
        )

        logger.info(f"Assessment overridden for claim {claim_id}")
        return JSONResponse(content={"status": "override_logged", "claim_id": claim_id})

    except Exception as e:
        logger.error(f"Error logging override: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/claim-logs/{claim_id}")
async def get_claim_logs(claim_id: str):
    """Retrieve audit log for a specific claim"""
    log_file = LOG_DIR / f"claim_{claim_id}_audit.jsonl"

    if not log_file.exists():
        return {"claim_id": claim_id, "logs": []}

    logs = []
    with open(log_file, "r") as f:
        for line in f:
            logs.append(json.loads(line))

    return {"claim_id": claim_id, "logs": logs}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")