terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}
data "aws_availability_zones" "available" { state = "available" }

locals {
  account_id   = data.aws_caller_identity.current.account_id
  az           = data.aws_availability_zones.available.names[0]
  ecr_registry = "${local.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com"
  tags         = { Project = var.app_name, ManagedBy = "terraform" }
}

# ── ECR Repositories ──────────────────────────────────────────────────────────

resource "aws_ecr_repository" "api" {
  name         = "${var.app_name}-api"
  force_delete = true
  image_scanning_configuration { scan_on_push = true }
  tags = local.tags
}

resource "aws_ecr_repository" "mcp" {
  name         = "${var.app_name}-mcp"
  force_delete = true
  image_scanning_configuration { scan_on_push = true }
  tags = local.tags
}

resource "aws_ecr_repository" "web" {
  name         = "${var.app_name}-web"
  force_delete = true
  image_scanning_configuration { scan_on_push = true }
  tags = local.tags
}

resource "aws_ecr_lifecycle_policy" "keep_5" {
  for_each   = { api = aws_ecr_repository.api.name, mcp = aws_ecr_repository.mcp.name, web = aws_ecr_repository.web.name }
  repository = each.value
  policy = jsonencode({
    rules = [{ rulePriority = 1, description = "Keep last 5 images",
      selection = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 5 },
      action = { type = "expire" } }]
  })
}

# ── CloudWatch Log Group ───────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ec2/${var.app_name}"
  retention_in_days = 14
  tags              = local.tags
}
