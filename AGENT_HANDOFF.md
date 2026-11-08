# Phantom Command

The complete simulated frontend lives in [apps/dashboard/twin](apps/dashboard/twin). Start with its [README](apps/dashboard/twin/README.md), [implementation handoff](apps/dashboard/twin/AGENT_HANDOFF.md), [validation record](apps/dashboard/twin/VALIDATION.md), and [license inventory](apps/dashboard/twin/THIRD_PARTY_LICENSES.md).

```sh
cd apps/dashboard/twin
npm ci
npm run dev
```

Six connected workspaces implement deterministic observation → incident → policy → rover investigation → evidence → resolution. All external actions and model responses are mocked. The library laboratory remains at `/lab.html` and the original twin at `/legacy.html`. Live backend/hardware integration and sponsor compliance remain separate work.
