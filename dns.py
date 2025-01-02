import requests
import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

# Configuration
ADGUARD_URL = os.getenv("ADGUARD_URL")
ADGUARD_USERNAME = os.getenv("ADGUARD_USERNAME")
ADGUARD_PASSWORD = os.getenv("ADGUARD_PASSWORD")
HOME_ASSISTANT_URL = os.getenv("HOME_ASSISTANT_URL")
HOME_ASSISTANT_TOKEN = os.getenv("HOME_ASSISTANT_TOKEN")

# Mapping IPs to friendly names
IP_MAPPING = {
    "10.99.0.21": "sensor.adguard_queries_ipad_mathieu",
    "10.99.0.22": "sensor.adguard_queries_ipad_alice",
    "10.99.0.23": "sensor.adguard_queries_ipad_lily",
    "10.99.0.24": "sensor.adguard_queries_a9_mathieu",
}

QUERY_LIMIT = int(os.getenv("QUERY_LIMIT", 1000))


def fetch_querylog(limit):
    """Fetch DNS query log from AdGuard."""
    try:
        response = requests.get(
            f"{ADGUARD_URL}?limit={limit}",
            auth=(ADGUARD_USERNAME, ADGUARD_PASSWORD),
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error fetching query log: {e}")
        return None


def process_querylog(data, ip_mapping):
    """Process query log and count queries from specific clients in the last 10 minutes."""
    if not data or "data" not in data:
        print("No valid data received from AdGuard.")
        return {}

    now = datetime.now(timezone.utc)
    ten_minutes_ago = now - timedelta(minutes=10)

    ip_query_counts = {ip: 0 for ip in ip_mapping.keys()}

    for query in data["data"]:
        raw_time = query.get("time", "")
        client_ip = query.get("client", "")

        if raw_time and client_ip in ip_mapping:
            # Process time: remove sub-second precision and handle timezone
            processed_time = raw_time.split(".")[0] + raw_time[-6:]
            try:
                query_timestamp = datetime.fromisoformat(processed_time)
                if query_timestamp > ten_minutes_ago:
                    ip_query_counts[client_ip] += 1
            except ValueError:
                print(f"Invalid time format: {raw_time}")

    return ip_query_counts


def publish_to_home_assistant(ip_query_counts, ip_mapping):
    """Publish query counts and usage state to Home Assistant."""
    headers = {
        "Authorization": f"Bearer {HOME_ASSISTANT_TOKEN}",
        "Content-Type": "application/json",
    }

    for ip, count in ip_query_counts.items():
        sensor_name = ip_mapping[ip]
        is_in_use = count > 10  # Decision logic

        # Push query count
        url_count = f"{HOME_ASSISTANT_URL}/{sensor_name}"
        payload_count = {
            "state": count,
            "attributes": {
                "ip": ip,
                "unit_of_measurement": "queries",
                "friendly_name": f"AdGuard Queries ({sensor_name})",
            },
        }
        try:
            response = requests.post(url_count, headers=headers, json=payload_count)
            response.raise_for_status()
            print(f"Updated sensor {sensor_name}: {count} queries")
        except requests.RequestException as e:
            print(f"Error updating Home Assistant sensor {sensor_name}: {e}")

        # Push in-use state
        in_use_sensor = f"{sensor_name}_in_use"
        url_in_use = f"{HOME_ASSISTANT_URL}/{in_use_sensor}"
        payload_in_use = {
            "state": "on" if is_in_use else "off",
            "attributes": {
                "ip": ip,
                "query_count": count,
                "friendly_name": f"Device In Use ({sensor_name})",
            },
        }
        try:
            response = requests.post(url_in_use, headers=headers, json=payload_in_use)
            response.raise_for_status()
            print(f"Updated in-use sensor {in_use_sensor}: {'on' if is_in_use else 'off'}")
        except requests.RequestException as e:
            print(f"Error updating Home Assistant in-use sensor {in_use_sensor}: {e}")


if __name__ == "__main__":
    querylog = fetch_querylog(QUERY_LIMIT)
    query_counts = process_querylog(querylog, IP_MAPPING)

    # Publish the results to Home Assistant
    publish_to_home_assistant(query_counts, IP_MAPPING)
