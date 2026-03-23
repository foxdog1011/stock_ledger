output "public_ip" {
  description = "Elastic IP — your app URL: http://<this>"
  value       = aws_eip.app.public_ip
}

output "ssh_command" {
  description = "SSH into your server"
  value       = "ssh -i <your-key.pem> ec2-user@${aws_eip.app.public_ip}"
}

output "ecr_registry" {
  description = "ECR registry base URL (set as ECR_REGISTRY in GitHub Secrets)"
  value       = local.ecr_registry
}

output "ecr_api_url"  { value = aws_ecr_repository.api.repository_url }
output "ecr_mcp_url"  { value = aws_ecr_repository.mcp.repository_url }
output "ecr_web_url"  { value = aws_ecr_repository.web.repository_url }
