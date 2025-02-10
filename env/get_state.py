import requests
import json
import socket

PROMETHEUS_URL = f"http://localhost:9090/api/v1/query"
query = 'avg(container_memory_working_set_bytes{pod=~"reviews-v1-.*"}) by (namespace, pod) / on (namespace, pod) group_left kube_pod_container_resource_limits{resource="memory", pod=~"reviews-v1-.*"} * 100'

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
        value = item["value"][1]  # Nilai metrik ada di indeks ke-1
        print(f"Namespace: {namespace}, Pod: {pod}, Memory Usage (%): {value}")

if __name__ == "__main__":
    main()
