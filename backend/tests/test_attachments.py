import io
import sqlite3

import pytest
from PIL import Image

import attachments
import db

PDF_BYTES = b"%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"


def create_item(client, name="Furnace"):
    res = client.post("/api/items", json={"name": name})
    assert res.status_code == 201, res.text
    return res.json()


def png_bytes(size=(1200, 900), mode="RGB"):
    buffer = io.BytesIO()
    Image.new(mode, size, (200, 30, 30, 128) if mode == "RGBA" else (200, 30, 30)).save(buffer, "PNG")
    return buffer.getvalue()


def upload(client, item_id, filename, content, content_type="application/octet-stream"):
    return client.post(f"/api/items/{item_id}/attachments", files={"file": (filename, content, content_type)})


def upload_ok(client, item_id, filename, content, content_type="application/octet-stream"):
    res = upload(client, item_id, filename, content, content_type)
    assert res.status_code == 201, res.text
    return res.json()


def stored_files(settings):
    return sorted(p.name for p in settings.attachments_dir.iterdir() if p.is_file())


# ============================================================================
# Upload and classification
# ============================================================================


def test_image_upload_gets_a_preview(client):
    item = create_item(client)
    attachment = upload_ok(client, item["id"], "furnace.png", png_bytes(), "image/png")
    assert attachment["kind"] == "image"
    assert attachment["content_type"] == "image/png"
    assert attachment["filename"] == "furnace.png"
    assert attachment["size_bytes"] == len(png_bytes())

    preview = client.get(f"/api/attachments/{attachment['id']}/preview")
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/jpeg"
    assert "immutable" in preview.headers["cache-control"]
    image = Image.open(io.BytesIO(preview.content))
    assert max(image.size) == attachments.PREVIEW_SIZE


def test_transparent_image_preview_is_flattened(client):
    item = create_item(client)
    attachment = upload_ok(client, item["id"], "logo.png", png_bytes((50, 50), "RGBA"))
    preview = client.get(f"/api/attachments/{attachment['id']}/preview")
    assert Image.open(io.BytesIO(preview.content)).mode == "RGB"


def test_pdf_is_detected_by_its_bytes(client):
    item = create_item(client)
    attachment = upload_ok(client, item["id"], "manual", PDF_BYTES)
    assert (attachment["kind"], attachment["content_type"]) == ("pdf", "application/pdf")
    assert client.get(f"/api/attachments/{attachment['id']}/preview").status_code == 404


@pytest.mark.parametrize(
    "filename, content, kind",
    [
        ("notes.txt", "Filter size 16x25x1 ✓".encode(), "text"),
        ("parts.csv", b"part,cost\nfilter,45\n", "text"),
        # Sent as plain text, so markup is shown, never run.
        ("page.html", b"<script>alert(1)</script>", "text"),
        # Named like a PDF or an image, but the bytes aren't one.
        ("fake.pdf", b"<script>alert(1)</script>", "file"),
        ("fake.png", b"not an image", "file"),
        ("binary.txt", b"abc\x00def", "file"),
        ("latin1.txt", "café au lait".encode("latin-1"), "file"),
        ("warranty.docx", b"PK\x03\x04 zipped", "file"),
    ],
)
def test_kind_comes_from_the_contents(client, filename, content, kind):
    item = create_item(client)
    assert upload_ok(client, item["id"], filename, content, "image/png")["kind"] == kind


def test_utf8_cut_mid_character_is_still_text(client):
    item = create_item(client)
    content = b"a" * (attachments.SNIFF_BYTES - 1) + "é".encode()
    assert upload_ok(client, item["id"], "long.txt", content)["kind"] == "text"


def test_uploaded_bytes_are_stored_unchanged(client, settings):
    item = create_item(client)
    attachment = upload_ok(client, item["id"], "manual.pdf", PDF_BYTES)
    assert client.get(f"/api/attachments/{attachment['id']}/content").content == PDF_BYTES
    assert len(stored_files(settings)) == 1


@pytest.mark.parametrize(
    "sent, kept",
    [
        ("C:\\Users\\me\\Scans\\receipt.pdf", "receipt.pdf"),
        ("../../etc/passwd", "passwd"),
        ("  water   filter manual.pdf ", "water filter manual.pdf"),
        ("/", "file"),
        ("x" * 300 + ".pdf", "x" * 255),
    ],
)
def test_upload_filename_is_cleaned(client, sent, kept):
    item = create_item(client)
    assert upload_ok(client, item["id"], sent, PDF_BYTES)["filename"] == kept


def test_duplicate_names_get_a_suffix(client):
    item = create_item(client)
    names = [upload_ok(client, item["id"], "receipt.pdf", PDF_BYTES)["filename"] for _ in range(3)]
    assert names == ["receipt.pdf", "receipt (2).pdf", "receipt (3).pdf"]


def test_same_name_on_another_item_is_fine(client):
    first, second = create_item(client, "Furnace"), create_item(client, "Water heater")
    upload_ok(client, first["id"], "manual.pdf", PDF_BYTES)
    assert upload_ok(client, second["id"], "manual.pdf", PDF_BYTES)["filename"] == "manual.pdf"


def test_archived_name_can_be_reused(client):
    item = create_item(client)
    old = upload_ok(client, item["id"], "manual.pdf", PDF_BYTES)
    client.delete(f"/api/attachments/{old['id']}")
    assert upload_ok(client, item["id"], "manual.pdf", PDF_BYTES)["filename"] == "manual.pdf"


# ============================================================================
# Upload limits and errors
# ============================================================================


def test_upload_to_missing_or_archived_item_is_404(client, settings):
    item = create_item(client)
    client.delete(f"/api/items/{item['id']}")
    assert upload(client, item["id"], "a.pdf", PDF_BYTES).status_code == 404
    assert upload(client, 999, "a.pdf", PDF_BYTES).status_code == 404
    assert stored_files(settings) == []


def test_too_large_by_content_length(client, settings, monkeypatch):
    monkeypatch.setattr(attachments, "MAX_UPLOAD_BYTES", 1000)
    monkeypatch.setattr(attachments, "MULTIPART_OVERHEAD_BYTES", 0)
    item = create_item(client)
    res = upload(client, item["id"], "big.bin", b"x" * 1000)  # the multipart framing tips it over
    assert res.status_code == 413
    assert stored_files(settings) == []


def test_too_large_by_file_size(client, settings, monkeypatch):
    monkeypatch.setattr(attachments, "MAX_UPLOAD_BYTES", 1000)
    item = create_item(client)
    assert upload(client, item["id"], "big.bin", b"x" * 1001).status_code == 413
    assert upload(client, item["id"], "ok.bin", b"x" * 1000).status_code == 201


def test_upload_needs_content_length(client):
    item = create_item(client)
    res = client.post(
        f"/api/items/{item['id']}/attachments",
        content=iter([b"chunked"]),
        headers={"Content-Type": "multipart/form-data; boundary=x"},
    )
    assert res.status_code == 411


@pytest.mark.parametrize(
    "kwargs",
    [
        {"files": {"other": ("a.pdf", PDF_BYTES)}},
        {"files": {"file": ("a.pdf", PDF_BYTES)}, "data": {"extra": "field"}},
        {"files": [("file", ("a.pdf", PDF_BYTES)), ("file", ("b.pdf", PDF_BYTES))]},
        {"json": {"file": "a.pdf"}},
        {"content": b"--x\r\nnot a real form", "headers": {"Content-Type": "multipart/form-data; boundary=x"}},
    ],
)
def test_bad_upload_bodies_are_422(client, settings, kwargs):
    item = create_item(client)
    assert client.post(f"/api/items/{item['id']}/attachments", **kwargs).status_code == 422
    assert stored_files(settings) == []


def test_failed_insert_removes_the_file(client, settings, monkeypatch):
    item = create_item(client)

    def boom(*args, **kwargs):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(db, "insert_attachment", boom)
    with pytest.raises(sqlite3.OperationalError):
        upload(client, item["id"], "photo.png", png_bytes())
    assert stored_files(settings) == []
    assert list((settings.attachments_dir / "previews").iterdir()) == []


# ============================================================================
# Serving
# ============================================================================


@pytest.mark.parametrize(
    "filename, content, media_type, disposition, sandboxed",
    [
        ("photo.png", png_bytes(), "image/png", "inline", True),
        ("manual.pdf", PDF_BYTES, "application/pdf", "inline", False),
        ("page.html", b"<script>alert(1)</script>", "text/plain; charset=utf-8", "inline", True),
        ("warranty.docx", b"PK\x03\x04", "application/octet-stream", "attachment", False),
    ],
)
def test_content_headers(client, filename, content, media_type, disposition, sandboxed):
    item = create_item(client)
    attachment = upload_ok(client, item["id"], filename, content)
    res = client.get(f"/api/attachments/{attachment['id']}/content")
    assert res.status_code == 200
    assert res.headers["content-type"] == media_type
    assert res.headers["content-disposition"].startswith(f'{disposition}; filename="{filename}"')
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["cache-control"] == "private, no-store"
    assert ("content-security-policy" in res.headers) == sandboxed


def test_non_ascii_filename_is_encoded_in_the_header(client):
    item = create_item(client)
    attachment = upload_ok(client, item["id"], "réçu.pdf", PDF_BYTES)
    disposition = client.get(f"/api/attachments/{attachment['id']}/content").headers["content-disposition"]
    assert disposition == "inline; filename*=utf-8''r%C3%A9%C3%A7u.pdf"


def test_missing_file_on_disk_is_404(client, settings):
    item = create_item(client)
    attachment = upload_ok(client, item["id"], "manual.pdf", PDF_BYTES)
    for name in stored_files(settings):
        (settings.attachments_dir / name).unlink()
    assert client.get(f"/api/attachments/{attachment['id']}/content").status_code == 404


@pytest.mark.parametrize("suffix", ["content", "preview"])
def test_unknown_attachment_is_404(client, suffix):
    assert client.get(f"/api/attachments/999/{suffix}").status_code == 404


# ============================================================================
# Item detail, rename, archive
# ============================================================================


def test_item_detail_lists_active_attachments_newest_first(client):
    item = create_item(client)
    assert client.get(f"/api/items/{item['id']}").json()["attachments"] == []
    first = upload_ok(client, item["id"], "first.pdf", PDF_BYTES)
    second = upload_ok(client, item["id"], "second.pdf", PDF_BYTES)
    listed = client.get(f"/api/items/{item['id']}").json()["attachments"]
    assert [a["id"] for a in listed] == [second["id"], first["id"]]
    assert set(listed[0]) == {"id", "filename", "kind", "content_type", "size_bytes", "created_at"}


def test_rename(client):
    item = create_item(client)
    attachment = upload_ok(client, item["id"], "IMG_4032.png", png_bytes())
    res = client.patch(f"/api/attachments/{attachment['id']}", json={"filename": "  furnace\t receipt.png "})
    assert res.status_code == 200
    assert res.json() == {**attachment, "filename": "furnace receipt.png"}
    # Browsers percent-encode control characters in an upload's filename, but JSON can carry them.
    res = client.patch(f"/api/attachments/{attachment['id']}", json={"filename": "a\x00b\x1f\nc.png"})
    assert res.json()["filename"] == "abc.png"
    res = client.patch(f"/api/attachments/{attachment['id']}", json={"filename": "C:\\scans\\receipt.png"})
    assert res.json()["filename"] == "receipt.png"
    # The kind stays what the contents say, whatever the new name.
    assert client.patch(f"/api/attachments/{attachment['id']}", json={"filename": "x.txt"}).json()["kind"] == "image"


def test_rename_to_a_taken_name_gets_a_suffix(client):
    item = create_item(client)
    upload_ok(client, item["id"], "manual.pdf", PDF_BYTES)
    other = upload_ok(client, item["id"], "other.pdf", PDF_BYTES)
    res = client.patch(f"/api/attachments/{other['id']}", json={"filename": "manual.pdf"})
    assert res.json()["filename"] == "manual (2).pdf"
    # Renaming to its own name is a no-op, not "manual (2) (2).pdf".
    res = client.patch(f"/api/attachments/{other['id']}", json={"filename": "manual (2).pdf"})
    assert res.json()["filename"] == "manual (2).pdf"


@pytest.mark.parametrize("body", [{"filename": None}, {"filename": "   "}, {"filename": "x" * 256}, {"size_bytes": 1}])
def test_rename_validation(client, body):
    item = create_item(client)
    attachment = upload_ok(client, item["id"], "manual.pdf", PDF_BYTES)
    assert client.patch(f"/api/attachments/{attachment['id']}", json=body).status_code == 422


def test_empty_patch_returns_attachment_unchanged(client):
    item = create_item(client)
    attachment = upload_ok(client, item["id"], "manual.pdf", PDF_BYTES)
    assert client.patch(f"/api/attachments/{attachment['id']}", json={}).json() == attachment


def test_delete_archives_and_keeps_the_file(client, settings):
    item = create_item(client)
    attachment = upload_ok(client, item["id"], "photo.png", png_bytes())
    res = client.delete(f"/api/attachments/{attachment['id']}")
    assert res.status_code == 200

    assert client.get(f"/api/items/{item['id']}").json()["attachments"] == []
    for path in ("content", "preview"):
        assert client.get(f"/api/attachments/{attachment['id']}/{path}").status_code == 404
    assert client.patch(f"/api/attachments/{attachment['id']}", json={"filename": "x"}).status_code == 404
    assert client.delete(f"/api/attachments/{attachment['id']}").status_code == 404

    assert len(stored_files(settings)) == 1
    row = sqlite3.connect(settings.db_path).execute("SELECT archived_at FROM attachments").fetchone()
    assert row[0] is not None


def test_archived_items_attachments_are_404(client):
    item = create_item(client)
    attachment = upload_ok(client, item["id"], "manual.pdf", PDF_BYTES)
    client.delete(f"/api/items/{item['id']}")
    assert client.get(f"/api/attachments/{attachment['id']}/content").status_code == 404
    assert client.patch(f"/api/attachments/{attachment['id']}", json={"filename": "x"}).status_code == 404
    assert client.delete(f"/api/attachments/{attachment['id']}").status_code == 404


def test_ids_are_not_reused(client):
    item = create_item(client)
    first = upload_ok(client, item["id"], "a.pdf", PDF_BYTES)
    conn = sqlite3.connect(client.app.state.settings.db_path)
    conn.execute("DELETE FROM attachments")
    conn.commit()
    assert upload_ok(client, item["id"], "b.pdf", PDF_BYTES)["id"] > first["id"]
