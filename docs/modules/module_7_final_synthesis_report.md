# Module 7: Final Result and Report (Synthesis)

## 1. Module Overview
* **Module Name:** Final Result and Report (Synthesis)
* **Primary Objective:** Act as the final display and aggregation layer by providing the user with a clear synthesis containing adjusted body measurements, compatibility status, and personalized recommendations.
* **Key Capabilities:**
  * Retrieve and centralize all results produced by the calculation engines (Modules 5 and 6).
  * Create, edit, and store the measurement report (`Rapport_mesure`).
  * Display a comprehensive visual and textual assessment for the client or tailor (verdict, alerts, cutting adjustments, recommendations).

## 2. System Position
* **Connected Modules:** Module 1 (Authentication and User Profile), Module 3 (Fabric Catalog), Module 4 (Garment Model Catalog), Module 5 (Ease Allowance Calculation Engine), Module 6 (Compatibility Verification Engine).
* **Dependencies:** This module serves as the final endpoint of the system. It relies entirely on data provided by the modules mentioned above.

## 3. Stakeholders / Actors
* **Human Users:**
  * Client (Consults the final report to verify if the chosen garment and fabric are suitable).
  * Stylist / Tailor (Consults the report to view adjusted measurements and apply cutting recommendations during garment construction).
* **Automated Systems:** User Interface (UI) / Report Rendering Engine.

## 4. Functional Description
This module enables the system to:
* Receive notifications upon completion of combination processing (Measurement + Fabric + Garment Model).
* Instantiate the measurement report by linking the measurement ID, fabric ID, and garment model ID.
* Format and display the adjusted measurements supplied by the ease allowance calculation engine.
* Display the overall compatibility verdict (e.g., *"Compatible"*, *"Incompatible"*, *"Minor adjustments needed"*).
* Formulate and present explicit advice or warnings (e.g., *"Caution: Fabric is very rigid for a fitted model, add +2cm ease allowance to chest circumference"*).

## 5. Glossary
* **Verdict:** The final qualitative status indicating whether the combination of body shape, fabric, and model is feasible without risk.
* **Adjusted Measurements:** Target body dimensions obtained after applying ease allowance or elasticity coefficients.
* **Advice / Recommendations:** Textual guidance intended to direct the user or tailor based on the verdict outcome.

## 6. User Use Cases

### User Case: Display and Consult Synthesis Report
* **Goal:** Present the complete compatibility summary and adjusted measurements to the client and tailor.
* **Trigger:** The Compatibility Verification Engine (Module 6) completes the combination evaluation.
* **Steps:**
  1. The system aggregates data from Measurement (Module 1), Fabric (Module 3), Garment Model (Module 4), Adjusted Measurements (Module 5), and Verdict (Module 6).
  2. The module creates the measurement report record along with its generation date (`date_generation`).
  3. The interface renders the report component using color-coded verdicts (Green = Compatible, Red = Incompatible).
  4. The user reviews detailed measurements and tailoring recommendations.
* **Outcome:** The report is displayed on-screen and saved to the user's history.

## 7. Business Rules
* A measurement report must strictly be linked to one and only one Measurement entry, one Fabric, and one Garment Model.
* A Measurement record, Fabric, or Garment Model can appear in multiple measurement reports or none.
* If Module 6 yields an "Incompatible" verdict, the report must explicitly highlight error or incompatibility zones in red alongside clear explanations.
* A generated report is immutable; it reflects the exact state of calculations at its generation timestamp (`date_generation`).

## 8. Module States
* `waiting_data`: Awaiting output from calculation modules 5 and 6.
* `rendering`: Aggregating data and building the synthesis view.
* `displayed`: Report rendered and viewable by the user.
* `saved`: Report archived and accessible within the user profile.

## 9. Interactions with Other Modules
* **Incoming Events (Inputs):**
  * `measurements.adjusted` *(from Module 5: Ease Allowance Engine)*: Transmits JSON containing recalculated body dimensions based on fabric stiffness.
  * `compatibility.evaluated` *(from Module 6: Compatibility Engine)*: Transmits the verdict ("compatible"/"incompatible") and alert details.
  * `fabric.details` *(from Module 3: Fabric Catalog)*: Receives fabric name and thumbnail image.
  * `model.details` *(from Module 4: Model Catalog)*: Receives garment name, photo, and description.
* **Triggered Action:** Creation of the `Rapport_mesure` entity and generation of the synthesis view.
* **Outgoing Events (Outputs):**
  * `report.rendered` *(to User Interface)*: Renders the final report view.
  * `report.saved` *(to Module 1: User Profile)*: Archives the generated report record into the client account history.

## 10. Error Handling
* **Error:** Failure to receive data from upstream modules (e.g., Module 5 or 6 calculation timeout).
  * **Response:** Abort report generation and display the message: *"Unable to generate report. Please check selected fabric and model."*
* **Error:** Excessively long recommendation text or corrupted data (inconsistent, missing, or negative values).
  * **Response:** Block report generation, display the message *"Certain measurements are invalid. Please retake body measurements"*, and log the error in system logs.