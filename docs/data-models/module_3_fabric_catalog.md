# Conceptual Data Model — Module 3: Fabric Catalog

## Entity: FABRIC_CATEGORY
| Attribute | Type | Constraint |
|---|---|---|
| category_id (id) | UUID | auto-increment, unique |
| category_name | Short string | max 50 characters |
| category_description | Free text | optional |
| reference_rigidity_level | Enum | `rigid`, `semi-stretch`, `stretch` |

## Entity: FABRIC
| Attribute | Type | Constraint |
|---|---|---|
| fabric_id (id) | UUID | auto-increment, unique |
| fabric_name | Short string | max 100 characters |
| fabric_elasticity_rate | Decimal | 0 to 100 (%) |
| fabric_weight | Decimal | g/m², > 0 |
| fabric_composition | Free text | e.g. "70% cotton, 30% polyester" |
| fabric_unit_price | Decimal | > 0 |
| fabric_photo | String (URL) | image link |

## Association: BELONGS_TO

```
FABRIC_CATEGORY  (0,n) ────── BELONGS_TO ────── (1,1)  FABRIC
```

A fabric belongs to exactly one category; a category groups 0 to n fabrics.

## Normal form check
- **1NF**: all attributes are atomic.
- **2NF**: no composite key, so automatically satisfied.
- **3NF**: `reference_rigidity_level` is isolated in FABRIC_CATEGORY to avoid a transitive
  dependency (it depends on the fabric type, not on the specific fabric reference).
