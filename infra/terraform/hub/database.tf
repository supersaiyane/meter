# Aurora Serverless v2. Encrypted, private, and backed up no longer than the
# retention policy allows.
#
# Serverless v2 rather than provisioned because Meter's load is a burst once an
# hour and nothing in between. A provisioned instance sized for the burst is
# idle for fifty five minutes of every hour, and one sized for the average
# cannot absorb the burst.

resource "aws_db_subnet_group" "hub" {
  name        = local.name
  description = "Private subnets only. The cluster has no route to the internet."
  subnet_ids  = aws_subnet.private[*].id
}

resource "aws_security_group" "database" {
  name        = "${local.name}-database"
  description = "Aurora. Reachable from the task security group only."
  vpc_id      = aws_vpc.hub.id

  tags = { Name = "${local.name}-database" }
}

resource "aws_vpc_security_group_ingress_rule" "database_from_tasks" {
  security_group_id            = aws_security_group.database.id
  description                  = "PostgreSQL from the ECS tasks. Not from the VPC, from the tasks."
  referenced_security_group_id = aws_security_group.tasks.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}

resource "aws_kms_key" "database" {
  description             = "Aurora storage and backups for Meter ${var.env}."
  enable_key_rotation     = true
  deletion_window_in_days = 30
}

resource "aws_kms_alias" "database" {
  name          = "alias/${local.name}-database"
  target_key_id = aws_kms_key.database.key_id
}

# The master password is generated and stored by AWS rather than passed in as a
# variable. A password in a variable is a password in state, and Terraform state
# is read by everything that runs a plan.
resource "aws_rds_cluster" "hub" {
  cluster_identifier = local.name
  engine             = "aurora-postgresql"
  engine_mode        = "provisioned"
  engine_version     = "16.6"
  database_name      = "meter"
  master_username    = "meter"

  manage_master_user_password   = true
  master_user_secret_kms_key_id = aws_kms_key.database.arn

  db_subnet_group_name   = aws_db_subnet_group.hub.name
  vpc_security_group_ids = [aws_security_group.database.id]

  storage_encrypted = true
  kms_key_id        = aws_kms_key.database.arn

  backup_retention_period      = var.backup_retention_days
  preferred_backup_window      = "02:00-03:00"
  preferred_maintenance_window = "sun:03:30-sun:04:30"
  copy_tags_to_snapshot        = true

  # A snapshot on destroy in production, none in development. The final
  # snapshot is what makes an accidental destroy recoverable, and it is exactly
  # the moment nobody thinks to take one by hand.
  skip_final_snapshot       = var.env != "prod"
  final_snapshot_identifier = var.env == "prod" ? "${local.name}-final" : null
  deletion_protection       = var.env == "prod"

  serverlessv2_scaling_configuration {
    min_capacity = var.database_min_capacity
    max_capacity = var.database_max_capacity
  }

  # Constraint 11: an invariant enforced only by application code is an
  # invariant that will eventually be violated. The same reasoning applies to
  # the audit trail, so the database's own log of connections and DDL goes to
  # CloudWatch rather than staying inside the instance.
  enabled_cloudwatch_logs_exports = ["postgresql"]

  lifecycle {
    # The password is rotated by Secrets Manager, not by Terraform. Without
    # this, every plan after a rotation proposes to undo it.
    ignore_changes = [master_user_secret_kms_key_id]
  }
}

resource "aws_rds_cluster_instance" "writer" {
  identifier          = "${local.name}-writer"
  cluster_identifier  = aws_rds_cluster.hub.id
  instance_class      = "db.serverless"
  engine              = aws_rds_cluster.hub.engine
  engine_version      = aws_rds_cluster.hub.engine_version
  publicly_accessible = false

  # Performance Insights, at the free seven day tier. A slow query at 300
  # accounts is found here or by guessing.
  performance_insights_enabled          = true
  performance_insights_retention_period = 7
  # The same key the cluster storage uses. Performance Insights holds query
  # text, which for this product means the shape of a customer's cost queries.
  performance_insights_kms_key_id = aws_kms_key.database.arn
}
