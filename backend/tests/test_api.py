import re
from datetime import date

import pytest

from GoldrynBackend import next_due

TIMESTAMP = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")


def create_item(client, **fields):
    res = client.post("/api/items", json={"name": "Water filter", **fields})
    assert res.status_code == 201, res.text
    return res.json()


def create_note(client, item_id, body="Use the 3rd-party filter"):
    res = client.post(f"/api/items/{item_id}/notes", json={"body": body})
    assert res.status_code == 201, res.text
    return res.json()


def create_record(client, item_id, **fields):
    res = client.post(f"/api/items/{item_id}/maintenance_records", json={"date": "2026-08-15", **fields})
    assert res.status_code == 201, res.text
    return res.json()


# ============================================================================
# Auth on every route
# ============================================================================


@pytest.mark.parametrize(
    "method, path",
    [
        ("GET", "/api/items"),
        ("GET", "/api/items/1"),
        ("POST", "/api/items"),
        ("PATCH", "/api/items/1"),
        ("DELETE", "/api/items/1"),
        ("GET", "/api/tags"),
        ("POST", "/api/items/1/notes"),
        ("PATCH", "/api/notes/1"),
        ("DELETE", "/api/notes/1"),
        ("POST", "/api/items/1/maintenance_records"),
        ("PATCH", "/api/maintenance_records/1"),
        ("DELETE", "/api/maintenance_records/1"),
        ("POST", "/api/items/1/attachments"),
        ("PATCH", "/api/attachments/1"),
        ("DELETE", "/api/attachments/1"),
        ("GET", "/api/attachments/1/content"),
        ("GET", "/api/attachments/1/preview"),
    ],
)
def test_routes_require_session(anon, method, path):
    # 401 wins over body validation, so an expired session never reads as "invalid data".
    assert anon.request(method, path, json={}).status_code == 401


# ============================================================================
# Items
# ============================================================================


def test_create_item_returns_full_item(client):
    item = create_item(client, color="blue", cadence_days=90, next_maintenance_notes="Not OEM")
    assert item == {
        "id": item["id"],
        "name": "Water filter",
        "color": "blue",
        "cadence_days": 90,
        "next_maintenance_notes": "Not OEM",
        "created_at": item["created_at"],
        "next_due": None,
        "tags": [],
    }
    assert TIMESTAMP.match(item["created_at"])


def test_create_item_name_only(client):
    item = create_item(client)
    assert (item["color"], item["cadence_days"], item["next_maintenance_notes"]) == (None, None, None)
    assert item["tags"] == []


def test_create_item_trims_name(client):
    assert create_item(client, name="  Furnace  ")["name"] == "Furnace"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": ""},
        {"name": "   "},
        {"name": None},
        {"name": "x" * 201},
        {"name": "Filter", "cadence_days": 0},
        {"name": "Filter", "cadence_days": -5},
        {"name": "Filter", "cadence_days": 1.5},
        {"name": "Filter", "cadence_days": 36501},
        {"name": "Filter", "cadence_days": "soon"},
        {"name": "Filter", "color": "x" * 33},
        {"name": "Filter", "archived_at": "2026-01-01T00:00:00Z"},
        {"name": "Filter", "id": 5},
    ],
)
def test_create_item_validation(client, payload):
    assert client.post("/api/items", json=payload).status_code == 422


def test_list_items_with_next_due(client):
    filter_ = create_item(client, name="Filter", cadence_days=90)
    gutters = create_item(client, name="Gutters", cadence_days=180)
    furnace = create_item(client, name="Furnace")  # no cadence
    create_record(client, filter_["id"], date="2026-08-15")
    create_record(client, filter_["id"], date="2026-02-01")  # older: not the one that counts
    create_record(client, furnace["id"], date="2026-01-01")

    res = client.get("/api/items")
    assert res.status_code == 200
    assert res.json() == [
        {"id": filter_["id"], "name": "Filter", "color": None, "cadence_days": 90, "next_due": "2026-11-13"},
        # No records: still listed (LEFT JOIN), next_due null.
        {"id": gutters["id"], "name": "Gutters", "color": None, "cadence_days": 180, "next_due": None},
        # Records but no cadence: next_due null.
        {"id": furnace["id"], "name": "Furnace", "color": None, "cadence_days": None, "next_due": None},
    ]


def test_list_items_order(client):
    """Soonest due first (overdue lead), then everything without a due date; ties keep creation order."""
    loose = create_item(client, name="Loose")  # no cadence, no records
    fresh = create_item(client, name="Fresh", cadence_days=30)  # cadence, no records
    later = create_item(client, name="Later", cadence_days=365)
    overdue = create_item(client, name="Overdue", cadence_days=30)
    tie = create_item(client, name="Tie", cadence_days=365)
    logged = create_item(client, name="Logged")  # records, no cadence
    create_record(client, later["id"], date="2026-08-15")  # due 2027-08-15
    create_record(client, overdue["id"], date="2020-01-01")  # due 2020-01-31
    create_record(client, tie["id"], date="2026-08-15")  # same due date as Later, created after it
    create_record(client, logged["id"], date="2026-01-01")

    names = [i["name"] for i in client.get("/api/items").json()]
    assert names == ["Overdue", "Later", "Tie", "Loose", "Fresh", "Logged"]


def test_list_items_empty(client):
    assert client.get("/api/items").json() == []


def test_get_item_detail(client):
    item = create_item(client, cadence_days=30)
    old_note = create_note(client, item["id"], "first")
    new_note = create_note(client, item["id"], "second")
    older = create_record(client, item["id"], date="2026-01-10", summary="Swapped", cost=45, contractor_info="Bob")
    newer = create_record(client, item["id"], date="2026-03-01")

    res = client.get(f"/api/items/{item['id']}")
    assert res.status_code == 200
    detail = res.json()
    assert detail["next_due"] == "2026-03-31"
    assert detail["created_at"] == item["created_at"]
    # Newest first; same-second notes fall back to id.
    assert [n["id"] for n in detail["notes"]] == [new_note["id"], old_note["id"]]
    assert [r["id"] for r in detail["maintenance_records"]] == [newer["id"], older["id"]]
    assert detail["maintenance_records"][1] == {
        "id": older["id"],
        "date": "2026-01-10",
        "summary": "Swapped",
        "cost": 45.0,
        "contractor_info": "Bob",
    }


@pytest.mark.parametrize("path", ["/api/items/999", "/api/items/9223372036854775807"])
def test_get_missing_item_is_404(client, path):
    assert client.get(path).status_code == 404


@pytest.mark.parametrize("path", ["/api/items/abc", "/api/items/0", "/api/items/99999999999999999999"])
def test_bad_item_id_is_422(client, path):
    assert client.get(path).status_code == 422


def test_patch_item_partial(client):
    item = create_item(client, color="blue", cadence_days=90, next_maintenance_notes="n")
    res = client.patch(f"/api/items/{item['id']}", json={"color": "green"})
    assert res.status_code == 200
    assert res.json() == {**item, "color": "green"}


def test_patch_item_null_clears_but_omitted_keeps(client):
    item = create_item(client, color="blue", cadence_days=90, next_maintenance_notes="n")
    res = client.patch(f"/api/items/{item['id']}", json={"cadence_days": None, "next_maintenance_notes": None})
    assert res.json() == {**item, "cadence_days": None, "next_maintenance_notes": None}


def test_patch_item_cadence_updates_next_due(client):
    item = create_item(client)
    create_record(client, item["id"], date="2026-01-01")
    res = client.patch(f"/api/items/{item['id']}", json={"cadence_days": 10})
    assert res.json()["next_due"] == "2026-01-11"


def test_patch_item_empty_body_returns_item(client):
    item = create_item(client)
    res = client.patch(f"/api/items/{item['id']}", json={})
    assert res.status_code == 200
    assert res.json() == item


@pytest.mark.parametrize("payload", [{"name": None}, {"name": " "}, {"cadence_days": 0}, {"bogus": 1}])
def test_patch_item_validation(client, payload):
    item = create_item(client)
    assert client.patch(f"/api/items/{item['id']}", json=payload).status_code == 422


@pytest.mark.parametrize("payload", [{"name": "x"}, {}])
def test_patch_missing_item_is_404(client, payload):
    assert client.patch("/api/items/999", json=payload).status_code == 404


def test_archive_item_hides_it(client):
    keep = create_item(client, name="Keep")
    gone = create_item(client, name="Gone")

    res = client.delete(f"/api/items/{gone['id']}")
    assert res.status_code == 200
    assert res.json() == {"message": "Item archived"}

    assert [i["id"] for i in client.get("/api/items").json()] == [keep["id"]]
    assert client.get(f"/api/items/{gone['id']}").status_code == 404
    assert client.patch(f"/api/items/{gone['id']}", json={"name": "Back"}).status_code == 404
    assert client.delete(f"/api/items/{gone['id']}").status_code == 404


def test_archive_keeps_rows_in_db(client, settings):
    import sqlite3

    item = create_item(client)
    create_note(client, item["id"])
    create_record(client, item["id"])
    client.delete(f"/api/items/{item['id']}")

    conn = sqlite3.connect(settings.db_path)
    archived_at = conn.execute("SELECT archived_at FROM items WHERE id = ?", (item["id"],)).fetchone()[0]
    assert TIMESTAMP.match(archived_at)
    assert conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM maintenance_records").fetchone()[0] == 1


def test_delete_missing_item_is_404(client):
    assert client.delete("/api/items/999").status_code == 404


# ============================================================================
# Tags
# ============================================================================


def set_tags(client, item_id, tags):
    res = client.patch(f"/api/items/{item_id}", json={"tags": tags})
    assert res.status_code == 200, res.text
    return res.json()


def test_create_item_with_tags_normalizes_them(client):
    item = create_item(client, tags=["  HVAC ", "Water   Heater"])
    assert item["tags"] == ["hvac", "water heater"]
    assert client.get(f"/api/items/{item['id']}").json()["tags"] == ["hvac", "water heater"]


def test_patch_tags_replaces_the_set_in_order(client):
    item = create_item(client, tags=["hvac", "basement"])
    assert set_tags(client, item["id"], ["kitchen", "hvac"])["tags"] == ["kitchen", "hvac"]


def test_patch_without_tags_keeps_them_and_empty_list_clears(client):
    item = create_item(client, tags=["hvac"])
    assert client.patch(f"/api/items/{item['id']}", json={"name": "Furnace"}).json()["tags"] == ["hvac"]
    assert set_tags(client, item["id"], [])["tags"] == []


def test_tags_are_shared_across_items_case_insensitively(client, settings):
    import sqlite3

    first = create_item(client, name="Furnace", tags=["HVAC"])
    second = create_item(client, name="AC", tags=["hvac"])
    assert first["tags"] == second["tags"] == ["hvac"]
    assert sqlite3.connect(settings.db_path).execute("SELECT COUNT(*) FROM tags").fetchone()[0] == 1


def test_duplicate_tags_collapse_before_the_limit(client):
    item = create_item(client, tags=["hvac", "HVAC", " hvac ", "a", "b"])
    assert item["tags"] == ["hvac", "a", "b"]


@pytest.mark.parametrize(
    "tags",
    [
        ["a", "b", "c", "d"],
        [""],
        ["   "],
        ["x" * 33],
        "hvac",
        [None],
    ],
)
def test_tag_validation(client, tags):
    assert client.post("/api/items", json={"name": "Furnace", "tags": tags}).status_code == 422
    item = create_item(client, tags=["keep"])
    assert client.patch(f"/api/items/{item['id']}", json={"tags": tags}).status_code == 422
    assert client.get(f"/api/items/{item['id']}").json()["tags"] == ["keep"]


def test_patch_null_tags_is_422(client):
    item = create_item(client)
    assert client.patch(f"/api/items/{item['id']}", json={"tags": None}).status_code == 422


def test_tag_name_at_max_length(client):
    assert create_item(client, tags=["x" * 32])["tags"] == ["x" * 32]


def test_patch_tags_on_missing_item_creates_nothing(client, settings):
    import sqlite3

    assert client.patch("/api/items/999", json={"tags": ["hvac"]}).status_code == 404
    assert sqlite3.connect(settings.db_path).execute("SELECT COUNT(*) FROM tags").fetchone()[0] == 0


def test_list_tags_most_used_first_then_by_name(client):
    create_item(client, name="Furnace", tags=["hvac", "basement"])
    create_item(client, name="AC", tags=["hvac", "attic"])
    res = client.get("/api/tags")
    assert res.status_code == 200
    assert res.json() == [
        {"name": "hvac", "item_count": 2},
        {"name": "attic", "item_count": 1},
        {"name": "basement", "item_count": 1},
    ]


def test_list_tags_skips_unused_and_archived(client):
    assert client.get("/api/tags").json() == []
    removed = create_item(client, name="Gutters", tags=["outside"])
    archived = create_item(client, name="Old filter", tags=["kitchen"])
    set_tags(client, removed["id"], [])
    client.delete(f"/api/items/{archived['id']}")
    assert client.get("/api/tags").json() == []


# ============================================================================
# Notes
# ============================================================================


def test_note_crud(client):
    item = create_item(client)
    note = create_note(client, item["id"], "Buy filters")
    assert note["body"] == "Buy filters"
    assert TIMESTAMP.match(note["created_at"])

    res = client.patch(f"/api/notes/{note['id']}", json={"body": "Buy 2 filters"})
    assert res.status_code == 200
    assert res.json() == {**note, "body": "Buy 2 filters"}

    res = client.delete(f"/api/notes/{note['id']}")
    assert res.status_code == 200
    assert client.get(f"/api/items/{item['id']}").json()["notes"] == []
    assert client.delete(f"/api/notes/{note['id']}").status_code == 404


@pytest.mark.parametrize("payload", [{}, {"body": ""}, {"body": "  \n "}, {"body": None}, {"body": "x", "item_id": 2}])
def test_create_note_validation(client, payload):
    item = create_item(client)
    assert client.post(f"/api/items/{item['id']}/notes", json=payload).status_code == 422


@pytest.mark.parametrize("payload", [{"body": ""}, {"body": None}])
def test_patch_note_validation(client, payload):
    note = create_note(client, create_item(client)["id"])
    assert client.patch(f"/api/notes/{note['id']}", json=payload).status_code == 422


def test_note_on_missing_item_is_404(client):
    assert client.post("/api/items/999/notes", json={"body": "x"}).status_code == 404


def test_missing_note_is_404(client):
    assert client.patch("/api/notes/999", json={"body": "x"}).status_code == 404
    assert client.patch("/api/notes/999", json={}).status_code == 404
    assert client.delete("/api/notes/999").status_code == 404


# ============================================================================
# Maintenance records
# ============================================================================


def test_record_crud(client):
    item = create_item(client, cadence_days=30)
    record = create_record(client, item["id"], summary="Replaced", cost=45.5, contractor_info="Bob's HVAC")
    assert record == {
        "id": record["id"],
        "date": "2026-08-15",
        "summary": "Replaced",
        "cost": 45.5,
        "contractor_info": "Bob's HVAC",
    }

    res = client.patch(f"/api/maintenance_records/{record['id']}", json={"date": "2026-09-01", "cost": None})
    assert res.status_code == 200
    assert res.json() == {**record, "date": "2026-09-01", "cost": None}
    assert client.get(f"/api/items/{item['id']}").json()["next_due"] == "2026-10-01"

    assert client.delete(f"/api/maintenance_records/{record['id']}").status_code == 200
    detail = client.get(f"/api/items/{item['id']}").json()
    assert detail["maintenance_records"] == []
    assert detail["next_due"] is None


def test_record_date_only(client):
    record = create_record(client, create_item(client)["id"])
    assert (record["summary"], record["cost"], record["contractor_info"]) == (None, None, None)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"date": None},
        {"date": "08/15/2026"},
        {"date": "2026-02-30"},
        {"date": "2026-08-15T10:00:00"},
        {"date": 1786752000},
        {"date": "2026-08-15", "cost": -1},
        {"date": "2026-08-15", "cost": "abc"},
    ],
)
def test_create_record_validation(client, payload):
    item = create_item(client)
    assert client.post(f"/api/items/{item['id']}/maintenance_records", json=payload).status_code == 422


@pytest.mark.parametrize("payload", [{"date": None}, {"date": "tomorrow"}, {"cost": -0.01}])
def test_patch_record_validation(client, payload):
    record = create_record(client, create_item(client)["id"])
    assert client.patch(f"/api/maintenance_records/{record['id']}", json=payload).status_code == 422


def test_record_on_missing_item_is_404(client):
    assert client.post("/api/items/999/maintenance_records", json={"date": "2026-01-01"}).status_code == 404


def test_missing_record_is_404(client):
    assert client.patch("/api/maintenance_records/999", json={"cost": 1}).status_code == 404
    assert client.delete("/api/maintenance_records/999").status_code == 404


# ============================================================================
# Children of archived items
# ============================================================================


def test_children_of_archived_item_are_404(client):
    item = create_item(client)
    note = create_note(client, item["id"])
    record = create_record(client, item["id"])
    client.delete(f"/api/items/{item['id']}").raise_for_status()

    assert client.post(f"/api/items/{item['id']}/notes", json={"body": "x"}).status_code == 404
    assert client.patch(f"/api/notes/{note['id']}", json={"body": "x"}).status_code == 404
    assert client.delete(f"/api/notes/{note['id']}").status_code == 404

    assert client.post(f"/api/items/{item['id']}/maintenance_records", json={"date": "2026-01-01"}).status_code == 404
    assert client.patch(f"/api/maintenance_records/{record['id']}", json={"cost": 1}).status_code == 404
    assert client.delete(f"/api/maintenance_records/{record['id']}").status_code == 404


# ============================================================================
# next_due
# ============================================================================


@pytest.mark.parametrize(
    "last, cadence, expected",
    [
        (None, None, None),
        (None, 90, None),
        ("2026-08-15", None, None),
        ("2026-08-15", 90, date(2026, 11, 13)),
        ("2028-02-01", 29, date(2028, 3, 1)),  # leap year
        ("9999-12-01", 365, None),  # overflow doesn't 500
    ],
)
def test_next_due(last, cadence, expected):
    assert next_due(last, cadence) == expected
