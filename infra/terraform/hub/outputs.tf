output "alb_dns_name" {
  description = "Where the product is reached."
  value       = aws_lb.hub.dns_name
}

output "database_endpoint" {
  description = "For the migration task. The cluster is private, so this is not reachable from outside the VPC."
  value       = aws_rds_cluster.hub.endpoint
}

output "database_secret_arn" {
  description = "Where the generated master password lives. Never the password itself."
  value       = aws_rds_cluster.hub.master_user_secret[0].secret_arn
}

output "queue_url" {
  description = "Goes into METER_QUEUE_URL."
  value       = aws_sqs_queue.work.url
}

output "task_role_arn" {
  description = "Names in the trust policy of every collector role. The member and management stacks need it."
  value       = aws_iam_role.task.arn
}

output "ecr_repository_urls" {
  description = "Where the pipeline pushes. Four, and no mcp repository, per ADR-0009."
  value       = { for name, repo in aws_ecr_repository.meter : name => repo.repository_url }
}

output "private_subnet_ids" {
  description = "For the migration task, which runs in the same network as the services."
  value       = aws_subnet.private[*].id
}

output "task_security_group_id" {
  description = "For the migration task."
  value       = aws_security_group.tasks.id
}
