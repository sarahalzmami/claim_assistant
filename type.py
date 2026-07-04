from dataclasses import dataclass

@dataclass
class DamageAssessment:
    """Structure for damage assessment results"""

    damage_type: str  # scratch, dent, structural, paint, glass, etc.
    severity: str  # minor, moderate, severe
    vehicle_area: str  # bumper, door, fender, roof, windshield, etc.
    description: str  # detailed explanation from model
    confidence_score: float  # 0-100
    confidence_level: str  # low, medium, high
    flagged_for_review: bool  # True if confidence < 75%
    recommended_action: str  # next step


@dataclass
class CostEstimate:
    """Structure for cost estimation"""

    low_estimate: float  # USD
    high_estimate: float  # USD
    estimated_repair_time_hours: int
    parts_likely_needed: list[str]
    labor_estimate: float


@dataclass
class ClaimContext:
    """Mock claim data for demonstration"""

    claim_id: str
    policy_number: str
    vehicle_make_model: str
    vehicle_year: int
    accident_date: str
    reported_by: str
    damage_description: str