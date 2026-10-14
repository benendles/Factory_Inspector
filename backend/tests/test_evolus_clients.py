import os

import httpx
from dotenv import load_dotenv

load_dotenv()


def main():
    base_url = os.getenv("EVOLUS_BASE_URL", "https://api.evolus.ai").rstrip("/")
    api_key = os.getenv("EVOLUS_API_KEY")
    application_id = os.getenv("EVOLUS_APPLICATION_ID")

    if not api_key:
        raise ValueError("EVOLUS_API_KEY is missing from .env")

    if not application_id:
        raise ValueError("EVOLUS_APPLICATION_ID is missing from .env")

    headers = {
        "X-ApiKey": api_key,
        "X-Application-Id": application_id,
        "Accept": "application/json",
    }

    print("Connecting to Evolus...")

    try:
        response = httpx.get(
            f"{base_url}/api/v1/agents",
            headers=headers,
            timeout=30.0,
        )

        if response.is_success:
            print("\nSUCCESS: Evolus API connection works!")
            print(f"HTTP status: {response.status_code}")

            data = response.json()

            # Print the response without exposing request headers or secrets.
            print("\nEvolus response:")
            print(data)

        else:
            print(f"\nEvolus returned HTTP {response.status_code}.")
            print("Response:", response.text[:1000])

    except httpx.RequestError as exc:
        print(f"\nCould not connect to Evolus: {exc}")


if __name__ == "__main__":
    main()