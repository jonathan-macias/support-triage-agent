from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_ticket(client: TestClient, ticket_payload: dict[str, str]) -> None:
    response = client.post("/tickets", json=ticket_payload)

    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["subject"] == ticket_payload["subject"]
    assert data["status"] == "open"
    assert data["priority"] is None
    assert data["category"] is None


def test_create_ticket_invalid_email(client: TestClient, ticket_payload: dict[str, str]) -> None:
    response = client.post("/tickets", json={**ticket_payload, "customer_email": "not-an-email"})
    assert response.status_code == 422


def test_create_ticket_missing_field(client: TestClient) -> None:
    response = client.post("/tickets", json={"subject": "No body"})
    assert response.status_code == 422


def test_get_ticket(client: TestClient, ticket_payload: dict[str, str]) -> None:
    created = client.post("/tickets", json=ticket_payload).json()

    response = client.get(f"/tickets/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_get_ticket_not_found(client: TestClient) -> None:
    response = client.get("/tickets/999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Ticket not found"


def test_list_tickets_with_filters(client: TestClient, ticket_payload: dict[str, str]) -> None:
    first = client.post("/tickets", json=ticket_payload).json()
    client.post("/tickets", json={**ticket_payload, "subject": "Another problem"})
    client.patch(f"/tickets/{first['id']}", json={"priority": "urgent"})

    all_tickets = client.get("/tickets").json()
    urgent = client.get("/tickets", params={"priority": "urgent"}).json()

    assert len(all_tickets) == 2
    assert [t["id"] for t in urgent] == [first["id"]]


def test_list_tickets_pagination(client: TestClient, ticket_payload: dict[str, str]) -> None:
    for i in range(3):
        client.post("/tickets", json={**ticket_payload, "subject": f"Ticket {i}"})

    page = client.get("/tickets", params={"limit": 2, "offset": 0}).json()
    rest = client.get("/tickets", params={"limit": 2, "offset": 2}).json()

    assert len(page) == 2
    assert len(rest) == 1
    # Newest first
    assert page[0]["subject"] == "Ticket 2"


def test_list_tickets_invalid_limit(client: TestClient) -> None:
    assert client.get("/tickets", params={"limit": 0}).status_code == 422


def test_update_ticket(client: TestClient, ticket_payload: dict[str, str]) -> None:
    created = client.post("/tickets", json=ticket_payload).json()

    response = client.patch(
        f"/tickets/{created['id']}",
        json={"status": "in_progress", "category": "account", "summary": "Login failure"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "in_progress"
    assert data["category"] == "account"
    assert data["summary"] == "Login failure"
    # Fields not sent are left unchanged
    assert data["subject"] == ticket_payload["subject"]
    assert data["updated_at"] >= created["updated_at"]


def test_update_ticket_status_null_rejected(
    client: TestClient, ticket_payload: dict[str, str]
) -> None:
    created = client.post("/tickets", json=ticket_payload).json()
    response = client.patch(f"/tickets/{created['id']}", json={"status": None})
    assert response.status_code == 422


def test_delete_ticket(client: TestClient, ticket_payload: dict[str, str]) -> None:
    created = client.post("/tickets", json=ticket_payload).json()

    response = client.delete(f"/tickets/{created['id']}")

    assert response.status_code == 204
    assert client.get(f"/tickets/{created['id']}").status_code == 404
