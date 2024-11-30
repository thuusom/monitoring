import requests
import random
import time

BASE_URL = "http://varnish_server:80"  # Target Varnish server

# List of test URLs
URLS = [
    "/apache/",
    "/apache/nonexistent",
    "/",
    "/nonexistent",
    "/static/file.html",
    "/api/resource",
]

def send_requests():
    while True:
        url = random.choice(URLS)
        try:
            response = requests.get(BASE_URL + url)
            print(f"Requested {url}: {response.status_code}")
        except Exception as e:
            print(f"Error requesting {url}: {e}")
        time.sleep(random.uniform(0.01, 0.1))  # Random delay between 10ms and 100ms

if __name__ == "__main__":
    send_requests()