# Conceptual Data Model (MCD) — Module 1: Auth & User Profile

## Entities & Attributes

### 1. User (`User`)
* **`cni`**: VARCHAR(50) — *Primary Key*
* **`name`**: VARCHAR(50)
* **`email`**: VARCHAR(50)
* **`password`**: VARCHAR(50)
* **`registration_date`**: DATE
* **`role`**: ENUM

### 2. Profile Photo (`Photo_profil`)
* **`id_pp`**: VARCHAR(50) — *Primary Key*
* **`url`**: VARCHAR(50)
* **`updated_at`**: DATE

### 3. Body Measurement (`Mensuration`)
* **`id_measurement`**: VARCHAR(50) — *Primary Key*
* **`taken_at`**: DATE
* **`waist_circumference`**: DECIMAL
* **`bust_circumference`**: DECIMAL
* **`arm_length`**: DECIMAL
* **`waist_length`**: DECIMAL
* **`bust_height`**: DECIMAL
* **`hip_circumference`**: DECIMAL
* **`thigh_circumference`**: DECIMAL
* **`fabric`**: VARCHAR(50)

---

## Relationships & Cardinalities

1. **User — Photo_profil** (`possess` / *posséder*)
   * `User` (0,N) <---> (1,1) `Photo_profil`
   * *A user can have 0 to N profile photos over time; a profile photo belongs to exactly 1 user.*

2. **User — Mensuration** (`belong_to` / *appartenir*)
   * `User` (0,N) <---> (1,1) `Mensuration`
   * *A user can have multiple recorded body measurements; each measurement belongs to 1 user.*