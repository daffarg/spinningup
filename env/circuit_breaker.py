from gymnasium import Env
from gymnasium.spaces import Box, Discrete
import numpy as np
import requests

class CircuitBreaker(Env):
    def __init__(self):
        """ Action space: maxConnections, maxRequestsPerConnection, http1MaxPendingRequests """
        self.action_list = [(10, 1, 3), (10, 1, 1), (10, 1, 5)]
        
        """ Action space sebagai Discrete (jumlah aksi = len(self.action_list)) """
        self.action_space = Discrete(len(self.action_list))
        
        """ Observation space: memory usage, CPU usage """
        self.observation_space = Box(
            low=np.array([0, 0]),  
            high=np.array([1, 1]) 
        )

        """
            Initial state: 
            - Memory Usage
            - CPU Usage
        """
        memory_usage, cpu_usage = self.get_metrics()
        self.state = np.array([memory_usage, cpu_usage])

        # Environment parameters
        self.steps_left = 100  # Number of steps before the episode ends

        """ Prometheus (kube-prometheus-stack) """
        self.prometheus_monitoring_url = "http://localhost:9090/api/v1/query"
        self.memory_usage_query = 'avg(container_memory_working_set_bytes{pod=~"productpage-.*"}) by (namespace, pod) / on (namespace, pod) group_left kube_pod_container_resource_limits{resource="memory", pod=~"productpage-.*"}'
        self.cpu_usage_query = 'avg(rate(container_cpu_usage_seconds_total{pod=~"productpage-.*"}[5m])) by (namespace, pod) / on (namespace, pod) group_left kube_pod_container_resource_limits{resource="cpu", pod=~"productpage-.*"}'
        
        """ Prometheus (Istio) """
        self.prometheus_istio_url = "http://localhost:9091/api/v1/query"
        self.success_rate_query = 'sum(rate(istio_requests_total{destination_workload=~"productpage-.*", response_code="200"}[15m])) / sum(rate(istio_requests_total{destination_workload=~"productpage-.*"}[15m]))'

    def query_prometheus(self, url, query):
        """Fetch memory and CPU usage from Prometheus API."""
        response = requests.get(url, params={"query": query})
        if response.status_code == 200:
            result = response.json()
            results = result.get("data", {}).get("result", [])
            for item in results:
                namespace = item["metric"].get("namespace", "unknown")
                pod = item["metric"].get("pod", "unknown")
                value = item["value"][1] 
                try:
                    return float(value)
                except:
                    return 0
            return 0
        else:
            print("Error querying Prometheus:", response.text)
            return 0

    def get_memory_and_cpu_usage(self):
        """Fetch memory and CPU usage from Prometheus API."""
        avg_memory_usage = self.query_prometheus(self.prometheus_monitoring_url, self.memory_usage_query)
        avg_cpu_usage = self.query_prometheus(self.prometheus_monitoring_url, self.cpu_usage_query)

        return avg_memory_usage, avg_cpu_usage
    
    def get_success_rate(self):
        return self.query_prometheus(self.prometheus_istio_url, self.success_rate_query)
    
    # def set_circuit_breaker_params(max_connections, max_request_per_connection, http1_max_pending_requests):


    def step(self, action):
        """Apply an action and return the new state, reward, done, and info."""
        max_connections, max_requests_per_connection, http1_max_pending_requests = self.action_list[action]

        memory_usage, cpu_usage = self.get_memory_and_cpu_usage()

        self.state = np.array([memory_usage, cpu_usage])

        """ Get success rate """
        success_rate = self.get_success_rate()
        if success_rate >= 0.8:
            reward = success_rate
        else:
            reward = -1 + success_rate

        """ Decrement step """
        self.steps_left -= 1
        done = self.steps_left <= 0

        return self.state, reward, done, success_rate

    def reset(self):
        """Reset the environment to its initial state."""
        self.state = np.array([50, 100, 10, 0.5, 0.5])
        self.steps_left = 100
        return self.state
    
    def get_sample_action(self):
        return self.action_space.sample()

    def render(self):
        """Render the current state of the environment"""
        print(f"State: {self.state}")

    def close(self):
        """Cleanup the environment"""
        pass
