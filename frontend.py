"""
Chainlit frontend for ClaimAssist
Provides claims agent workflow: upload image → assess damage → review → approve → cost estimate
"""

import os
import json
from chainlit.logger import logger
import httpx
import chainlit as cl
from pathlib import Path
from pathlib import Path

from settings import settings

# Styling and message templates
cl.instrument_langchain_package = (
    False  # Disable LangChain instrumentation for this demo
)


@cl.on_chat_start
async def start():
    """Initialize the claims assessment session"""

    cl.user_session.set("claim_id", "CLM-2024-001")
    cl.user_session.set("assessment", None)
    cl.user_session.set("estimate", None)

    # Fetch initial claim context
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{settings.backend_url}/claims/CLM-2024-001")
            claim_data = response.json()
            cl.user_session.set("claim_context", claim_data)
    except Exception as e:
        claim_data = {
            "claim_id": "CLM-2024-001",
            "policy_number": "POL-987654",
            "vehicle_make_model": "Toyota Camry",
            "vehicle_year": 2021,
            "damage_description": "Rear-end collision at traffic light",
        }
        cl.user_session.set("claim_context", claim_data)

    # Welcome message with claim context
    await cl.Message(content=f"""
# ClaimAssist: AI-Powered Damage Assessment

## Claim Overview
- **Claim ID:** {claim_data.get('claim_id')}
- **Policy:** {claim_data.get('policy_number')}
- **Vehicle:** {claim_data.get('vehicle_make_model')} ({claim_data.get('vehicle_year')})
- **Reported Damage:** {claim_data.get('damage_description')}

---

## Next Steps

1. **Upload a damage photo** - I'll analyze it using AI vision
2. **Review the assessment** - Damage type, severity, confidence level
3. **Override if needed** - Correct the AI if you see something different
4. **Generate estimate** - Get repair cost range based on damage
5. **Approve or escalate** - Make the final call

**Instructions:** Type a message or upload an image file to start.
        """).send()


@cl.on_message
async def handle_message(message: cl.Message):
    """Process user messages and images"""

    claim_context = cl.user_session.get("claim_context")
    claim_id = cl.user_session.get("claim_id")

    # Check if user uploaded an image
    if message.elements:
        image_element = next(
            (el for el in message.elements if "image" in el.mime), None
        )

        if image_element:
            # Process image upload
            await process_damage_image(image_element, claim_id, claim_context)
            return

    # Handle text commands
    text = message.content.lower()

    if "estimate" in text or "cost" in text:
        await generate_cost_estimate()
    elif "override" in text or "change" in text or "correct" in text:
        await show_override_options()
    elif "approve" in text or "accept" in text:
        await approve_assessment()
    elif "escalate" in text or "adjuster" in text:
        await escalate_to_adjuster()
    else:
        # Generic help
        await cl.Message(content="""
I'm ready to help with damage assessment. What would you like to do?

- **Upload photo** - Send me an image of vehicle damage
- **View estimate** - Get cost estimate (type: estimate)
- **Override assessment** - Correct the AI assessment (type: override)
- **Approve** - Accept assessment and move forward (type: approve)
- **Escalate** - Send to senior adjuster (type: escalate)
            """).send()


async def process_damage_image(image_element, claim_id: str, claim_context: dict):
    """
    Process uploaded image through Claude Vision for damage assessment
    Handles Chainlit file elements properly
    """

    # Handle Chainlit file element
    image_path = None

    # Try to get the file path directly
    if hasattr(image_element, "path"):
        image_path = image_element.path

    # If no path, try to save from content
    if not image_path:
        try:
            image_path = f"/tmp/claim_{claim_id}_{image_element.name}"

            # Handle different content types
            if hasattr(image_element, "content"):
                content = image_element.content

                # If it's a string path, use it directly
                if isinstance(content, str) and Path(content).exists():
                    image_path = content
                # If it's bytes, write to file
                elif isinstance(content, bytes):
                    with open(image_path, "wb") as f:
                        f.write(content)
                else:
                    # Try reading from the element's file if available
                    logger.warning(f"Unexpected content type: {type(content)}")
                    image_path = None
        except Exception as e:
            logger.error(f"Error accessing image element: {str(e)}")
            image_path = None

    if not image_path or not Path(image_path).exists():
        await cl.Message(
            content="❌ Error: Could not process image file. Please try uploading again."
        ).send()
        return

    # Show processing message
    await cl.Message(
        content="🔍 Analyzing damage photo with AI vision model...",
    ).send()

    try:
        # Send to backend for assessment
        async with httpx.AsyncClient(timeout=30) as client:
            with open(image_path, "rb") as f:
                files = {"file": f}
                response = await client.post(
                    f"{settings.backend_url}/assess-damage?claim_id={claim_id}", files=files
                )

            if response.status_code != 200:
                await cl.Message(
                    content=f"❌ Assessment failed: {response.text}"
                ).send()
                return

            assessment = response.json()
            cl.user_session.set("assessment", assessment)

    except Exception as e:
        await cl.Message(
            content=f"❌ Error connecting to assessment service: {str(e)}"
        ).send()
        return

    # Format and display assessment
    confidence_icon = (
        "🟢"
        if assessment["confidence_level"] == "high"
        else "🟡" if assessment["confidence_level"] == "medium" else "🔴"
    )

    warning_text = ""
    if assessment["flagged_for_review"]:
        warning_text = """
⚠️ **FLAGGED FOR REVIEW** - Confidence below 75%
Consider escalating to senior adjuster for second opinion.
        """

    assessment_text = f"""
## Damage Assessment Results

{confidence_icon} **Confidence:** {assessment['confidence_score']:.0f}% ({assessment['confidence_level'].upper()})

**Damage Type:** `{assessment['damage_type']}`
**Severity:** `{assessment['severity']}`
**Vehicle Area:** `{assessment['vehicle_area']}`

**Description:**
> {assessment['description']}

**Recommended Action:** `{assessment['recommended_action']}`

{warning_text}

---

### Next Steps
- Type **estimate** to see repair cost range
- Type **override** to correct the assessment
- Type **approve** to accept and move forward
- Type **escalate** to send to senior adjuster
    """

    await cl.Message(content=assessment_text).send()


async def generate_cost_estimate():
    """Generate cost estimate based on damage assessment"""

    assessment = cl.user_session.get("assessment")
    claim_context = cl.user_session.get("claim_context")

    if not assessment:
        await cl.Message(
            content="⚠️ Please upload and assess a damage photo first."
        ).send()
        return

    # Show processing
    await cl.Message(
        content="💰 Generating cost estimate...",
    ).send()

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{settings.backend_url}/estimate-cost",
                params={
                    "damage_type": assessment["damage_type"],
                    "severity": assessment["severity"],
                    "vehicle_year": claim_context["vehicle_year"],
                    "vehicle_make_model": claim_context["vehicle_make_model"],
                },
            )

            if response.status_code != 200:
                await cl.Message(
                    content=f"❌ Estimation failed: {response.text}"
                ).send()
                return

            estimate = response.json()
            cl.user_session.set("estimate", estimate)

    except Exception as e:
        await cl.Message(content=f"❌ Error: {str(e)}").send()
        return

    # Format estimate
    estimate_text = f"""
## Repair Cost Estimate

**Estimated Cost Range:** `${estimate['low_estimate']:,} - ${estimate['high_estimate']:,}`

**Labor Estimate:** ${estimate['labor_estimate']:,}
**Estimated Repair Time:** {estimate['estimated_repair_time_hours']} hours

**Parts Likely Needed:**
"""

    for part in estimate["parts_likely_needed"]:
        estimate_text += f"\n- {part}"

    estimate_text += """

---

### Ready to Approve?
- Type **approve** to accept this estimate
- Type **override** to adjust the assessment
- Type **escalate** for senior adjuster review
    """

    await cl.Message(content=estimate_text).send()


async def show_override_options():
    """Show options for overriding AI assessment"""

    assessment = cl.user_session.get("assessment")

    if not assessment:
        await cl.Message(
            content="⚠️ Please assess a photo first before overriding."
        ).send()
        return

    override_text = f"""
## Override Assessment

**Current AI Assessment:**
- Damage Type: `{assessment['damage_type']}`
- Severity: `{assessment['severity']}`
- Vehicle Area: `{assessment['vehicle_area']}`
- Confidence: {assessment['confidence_score']:.0f}%

---

### What would you like to change?

**Damage Types:** scratch | dent | structural | paint | glass | multiple | other

**Severity Levels:** minor | moderate | severe

**Vehicle Areas:** bumper | door | fender | roof | windshield | hood | side-panel | other

**Example:** "Change to dent, severe, door"

*(Your changes are logged for model improvement)*
    """

    await cl.Message(content=override_text).send()


async def approve_assessment():
    """Approve the current assessment and proceed"""

    assessment = cl.user_session.get("assessment")
    estimate = cl.user_session.get("estimate")
    claim_id = cl.user_session.get("claim_id")

    if not assessment:
        await cl.Message(
            content="⚠️ No assessment to approve. Please upload an image first."
        ).send()
        return

    approval_text = f"""
✅ **Assessment Approved**

**Claim:** {claim_id}
**Damage:** {assessment['damage_type'].upper()} ({assessment['severity']})
**Confidence:** {assessment['confidence_score']:.0f}%

**Estimated Cost Range:** ${estimate['low_estimate']:,} - ${estimate['high_estimate']:,}

---

### Status
This assessment has been logged and sent to the authorization queue.

**Next Steps:**
1. Senior adjuster will review estimate
2. Approval authorization will be sent to repair shop
3. Policyholder will be notified of authorized amount

**Claim Status:** `ASSESSMENT_APPROVED` → `AWAITING_AUTHORIZATION`
    """

    await cl.Message(content=approval_text).send()


async def escalate_to_adjuster():
    """Escalate claim to senior adjuster"""

    assessment = cl.user_session.get("assessment")
    claim_id = cl.user_session.get("claim_id")

    if not assessment:
        await cl.Message(content="⚠️ Please assess a photo before escalating.").send()
        return

    escalation_text = f"""
📋 **Escalation Initiated**

**Reason for Escalation:**
- Low confidence assessment (< 75%)
- Complex or structural damage
- Multiple damage types detected

**Claim Details:**
- Claim ID: {claim_id}
- AI Confidence: {assessment['confidence_score']:.0f}%
- Damage: {assessment['damage_type']} ({assessment['severity']})

---

**Status:** `ESCALATED_TO_SENIOR_ADJUSTER`

This claim will be reviewed by an expert adjuster within 2-4 hours.
The policyholder will be notified of any status changes.
    """

    await cl.Message(content=escalation_text).send()


# Run with: chainlit run app/frontend.py --host 0.0.0.0 --port 8001
