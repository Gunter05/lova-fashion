# Module 6: Fabric/Model/Silhouette Compatibility Engine

## 1. Overview
*   **Name:** Fabric/Model/Silhouette Compatibility Verification Engine
*   **Main Objective:** Determine, via a system of rules, if the combination of the user's adjusted measurements + garment model + chosen fabric is viable, and flag any incompatibilities.
*   **What it does:** Produces a compatibility verdict (compatible, incompatible, or compatible with reservations) accompanied by explanations for each affected body zone.

## 2. Position in the System
The module sits at the center of the system: it receives data from three upstream modules and transmits its verdict to the downstream reporting module.
*   **Communicates upstream:** Module 5 (adjusted measurements), Module 4 (model constraints), Module 3 (fabric properties).
*   **Communicates downstream:** Module 7 — Report (transmission of the final verdict).

## 3. Actors Involved
*   **End User** — indirectly consumes the verdict via the report.
*   **Module 5** — Ease margins calculation engine (data provider).
*   **Module 4** — Model Catalog (data provider).
*   **Module 3** — Fabric Catalog (data provider).
*   **Module 7** — Report (verdict consumer).
*   **Administrator / Business Expert** — defines and adjusts compatibility rules and thresholds.

## 4. Functional Description
The module compares the user's adjusted measurements to the chosen model's constraints, taking into account the selected fabric's rigidity and elasticity. It then applies a set of rules to judge whether the association is viable, body zone by body zone.
**Expected result:** A clear verdict (compatible / incompatible / compatible with reservations), accompanied by a plain-language explanation for each identified risk zone.

## 5. Glossary
*   **Verdict:** Final result of the verification: compatible, incompatible, or compatible with reservations.
*   **Risk Zone:** Body part where the gap between the adjusted measurement and the model's constraint exceeds the tolerance threshold.
*   **Tolerance Threshold:** Maximum acceptable gap between the adjusted measurement and the model's measurement before triggering an alert. *(Note: Adapting to our recent discussion, this represents the mathematical or physical limit beyond which making the garment with this specific fabric becomes risky or impossible).*
*   **Compatibility Rule:** Condition combining cut, fabric, and measurement gap, used by the engine to establish a verdict.

## 6. Use Cases

**Case 1: Standard Verification**
*   **Action/Goal:** Obtain a compatibility verdict for a chosen model and fabric.
*   **Trigger:** The user selects a model and fabric after obtaining their measurements.
*   **Steps:** 
    1. Retrieve adjusted measurements (Module 5).
    2. Retrieve model constraints (Module 4).
    3. Retrieve fabric properties (Module 3).
    4. Apply compatibility rules.
    5. Calculate the global and per-zone verdict.
*   **Result:** The verdict is transmitted to the reporting module (Module 7).

**Case 2: Incompatibility Detection**
*   **Action/Goal:** Flag a problematic association between morphology, model, and fabric.
*   **Trigger:** The gap measured on a zone exceeds the tolerance threshold for a fitted cut with a rigid fabric.
*   **Steps:** 
    1. Identify the risk zone(s).
    2. Generate an explanatory message for each affected zone.
    3. Integrate into the global verdict.
*   **Result:** The rendered verdict is "incompatible" or "compatible with reservations," with justification per zone.

**Case 3: Rule Adjustment by a Business Expert**
*   **Action/Goal:** Correct a tolerance threshold deemed too strict or too lenient.
*   **Trigger:** The administrator modifies a rule in the engine's configuration.
*   **Steps:** 
    1. Modify the rules table.
    2. Validate the change.
    3. Apply to future verifications.
*   **Result:** New verifications use the updated threshold; already generated reports are not retroactively recalculated.

## 7. Business Rules
*   A verification requires all three inputs completely (adjusted measurements, model constraints, fabric properties); if data is missing, it cannot be executed.
*   Tolerance thresholds are defined by cut/fabric combination and must be modifiable without changing the engine's code.
*   An "incompatible" verdict must always be accompanied by at least one explanation per affected zone.
*   Rules must be applied deterministically: the same input data always produces the same verdict.

## 8. Module States
*   **Pending:** Verification requested, but not all necessary data is available yet.
*   **In Progress:** Verdict calculation is currently running.
*   **Completed – compatible:** Favorable verdict rendered, no risk zone identified.
*   **Completed – compatible with reservations:** Nuanced verdict: slight gap tolerated, with a warning.
*   **Completed – incompatible:** Unfavorable verdict rendered, one or more risk zones identified.
*   **Failed:** Verification could not be completed (missing data or technical error).

## 9. Interactions with Other Modules
**Events Received**
*   `Adjusted_measurements_available` — received from Module 5
*   `Model_constraints_provided` — received from Module 4
*   `Fabric_properties_provided` — received from Module 3
*   `Verification_request` — triggered by the user, relayed via the interface or Module 7

**Triggered Actions**
*   Aggregation of the three received datasets
*   Application of the compatibility rules engine
*   Calculation of the per-zone verdict, then the global verdict

**Events Sent**
*   `Verdict_available` — sent to Module 7 (report)
*   `Verification_failed` — sent to the caller if data was missing or an error occurred

## 10. Error Handling
*   **Missing data (e.g., fabric not specified):** Verification blocked with a clear message indicating the missing data; no approximate verdict is rendered.
*   **Inconsistent data (e.g., negative or aberrant measurement):** Rejection of the verification and escalation of a validation error.
*   **Missing rule for the encountered cut/fabric combination:** "Indeterminate" verdict rather than a false positive, with an alert sent to the administrator to complete the rules.
*   **Communication failure with a provider module (3, 4, or 5):** Limited automatic retry, then an explicit error message displayed to the user.