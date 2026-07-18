# tandem hub on GCP — Artifact Registry + Cloud Run v2. PREP-ONLY: never
# applied, zero resources exist.
#
# Cloud Run is the natural fit for an env-driven single-container HTTP
# service: registry + one service resource and done. Ingress is internal —
# nothing public-facing. Cloud Run instances are stateless; the SQLite
# ledger resets between instances (see ../README.md for the upgrade path).

terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

variable "project" {
  type = string
}

variable "region" {
  type    = string
  default = "us-east1"
}

variable "image_tag" {
  description = "tandem-hub image tag (git short-sha, same tag the homelab pipeline builds)"
  type        = string
}

provider "google" {
  project = var.project
  region  = var.region
}

resource "google_artifact_registry_repository" "hub" {
  repository_id = "tandem"
  format        = "DOCKER"
  location      = var.region
}

resource "google_cloud_run_v2_service" "hub" {
  name     = "tandem-hub"
  location = var.region
  # Internal only — no public invoker is granted anywhere in this config.
  ingress = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    scaling {
      # SQLite = exactly one writer; same constraint the k8s manifest
      # encodes with replicas: 1 + Recreate.
      max_instance_count = 1
    }
    containers {
      image = "${var.region}-docker.pkg.dev/${var.project}/${google_artifact_registry_repository.hub.repository_id}/tandem-hub:${var.image_tag}"
      ports {
        container_port = 8712
      }
      env {
        name  = "STATE_DIRECTORY"
        value = "/tmp/tandem" # Cloud Run disk is in-memory/ephemeral
      }
      env {
        name = "TANDEM_BOOTSTRAP"
        value = jsonencode({
          tenant = "demo"
          members = [
            { handle = "alice", display_name = "Alice", admin = true },
            { handle = "bob", display_name = "Bob" },
          ]
        })
      }
      startup_probe {
        http_get {
          path = "/v1/health"
          port = 8712
        }
      }
      liveness_probe {
        http_get {
          path = "/v1/health"
          port = 8712
        }
      }
    }
  }
}
