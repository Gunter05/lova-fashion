"""
Smoke / integration tests for the Pattern Catalog (Module 4).

Three end-to-end scenarios:
    1. test_happy_path         — Upload → Draft → edit → zones + fabrics → publish
                                  → client detail view → internal constraints
    2. test_edit_and_republish_cycle — Published → PATCH (snapshot) → republish
                                       → version increments monotonically
    3. test_archive_flow       — Published → archive → client 404 → constraints 200

All tests use the ``client`` and ``db_session`` fixtures provided by conftest.py.
The AI analyzer and Supabase storage calls are mocked for isolation.
"""

import asyncio
import io
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from app.modules.auth_catalogues.ai_client import AIAnalysisResult
from app.modules.auth_catalogues.models import CriticalZone, ModelSnapshot

# ---------------------------------------------------------------------------
# Header shortcuts
# ---------------------------------------------------------------------------

CLIENT_HEADERS = {"X-User-Role": "client"}
ADMIN_HEADERS = {"X-User-Role": "administrator"}
ANY_AUTH = {"X-User-Role": "administrator"}
MANAGER_HEADERS = {"X-User-Role": "catalog_manager"}

# ---------------------------------------------------------------------------
# Fake data
# ---------------------------------------------------------------------------

_FAKE_IMAGE = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # minimal JPEG-like bytes
_FAKE_PHOTO_URL = "https://storage.example.com/inspiration-images/fake.jpg"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _mock_ai_result() -> AIAnalysisResult:
    """High-confidence AI result that passes the 0.70 threshold."""
    return AIAnalysisResult(
        garment_type="Dress",
        cut_type="Fitted",
        critical_zones=["Chest", "Waist"],
        confidence=0.95,
    )


def _post_init_model(client):
    """POST /api/v1/models/init with mocked AI + storage and return the response."""
    with patch(
        "app.modules.auth_catalogues.service.ai_client.analyze_image",
        MagicMock(return_value=_mock_ai_result()),
    ), patch(
        "app.modules.auth_catalogues.service.storage.upload_inspiration_image",
        MagicMock(return_value=_FAKE_PHOTO_URL),
    ), patch(
        "app.modules.auth_catalogues.service.storage.delete_image",
        MagicMock(),
    ):
        return client.post(
            "/api/v1/models/init",
            files={"image": ("test.jpg", io.BytesIO(_FAKE_IMAGE), "image/jpeg")},
            headers=CLIENT_HEADERS,
        )


def _seed_zones(db_session) -> list[str]:
    """
    Ensure the critical_zone table has the standard 7 zones and return their IDs.

    Uses asyncio.get_event_loop() to run the coroutine from sync test code,
    matching the pattern from test_properties.py.
    """
    async def _ensure_zones():
        result = await db_session.execute(select(CriticalZone))
        zones = result.scalars().all()
        if not zones:
            seed_names = [
                "Chest", "Waist", "Hips", "Shoulders", "Neck", "Thighs", "Ankles"
            ]
            for name in seed_names:
                db_session.add(CriticalZone(zone_name=name))
            await db_session.commit()
            result = await db_session.execute(select(CriticalZone))
            zones = result.scalars().all()
        return [str(z.zone_id) for z in zones]

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_ensure_zones())


def _count_snapshots(db_session, model_id: str) -> int:
    """Return the number of ModelSnapshot rows for the given model_id."""
    async def _query():
        result = await db_session.execute(
            select(ModelSnapshot).where(ModelSnapshot.model_id == model_id)
        )
        return len(result.scalars().all())

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_query())


def _create_fabric(client) -> str:
    """
    Create a fabric category + fabric via Module 3 endpoints and return the fabric_id.

    Uses the catalog_manager role as required by Module 3.
    """
    import uuid

    # Create category
    cat_resp = client.post(
        "/api/v1/categories",
        json={
            "category_name": f"SmokeTestCat-{uuid.uuid4().hex[:6]}",
            "reference_rigidity_level": "rigid",
        },
        headers=MANAGER_HEADERS,
    )
    assert cat_resp.status_code == 201, f"Category creation failed: {cat_resp.text}"
    category_id = cat_resp.json()["category_id"]

    # Create fabric
    fabric_resp = client.post(
        "/api/v1/fabrics",
        json={
            "fabric_name": f"SmokeTestFabric-{uuid.uuid4().hex[:6]}",
            "fabric_elasticity_rate": 30.0,
            "fabric_weight": 150.0,
            "fabric_unit_price": 8.50,
            "category_id": category_id,
        },
        headers=MANAGER_HEADERS,
    )
    assert fabric_resp.status_code == 201, f"Fabric creation failed: {fabric_resp.text}"
    return fabric_resp.json()["fabric_id"]


def _create_published_model(client, db_session) -> str:
    """
    Full happy-path workflow: init → seed zones → assign zones → create fabric
    → assign fabrics → publish.  Returns the published model_id string.
    """
    # 1. Init (Draft)
    init_resp = _post_init_model(client)
    assert init_resp.status_code == 201, f"Init failed: {init_resp.text}"
    model_id = init_resp.json()["model_id"]

    # 2. Seed zones
    zone_ids = _seed_zones(db_session)

    # 3. Assign first zone
    zone_resp = client.put(
        f"/api/v1/models/{model_id}/zones",
        json={"zone_ids": [zone_ids[0]]},
        headers=ADMIN_HEADERS,
    )
    assert zone_resp.status_code == 200, f"Zone assignment failed: {zone_resp.text}"

    # 4. Create + assign fabric
    fabric_id = _create_fabric(client)
    fabric_resp = client.put(
        f"/api/v1/models/{model_id}/fabrics",
        json={"fabric_ids": [fabric_id]},
        headers=ADMIN_HEADERS,
    )
    assert fabric_resp.status_code == 200, f"Fabric assignment failed: {fabric_resp.text}"

    # 5. Publish
    pub_resp = client.post(
        f"/api/v1/models/{model_id}/publish",
        headers=ADMIN_HEADERS,
    )
    assert pub_resp.status_code == 200, f"Publish failed: {pub_resp.text}"

    return model_id


# ===========================================================================
# Test 1 — Happy path
# Upload → Draft → admin edits → zones + fabrics → publish
# → client views detail → constraints endpoint
# ===========================================================================


def test_happy_path(client, db_session):
    """
    Full happy-path end-to-end:
    1. POST /models/init  → 201, Draft, version == 1
    2. Seed zones
    3. PATCH description  → 200
    4. PUT zones          → 200, one zone assigned
    5. Create category + fabric via Module 3
    6. PUT fabrics        → 200, one fabric assigned
    7. POST /publish      → 200, Published, version == 1
    8. GET /models/{id}   (client) → 200, has zones + fabrics, no creator_id
    9. GET /models/{id}/constraints → 200, has model_id, version, zones, fabrics
    """
    # ── Step 1: init model ─────────────────────────────────────────────────
    init_resp = _post_init_model(client)
    assert init_resp.status_code == 201, f"Init failed: {init_resp.text}"
    body = init_resp.json()
    model_id = body["model_id"]
    assert body["status"] == "Draft"
    assert body["version"] == 1

    # ── Step 2: seed zones ─────────────────────────────────────────────────
    zone_ids = _seed_zones(db_session)
    assert len(zone_ids) > 0, "No zones seeded"

    # ── Step 3: admin edits description ───────────────────────────────────
    patch_resp = client.patch(
        f"/api/v1/models/{model_id}",
        json={"description": "Admin added this description"},
        headers=ADMIN_HEADERS,
    )
    assert patch_resp.status_code == 200, f"PATCH failed: {patch_resp.text}"
    assert patch_resp.json()["description"] == "Admin added this description"

    # ── Step 4: assign one zone ────────────────────────────────────────────
    zone_resp = client.put(
        f"/api/v1/models/{model_id}/zones",
        json={"zone_ids": [zone_ids[0]]},
        headers=ADMIN_HEADERS,
    )
    assert zone_resp.status_code == 200, f"Zone assignment failed: {zone_resp.text}"
    assert len(zone_resp.json()["zones"]) == 1

    # ── Step 5: create category + fabric (Module 3) ────────────────────────
    fabric_id = _create_fabric(client)

    # ── Step 6: assign fabric ──────────────────────────────────────────────
    fabric_resp = client.put(
        f"/api/v1/models/{model_id}/fabrics",
        json={"fabric_ids": [fabric_id]},
        headers=ADMIN_HEADERS,
    )
    assert fabric_resp.status_code == 200, f"Fabric assignment failed: {fabric_resp.text}"
    assert len(fabric_resp.json()["fabrics"]) == 1

    # ── Step 7: publish ────────────────────────────────────────────────────
    pub_resp = client.post(
        f"/api/v1/models/{model_id}/publish",
        headers=ADMIN_HEADERS,
    )
    assert pub_resp.status_code == 200, f"Publish failed: {pub_resp.text}"
    pub_body = pub_resp.json()
    assert pub_body["status"] == "Published"
    assert pub_body["version"] == 1

    # ── Step 8: client views detail ───────────────────────────────────────
    detail_resp = client.get(
        f"/api/v1/models/{model_id}",
        headers=CLIENT_HEADERS,
    )
    assert detail_resp.status_code == 200, f"GET detail failed: {detail_resp.text}"
    detail = detail_resp.json()
    assert len(detail["zones"]) == 1
    assert len(detail["fabrics"]) == 1
    # creator_id must NOT be exposed to clients
    assert "creator_id" not in detail

    # ── Step 9: internal constraints endpoint ─────────────────────────────
    constraints_resp = client.get(
        f"/api/v1/models/{model_id}/constraints",
        headers=ANY_AUTH,
    )
    assert constraints_resp.status_code == 200, (
        f"Constraints failed: {constraints_resp.text}"
    )
    constraints = constraints_resp.json()
    assert constraints["model_id"] == model_id
    assert constraints["version"] == 1
    assert len(constraints["zones"]) == 1
    assert len(constraints["fabrics"]) == 1


# ===========================================================================
# Test 2 — Edit-and-republish cycle
# Published → PATCH (snapshot) → version++ after republish → repeat
# ===========================================================================


def test_edit_and_republish_cycle(client, db_session):
    """
    Edit-and-republish cycle:
    1. Create a published model (full happy path)
    2. Snapshot count before = 0
    3. PATCH description → snapshot created → count == 1
    4. POST /publish → version == 2
    5. PATCH again → snapshot count == 2
    6. POST /publish → version == 3
    """
    # ── Step 1: create published model ────────────────────────────────────
    model_id = _create_published_model(client, db_session)

    # ── Step 2: snapshot count before any edits ───────────────────────────
    count_before = _count_snapshots(db_session, model_id)
    assert count_before == 0, f"Expected 0 snapshots before edit, got {count_before}"

    # ── Step 3: first PATCH on Published model — creates a snapshot ────────
    patch1_resp = client.patch(
        f"/api/v1/models/{model_id}",
        json={"description": "first edit"},
        headers=ADMIN_HEADERS,
    )
    assert patch1_resp.status_code == 200, f"First PATCH failed: {patch1_resp.text}"

    count_after_patch1 = _count_snapshots(db_session, model_id)
    assert count_after_patch1 == 1, (
        f"Expected 1 snapshot after first PATCH, got {count_after_patch1}"
    )

    # ── Step 4: republish — version increments ────────────────────────────
    pub2_resp = client.post(
        f"/api/v1/models/{model_id}/publish",
        headers=ADMIN_HEADERS,
    )
    assert pub2_resp.status_code == 200, f"Second publish failed: {pub2_resp.text}"
    assert pub2_resp.json()["version"] == 2, (
        f"Expected version 2, got {pub2_resp.json()['version']}"
    )

    # ── Step 5: second PATCH — creates another snapshot ───────────────────
    patch2_resp = client.patch(
        f"/api/v1/models/{model_id}",
        json={"description": "second edit"},
        headers=ADMIN_HEADERS,
    )
    assert patch2_resp.status_code == 200, f"Second PATCH failed: {patch2_resp.text}"

    count_after_patch2 = _count_snapshots(db_session, model_id)
    assert count_after_patch2 == 2, (
        f"Expected 2 snapshots after second PATCH, got {count_after_patch2}"
    )

    # ── Step 6: republish again — version strictly increases ──────────────
    pub3_resp = client.post(
        f"/api/v1/models/{model_id}/publish",
        headers=ADMIN_HEADERS,
    )
    assert pub3_resp.status_code == 200, f"Third publish failed: {pub3_resp.text}"
    assert pub3_resp.json()["version"] == 3, (
        f"Expected version 3, got {pub3_resp.json()['version']}"
    )


# ===========================================================================
# Test 3 — Archive flow
# Published → archive → client 404 → constraints still 200
# ===========================================================================


def test_archive_flow(client, db_session):
    """
    Archive flow:
    1. Create a published model (full happy path)
    2. POST /archive → 200, status == "Archived"
    3. GET /models (client) → model_id NOT in items
    4. GET /models/{id} (client) → 404
    5. GET /models/{id}/constraints → 200 (still accessible for archived models)
    """
    # ── Step 1: create published model ────────────────────────────────────
    model_id = _create_published_model(client, db_session)

    # ── Step 2: archive the model ─────────────────────────────────────────
    archive_resp = client.post(
        f"/api/v1/models/{model_id}/archive",
        headers=ADMIN_HEADERS,
    )
    assert archive_resp.status_code == 200, f"Archive failed: {archive_resp.text}"
    archive_body = archive_resp.json()
    assert archive_body["status"] == "Archived"

    # ── Step 3: client listing excludes archived model ────────────────────
    list_resp = client.get(
        "/api/v1/models",
        headers=CLIENT_HEADERS,
    )
    assert list_resp.status_code == 200, f"GET /models failed: {list_resp.text}"
    listed_ids = {item["model_id"] for item in list_resp.json()["items"]}
    assert model_id not in listed_ids, (
        f"Archived model {model_id} should not appear in client listing"
    )

    # ── Step 4: client detail returns 404 for archived model ──────────────
    detail_resp = client.get(
        f"/api/v1/models/{model_id}",
        headers=CLIENT_HEADERS,
    )
    assert detail_resp.status_code == 404, (
        f"Expected 404 for archived model, got {detail_resp.status_code}: {detail_resp.text}"
    )

    # ── Step 5: constraints endpoint still serves archived models ─────────
    constraints_resp = client.get(
        f"/api/v1/models/{model_id}/constraints",
        headers=ANY_AUTH,
    )
    assert constraints_resp.status_code == 200, (
        f"Constraints endpoint should return 200 for archived model, "
        f"got {constraints_resp.status_code}: {constraints_resp.text}"
    )
    constraints = constraints_resp.json()
    assert constraints["model_id"] == model_id
