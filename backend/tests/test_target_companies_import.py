import io

from app.models.target_company import TargetCompany


def _signup(client, email="admin@proair.com"):
    resp = client.post(
        "/auth/signup",
        json={"email": email, "password": "password123", "name": "Rep", "invite_code": "test-invite-code"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _csv_file(content: str):
    return {"file": ("companies.csv", io.BytesIO(content.encode("utf-8")), "text/csv")}


def test_import_creates_companies_with_mapped_columns(client, db_session):
    headers = _signup(client)
    csv_content = (
        "Account Name,Industry,Notes\n"
        "Acme Corp,Manufacturing,some note\n"
        "Globex Inc,Software,another note\n"
    )
    resp = client.post(
        "/target-companies/import",
        headers=headers,
        files=_csv_file(csv_content),
        data={"name_column": "Account Name", "industry_column": "Industry"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["created"]) == 2
    assert body["skipped"] == []
    assert body["errors"] == []
    names = {c["name"] for c in body["created"]}
    assert names == {"Acme Corp", "Globex Inc"}
    industries = {c["industry"] for c in body["created"]}
    assert industries == {"Manufacturing", "Software"}


def test_import_without_industry_column(client, db_session):
    headers = _signup(client)
    csv_content = "Company\nAcme Corp\n"
    resp = client.post(
        "/target-companies/import",
        headers=headers,
        files=_csv_file(csv_content),
        data={"name_column": "Company"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["created"]) == 1
    assert body["created"][0]["industry"] is None


def test_import_skips_existing_duplicate_case_insensitive(client, db_session):
    headers = _signup(client)
    db_session.add(TargetCompany(name="Acme Corp", keywords=[]))
    db_session.commit()

    csv_content = "Name\nacme corp\nNew Co\n"
    resp = client.post(
        "/target-companies/import",
        headers=headers,
        files=_csv_file(csv_content),
        data={"name_column": "Name"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["created"]) == 1
    assert body["created"][0]["name"] == "New Co"
    assert len(body["skipped"]) == 1
    assert body["skipped"][0]["reason"] == "duplicate"
    assert body["skipped"][0]["row"] == 2


def test_import_skips_duplicate_within_same_file(client, db_session):
    headers = _signup(client)
    csv_content = "Name\nAcme Corp\nACME CORP\n"
    resp = client.post(
        "/target-companies/import",
        headers=headers,
        files=_csv_file(csv_content),
        data={"name_column": "Name"},
    )
    body = resp.json()
    assert len(body["created"]) == 1
    assert len(body["skipped"]) == 1


def test_import_reports_row_error_for_missing_name(client, db_session):
    headers = _signup(client)
    csv_content = "Name,Industry\n,Manufacturing\nValid Co,Software\n"
    resp = client.post(
        "/target-companies/import",
        headers=headers,
        files=_csv_file(csv_content),
        data={"name_column": "Name", "industry_column": "Industry"},
    )
    body = resp.json()
    assert len(body["created"]) == 1
    assert len(body["errors"]) == 1
    assert body["errors"][0]["row"] == 2


def test_import_rejects_missing_name_column(client, db_session):
    headers = _signup(client)
    csv_content = "Company,Industry\nAcme Corp,Manufacturing\n"
    resp = client.post(
        "/target-companies/import",
        headers=headers,
        files=_csv_file(csv_content),
        data={"name_column": "Name"},
    )
    assert resp.status_code == 400


def test_import_rejects_non_csv_extension(client, db_session):
    headers = _signup(client)
    resp = client.post(
        "/target-companies/import",
        headers=headers,
        files={"file": ("companies.txt", io.BytesIO(b"Name\nAcme\n"), "text/plain")},
        data={"name_column": "Name"},
    )
    assert resp.status_code == 400


def test_import_rejects_oversized_row_count(client, db_session):
    headers = _signup(client)
    rows = "\n".join(f"Company {i}" for i in range(501))
    csv_content = f"Name\n{rows}\n"
    resp = client.post(
        "/target-companies/import",
        headers=headers,
        files=_csv_file(csv_content),
        data={"name_column": "Name"},
    )
    assert resp.status_code == 400


def test_import_requires_admin(client, db_session):
    _signup(client, email="admin@proair.com")
    user_headers = _signup(client, email="rep@proair.com")
    csv_content = "Name\nAcme Corp\n"
    resp = client.post(
        "/target-companies/import",
        headers=user_headers,
        files=_csv_file(csv_content),
        data={"name_column": "Name"},
    )
    assert resp.status_code == 403


def test_import_sanitizes_formula_injection_prefix(client, db_session):
    headers = _signup(client)
    csv_content = "Name,Industry\n=cmd|'/c calc'!A1,+SUM(A1:A2)\n"
    resp = client.post(
        "/target-companies/import",
        headers=headers,
        files=_csv_file(csv_content),
        data={"name_column": "Name", "industry_column": "Industry"},
    )
    body = resp.json()
    assert len(body["created"]) == 1
    assert body["created"][0]["name"].startswith("'=")
    assert body["created"][0]["industry"].startswith("'+")


def test_import_auto_follows_importing_admin(client, db_session):
    headers = _signup(client)
    csv_content = "Name\nAcme Corp\n"
    resp = client.post(
        "/target-companies/import",
        headers=headers,
        files=_csv_file(csv_content),
        data={"name_column": "Name"},
    )
    body = resp.json()
    assert body["created"][0]["follower_count"] == 1
    assert body["created"][0]["is_muted"] is False

    # The importing admin sees it immediately in their own tracked-companies list,
    # rather than the import appearing to do nothing from their perspective.
    listed = client.get("/target-companies", headers=headers).json()
    assert len(listed) == 1
    assert listed[0]["name"] == "Acme Corp"
