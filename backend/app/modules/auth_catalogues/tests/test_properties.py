"""
Property-based tests for the Fabric Catalog module (auth_catalogues).

Uses pytest + hypothesis to automatically generate boundary-covering inputs
and verify each correctness property defined in the design document.

Properties covered:
    P1.2 — Listing exclusion         (Validates: Requirements 1.3)
    P3.1 — No unavailable selection  (Validates: Requirements 3.2)
    P3.3 — Alternatives count        (Validates: Requirements 3.2)
    P4.2 — Category orphan prevention(Validates: Requirements 4.7)
    P5.1 — Elasticity range invariant(Validates: Requirements 5.4)
    P5.2 — Price positivity invariant(Validates: Requirements 5.5)
    P7.1 — Elasticity round-trip     (Validates: Requirements 7.1)

Each test uses FastAPI's TestClient with an in-memory SQLite database so no
external Supabase connection is required (see conftest.py).

Role header: the role dependency reads `X-User-Role` (FastAPI converts
header names to lowercase with underscores in the Header() dependency, so
we send the canonical HTTP header `X-User-Role`).
"""

import uuid
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
import pytest

# ---------------------------------------------------------------------------
# Shared header shortcuts
# ---------------------------------------------------------------------------

CLIENT_HEADERS = {"X-User-Role": "client"}
MANAGER_HEADERS = {"X-User-Role": "catalog_manager"}

# ---------------------------------------------------------------------------
# Hypothesis settings — suppress the function-scoped fixture health-check
# because we intentionally use function-scoped pytest fixtures with @given.
# ---------------------------------------------------------------------------

PBT_SETTINGS = settings(
    max_examples=30,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,  # disable per-example time limit (varies across machines)
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Valid fabric name (1–100 chars, printable text)
fabric_name_st = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs")),
    min_size=1,
    max_size=50,
).filter(lambda s: s.strip())

# Valid category name (1–50 chars)
category_name_st = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs")),
    min_size=1,
    max_size=30,
).filter(lambda s: s.strip())

# Rigidity level enum values
rigidity_st = st.sampled_from(["rigid", "semi-stretch", "stretch"])

# Elasticity rate — boundary-covering: exactly at bounds and just outside
elasticity_valid_st = st.floats(min_value=0.0, max_value=100.0, allow_nan=False)

# Out-of-range elasticity: below 0 or above 100
elasticity_invalid_st = st.one_of(
    st.floats(max_value=-0.01, allow_nan=False, allow_infinity=False),
    st.floats(min_value=100.01, max_value=1e6, allow_nan=False, allow_infinity=False),
)

# Valid unit price (> 0)
price_valid_st = st.floats(min_value=0.01, max_value=9999.99, allow_nan=False)

# Invalid unit price (<= 0)
price_invalid_st = st.one_of(
    st.just(0.0),
    st.floats(max_value=-0.01, allow_nan=False, allow_infinity=False),
)

# Valid weight (> 0)
weight_valid_st = st.floats(min_value=0.01, max_value=9999.0, allow_nan=False)

# Non-available fabric statuses
non_available_status_st = st.sampled_from(["unavailable", "archived"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_category(client, name: str = "TestCategory", rigidity: str = "rigid") -> str:
    """Create a category via the API and return its category_id."""
    resp = client.post(
        "/api/v1/categories",
        json={
            "category_name": name,
            "reference_rigidity_level": rigidity,
        },
        headers=MANAGER_HEADERS,
    )
    assert resp.status_code == 201, f"Category creation failed: {resp.text}"
    return resp.json()["category_id"]


def _create_fabric(
    client,
    category_id: str,
    *,
    name: str = "Test Fabric",
    elasticity: float = 50.0,
    weight: float = 200.0,
    price: float = 10.0,
    status: str = "available",
) -> dict:
    """Create a fabric via the manager API and return the full response dict."""
    resp = client.post(
        "/api/v1/fabrics",
        json={
            "fabric_name": name,
            "fabric_elasticity_rate": elasticity,
            "fabric_weight": weight,
            "fabric_unit_price": price,
            "category_id": category_id,
        },
        headers=MANAGER_HEADERS,
    )
    assert resp.status_code == 201, f"Fabric creation failed: {resp.text}"
    fabric = resp.json()

    # If a non-available status is requested, patch it immediately
    if status != "available":
        patch_resp = client.patch(
            f"/api/v1/fabrics/{fabric['fabric_id']}",
            json={"fabric_status": status},
            headers=MANAGER_HEADERS,
        )
        assert patch_resp.status_code == 200
        fabric = patch_resp.json()

    return fabric


# ===========================================================================
# P1.2 — Listing exclusion
# For every fabric with fabric_status of unavailable or archived, it SHALL
# NOT appear in any client-facing listing response (GET /fabrics).
#
# Validates: Requirements 1.3
# ===========================================================================


@PBT_SETTINGS
@given(status=non_available_status_st)
def test_p1_2_listing_exclusion(client, status):
    """
    **Validates: Requirements 1.3**

    Property P1.2: Fabrics whose status is unavailable or archived must
    never appear in the GET /fabrics listing visible to clients.
    """
    # Create category + fabric with the given non-available status
    cat_id = _create_category(client, name=f"Cat-{uuid.uuid4().hex[:6]}")
    fabric = _create_fabric(
        client,
        cat_id,
        name=f"Fabric-{uuid.uuid4().hex[:6]}",
        status=status,
    )
    fabric_id = fabric["fabric_id"]

    # Fetch client listing and verify the fabric is absent
    resp = client.get("/api/v1/fabrics", headers=CLIENT_HEADERS)
    assert resp.status_code == 200
    listed_ids = {f["fabric_id"] for f in resp.json()}
    assert fabric_id not in listed_ids, (
        f"Fabric {fabric_id} with status='{status}' appeared in listing"
    )


# ===========================================================================
# P3.1 — No unavailable selection
# It SHALL be impossible for the system to confirm a selection of a fabric
# with fabric_status != available (POST /fabrics/{id}/select).
#
# Validates: Requirements 3.2
# ===========================================================================


@PBT_SETTINGS
@given(status=non_available_status_st)
def test_p3_1_no_unavailable_selection(client, status):
    """
    **Validates: Requirements 3.2**

    Property P3.1: Selecting any non-available fabric must never return
    HTTP 200. It must return 409 (unavailable) or 404 (archived/missing).
    """
    cat_id = _create_category(client, name=f"Cat-{uuid.uuid4().hex[:6]}")
    fabric = _create_fabric(
        client,
        cat_id,
        name=f"Fabric-{uuid.uuid4().hex[:6]}",
        status=status,
    )
    fabric_id = fabric["fabric_id"]

    resp = client.post(
        f"/api/v1/fabrics/{fabric_id}/select",
        headers=CLIENT_HEADERS,
    )
    assert resp.status_code != 200, (
        f"Expected non-200 for fabric with status='{status}', got {resp.status_code}"
    )
    # Verify the status code is one of the expected error codes
    assert resp.status_code in (404, 409), (
        f"Expected 404 or 409 for status='{status}', got {resp.status_code}"
    )


# ===========================================================================
# P3.3 — Alternatives count and no self-inclusion
# The number of alternatives returned SHALL be at most 3 and SHALL NOT
# include the rejected fabric itself.
#
# Validates: Requirements 3.2
# ===========================================================================


@PBT_SETTINGS
@given(n_alternatives=st.integers(min_value=0, max_value=5))
def test_p3_3_alternatives_count_and_no_self(client, n_alternatives):
    """
    **Validates: Requirements 3.2**

    Property P3.3: When selecting an unavailable fabric, the 409 response
    must contain at most 3 alternatives, and the rejected fabric must not
    be included among them.
    """
    cat_id = _create_category(client, name=f"Cat-{uuid.uuid4().hex[:6]}")

    # Create the target fabric (unavailable)
    target = _create_fabric(
        client,
        cat_id,
        name=f"Target-{uuid.uuid4().hex[:6]}",
        status="unavailable",
    )
    target_id = target["fabric_id"]

    # Create n_alternatives available fabrics in the same category
    for i in range(n_alternatives):
        _create_fabric(
            client,
            cat_id,
            name=f"Alt{i:02d}-{uuid.uuid4().hex[:4]}",
            status="available",
        )

    resp = client.post(
        f"/api/v1/fabrics/{target_id}/select",
        headers=CLIENT_HEADERS,
    )
    assert resp.status_code == 409

    body = resp.json()
    # TestClient wraps JSON body differently for non-200 JSONResponse
    # The service raises HTTPException with a dict detail; FastAPI + JSONResponse
    # may place it under "detail" or at the root depending on how the route
    # handler processes it.  We handle both forms.
    if "alternatives" in body:
        alternatives = body["alternatives"]
    else:
        alternatives = body.get("detail", {}).get("alternatives", [])

    # At most 3
    assert len(alternatives) <= 3, (
        f"Expected <= 3 alternatives, got {len(alternatives)}"
    )

    # Self must not be included
    alt_ids = {a["fabric_id"] for a in alternatives}
    assert target_id not in alt_ids, (
        f"Rejected fabric {target_id} appeared in its own alternatives list"
    )


# ===========================================================================
# P4.2 — Category orphan prevention
# Deleting a category with associated fabrics SHALL always be rejected (409).
#
# Validates: Requirements 4.7
# ===========================================================================


@PBT_SETTINGS
@given(n_fabrics=st.integers(min_value=1, max_value=4))
def test_p4_2_category_orphan_prevention(client, n_fabrics):
    """
    **Validates: Requirements 4.7**

    Property P4.2: Attempting to delete a category that still owns at least
    one fabric must always return HTTP 409.
    """
    cat_id = _create_category(client, name=f"Cat-{uuid.uuid4().hex[:6]}")

    # Create n_fabrics fabrics in this category
    for i in range(n_fabrics):
        _create_fabric(
            client,
            cat_id,
            name=f"Fab{i:02d}-{uuid.uuid4().hex[:4]}",
        )

    resp = client.delete(
        f"/api/v1/categories/{cat_id}",
        headers=MANAGER_HEADERS,
    )
    assert resp.status_code == 409, (
        f"Expected 409 when deleting category with {n_fabrics} fabric(s), "
        f"got {resp.status_code}"
    )

    # Verify the category still exists
    get_resp = client.get(
        f"/api/v1/categories/{cat_id}",
        headers=MANAGER_HEADERS,
    )
    assert get_resp.status_code == 200, (
        "Category was deleted despite having associated fabrics"
    )


# ===========================================================================
# P5.1 — Elasticity range invariant
# For any POST /fabrics or PATCH /fabrics/{id} request where
# fabric_elasticity_rate is outside [0, 100], return 422.
#
# Validates: Requirements 5.4
# ===========================================================================


@PBT_SETTINGS
@given(bad_elasticity=elasticity_invalid_st)
def test_p5_1_elasticity_range_create(client, bad_elasticity):
    """
    **Validates: Requirements 5.4**

    Property P5.1 (POST): Creating a fabric with fabric_elasticity_rate
    outside [0, 100] must return HTTP 422.
    """
    cat_id = _create_category(client, name=f"Cat-{uuid.uuid4().hex[:6]}")

    resp = client.post(
        "/api/v1/fabrics",
        json={
            "fabric_name": "Test Fabric",
            "fabric_elasticity_rate": bad_elasticity,
            "fabric_weight": 200.0,
            "fabric_unit_price": 10.0,
            "category_id": cat_id,
        },
        headers=MANAGER_HEADERS,
    )
    assert resp.status_code == 422, (
        f"Expected 422 for elasticity={bad_elasticity}, got {resp.status_code}"
    )


@PBT_SETTINGS
@given(bad_elasticity=elasticity_invalid_st)
def test_p5_1_elasticity_range_patch(client, bad_elasticity):
    """
    **Validates: Requirements 5.4**

    Property P5.1 (PATCH): Updating a fabric with fabric_elasticity_rate
    outside [0, 100] must return HTTP 422.
    """
    cat_id = _create_category(client, name=f"Cat-{uuid.uuid4().hex[:6]}")
    fabric = _create_fabric(client, cat_id, name=f"Fab-{uuid.uuid4().hex[:6]}")

    resp = client.patch(
        f"/api/v1/fabrics/{fabric['fabric_id']}",
        json={"fabric_elasticity_rate": bad_elasticity},
        headers=MANAGER_HEADERS,
    )
    assert resp.status_code == 422, (
        f"Expected 422 for elasticity={bad_elasticity} on PATCH, got {resp.status_code}"
    )


# ===========================================================================
# P5.2 — Price positivity invariant
# For any POST /fabrics or PATCH /fabrics/{id} request where
# fabric_unit_price <= 0, return 422.
#
# Validates: Requirements 5.5
# ===========================================================================


@PBT_SETTINGS
@given(bad_price=price_invalid_st)
def test_p5_2_price_positivity_create(client, bad_price):
    """
    **Validates: Requirements 5.5**

    Property P5.2 (POST): Creating a fabric with fabric_unit_price <= 0
    must return HTTP 422.
    """
    cat_id = _create_category(client, name=f"Cat-{uuid.uuid4().hex[:6]}")

    resp = client.post(
        "/api/v1/fabrics",
        json={
            "fabric_name": "Test Fabric",
            "fabric_elasticity_rate": 50.0,
            "fabric_weight": 200.0,
            "fabric_unit_price": bad_price,
            "category_id": cat_id,
        },
        headers=MANAGER_HEADERS,
    )
    assert resp.status_code == 422, (
        f"Expected 422 for price={bad_price}, got {resp.status_code}"
    )


@PBT_SETTINGS
@given(bad_price=price_invalid_st)
def test_p5_2_price_positivity_patch(client, bad_price):
    """
    **Validates: Requirements 5.5**

    Property P5.2 (PATCH): Updating a fabric with fabric_unit_price <= 0
    must return HTTP 422.
    """
    cat_id = _create_category(client, name=f"Cat-{uuid.uuid4().hex[:6]}")
    fabric = _create_fabric(client, cat_id, name=f"Fab-{uuid.uuid4().hex[:6]}")

    resp = client.patch(
        f"/api/v1/fabrics/{fabric['fabric_id']}",
        json={"fabric_unit_price": bad_price},
        headers=MANAGER_HEADERS,
    )
    assert resp.status_code == 422, (
        f"Expected 422 for price={bad_price} on PATCH, got {resp.status_code}"
    )


# ===========================================================================
# P7.1 — Elasticity round-trip accuracy
# For any fabric created with a known fabric_elasticity_rate R, GET
# /fabrics/{id}/properties returns fabric_elasticity_rate equal to R.
#
# Validates: Requirements 7.1
# ===========================================================================


@PBT_SETTINGS
@given(elasticity=elasticity_valid_st)
def test_p7_1_elasticity_round_trip(client, elasticity):
    """
    **Validates: Requirements 7.1**

    Property P7.1: The elasticity rate stored when creating a fabric must
    be returned unchanged by GET /fabrics/{id}/properties.

    We round to 2 decimal places to match the NUMERIC(5,2) column precision
    (SQLite stores exact floats, but the route returns Python floats which
    may have minor float-representation noise — we only require that the
    value round-trips within the stored precision).
    """
    cat_id = _create_category(client, name=f"Cat-{uuid.uuid4().hex[:6]}")

    # Round to 2 dp to match column precision before storing
    stored_elasticity = round(elasticity, 2)

    resp = client.post(
        "/api/v1/fabrics",
        json={
            "fabric_name": f"Fab-{uuid.uuid4().hex[:6]}",
            "fabric_elasticity_rate": stored_elasticity,
            "fabric_weight": 200.0,
            "fabric_unit_price": 10.0,
            "category_id": cat_id,
        },
        headers=MANAGER_HEADERS,
    )
    assert resp.status_code == 201, f"Fabric creation failed: {resp.text}"
    fabric_id = resp.json()["fabric_id"]

    # Retrieve via the internal /properties endpoint (any authenticated role)
    props_resp = client.get(
        f"/api/v1/fabrics/{fabric_id}/properties",
        headers=CLIENT_HEADERS,
    )
    assert props_resp.status_code == 200
    returned_elasticity = props_resp.json()["fabric_elasticity_rate"]

    assert round(returned_elasticity, 2) == stored_elasticity, (
        f"Round-trip mismatch: stored {stored_elasticity}, "
        f"returned {returned_elasticity}"
    )
