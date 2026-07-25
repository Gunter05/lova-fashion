# Module 1: Authentication and User Profile

## 1. Module Overview
The first module is named Authentication and User Profile. Its objective is to manage registration, authentication, user profile management, body measurements history, and profile picture archiving. Specifically, it allows users to:
* Create a user account;
* Manage personal profile information;
* Associate and update a profile picture;
* Record and consult a user's raw body measurements history.

## 2. System Position
This module is connected to all other modules as it allows users to access their dedicated space within the application, use its features, and manage their data. It serves as the foundational building block of the system, providing user and measurement data to the other modules. That said, it does not depend on any other module.

## 3. Stakeholders / Actors
All users (Admin, Stylist/Tailor, and Client) are involved, as a session must be established before using the application. Aside from end users, the application's authentication service and the automated measurement service also interact with this module.

## 4. Functional Description
This module enables the system to:
* Register a user with a unique identifier (National ID/CNI), full name, email, password, and role;
* Authenticate a user to initiate a secure session;
* Store and update the user's profile picture;
* Save a full set of raw body measurements (waist circumference, chest circumference, arm length, etc.) on a given date;
* Maintain a historical log of measurements taken over time for a user.

## 5. Glossary
* **User:** A person registered on the platform holding an active account.
* **CNI:** National Identity Card / ID number serving as the unique key upon registration.
* **Measurement (Mensuration):** Set of raw body dimensions recorded at a specific date.
* **Profile Picture:** Image attached to the user account used as an avatar.

## 6. User Use Cases

### User Case 1: User Registration
* **Goal:** Allow a new user to access the platform.
* **Trigger:** The client clicks on "Sign Up".
* **Steps:**
  1. The client opens the application and enters their details (CNI, name, email, password, role).
  2. The system verifies the uniqueness of the CNI and email address.
  3. The system saves the user account along with the current date (`date_inscription`).
* **Outcome:** The account is created and the user can log in.

### User Case 2: Recording a New Body Measurement
* **Goal:** Save a set of body measurements for a user.
* **Trigger:** Validation of the measurement capture process (manually or via camera).
* **Steps:**
  1. The system retrieves the logged-in user's identifier.
  2. Measurement values (Waist, Chest, Arm Length, etc.) are entered or calculated.
  3. The system generates a unique identifier `idMesure` and links the measurement set to the user.
* **Outcome:** A new measurement record is added to the user's history.

## 7. Business Rules
* A User is uniquely identified by their CNI.
* A User can possess multiple profile pictures over time or none at all, but a specific profile picture belongs to exactly one User.
* A User can record multiple body measurement entries over time, but a Measurement entry belongs strictly to one User.
* The role field defines access permissions within the platform (Client, Tailor, Admin).

## 8. Module States
* `unauthenticated`: Unauthenticated user / Guest
* `authenticated`: Active user session
* `profile_incomplete`: Account created without any recorded body measurements
* `profile_active`: Account with up-to-date profile and measurements

## 9. Interactions with Other Modules
* **Incoming Events (Inputs):**
  * `measurements.estimated` *(from Module 2: Automated Measurement)*: Receives a JSON payload containing body measurement values calculated by the algorithm (chest, waist, hips, etc.) after analyzing uploaded images.
* **Triggered Action:** Creation and archiving of a new entry in the `Mensuration` entity, directly linked to the active user's profile (`cni`).
* **Outgoing Events (Outputs):**
  * `user.authenticated` *(to the entire system)*: Confirms user identity and grants access to downstream workflows (fabric selection, garment model choice, report consultations).
  * `user.profile_data` *(to Module 5: Ease Allowance Calculation Engine)*: Sends the selected body measurement history to trigger adjustment calculations.

## 10. Error Handling
* **Error:** CNI or Email address already in use during registration.
  * **Response:** Reject account creation and display a uniqueness error message.
* **Error:** Attempt to record body measurements containing negative or invalid values.
  * **Response:** Block saving and prompt the user to re-enter valid data.