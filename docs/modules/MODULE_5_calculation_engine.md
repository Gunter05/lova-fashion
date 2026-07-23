# MODULE 5: EASE ALLOWANCE CALCULATION ENGINE

## 1. Module Overview

**Module name:** Ease Allowance Calculation Engine

**Main objective:** Adapt raw body measurements to convert them into real sewing measurements, ready for garment cutting.

**What it does:** It takes as input the chest, waist, and hip circumferences measured at skin level, looks at the selected fabric, and adds or removes safety centimeters (ease) so that the final garment is comfortable and wearable.

## 2. Position in the System

The Ease Allowance Calculation Engine communicates with:
- Measurement Capture (Module 2 — to retrieve raw measurements)
- Fabric catalog (to obtain elasticity and rigidity rates)
- Final result / Report (to transmit the adjusted cutting pattern)

## 3. Actors Involved

- **Automated system (Business Rules Engine):** Applies the mathematical adjustment formulas.
- **Tailor / Seamstress (Indirect recipient):** Receives the final adjusted measurements to cut the fabric.

## 4. Functional Description

The module allows:
- Linking existing raw measurements to a specific fabric.
- Applying a positive ease value (widening) for non-elastic fabrics.
- Applying a negative ease value (fitting/contraction) for stretch fabrics.
- Generating the final technical sheet of adjusted measurements for garment construction.

## 5. Glossary

- **Ease (Ease allowance):** Additional space added to body measurements in a garment to allow movement, sitting, and comfortable breathing.
- **Rigid fabric:** Non-elastic textile (e.g., Wax print) that requires a mandatory positive ease allowance to prevent the garment from tearing with movement.
- **Stretch fabric:** Elastic textile (e.g., Jersey) capable of stretching, requiring a reduced or negative ease allowance to stay fitted to the body.

## 6. Use Case

**Name:** Adjust the sewing pattern according to the fabric

**Goal:** Obtain the final adjusted measurements for manufacturing.

**Trigger:** The user selects a fabric for their project.

**Steps:**
1. The system retrieves the user's raw measurements.
2. The system queries the physical properties of the selected fabric.
3. The system applies the mathematical rule associated with the fabric (e.g., +4 cm for Wax).
4. The system calculates the new chest, waist, and hip values.

**Result:** The adjusted sewing pattern measurements are generated.

## 7. Business Rules

- If the fabric has the property `elasticity: "rigid"` (e.g., Wax print), the engine must add a minimum standard ease allowance of **+4 cm** to all zones.
- If the fabric has the property `elasticity: "stretch"` (e.g., Jersey), the engine must apply a negative ease allowance of **−2 cm**.
- Final adjusted measurements can never be lower than 0 cm.

## 8. Module States

- **idle** → Waiting for raw measurement data or fabric selection.
- **calculated** → Ease successfully applied, final garment measurements available.

## 9. Interactions with Other Modules

- **Input:** `measurements.brute_calculated` OR `catalog.fabric_selected` (Receives the signal as soon as raw measurements and fabric are both known).
- **Action:** Mathematical calculation of the adjusted pattern lines.
- **Output:** `ease.calculation_completed` (Sends the final adjusted measurement report to the synthesis module).

## 10. Error Handling

**Error:** The selected fabric has no elasticity or ease properties defined in the database.

**Response:** The engine applies a default standard safety margin of **+3 cm** to avoid blocking the application, and generates a system alert for the administrator to correct the fabric record.
