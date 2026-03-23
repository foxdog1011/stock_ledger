# ── Amazon Linux 2023 AMI ─────────────────────────────────────────────────────

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]
  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# ── EC2 Instance (t2.micro — free tier eligible) ──────────────────────────────

resource "aws_instance" "app" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = "t2.micro"
  key_name               = var.key_name
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.ec2.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2.name

  root_block_device {
    volume_type = "gp2"
    volume_size = 30  # free tier: up to 30GB
  }

  user_data = base64encode(templatefile("${path.module}/user_data.sh", {
    ecr_registry        = local.ecr_registry
    aws_region          = var.aws_region
    app_name            = var.app_name
    anthropic_api_key   = var.anthropic_api_key
    finmind_token       = var.finmind_token
  }))

  tags = merge(local.tags, { Name = "${var.app_name}-server" })
}

# ── Elastic IP (stays fixed across reboots) ───────────────────────────────────

resource "aws_eip" "app" {
  instance = aws_instance.app.id
  domain   = "vpc"
  tags     = merge(local.tags, { Name = "${var.app_name}-eip" })
}
