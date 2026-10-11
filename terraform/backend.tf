terraform {
  required_version = ">= 1.6.0"

  backend "gcs" {
    bucket = "polan-words-assist-static"
    prefix = "tf-state-prd"
  }

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.30"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}