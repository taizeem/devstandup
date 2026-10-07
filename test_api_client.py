import json
import requests
from requests.auth import HTTPBasicAuth

# ==============================================================================
# CONFIGURATION
# ==============================================================================
BASE_URL = "http://127.0.0.1:8000"


USERNAME = "dave_discord"
PASSWORD = "pass123"

# Target Team ID
TEAM_ID = 4

SUBMIT_URL = f"{BASE_URL}/api/v1/standups/submit/{TEAM_ID}/"
HISTORY_URL = f"{BASE_URL}/api/v1/standups/history/?team_id={TEAM_ID}"


def print_response(title: str, response: requests.Response):
    print(f"\n{'=' * 60}")
    print(f"📡 {title}")
    print(f"{'=' * 60}")
    print(f"Status Code : {response.status_code}")
    try:
        data = response.json()
        print("Response Body:\n" + json.dumps(data, indent=2))
    except Exception:
        print(f"Raw Response: {response.text}")


def main():
    session = requests.Session()
    session.auth = HTTPBasicAuth(USERNAME, PASSWORD)
    session.headers.update({"Content-Type": "application/json"})

    # -------------------------------------------------------------------------
    # TEST 1: Submit a valid standup entry
    # -------------------------------------------------------------------------
    payload_valid = {
        "yesterday": "Implemented webhook retry logic and worker deadlocks profiling.",
        "today": "Refactoring serializers and setting up Discord embeds.",
        "blockers": "None",
    }

    res_submit = session.post(SUBMIT_URL, json=payload_valid)
    print_response("TEST 1: Valid Standup Submission (POST)", res_submit)

    if res_submit.status_code not in (200, 201):
        print("\n❌ Failed to submit. Ensure your Django server is running and user credentials match.")
        return

    # -------------------------------------------------------------------------
    # TEST 2: Update existing entry for today (Idempotency Check)
    # -------------------------------------------------------------------------
    payload_update = {
        "yesterday": "Implemented webhook retry logic (Updated).",
        "today": "Refactoring serializers (Updated).",
        "blockers": "Need staging Redis instance access.",
    }

    res_update = session.post(SUBMIT_URL, json=payload_update)
    print_response("TEST 2: Update Existing Entry (Idempotent 200 OK)", res_update)

    # -------------------------------------------------------------------------
    # TEST 3: Validation Error Handling (Missing Required Field)
    # -------------------------------------------------------------------------
    payload_invalid = {
        "yesterday": "",  # Empty field should trigger validation error
        "today": "Working on frontend bugs.",
        "blockers": "None",
    }

    res_invalid = session.post(SUBMIT_URL, json=payload_invalid)
    print_response("TEST 3: Validation Check (Expected 400 Bad Request)", res_invalid)

    # -------------------------------------------------------------------------
    # TEST 4: Query Standup History for this Team
    # -------------------------------------------------------------------------
    res_history = session.get(HISTORY_URL)
    print_response("TEST 4: Query Standup History (GET)", res_history)


if __name__ == "__main__":
    main()