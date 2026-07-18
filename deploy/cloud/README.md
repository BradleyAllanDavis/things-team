# ☁️ Cloud projections — PREP-ONLY

Terraform for running the tandem-hub container on the two majors. **Nothing
here has been applied. Zero cloud resources exist. Zero dollars spent.**
These are written, reviewed manifests awaiting an account + a reason.

| Cloud | Path | Runtime | Registry |
|---|---|---|---|
| AWS | `aws/` | ECS on Fargate (public IP, no ALB yet) | ECR |
| GCP | `gcp/` | Cloud Run v2 (internal ingress) | Artifact Registry |

Both take the same image the homelab pipeline already builds; the only
cloud-specific step is retagging/pushing it to the cloud registry.

State caveat, stated up front: both runtimes give the container ephemeral
disk, so the SQLite ledger resets on every restart. Fine for a demo
instance; the persistence upgrade is EFS (AWS) / a managed DB or GCS-backed
litestream (GCP) — deliberately not built until an actual cloud deployment
is scheduled.

Apply path (when the time comes): `tofu init && tofu plan` with real
credentials, review, `tofu apply`. Until then this directory is
documentation that happens to be executable.
