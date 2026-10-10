import pytest


@pytest.mark.integration
async def test_health_reports_database_and_fhir(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["database"] is True
    assert body["fhir"] is True
    assert body["fhir_version"] == "4.0.1"
