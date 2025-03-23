from gymnasium import Env
from gymnasium.spaces import Box, Discrete
from kubernetes import config, dynamic
from kubernetes.client import api_client
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from datetime import datetime
import numpy as np
import requests

class CircuitBreaker(Env):
    def __init__(self):
        """ Action space: maxConnections, maxRequestsPerConnection, http1MaxPendingRequests """
        self.action_list = [(10, 1, 3), (10, 1, 1), (10, 1, 5)]
        
        """ Action space sebagai Discrete (jumlah aksi = len(self.action_list)) """
        self.action_space = Discrete(len(self.action_list))
        
        """ Observation space: memory usage, CPU usage, request rate (rate of istio_requests_total) """
        self.observation_space = Box(
            low=np.array([0, 0, 0]),  
            high=np.array([1, 1, 1e6]) 
        )

        """
            Initial state: 
            - Memory Usage
            - CPU Usage
            - Request Rate
        """
        memory_usage, cpu_usage = self.get_metrics()
        req_rate = self.query_prometheus(self.prometheus_istio_url, self.request_rate_query)
        self.state = np.array([memory_usage, cpu_usage, req_rate])

        # Environment parameters
        self.steps_left = 100  # Number of steps before the episode ends

        """ Prometheus (kube-prometheus-stack) """
        self.prometheus_monitoring_url = "http://localhost:30090/api/v1/query"
        self.memory_usage_query = 'avg(container_memory_working_set_bytes{pod=~"productpage-.*"}) by (namespace, pod) / on (namespace, pod) group_left kube_pod_container_resource_limits{resource="memory", pod=~"productpage-.*"}'
        self.cpu_usage_query = 'avg(rate(container_cpu_usage_seconds_total{pod=~"productpage-.*"}[15m])) by (namespace, pod) / on (namespace, pod) group_left kube_pod_container_resource_limits{resource="cpu", pod=~"productpage-.*"}'

        """ Prometheus (Istio) """
        self.prometheus_istio_url = "http://localhost:30091/api/v1/query_range"
        self.success_rate_query = 'sum(istio_requests_total{app="wikibench",destination_app="productpage",response_code="200"})/sum(istio_requests_total{app="wikibench",destination_app="productpage"})'
        self.request_rate_query = 'sum(rate(istio_requests_total{app="wikibench", destination_app="productpage"}[5m]))'

    def query_prometheus(self, url, query):
        """Query into Prometheus API."""
        
        response = requests.get(url, params={"query": query})
        if response.status_code == 200:
            result = response.json()
            results = result.get("data", {}).get("result", [])
            for item in results:
                value = item["value"][1] 
                try:
                    return float(value)
                except:
                    return 0
            return 0
        else:
            print("Error querying Prometheus:", response.text)
            return 0
        
    def query_success_rate_prometheus(self):
        """Query success rate of requests into Prometheus Istio API."""
        end_time = int(datetime.now().timestamp() * 1e6) 
        start_time = int(end_time - (15 * 1e6))

        params = {
            "query": self.query_success_rate_prometheus,
            "start": start_time,
            "end": end_time,
            "step": "60m", # use big step to get only one value
        }
        
        response = requests.get(self.prometheus_istio_url, params=params)
        if response.status_code == 200:
            result = response.json()
            results = result.get("data", {}).get("result", [])
            for item in results:
                value = item["values"][0][-1][1]
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
    
    def set_circuit_breaker_params(self, max_connections, max_request_per_connection, http1_max_pending_requests):
        client = dynamic.DynamicClient(
            api_client.ApiClient(configuration=config.load_kube_config())
        )

        try:
            destination_rule_api = client.resources.get(
                api_version="networking.istio.io/v1alpha3", kind="DestinationRule"
            )
        except ResourceNotFoundError:
            print("DestinationRule resource not found in the cluster.")
            return

        dr_name = "productpage"
        namespace = "default"

        try:
            destination_rule = destination_rule_api.get(name=dr_name, namespace=namespace)
        except ResourceNotFoundError:
            print(f"DestinationRule {dr_name} not found in namespace {namespace}.")
            return
        
        destination_rule_dict = destination_rule.to_dict()

        """ Update circuit breaker params """
        destination_rule_dict["spec"]["trafficPolicy"]["connectionPool"]["tcp"]["maxConnections"] = max_connections
        destination_rule_dict["spec"]["trafficPolicy"]["connectionPool"]["http"]["maxRequestsPerConnection"] = max_request_per_connection
        destination_rule_dict["spec"]["trafficPolicy"]["connectionPool"]["http"]["http1MaxPendingRequests"] = http1_max_pending_requests

        updated_rule = destination_rule_api.patch(
            name=dr_name, namespace=namespace, body=destination_rule_dict, content_type="application/merge-patch+json"
        )
        print(f"Updated DestinationRule: {updated_rule.to_dict()}")

    def step(self, action):
        """Apply an action and return the new state, reward, done, and info."""
        max_connections, max_requests_per_connection, http1_max_pending_requests = self.action_list[action]
        self.set_circuit_breaker_params(max_connections, max_requests_per_connection, http1_max_pending_requests)

        memory_usage, cpu_usage = self.get_memory_and_cpu_usage()
        req_rate = self.query_prometheus(self.prometheus_istio_url, self.request_rate_query)

        self.state = np.array([memory_usage, cpu_usage, req_rate])

        """ Get success rate """
        success_rate = self.query_success_rate_prometheus()
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
        memory_usage, cpu_usage = self.get_metrics()
        self.state = np.array([memory_usage, cpu_usage])
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
