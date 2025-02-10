import requests
import json
import socket

PROMETHEUS_URL = f"http://localhost:9091/api/v1/query"
query = 'sum(rate(istio_requests_total{destination_workload=~"reviews-.*", response_code="200"}[60m])) / sum(rate(istio_requests_total{destination_workload=~"reviews-.*"}[60m]))'

def query_prometheus(query):
    response = requests.get(PROMETHEUS_URL, params={"query": query})
    if response.status_code == 200:
        result = response.json()
        return result.get("data", {}).get("result", [])
    else:
        print("Error querying Prometheus:", response.text)
        return []

def main():
    results = query_prometheus(query)
    for item in results:
        namespace = item["metric"].get("namespace", "unknown")
        pod = item["metric"].get("pod", "unknown")
        value = item["value"][1]
        print(f'Success rate: {value}')

if __name__ == "__main__":
    main()
