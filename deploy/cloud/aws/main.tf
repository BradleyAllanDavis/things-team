# tandem hub on AWS — ECR + ECS Fargate. PREP-ONLY: never applied, zero
# resources exist. Written against provider ~> 5.0; validate with
# `tofu init && tofu validate` (needs only the provider download, no creds).
#
# Scope decisions (deliberate, minimal):
#   - default VPC + public subnets + assign_public_ip, ingress locked to
#     var.admin_cidr. ponytail: no ALB/ACM/Route53 until a domain fronts
#     this; add them when the service needs a stable public name.
#   - ephemeral task storage: the SQLite ledger resets on redeploy.
#     ponytail: EFS volume when cloud persistence actually matters.

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "image_tag" {
  description = "tandem-hub image tag (git short-sha, same tag the homelab pipeline builds)"
  type        = string
}

variable "admin_cidr" {
  description = "CIDR allowed to reach the hub API — nothing is public by default"
  type        = string
}

provider "aws" {
  region = var.region
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_ecr_repository" "hub" {
  name                 = "tandem-hub"
  image_tag_mutability = "IMMUTABLE"
}

resource "aws_ecs_cluster" "hub" {
  name = "tandem"
}

# Execution role: what the ECS agent needs (pull from ECR, write logs).
# The task itself gets no role — the hub calls no AWS APIs.
data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "tandem-hub-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_cloudwatch_log_group" "hub" {
  name              = "/ecs/tandem-hub"
  retention_in_days = 14
}

resource "aws_ecs_task_definition" "hub" {
  family                   = "tandem-hub"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution.arn

  container_definitions = jsonencode([{
    name      = "hub"
    image     = "${aws_ecr_repository.hub.repository_url}:${var.image_tag}"
    essential = true
    portMappings = [{ containerPort = 8712, protocol = "tcp" }]
    environment = [
      # Fargate task storage is ephemeral — see the header note.
      { name = "STATE_DIRECTORY", value = "/tmp/tandem" },
      { name = "TANDEM_BOOTSTRAP", value = jsonencode({
        tenant  = "demo"
        members = [
          { handle = "alice", display_name = "Alice", admin = true },
          { handle = "bob", display_name = "Bob" },
        ]
      }) },
    ]
    healthCheck = {
      command  = ["CMD-SHELL", "python -c \"import urllib.request;urllib.request.urlopen('http://127.0.0.1:8712/v1/health')\""]
      interval = 30
      retries  = 3
    }
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.hub.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "hub"
      }
    }
  }])
}

resource "aws_security_group" "hub" {
  name   = "tandem-hub"
  vpc_id = data.aws_vpc.default.id

  ingress {
    from_port   = 8712
    to_port     = 8712
    protocol    = "tcp"
    cidr_blocks = [var.admin_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_ecs_service" "hub" {
  name            = "tandem-hub"
  cluster         = aws_ecs_cluster.hub.id
  task_definition = aws_ecs_task_definition.hub.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.hub.id]
    assign_public_ip = true
  }
}
