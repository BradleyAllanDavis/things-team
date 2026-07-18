# 🚢 tandem hub on Kubernetes — the Nix-homelab-to-K8s projection

The tandem hub runs in production as a NixOS systemd service
(`deploy/nix/module.nix`). This directory documents its second deployment
target: a container on the homelab k3s cluster, delivered by GitOps. Same
process, same env-driven configuration, two runtimes — the point of the
exercise is that a service designed around explicit configuration and
externalized state ports between the two with zero code changes.

## Translation table

The hub was written against systemd's contract. Every concept maps 1:1:

| Concern | NixOS / systemd (production) | Kubernetes (this deployment) |
|---|---|---|
| Process supervision | systemd unit, `Restart=always` | Deployment (replicas: 1) |
| Configuration | `Environment=` from the nix module | `env:` in the pod spec |
| Durable state (`STATE_DIRECTORY`) | `StateDirectory=` under `/var/lib` | PersistentVolumeClaim mounted at `/data` |
| Secrets | `LoadCredential=` (root-only files) | k8s Secret → `CREDENTIALS_DIRECTORY` volume (unused here — the demo instance holds no secrets) |
| Health | process exit → restart | `livenessProbe`/`readinessProbe` on `GET /v1/health` |
| Least privilege | `DynamicUser` | `runAsNonRoot` + fixed uid 10001 + `fsGroup` |
| Rollout | `nixos-rebuild switch` | `git push` → CI → Argo CD sync |
| Rollback | previous NixOS generation | `git revert` of the image-tag bump |

SQLite forces one honest constraint either way: exactly one writer.
`replicas: 1` + `strategy: Recreate` is that constraint written down, not a
limitation discovered later.

## Pipeline (one command: `git push`)

```
edit hub/ → git push (Forgejo: things-team, branch main)
  → Forgejo Actions (.forgejo/workflows/build-deploy.yml, self-hosted runner)
      → podman build+push  (tag = git short-sha)
          → Forgejo container registry (forgejo:443/bradley/tandem-hub)
      → bump image tag in k3s-gitops workloads/tandem-hub.yaml → git push
          → Argo CD reconciles → new pod on the k3s cluster
              → http://dozer:30305/v1/health
```

No kubectl in the loop. The k3s-gitops repo is the only write path to the
cluster; Argo CD reconciles whatever is on its main branch. A deploy is a
commit; a rollback is a revert; the audit log is `git log`.

## The manifests

Live in the GitOps repo, not here — Argo CD applies exactly one source of
truth: `k3s-gitops/workloads/tandem-hub.yaml` (Namespace, PVC, Deployment,
Service). Heavily commented; written as the interview answer to "deploy a
stateful single-writer service on Kubernetes."

## What the deployed instance is

A demo tenant (`demo`, members `alice`/`bob`, zero devices) bootstrapped from
`TANDEM_BOOTSTRAP` — it exercises the real startup path but holds no
credentials and can authenticate no one. The production family hub stays on
NixOS; this instance exists to prove the projection, not to replace it.

## Cloud

`deploy/cloud/` holds the AWS (ECR + ECS Fargate) and GCP (Artifact
Registry + Cloud Run) versions of the same projection — Terraform,
prep-only, nothing provisioned. See its README.
