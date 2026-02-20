# Temporal Server Hosting Deep Dive for Mycel

Date: 2026-02-20

## Executive Take
For a one-user personal assistant, the main tradeoff is simple:
- Temporal Cloud is lowest-ops but has a hard floor cost of about **$100/month** (Starter), even at tiny workload.
- Self-hosting on your laptop is cheapest and fastest for build phase, but sleep/reboot downtime is real.
- Self-hosting on a small VPS is the best long-term cost/ops balance for this specific project if you can tolerate light ops.

---

## 1) The Options

### A. Temporal Cloud (managed)

#### Current pricing (official)
From Temporal pricing/docs:
- **Starter**: **$100/month**, includes **1 namespace**, **10M actions/month**, **40GB storage**.
- **Growth**: **$400/month**, includes **3 namespaces**, **20M actions/month**, **80GB storage**.
- **Pro**: **$1500/month**, includes **3 namespaces**, **80GB storage**.
- Action overage examples shown by Temporal:
  - Starter: next 100M actions at **$100/100M**, then **$80/100M**, then **$60/100M**.
  - Growth: next 250M at **$80/100M**, then **$70/100M**, then **$55/100M**.
- Storage overage: **$0.00056 per GB-hour**.
- Extra namespaces:
  - Growth: first 5 at **$9/namespace/month**, then **$8**.
  - Pro: first 25 at **$8/namespace/month**, then **$7**.

#### What you get
- Fully managed Temporal service (no DB/cluster ops).
- Cloud SLAs documented at **99.9% regional** and **99.99% multi-region**.
- Plan-based support (Business Hours on Starter; higher plans add 24/7 and tighter response targets).
- Built-in Temporal Cloud observability/ops surface (namespace limits, dashboards, managed control plane).

#### What you lose
- Harder cost floor for hobby scale (base plan dominates actual usage).
- Data residency/locality constrained to Temporal Cloud region offerings (not “your laptop/local disk”).
- Less low-level control than self-hosting.

#### Realistic monthly estimate for Mycel workload
Given this workload (Section 5 assumptions), usage is far below 10M actions/month.
- Actions/month estimate: ~**20k-60k** (far below Starter included 10M).
- Storage first year: ~**1GB**, below included 40GB.
- Namespaces needed: **1**.

**Estimated Temporal Cloud monthly cost: ~`$100`** (Starter base, no overage).

---

### B. Self-hosted on Mac (`temporal server start-dev`)

#### What `start-dev` gives you
`temporal server start-dev` is a local single-process dev server with UI.
- `--db-filename` not set => DB is **in-memory**.
- `--db-filename <path>` => persists to **SQLite file**.
- SQLite pragmas are configurable via CLI flags.

#### Persistence options
- **In-memory**: fastest, zero setup, but all state lost on stop/reboot.
- **SQLite file**: durable local file persistence; workflows/history survive process restart if DB file remains.
- **Postgres**: not via `start-dev`; requires full Temporal Server self-host deployment config.

#### Sleep/reboot behavior
- While Mac sleeps/offline, Temporal Server is down, so workflows do not progress.
- On restart, Temporal rebuilds workflow state from event history (replay) and resumes.
- Durable timers are fault-tolerant and survive service restart; they never fire early but may fire late after downtime.
- If using in-memory backend, restart = total workflow/history loss.

#### Resource usage (measured)
On this MacBook Pro (arm64), measured idle RSS for `temporal server start-dev` process was about:
- ~**115 MB** (fresh run)
- another existing run observed at ~**150 MB**

CPU at idle was near 0% with no workload.

`needs verification`: under sustained load (many activities/signals), memory/CPU for your exact workflows should be profiled locally.

#### Viability
- **Great for MVP/dev and even personal daily use** if occasional downtime during sleep/reboot is acceptable.
- Not ideal for “always-on promise keeping” (timers/reminders while laptop sleeps).

---

### C. Self-hosted on VPS (production self-host)

#### Minimum viable deployment
For this scale, a practical MVP deployment is:
- Single VPS
- Docker Compose
- Temporal + UI + Postgres on persistent volume

Temporal docs/repo show Docker Compose paths for self-hosting and local setups; production-grade Kubernetes is available but optional.

#### Resource requirements (realistic at this scale)
Temporal does not publish a single hard “minimum VM” for production personal-scale workloads.
For one-user Mycel, a practical starting envelope is:
- **2 vCPU, 2-4 GB RAM, 20+ GB SSD**
- Persistent disk for Postgres/Temporal state

Why this envelope:
- `start-dev` alone idles around ~115-150MB RSS on this machine.
- VPS deployment adds Postgres + container overhead + headroom for spikes/backups.

`needs verification`: exact steady-state memory for your workflow mix should be load-tested before committing to the smallest plan.

#### Cheapest viable VPS options (current public pricing)
- **Hetzner Cloud CX22** (2 vCPU, 4GB RAM, 40GB NVMe): **~$4.79/month**.
- **DigitalOcean Basic Droplet**:
  - 2 vCPU/2GB: **$12/month**
  - 2 vCPU/4GB: **$24/month**
- **Fly.io**:
  - Pricing is usage-based/per-second; memory+CPU rates published.
  - Dedicated shared examples on pricing page indicate small always-on machines generally land in roughly low-double-digit monthly range depending size.
  - `needs verification`: exact monthly for chosen machine class should be confirmed in Fly calculator before decision.
- **Railway**:
  - Hobby base: **$5/month** includes usage credits.
  - Resource rates: **$20/vCPU-month**, **$10/GB RAM-month**, **$0.15/GB volume-month**.
  - A 1 vCPU + 2GB always-on service is about $40 usage/month (minus included credits on plan).

#### Ops burden introduced
You own:
- Upgrades (Temporal, Postgres, schema compatibility)
- Backups/restores (at least Postgres daily snapshots)
- Monitoring/alerting (service up, disk full, DB health)
- Incident response (restart policies, broken deploy rollback)

#### Docker Compose vs Kubernetes at this scale
- **Docker Compose** is the right default for this one-user project.
- **Kubernetes** only makes sense if you need HA/multi-zone, team ops, or already run K8s.

---

### D. Hybrid approaches

1. **Local dev + Temporal Cloud “prod namespace”**
- Build cheaply locally, route important workflows to Cloud when needed.
- Lowest risk but has Cloud base cost once enabled.

2. **Worker local, Temporal Server on VPS**
- Keeps durable server/timers always-on while coding on laptop.
- Requires secure network path (TLS/firewall/VPN) between laptop worker and VPS Temporal endpoint.

3. **Worker + server both local during daytime, VPS catches scheduled-only workflows**
- Split critical reminders/promises to VPS namespace; interactive experimentation stays local.
- More complexity, but cost-efficient reliability.

---

## 2) Comparison Matrix

| Option | Cost/month (Temporal infra only) | Ops burden | Reliability | Persistence | Sleep/Reboot resilience | Scalability headroom |
|---|---:|---|---|---|---|---|
| Temporal Cloud Starter | ~$100 | Low | High (managed SLA) | Managed durable | High | High |
| Mac `start-dev` in-memory | $0 | Very low | Low-Med | None across restart | Poor | Low |
| Mac `start-dev` + SQLite | $0 | Low | Med (when laptop awake) | Local durable file | Medium (resume after reboot) | Low-Med |
| VPS self-host (Hetzner-like) | ~$5-$25 | Medium | Med-High (if maintained) | Durable DB volume | High | Medium |
| VPS self-host (DO/Fly/Railway variants) | ~$12-$45+ | Medium | Med-High | Durable DB volume | High | Medium |

---

## 3) Risk Analysis

### Temporal Cloud
- **Break mode**: billing surprise from crossing plan/overage thresholds; regional outage.
- **Impact**: medium (cost), low-medium (availability if single-region).
- **Recovery**: usage alerts, choose multi-region if needed, control retention/history growth.

### Mac local (`start-dev`)
- **Break mode**: laptop sleeps/reboots; in-memory loss if no DB file.
- **Impact**: high for reminders/promises while offline; potentially severe data loss with in-memory.
- **Recovery**: use SQLite file at minimum, auto-start on login, periodic DB backups.

### VPS self-host
- **Break mode**: server crash, disk full, DB corruption, bad upgrade.
- **Impact**: medium-high.
- **Recovery**: daily backups + restore drill, pinned versions, health checks, restart policies.

### Hybrid
- **Break mode**: split-brain architecture mistakes, wrong namespace routing.
- **Impact**: medium.
- **Recovery**: strict routing rules, clear ownership of “critical” workflows, observability by namespace.

---

## 4) The Sleep/Reboot Problem (Deep Dive)

### What happens when Temporal Server stops
- Workflow execution state is persisted as event history in persistence store.
- While server is down, no workflow tasks/activities/timers are processed.

### Replay behavior on restart
- On recovery, workers replay workflow history to rebuild deterministic state and continue execution.
- This is core to Temporal’s durable execution model.

### Timer drift when server is down
- Temporal timers are durable/fault-tolerant and survive restarts.
- Temporal guarantees timers won’t fire **before** scheduled time.
- If server is down at due time, they fire after restart (late, not lost), subject to persistence durability.

### Data-loss risk by backend
- **In-memory**: highest risk; full loss on restart.
- **SQLite file**: low-medium risk; durable on disk but vulnerable to local disk corruption/no backup.
- **Postgres on VPS with backups**: low risk if backups and volumes are configured correctly.
- **Temporal Cloud**: lowest operational risk (managed durability), but still design for rare outage scenarios.

---

## 5) Cost Modeling for Mycel Workload

Assumptions (daily):
- 100 user messages/day
- 100 background activities/day
- 10 schedules/day
- 5 long-running conversation workflows active
- 1GB total storage in year 1

Action model (inference from Temporal action definitions):
- 100 signals/day => ~100 actions
- Workflow task cycles for signaled turns => ~300 actions/day (scheduled/started/completed)
- 100 activities/day => ~300 actions/day (schedule/start/close)
- 10 schedule executions/day => ~30 actions/day (3 per schedule action)
- Misc workflow lifecycle overhead => ~20 actions/day

Estimated total: ~**750 actions/day** ~= **22,500 actions/month**.

Stress factor x3 (to include retries/spikes): ~**67,500 actions/month**.

### Cost by option
- **Temporal Cloud Starter**: still under included 10M actions and 40GB storage => **~$100/month**.
- **Mac local**: **$0 direct infra**.
- **VPS self-host**:
  - Hetzner CX22 example: **~$4.79/month** + optional backup costs.
  - DigitalOcean likely practical floor for 2GB: **~$12/month**.
  - Railway 1 vCPU + 2GB always-on: roughly **~$35-$40/month effective** depending plan credits.
  - Fly.io: usage-based; verify exact machine+volume monthly in calculator (`needs verification`).

---

## 6) Recommendation (Opinionated)

### Phase 1: MVP / building
Use **local `temporal server start-dev` with SQLite persistence**.
- Why: near-zero ops, zero infra cost, fast iteration, preserves history across restarts.
- Required guardrail: never use in-memory for anything you care about.

### Phase 2: Daily driver (real assistant)
Move Temporal Server to a **small VPS (Docker Compose + Postgres)**, keep worker local if desired.
- Why: reminders/promises keep running when laptop sleeps.
- Best cost/ops value: Hetzner-like low-cost VM if acceptable region/compliance.

### Phase 3: Long-term production
Choose based on your tolerance for ops vs spend:
- If you want near-zero ops and can justify cost: **Temporal Cloud Starter**.
- If cost discipline matters more and you can handle light ops: **stay self-hosted VPS** with solid backups/monitoring.

For Mycel (one user, cost-sensitive, limited ops time), the default path is:
1. Local SQLite now.
2. Single VPS next.
3. Temporal Cloud only if/when ops burden becomes the bottleneck.

---

## Sources
- Temporal Pricing: https://temporal.io/pricing
- Temporal pricing action definitions: https://docs.temporal.io/cloud/pricing
- Temporal Cloud limits/SLA: https://docs.temporal.io/cloud/limits
- Temporal Cloud overview: https://docs.temporal.io/cloud
- Temporal CLI `server start-dev` flags (`--db-filename`, SQLite): https://docs.temporal.io/cli/server
- Temporal durable execution overview: https://temporal.io/blog/what-is-durable-execution
- Temporal timer durability (survive restarts): https://docs.temporal.io/develop/java/timers
- Temporal timer semantics (not before, may be later): https://docs.temporal.io/workflow-execution/timers-delays
- Workflow replay concept: https://docs.temporal.io/evaluate/development-production-features/replay
- Temporal self-host deployment docs: https://docs.temporal.io/self-hosted-guide/deployment
- Temporal docker-compose repo: https://github.com/temporalio/docker-compose
- Temporal persistence backends (self-host): https://docs.temporal.io/self-hosted-guide/persistence
- Hetzner Cloud pricing: https://www.hetzner.com/cloud/
- DigitalOcean Droplet pricing: https://www.digitalocean.com/pricing/droplets
- Fly.io pricing: https://fly.io/docs/about/pricing/
- Railway plans/pricing: https://railway.com/pricing and https://railway.com/docs/reference/pricing/plans

