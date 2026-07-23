# MODULE 2: MEASUREMENT CAPTURE (PHOTO CAPTURE & ESTIMATION)

## 1. Module Overview

**Module name:** Measurement Capture (Photo Capture & Body Measurement Estimation)

**Main objective:** Automatically extract a user's real body measurements from photos, removing the need for a physical measuring tape.

**What it does:** It allows the user to submit two photos (front and profile), enter their total height, and receive in return their chest, waist, and hip circumferences, as well as their body shape (morphology).

## 2. Position in the System

The Measurement Capture module communicates with:
- Authentication and user profile
- Ease Allowance Calculation Engine (Module 5)
- Fabric/pattern/body-shape compatibility verification engine

## 3. Actors Involved

- **Client / End user:** Provides their height and photos to obtain their measurements.
- **Automated system (Vision & Geometry Algorithm):** Analyzes the images, places anatomical landmarks, and calculates circumferences.

## 4. Functional Description

The module allows:
- Uploading a front-view photo and a profile-view photo.
- Entering overall stature (height in centimeters).
- Detecting the body silhouette and contours.
- Calculating raw anatomical measurements (chest, waist, hips).
- Identifying the corresponding body-shape category.

## 5. Glossary

- **Stature:** The total height of a person measured while standing, from head to feet.
- **Raw measurement:** Exact anatomical body measurement (skin-level), calculated mathematically before any adjustment for garment construction.
- **Chest/Waist/Hip ratio:** Mathematical proportions between chest, waist, and hips used to classify a body shape.

## 6. Use Case

**Name:** Estimate anatomical measurements

**Goal:** Obtain chest, waist, and hip circumferences without a physical tape measure.

**Trigger:** The user submits their two photos and their stature.

**Steps:**
1. The system validates the format and presence of both images (front and profile).
2. The algorithm detects key body landmarks (shoulders, waist, hips).
3. The system converts pixel dimensions into centimeters based on the provided stature.
4. The system applies the ellipse formula to estimate circumferences.
5. The system compares proportions to determine body shape.

**Result:** Raw measurements and body shape are saved and displayed.

## 7. Business Rules

- A capture session requires both a front photo AND a profile photo.
- The entered stature must be a positive value between 100 cm and 250 cm.
- The body-shape classification must correspond to one of the 5 target silhouettes (Hourglass, Rectangle, Pear, Inverted Triangle, Apple).

## 8. Module States

- **empty** → No photo or stature provided for this session.
- **processing** → Image analysis and geometric calculations in progress.
- **success** → Measurements extracted and body shape successfully identified.
- **failed** → Extraction failed (body not detected, poor image quality).

## 9. Interactions with Other Modules

- **Input:** `profile.capture_submitted` (Triggered when the user submits the capture form).
- **Action:** Image analysis and body-shape profile calculation.
- **Output:** `measurements.brute_calculated` (Sends the raw chest/waist/hip circumferences and the body shape to the database and to the ease allowance engine).

## 10. Error Handling

**Error:** Key anatomical landmarks not found in the photo (e.g., insufficient lighting or overly loose clothing).

**Response:** Cancel processing, move to the `failed` state, and display a message to the user: *"The system was unable to identify your body shape. Please retake the photos in a well-lit area wearing form-fitting clothing."*
