import pytest
import logging

logging.basicConfig(level=logging.INFO)

def test_health(client):
    """test health check endpoint"""
    response = client.get("/api/v1/agent/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_ask_general(client):
    """test general knowledge query"""
    query = "who are you?"
    response = client.post("/api/v1/agent/ask", json={"query": query})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "response" in data
    print(f"\ngeneral query: {query}")
    print(f"response: {data['response'][:100]}...")

def test_ask_sql(client):
    """test sql agent functionality"""
    query = "count the total number of currencies in the database"
    response = client.post("/api/v1/agent/ask", json={"query": query})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    print(f"\nsql query: {query}")
    print(f"response: {data['response']}")

def test_ask_api(client):
    """test api agent functionality with a valid uuid from db"""
    query = "get details for currency with id a9412b9c-9515-4713-b410-85a8aaf348cc"
    response = client.post("/api/v1/agent/ask", json={"query": query})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    print(f"\napi query: {query}")
    print(f"response: {data['response']}")

def test_ask_rag(client):
    """test rag agent functionality with indexed docs"""
    query = "what are the key value propositions of the PG service?"
    response = client.post("/api/v1/agent/ask", json={"query": query})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    print(f"\nrag query: {query}")
    print(f"response: {data['response'][:200]}...")
