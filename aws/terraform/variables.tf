variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "ap-northeast-1"
}

variable "anthropic_api_key" {
  description = "Anthropic API key for J.A.R.V.I.S."
  type        = string
  sensitive   = true
}

variable "finmind_token" {
  description = "FinMind API token"
  type        = string
  sensitive   = true
  default     = ""
}

variable "app_name" {
  type    = string
  default = "stock-ledger"
}

variable "key_name" {
  description = "EC2 Key Pair name (create in AWS Console first, then paste name here)"
  type        = string
}

variable "allowed_ssh_cidr" {
  description = "Your IP for SSH access (e.g. 1.2.3.4/32). Use 0.0.0.0/0 for anywhere."
  type        = string
  default     = "0.0.0.0/0"
}
