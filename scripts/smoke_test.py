#!/usr/bin/env python3
"""
Smoke Test Script for Adina Bot API

Tests all critical endpoints and reports PASS/FAIL status.
"""
import os
import sys
import json
import tempfile
import requests

BASE_URL = os.environ.get("API_URL", "http://localhost:8000")
API_KEY = os.environ.get("API_KEY", "adina-local-dev-key")

HEADERS = {"x-api-key": API_KEY}

results = []


def truncate(text, max_len=200):
    """Truncate text to max_len characters."""
    text = str(text)
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


def test_endpoint(name, method, path, headers=None, json_data=None, files=None, expect_status=(200,)):
    """Test an endpoint and record result."""
    url = f"{BASE_URL}{path}"
    hdrs = headers or {}

    try:
        if method.upper() == "GET":
            resp = requests.get(url, headers=hdrs, timeout=30)
        elif method.upper() == "POST":
            if files:
                resp = requests.post(url, headers=hdrs, files=files, timeout=30)
            else:
                resp = requests.post(url, headers=hdrs, json=json_data, timeout=30)
        else:
            results.append((name, "FAIL", f"Unknown method: {method}", ""))
            return None

        status = resp.status_code
        try:
            body = resp.json()
            body_str = json.dumps(body)
        except:
            body_str = resp.text
            body = None

        if status in expect_status:
            results.append((name, "PASS", status, truncate(body_str)))
        else:
            results.append((name, "FAIL", status, truncate(body_str)))

        return {"status": status, "body": body, "text": resp.text}

    except requests.exceptions.ConnectionError as e:
        results.append((name, "FAIL", "Connection Error", str(e)[:100]))
        return None
    except Exception as e:
        results.append((name, "FAIL", "Exception", str(e)[:100]))
        return None


def main():
    print("=" * 60)
    print("ADINA BOT SMOKE TEST")
    print(f"Base URL: {BASE_URL}")
    print(f"API Key: {API_KEY[:8]}...")
    print("=" * 60)
    print()

    # 1. Health check (no auth)
    test_endpoint("GET /health", "GET", "/health")

    # 2. Ready check (no auth)
    test_endpoint("GET /ready", "GET", "/ready")

    # 3. Get leads (requires auth)
    test_endpoint("GET /api/leads", "GET", "/api/leads", headers=HEADERS)

    # 4. Get templates (requires auth)
    test_endpoint("GET /api/templates", "GET", "/api/templates", headers=HEADERS)

    # 5. Get outreach templates (requires auth)
    test_endpoint("GET /api/outreach-templates", "GET", "/api/outreach-templates", headers=HEADERS)

    # 6. CSV upload test
    csv_content = "name,email,company,title\nJohn Doe,john@example.com,Acme Inc,CEO"
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write(csv_content)
        csv_path = f.name

    try:
        with open(csv_path, 'rb') as f:
            files = {"file": ("test_leads.csv", f, "text/csv")}
            test_endpoint("POST /api/leads/upload (CSV)", "POST", "/api/leads/upload",
                         headers=HEADERS, files=files, expect_status=(200, 201))
    finally:
        os.unlink(csv_path)

    # 7. Test domain contacts endpoint with known domain
    # The endpoint requires a body with domain and source, even though domain is in path
    test_endpoint(
        "POST /api/companies/stripe.com/contacts",
        "POST",
        "/api/companies/stripe.com/contacts",
        headers=HEADERS,
        json_data={"domain": "stripe.com", "source": "hunter"},
        expect_status=(200, 502, 503)  # 200 OK, or 502/503 if API key missing/service unavailable
    )

    # 8. Test SerpAPI discover endpoint
    serpapi_payload = {
        "industry": "healthcare",
        "country": "us",
        "source": "google_maps",
        "limit": 20
    }
    resp = test_endpoint(
        "POST /api/companies/discover (SerpAPI)",
        "POST",
        "/api/companies/discover",
        headers=HEADERS,
        json_data=serpapi_payload,
        expect_status=(200,)
    )

    # Additional SerpAPI validation
    if resp and resp.get("body"):
        body = resp["body"]
        # Check it's not HTML/SVG junk
        text = resp.get("text", "")
        if "<html" in text.lower() or "<svg" in text.lower():
            results.append(("SerpAPI response validation", "FAIL", "Response contains HTML/SVG", truncate(text)))
        elif isinstance(body, dict):
            # Check for proper structure
            if "companies" in body:
                companies = body.get("companies", [])
                message = body.get("message", "")
                if message == "SerpAPI not configured":
                    results.append(("SerpAPI not configured check", "PASS", 200, f"Expected message received: {message}"))
                elif isinstance(companies, list):
                    results.append(("SerpAPI response structure", "PASS", 200, f"Got {len(companies)} companies"))
                else:
                    results.append(("SerpAPI response structure", "FAIL", 200, f"companies is not a list: {type(companies)}"))
            else:
                results.append(("SerpAPI response structure", "FAIL", 200, f"Missing 'companies' key in response"))

    # 9. Test lead profile endpoint
    # First, get any existing lead ID
    leads_resp = test_endpoint(
        "GET /api/leads (for profile test)",
        "GET",
        "/api/leads",
        headers=HEADERS,
        expect_status=(200,)
    )
    lead_id = None
    if leads_resp and isinstance(leads_resp.get("body"), list) and leads_resp["body"]:
        lead_id = leads_resp["body"][0].get("id")

    if lead_id:
        profile_resp = test_endpoint(
            f"GET /api/leads/{lead_id}/profile",
            "GET",
            f"/api/leads/{lead_id}/profile",
            headers=HEADERS,
            expect_status=(200,)
        )
        if profile_resp and isinstance(profile_resp.get("body"), dict):
            p = profile_resp["body"]
            required_fields = {"id", "company", "status", "contacts", "industry"}
            missing = required_fields - set(p.keys())
            if missing:
                results.append(("Lead profile structure", "FAIL", 200, f"Missing fields: {missing}"))
            else:
                results.append(("Lead profile structure", "PASS", 200, f"company={p.get('company')}, contacts={len(p.get('contacts', []))}"))
    else:
        results.append(("Lead profile (no leads to test)", "PASS", "SKIP", "No leads in DB"))

    # 10. Test import with profile fields (phone, website_url, contacts)
    import_payload = {
        "companies": [
            {
                "name": "Smoke Test Co Profile",
                "domain": "smoketestprofile.com",
                "description": "A test company for profile fields",
                "industry": "Technology",
                "size": None,
                "location": "Austin, TX",
                "phone": "+1-555-0199",
                "website_url": "https://smoketestprofile.com",
                "contact_name": "Alice Test",
                "contact_role": "CEO",
                "contact_email": "alice@smoketestprofile.com",
                "contacts": [
                    {"name": "Alice Test", "title": "CEO", "email": "alice@smoketestprofile.com", "source": "hunter"},
                    {"name": "Bob Test", "title": "CTO", "email": "bob@smoketestprofile.com", "source": "hunter"},
                ],
                "source": "google_maps"
            }
        ]
    }
    import_resp = test_endpoint(
        "POST /api/leads/import (profile fields)",
        "POST",
        "/api/leads/import",
        headers=HEADERS,
        json_data=import_payload,
        expect_status=(200,)
    )
    if import_resp and isinstance(import_resp.get("body"), dict):
        body = import_resp["body"]
        if body.get("imported", 0) > 0:
            # Verify profile was persisted: fetch the newly created lead
            imported_lead = body.get("leads", [{}])[0]
            new_id = imported_lead.get("id")
            if new_id:
                profile_check = test_endpoint(
                    "GET profile after import (contacts_json)",
                    "GET",
                    f"/api/leads/{new_id}/profile",
                    headers=HEADERS,
                    expect_status=(200,)
                )
                if profile_check and isinstance(profile_check.get("body"), dict):
                    p = profile_check["body"]
                    contacts = p.get("contacts", [])
                    phone = p.get("phone")
                    if len(contacts) >= 2:
                        results.append(("Import persists contacts list", "PASS", 200, f"{len(contacts)} contacts stored"))
                    else:
                        results.append(("Import persists contacts list", "FAIL", 200, f"Expected ≥2 contacts, got {len(contacts)}"))
                    if phone == "+1-555-0199":
                        results.append(("Import persists phone field", "PASS", 200, f"phone={phone}"))
                    else:
                        results.append(("Import persists phone field", "FAIL", 200, f"Expected +1-555-0199, got {phone}"))
        elif body.get("skipped", 0) > 0:
            results.append(("POST /api/leads/import (profile fields)", "PASS", 200, "Lead already exists (skipped)"))

    # 11. Gmail status check (informational)
    test_endpoint(
        "GET /api/gmail/status",
        "GET",
        "/api/gmail/status",
        headers=HEADERS,
        expect_status=(200,)
    )

    # Print results table
    print()
    print("=" * 80)
    print(f"{'TEST':<45} {'RESULT':<8} {'STATUS':<15} BODY")
    print("=" * 80)

    pass_count = 0
    fail_count = 0

    for name, result, status, body in results:
        if result == "PASS":
            pass_count += 1
            marker = "\033[92mPASS\033[0m"  # Green
        else:
            fail_count += 1
            marker = "\033[91mFAIL\033[0m"  # Red

        print(f"{name:<45} {marker:<17} {str(status):<15} {body[:40]}")

    print("=" * 80)
    print(f"\nTotal: {pass_count} PASS, {fail_count} FAIL")
    print()

    if fail_count > 0:
        print("FAILURES DETECTED - see above for details")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
