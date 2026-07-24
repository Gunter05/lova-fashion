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


# ===========================================================================
# Module 4 — Pattern Catalog Property-Based Tests
# ===========================================================================
# Properties covered (§10 of design.md):
#   P1.2 — No draft on AI failure
#   P1.3 — Client-only invariant  (admin cannot call POST /models/init)
#   P2.2 — Exclusion invariant    (Draft/Archived excluded from GET /models)
#   P4.2 — Enum invariant         (invalid garment_type/cut_type → 422)
#   P6.1 — Completeness gate      (publish with 0 zones or 0 fabrics → 422)
#   P7.1 — Snapshot count         (K PATCHes on Published → K snapshots)
#   P7.2 — Version monotonicity   (publish/PATCH/publish cycles increase version)
#   P7.4 — Atomicity under failure (DB fault → MODEL unchanged, no partial snapshot)
#   P8.1 — Client invisibility    (Archived → excluded from listing, 404 on detail)
#   P9.2 — Archived accessibility (Archived → GET /constraints returns 200)
# ===========================================================================

import io
from unittest.mock import MagicMock, patch

from sqlalchemy import select, text

from app.modules.auth_catalogues.models import Model, ModelSnapshot

# ---------------------------------------------------------------------------
# Module 4 header shortcuts
# ---------------------------------------------------------------------------

ADMIN_HEADERS = {"X-User-Role": "administrator"}
CLIENT_M4_HEADERS = {"X-User-Role": "client"}
ANY_AUTH_HEADERS = {"X-User-Role": "administrator"}  # any valid role

# Valid enum values (used to build exclusion filters for P4.2)
VALID_GARMENT_TYPES = {
    "Dress", "Shirt", "Blouse", "Trousers", "Skirt",
    "Jacket", "Coat", "Shorts", "Suit", "Traditional",
}
VALID_CUT_TYPES = {"Fitted", "Semi-fitted", "Loose"}

# ---------------------------------------------------------------------------
# Strategies — Module 4
# ---------------------------------------------------------------------------

# N: number of models to create (small to keep tests fast)
n_models_st = st.integers(min_value=1, max_value=4)

# K: number of PATCH / publish cycles (small)
k_cycles_st = st.integers(min_value=1, max_value=3)

# Invalid garment type: any non-empty string that is not a valid enum value
invalid_garment_type_st = st.text(
    min_size=1,
    max_size=50,
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
).filter(lambda s: s.strip() and s.strip() not in VALID_GARMENT_TYPES)

# Invalid cut type: any non-empty string not in the valid set
invalid_cut_type_st = st.text(
    min_size=1,
    max_size=20,
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
).filter(lambda s: s.strip() and s.strip() not in VALID_CUT_TYPES)

# ---------------------------------------------------------------------------
# Module 4 helpers
# ---------------------------------------------------------------------------

_FAKE_IMAGE = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # minimal JPEG-like bytes
_FAKE_PHOTO_URL = "https://storage.example.com/inspiration-images/fake.jpg"


def _mock_ai_success():
    """Return a mock for ai_client.analyze_image that returns high confidence."""
    from app.modules.auth_catalogues.ai_client import AIAnalysisResult
    mock = MagicMock(
        return_value=AIAnalysisResult(
            garment_type="Dress",
            cut_type="Fitted",
            critical_zones=["Chest", "Waist"],
            confidence=0.92,
        )
    )
    return mock


def _mock_ai_low_confidence(confidence: float = 0.50):
    """Return a mock for ai_client.analyze_image that raises AILowConfidenceError."""
    from app.modules.auth_catalogues.ai_client import AILowConfidenceError
    mock = MagicMock(side_effect=AILowConfidenceError(confidence))
    return mock


def _mock_storage_success():
    """Return a mock for storage.upload_inspiration_image."""
    return MagicMock(return_value=_FAKE_PHOTO_URL)


def _post_init_model(client, *, ai_mock=None, storage_mock=None):
    """
    POST /api/v1/models/init with mocked AI and storage.

    Returns the (response, patchers) tuple. Patchers are already started/stopped
    inside this helper — callers just get the response.
    """
    if ai_mock is None:
        ai_mock = _mock_ai_success()
    if storage_mock is None:
        storage_mock = _mock_storage_success()

    with patch(
        "app.modules.auth_catalogues.service.ai_client.analyze_image",
        ai_mock,
    ), patch(
        "app.modules.auth_catalogues.service.storage.upload_inspiration_image",
        storage_mock,
    ), patch(
        "app.modules.auth_catalogues.service.storage.delete_image",
        MagicMock(),
    ):
        resp = client.post(
            "/api/v1/models/init",
            files={"image": ("test.jpg", io.BytesIO(_FAKE_IMAGE), "image/jpeg")},
            headers=CLIENT_M4_HEADERS,
        )
    return resp


def _create_draft_model(client) -> str:
    """Create a Draft model and return its model_id string."""
    resp = _post_init_model(client)
    assert resp.status_code == 201, f"Draft creation failed: {resp.text}"
    return resp.json()["model_id"]


def _seed_zones(client, db_session) -> list[str]:
    """
    Return a list of zone_ids from the critical_zone seed table.

    The conftest creates all DB tables but does NOT seed data.  We insert the
    standard 7 zones here if they don't exist yet, then return their IDs.
    """
    import asyncio
    from app.modules.auth_catalogues.models import CriticalZone

    async def _ensure_zones():
        result = await db_session.execute(select(CriticalZone))
        zones = result.scalars().all()
        if not zones:
            seed_names = ["Chest", "Waist", "Hips", "Shoulders", "Neck", "Thighs", "Ankles"]
            for name in seed_names:
                db_session.add(CriticalZone(zone_name=name))
            await db_session.commit()
            result = await db_session.execute(select(CriticalZone))
            zones = result.scalars().all()
        return [str(z.zone_id) for z in zones]

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_ensure_zones())


def _assign_zones(client, model_id: str, zone_ids: list[str]):
    """PUT /models/{id}/zones with the given zone_ids."""
    resp = client.put(
        f"/api/v1/models/{model_id}/zones",
        json={"zone_ids": zone_ids},
        headers=ADMIN_HEADERS,
    )
    return resp


def _create_available_fabric(client) -> str:
    """Create a real fabric in Module 3 and return its fabric_id."""
    cat_id = _create_category(client, name=f"M4Cat-{uuid.uuid4().hex[:6]}")
    fabric = _create_fabric(
        client,
        cat_id,
        name=f"M4Fab-{uuid.uuid4().hex[:6]}",
    )
    return fabric["fabric_id"]


def _assign_fabrics(client, model_id: str, fabric_ids: list[str]):
    """PUT /models/{id}/fabrics with the given fabric_ids."""
    resp = client.put(
        f"/api/v1/models/{model_id}/fabrics",
        json={"fabric_ids": fabric_ids},
        headers=ADMIN_HEADERS,
    )
    return resp


def _publish_model(client, model_id: str):
    """POST /models/{id}/publish and return the response."""
    return client.post(
        f"/api/v1/models/{model_id}/publish",
        headers=ADMIN_HEADERS,
    )


def _patch_model(client, model_id: str, description: str = "updated desc"):
    """PATCH /models/{id} with a description update (triggers snapshot on Published)."""
    with patch(
        "app.modules.auth_catalogues.service.ai_client.analyze_image",
        _mock_ai_success(),
    ):
        return client.patch(
            f"/api/v1/models/{model_id}",
            json={"description": description},
            headers=ADMIN_HEADERS,
        )


def _create_published_model(client, db_session) -> str:
    """
    Full workflow: Draft → assign zones + fabric → publish.
    Returns the published model_id string.
    """
    model_id = _create_draft_model(client)
    zone_ids = _seed_zones(client, db_session)
    _assign_zones(client, model_id, zone_ids[:1])
    fabric_id = _create_available_fabric(client)
    _assign_fabrics(client, model_id, [fabric_id])
    resp = _publish_model(client, model_id)
    assert resp.status_code == 200, f"Publish failed: {resp.text}"
    return model_id


# ===========================================================================
# P1.2 — No draft on AI failure
# IF the AI Analyzer returns confidence < 0.70, no MODEL row SHALL exist.
#
# **Validates: Requirements 1.2**
# ===========================================================================

MODULE4_PBT_SETTINGS = settings(
    max_examples=10,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


@MODULE4_PBT_SETTINGS
@given(confidence=st.floats(min_value=0.0, max_value=0.69, allow_nan=False))
def test_p1_2_no_draft_on_low_confidence(client, db_session, confidence):
    """
    **Validates: Requirements 1.2**

    Property P1.2: When the AI returns a confidence score below 0.70 for
    any input image, the system SHALL NOT create a MODEL row in the database.
    """
    import asyncio

    # Count MODEL rows before the request
    async def _count():
        result = await db_session.execute(select(Model))
        return len(result.scalars().all())

    loop = asyncio.get_event_loop()
    before = loop.run_until_complete(_count())

    # Make the AI return low confidence
    resp = _post_init_model(client, ai_mock=_mock_ai_low_confidence(confidence))

    # Must reject with 422
    assert resp.status_code == 422, (
        f"Expected 422 for confidence={confidence:.3f}, got {resp.status_code}: {resp.text}"
    )

    after = loop.run_until_complete(_count())
    assert after == before, (
        f"A MODEL row was created despite AI confidence={confidence:.3f} < 0.70. "
        f"Row count before={before}, after={after}."
    )


# ===========================================================================
# P1.3 — Client-only invariant
# IF the authenticated user does not have the `client` role, SHALL return 403.
#
# **Validates: Requirements 1.4**
# ===========================================================================


def test_p1_3_admin_cannot_init_model(client):
    """
    **Validates: Requirements 1.4**

    Property P1.3: POST /models/init with a non-client role (administrator)
    SHALL return HTTP 403 and SHALL NOT create a MODEL row.
    """
    with patch(
        "app.modules.auth_catalogues.service.storage.upload_inspiration_image",
        _mock_storage_success(),
    ), patch(
        "app.modules.auth_catalogues.service.ai_client.analyze_image",
        _mock_ai_success(),
    ):
        resp = client.post(
            "/api/v1/models/init",
            files={"image": ("test.jpg", io.BytesIO(_FAKE_IMAGE), "image/jpeg")},
            headers=ADMIN_HEADERS,  # administrator role — should be rejected
        )

    assert resp.status_code == 403, (
        f"Expected 403 when admin calls POST /models/init, got {resp.status_code}: {resp.text}"
    )


# ===========================================================================
# P2.2 — Exclusion invariant
# No MODEL row with status=Draft or status=Archived SHALL appear in GET /models.
#
# **Validates: Requirements 2.3**
# ===========================================================================


@MODULE4_PBT_SETTINGS
@given(n=st.integers(min_value=1, max_value=3))
def test_p2_2_draft_and_archived_excluded(client, db_session, n):
    """
    **Validates: Requirements 2.3**

    Property P2.2: For any N Draft models and N Archived models, none of
    them SHALL appear in the client-facing GET /models listing response.
    """
    draft_ids = set()
    archived_ids = set()

    # Create N Draft models
    for _ in range(n):
        mid = _create_draft_model(client)
        draft_ids.add(mid)

    # Create N models, publish them, then archive them
    for _ in range(n):
        mid = _create_published_model(client, db_session)
        arch_resp = client.post(
            f"/api/v1/models/{mid}/archive",
            headers=ADMIN_HEADERS,
        )
        assert arch_resp.status_code == 200, f"Archive failed: {arch_resp.text}"
        archived_ids.add(mid)

    # GET /models — must return only Published
    resp = client.get("/api/v1/models", headers=ANY_AUTH_HEADERS)
    assert resp.status_code == 200

    listed_ids = {item["model_id"] for item in resp.json()["items"]}

    for mid in draft_ids:
        assert mid not in listed_ids, (
            f"Draft model {mid} appeared in GET /models listing"
        )
    for mid in archived_ids:
        assert mid not in listed_ids, (
            f"Archived model {mid} appeared in GET /models listing"
        )


# ===========================================================================
# P4.2 — Enum invariant
# No MODEL row SHALL have a garment_type or cut_type outside the valid enums.
# PATCH with invalid values SHALL return 422.
#
# **Validates: Requirements 4.3 / 4.4**
# ===========================================================================


@MODULE4_PBT_SETTINGS
@given(invalid_garment_type=invalid_garment_type_st)
def test_p4_2_invalid_garment_type_rejected(client, db_session, invalid_garment_type):
    """
    **Validates: Requirements 4.3**

    Property P4.2 (garment_type): PATCH /models/{id} with an invalid
    garment_type value SHALL return HTTP 422 and the MODEL row SHALL remain
    unchanged.
    """
    model_id = _create_draft_model(client)

    resp = client.patch(
        f"/api/v1/models/{model_id}",
        json={"garment_type": invalid_garment_type.strip()},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 422, (
        f"Expected 422 for garment_type='{invalid_garment_type}', "
        f"got {resp.status_code}: {resp.text}"
    )


@MODULE4_PBT_SETTINGS
@given(invalid_cut_type=invalid_cut_type_st)
def test_p4_2_invalid_cut_type_rejected(client, db_session, invalid_cut_type):
    """
    **Validates: Requirements 4.4**

    Property P4.2 (cut_type): PATCH /models/{id} with an invalid cut_type
    value SHALL return HTTP 422.
    """
    model_id = _create_draft_model(client)

    resp = client.patch(
        f"/api/v1/models/{model_id}",
        json={"cut_type": invalid_cut_type.strip()},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 422, (
        f"Expected 422 for cut_type='{invalid_cut_type}', "
        f"got {resp.status_code}: {resp.text}"
    )


# ===========================================================================
# P6.1 — Completeness gate invariant
# No MODEL row with status=Published SHALL have 0 zones or 0 fabrics.
# Publishing a Draft with 0 zones → 422; with 0 fabrics → 422.
#
# **Validates: Requirements 6.2 / 6.3**
# ===========================================================================


def test_p6_1_publish_requires_at_least_one_zone(client, db_session):
    """
    **Validates: Requirements 6.2**

    Property P6.1 (zones): Publishing a Draft with zero MODEL_CRITICAL_ZONE
    entries SHALL return HTTP 422 and the model status SHALL remain 'Draft'.
    """
    model_id = _create_draft_model(client)

    # Assign a fabric but NO zones
    fabric_id = _create_available_fabric(client)
    _assign_fabrics(client, model_id, [fabric_id])
    # Explicitly clear zones (empty assignment)
    _assign_zones(client, model_id, [])

    resp = _publish_model(client, model_id)
    assert resp.status_code == 422, (
        f"Expected 422 when publishing with 0 zones, got {resp.status_code}: {resp.text}"
    )

    # Verify the model is still Draft
    get_resp = client.get(
        f"/api/v1/models/{model_id}/constraints",
        headers=ANY_AUTH_HEADERS,
    )
    # constraints endpoint returns 404 for Draft, confirming status is still Draft
    assert get_resp.status_code == 404, (
        f"Expected model to remain Draft (constraints returns 404), "
        f"got {get_resp.status_code}"
    )


def test_p6_1_publish_requires_at_least_one_fabric(client, db_session):
    """
    **Validates: Requirements 6.3**

    Property P6.1 (fabrics): Publishing a Draft with zero MODEL_FABRIC entries
    SHALL return HTTP 422 and the model status SHALL remain 'Draft'.
    """
    model_id = _create_draft_model(client)

    # Assign zones but NO fabrics
    zone_ids = _seed_zones(client, db_session)
    _assign_zones(client, model_id, zone_ids[:1])
    # Explicitly clear fabrics
    _assign_fabrics(client, model_id, [])

    resp = _publish_model(client, model_id)
    assert resp.status_code == 422, (
        f"Expected 422 when publishing with 0 fabrics, got {resp.status_code}: {resp.text}"
    )

    # Verify still Draft (constraints endpoint returns 404 for Draft)
    get_resp = client.get(
        f"/api/v1/models/{model_id}/constraints",
        headers=ANY_AUTH_HEADERS,
    )
    assert get_resp.status_code == 404, (
        f"Expected model to remain Draft, got {get_resp.status_code}"
    )


# ===========================================================================
# P7.1 — Snapshot-before-update invariant
# For K PATCHes on a Published model, MODEL_SNAPSHOT count SHALL equal K.
#
# **Validates: Requirements 7.1**
# ===========================================================================


@MODULE4_PBT_SETTINGS
@given(k=st.integers(min_value=1, max_value=3))
def test_p7_1_snapshot_count_equals_patch_count(client, db_session, k):
    """
    **Validates: Requirements 7.1**

    Property P7.1: For any Published model PATCHed K times, there SHALL be
    exactly K MODEL_SNAPSHOT rows for that model_id upon completion.
    """
    import asyncio

    model_id = _create_published_model(client, db_session)

    # PATCH the model K times (each PATCH on a Published model creates one snapshot)
    for i in range(k):
        resp = _patch_model(client, model_id, description=f"edit #{i}")
        assert resp.status_code == 200, (
            f"PATCH {i+1} failed: {resp.status_code}: {resp.text}"
        )

    # Count snapshots in DB
    async def _count_snapshots():
        result = await db_session.execute(
            select(ModelSnapshot).where(
                ModelSnapshot.model_id == model_id
            )
        )
        return len(result.scalars().all())

    loop = asyncio.get_event_loop()
    snapshot_count = loop.run_until_complete(_count_snapshots())

    assert snapshot_count == k, (
        f"Expected {k} snapshot(s) after {k} PATCH(es), found {snapshot_count}"
    )


# ===========================================================================
# P7.2 — Version monotonicity
# The `version` field SHALL strictly increase with each publish/PATCH/publish cycle.
#
# **Validates: Requirements 7.2**
# ===========================================================================


@MODULE4_PBT_SETTINGS
@given(cycles=st.integers(min_value=1, max_value=3))
def test_p7_2_version_strictly_increases(client, db_session, cycles):
    """
    **Validates: Requirements 7.2**

    Property P7.2: After each PATCH + republish cycle on a Published model,
    the `version` field SHALL be strictly greater than the version before
    the cycle. It must never decrease.
    """
    model_id = _create_published_model(client, db_session)

    # Get initial version (should be 1 after first publish)
    constraints = client.get(
        f"/api/v1/models/{model_id}/constraints",
        headers=ANY_AUTH_HEADERS,
    )
    assert constraints.status_code == 200
    prev_version = constraints.json()["version"]
    assert prev_version == 1, f"Expected initial version=1, got {prev_version}"

    for cycle in range(cycles):
        # PATCH (creates snapshot)
        patch_resp = _patch_model(client, model_id, description=f"cycle {cycle}")
        assert patch_resp.status_code == 200, (
            f"PATCH in cycle {cycle} failed: {patch_resp.text}"
        )

        # Republish (increments version)
        pub_resp = _publish_model(client, model_id)
        assert pub_resp.status_code == 200, (
            f"Publish in cycle {cycle} failed: {pub_resp.text}"
        )

        new_version = pub_resp.json()["version"]
        assert new_version > prev_version, (
            f"Version did not increase in cycle {cycle}: "
            f"was {prev_version}, now {new_version}"
        )
        prev_version = new_version


# ===========================================================================
# P7.4 — Atomicity under failure
# IF snapshot write fails, the live MODEL row SHALL remain unchanged and
# no partial MODEL_SNAPSHOT row SHALL exist.
#
# **Validates: Requirements 7.2 (Req 7 AC2)**
# ===========================================================================


def test_p7_4_snapshot_failure_rolls_back(client, db_session):
    """
    **Validates: Requirements 7.2 (AC2)**

    Property P7.4: If a DB fault is injected during the snapshot write on a
    Published model PATCH, the live MODEL row SHALL remain unchanged and no
    partial MODEL_SNAPSHOT row SHALL exist.
    """
    import asyncio

    model_id = _create_published_model(client, db_session)

    # Capture the current state of the model before the injected failure
    constraints_before = client.get(
        f"/api/v1/models/{model_id}/constraints",
        headers=ANY_AUTH_HEADERS,
    )
    assert constraints_before.status_code == 200
    state_before = constraints_before.json()

    # Count snapshots before the attempt
    async def _count_snapshots():
        result = await db_session.execute(
            select(ModelSnapshot).where(ModelSnapshot.model_id == model_id)
        )
        return len(result.scalars().all())

    loop = asyncio.get_event_loop()
    snapshots_before = loop.run_until_complete(_count_snapshots())

    # Inject a fault: make crud.create_snapshot raise an exception mid-transaction
    from sqlalchemy.exc import SQLAlchemyError

    async def _failing_create_snapshot(db, model):
        raise SQLAlchemyError("Simulated DB fault during snapshot write")

    with patch(
        "app.modules.auth_catalogues.service.crud.create_snapshot",
        side_effect=_failing_create_snapshot,
    ):
        patch_resp = client.patch(
            f"/api/v1/models/{model_id}",
            json={"description": "this should fail atomically"},
            headers=ADMIN_HEADERS,
        )

    # The service should return 500 (snapshot failure rolls back everything)
    assert patch_resp.status_code == 500, (
        f"Expected 500 when snapshot fails, got {patch_resp.status_code}: {patch_resp.text}"
    )

    # MODEL row must remain unchanged
    constraints_after = client.get(
        f"/api/v1/models/{model_id}/constraints",
        headers=ANY_AUTH_HEADERS,
    )
    assert constraints_after.status_code == 200
    state_after = constraints_after.json()

    assert state_after["version"] == state_before["version"], (
        f"Model version changed after failed snapshot: "
        f"before={state_before['version']}, after={state_after['version']}"
    )

    # No partial snapshot row should have been created
    snapshots_after = loop.run_until_complete(_count_snapshots())
    assert snapshots_after == snapshots_before, (
        f"Partial snapshot was created: before={snapshots_before}, after={snapshots_after}"
    )


# ===========================================================================
# P8.1 — Client invisibility after archive
# Archived model SHALL NOT appear in GET /models; GET /models/{id} → 404.
#
# **Validates: Requirements 8.2 / 8.3**
# ===========================================================================


def test_p8_1_archived_excluded_from_catalog(client, db_session):
    """
    **Validates: Requirements 8.2 / 8.3**

    Property P8.1: After archiving a Published model:
      - GET /models SHALL NOT include it.
      - GET /models/{model_id} SHALL return HTTP 404.
    """
    model_id = _create_published_model(client, db_session)

    # Verify it appears in the listing before archiving
    list_resp_before = client.get("/api/v1/models", headers=ANY_AUTH_HEADERS)
    assert list_resp_before.status_code == 200
    ids_before = {item["model_id"] for item in list_resp_before.json()["items"]}
    assert model_id in ids_before, "Published model not found in listing before archiving"

    # Archive the model
    arch_resp = client.post(
        f"/api/v1/models/{model_id}/archive",
        headers=ADMIN_HEADERS,
    )
    assert arch_resp.status_code == 200, f"Archive failed: {arch_resp.text}"

    # GET /models — must exclude the archived model
    list_resp_after = client.get("/api/v1/models", headers=ANY_AUTH_HEADERS)
    assert list_resp_after.status_code == 200
    ids_after = {item["model_id"] for item in list_resp_after.json()["items"]}
    assert model_id not in ids_after, (
        f"Archived model {model_id} still appears in GET /models"
    )

    # GET /models/{id} — must return 404
    detail_resp = client.get(
        f"/api/v1/models/{model_id}",
        headers=ANY_AUTH_HEADERS,
    )
    assert detail_resp.status_code == 404, (
        f"Expected 404 for archived model detail, got {detail_resp.status_code}"
    )


# ===========================================================================
# P9.2 — Archived accessibility via constraints endpoint
# For every Archived model, GET /models/{id}/constraints SHALL return 200.
#
# **Validates: Requirements 9.2**
# ===========================================================================


def test_p9_2_archived_accessible_via_constraints(client, db_session):
    """
    **Validates: Requirements 9.2**

    Property P9.2: After archiving a Published model, the internal constraints
    endpoint SHALL return HTTP 200 with complete data (model_id, version,
    garment_type, cut_type, zones, fabrics).

    The endpoint SHALL never return HTTP 404 for an Archived model.
    """
    model_id = _create_published_model(client, db_session)

    # Capture constraints while Published
    pub_constraints = client.get(
        f"/api/v1/models/{model_id}/constraints",
        headers=ANY_AUTH_HEADERS,
    )
    assert pub_constraints.status_code == 200
    pub_data = pub_constraints.json()

    # Archive the model
    arch_resp = client.post(
        f"/api/v1/models/{model_id}/archive",
        headers=ADMIN_HEADERS,
    )
    assert arch_resp.status_code == 200, f"Archive failed: {arch_resp.text}"

    # Constraints endpoint must still return 200 for Archived model
    arch_constraints = client.get(
        f"/api/v1/models/{model_id}/constraints",
        headers=ANY_AUTH_HEADERS,
    )
    assert arch_constraints.status_code == 200, (
        f"Expected 200 on constraints for Archived model, "
        f"got {arch_constraints.status_code}: {arch_constraints.text}"
    )

    arch_data = arch_constraints.json()

    # Data integrity — key fields must match what was there when Published
    assert arch_data["model_id"] == pub_data["model_id"]
    assert arch_data["version"] == pub_data["version"]
    assert arch_data["garment_type"] == pub_data["garment_type"]
    assert arch_data["cut_type"] == pub_data["cut_type"]

    # Required fields must be present and non-null
    assert "zones" in arch_data and arch_data["zones"] is not None
    assert "fabrics" in arch_data and arch_data["fabrics"] is not None
    assert "model_name" in arch_data and arch_data["model_name"]
