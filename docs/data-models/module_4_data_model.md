### Entity: `MODEL`
The core of the module, managing the garment's lifecycle from the client's initial upload to publication by the administrator.

| Attribute       | Type         | Constraint                                                                 |
| :-------------- | :----------- | :------------------------------------------------------------------------- |
| `model_id`      | VARCHAR(36)  | **PRIMARY KEY** (UUID recommended for uniqueness).                         |
| `model_name`    | VARCHAR(100) | NOT NULL.                                                                  |
| `description`   | TEXT         | NULLABLE.                                                                  |
| `photo_url`     | VARCHAR(255) | NOT NULL. (URL of the image analyzed by the AI).                           |
| `garment_type`  | VARCHAR(50)  | NOT NULL. (e.g., Dress, Shirt).                                            |
| `cut_type`      | VARCHAR(50)  | NOT NULL. Check: IN ('Fitted', 'Semi-fitted', 'Loose').                    |
| `status`        | VARCHAR(20)  | NOT NULL. Default 'Draft'. Check: IN ('Draft', 'Published', 'Archived').   |
| `version`       | INT          | NOT NULL. Default 1. (Ensures immutability for older reports).             |
| `creator_id`    | VARCHAR(36)  | **FOREIGN KEY** (references `user_id`). NOT NULL.                          |

### Entity: `CRITICAL_ZONE`
Defines the specific body parts constrained by a given model.

| Attribute     | Type         | Constraint                                        |
| :------------ | :----------- | :------------------------------------------------ |
| `zone_id`     | VARCHAR(36)  | **PRIMARY KEY**.                                  |
| `zone_name`   | VARCHAR(50)  | NOT NULL. UNIQUE. (e.g., Chest, Waist, Hips).     |
| `description` | TEXT         | NULLABLE.                                         |

### Entity: `FABRIC` (Reference from Module 3)
A simplified representation of fabrics to handle compatibility linking.

| Attribute     | Type         | Constraint       |
| :------------ | :----------- | :--------------- |
| `fabric_id`   | VARCHAR(36)  | **PRIMARY KEY**. |
| `fabric_name` | VARCHAR(100) | NOT NULL.        |

### Entity: `USER` (System Actors)

| Attribute     | Type         | Constraint                                       |
| :------------ | :----------- | :----------------------------------------------- |
| `user_id`     | VARCHAR(36)  | **PRIMARY KEY**.                                 |
| `role`        | VARCHAR(50)  | NOT NULL. Check: IN ('Client', 'Administrator'). |

---

## Join Tables (n:m Associations)

To resolve the many-to-many relationships when translating this into a Logical Data Model (LDM) / Database schema.

### Table: `MODEL_CRITICAL_ZONE` (Association: "Constrains")
| Attribute   | Type        | Constraint                                                                   |
| :---------- | :---------- | :--------------------------------------------------------------------------- |
| `model_id`  | VARCHAR(36) | **PRIMARY KEY, FOREIGN KEY** (references `MODEL`).                           |
| `zone_id`   | VARCHAR(36) | **PRIMARY KEY, FOREIGN KEY** (references `CRITICAL_ZONE`).                   |
| *Rule*      | *Business*  | A "Published" model must have **at least one** entry in this table (1,n).    |

### Table: `MODEL_FABRIC` (Association: "Accepts")
| Attribute   | Type        | Constraint                                                                   |
| :---------- | :---------- | :--------------------------------------------------------------------------- |
| `model_id`  | VARCHAR(36) | **PRIMARY KEY, FOREIGN KEY** (references `MODEL`).                           |
| `fabric_id` | VARCHAR(36) | **PRIMARY KEY, FOREIGN KEY** (references `FABRIC`).                          |
| *Rule*      | *Business*  | A "Published" model must have **at least one** entry in this table (1,n).    |