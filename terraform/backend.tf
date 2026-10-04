terraform {
  required_version = ">= 1.6.0"

  cloud {
    organization = "gkllc"

    workspaces {
      name    = "poland-words-assist"
      project = "fabe8953-8918-4dc5-8d5f-7b72742c42d9"
    }
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