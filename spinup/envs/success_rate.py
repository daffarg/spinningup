import requests
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor

def fetch_jaeger_traces():
    end_time = 1745986563  # Convert ke microseconds
    start_time = 1745985234

    jaeger_url = "http://192.168.49.2:30095/jaeger/api/traces"
    params = {
        "service": "productpage.default",
        "start": str(start_time),
        "end": str(end_time),
        "lookback": "15m",
    }

    response = requests.get(jaeger_url, params=params)
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error fetching traces: {response.status_code}")
        return None

def process_trace(trace):
    """Menghitung jumlah request sukses dan total request dari satu trace."""
    success_count = 0
    request_count = 0

    for span in trace.get("spans", []):
        for tag in span.get("tags", []):
            if tag["key"] == "http.status_code":
                request_count += 1
                if str(tag["value"]) == "200":
                    success_count += 1

    return success_count, request_count

def calculate_success_rate(traces):
    """Menghitung success rate dengan parallel processing."""
    total_requests = 0
    successful_requests = 0
    data = traces.get("data", [])
    print("Total requests: ", len(data))

    with ProcessPoolExecutor() as executor:
        results = executor.map(process_trace, data)

    for success, total in results:
        successful_requests += success
        total_requests += total

    if total_requests == 0:
        return 0.0
    return (successful_requests / total_requests) * 100

if __name__ == "__main__":
    traces = fetch_jaeger_traces()
    
    if traces:
        success_rate = calculate_success_rate(traces)
        print(f"Success Rate: {success_rate:.2f}%")
    else:
        print("Failed to retrieve trace data from Jaeger.")
