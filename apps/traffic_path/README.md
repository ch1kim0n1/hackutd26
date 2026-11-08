# apps/traffic_path — isolated traffic-path validation (#106)

Enforcing reverse proxy in front of #101 vpi services. Every request
becomes a FlowTuple -> #105 DecisionEngine: ALLOW forwards to real
backend, BLOCK returns 403 without backend contact, REDIRECT -> sink.
Decisions logged with trace_id; enforcement is REAL (denied requests
never reach the backend), not simulated.

Lab only: loopback/LAN, no internet exposure, no DDoS/jamming.

## Usage

```python
from defense_gateway import DecisionEngine
from traffic_path.proxy import PathProxy, lab_policy
proxy = PathProxy(engine=DecisionEngine(lab_policy()),
                  backend_url="http://127.0.0.1:8080")
proxy.forward("/health", src_node="ops-01", trace_id="t1")
```

## Tests

6 checks: allow reaches backend, block never touches backend,
decision log, redirect-to-sink, backend-down 502, real metrics data.
