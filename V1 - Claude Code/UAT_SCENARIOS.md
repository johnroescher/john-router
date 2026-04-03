## User Acceptance Testing (UAT) Scenarios

This document defines beta testing scenarios and feedback collection for the enhanced route planning system.

### Goals
- Validate that end-to-end conversational route planning works for multiple disciplines.
- Confirm clarification, modification, and proactive suggestion flows.
- Collect structured feedback for prompt and threshold tuning.

### Scenario 1: Classic Road Loop
- **Prompt:** "I want a 30km road loop starting near Boulder."
- **Expected:** 2-3 candidates, one selected; summary with distance, elevation, surface.
- **Verify:** Route within 20% distance target; response mentions local context.

### Scenario 2: MTB Named Route
- **Prompt:** "Can you take me on a classic MTB route around Moab?"
- **Expected:** Named route surfaced if available; candidate generation includes named route hints.
- **Verify:** Strategy includes classic/named route; response references trail name.

### Scenario 3: Exploration Gravel Ride
- **Prompt:** "I want a 25km gravel ride exploring new areas."
- **Expected:** Explorer strategy favored; route includes waypoint exploration.
- **Verify:** Suggests less-traveled paths; shows exploration rationale.

### Scenario 4: Clarification Flow
- **Prompt:** "I want a ride this afternoon."
- **Expected:** Clarification question about distance or discipline.
- **Verify:** Clarification displayed and subsequent user answer updates intent.

### Scenario 5: Modify Route Mid-Conversation
- **Prompt:** "Make it longer and avoid hills."
- **Expected:** Route modifier adjusts constraints; re-evaluation and updated route.
- **Verify:** New route length increases and elevation decreases.

### Scenario 6: Proactive Suggestions
- **Prompt:** "Give me a relaxed ride."
- **Expected:** Suggestions for flatter alternative or shorter loop.
- **Verify:** Action chips appear and trigger new request when clicked.

### Scenario 7: Knowledge Mention
- **Prompt:** "Any good gravel routes near Golden?"
- **Expected:** Knowledge retrieval adds local insight; response references area info.
- **Verify:** Response includes at least one local tip or named location.

### Feedback Collection
Collect feedback after each scenario:
- **Rating (1-5):** Overall satisfaction
- **Intent Match (1-5):** Did the route match the ask?
- **Clarity (1-5):** Was the explanation clear?
- **Trust (1-5):** Would you ride this route?
- **Open Feedback:** Free-form comments
- **Scenario ID:** Link feedback to scenario
- **Timestamp + Session ID**

### Tuning Notes
- Log common misunderstandings and missing constraints.
- Adjust LLM prompts for response clarity and local tone.
- Tune evaluation thresholds if too many candidates rejected.
