# What Meter is allowed to do in the management account, and nothing more.
#
# The whole grant is List and Describe on Organizations. That is enough to read
# the account list and the organizational unit tree, which is the only thing the
# hub needs from here. `organizations:*` would include CreateAccount,
# LeaveOrganization and AttachPolicy, and a reporting tool holding those will
# not survive a security review, correctly.

data "aws_caller_identity" "current" {}

# Two independent conditions, both required.
#
# The principal is the hub's task role by name, so a different role in the same
# account cannot assume this one. The ExternalId is the second condition, which
# is what makes this safe if the hub account id is ever guessed or if the role
# name is reused. Either alone is weaker than most people assume: a named
# principal without an ExternalId is the classic confused deputy, and an
# ExternalId without a named principal trusts a shared secret on its own.
data "aws_iam_policy_document" "trust" {
  statement {
    sid     = "HubTaskRoleOnly"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${var.hub_account_id}:role/${var.hub_task_role_name}"]
    }

    condition {
      test     = "StringEquals"
      variable = "sts:ExternalId"
      values   = [var.external_id]
    }
  }
}

# Every action here is read only and every one is used. Nothing is included
# speculatively, because an unused permission is a permission nobody will
# remember to remove.
data "aws_iam_policy_document" "org_read" {
  statement {
    sid    = "ReadTheOrganizationTree"
    effect = "Allow"

    actions = [
      # finops_providers/aws/accounts.py, account discovery.
      "organizations:ListAccounts",
      "organizations:ListAccountsForParent",
      "organizations:ListRoots",
      "organizations:ListOrganizationalUnitsForParent",
      "organizations:ListParents",
      "organizations:ListTagsForResource",
      # The organization itself, for the payer account and the feature set.
      "organizations:DescribeOrganization",
      "organizations:DescribeAccount",
      "organizations:DescribeOrganizationalUnit",
    ]

    # Organizations does not support resource level permissions on these
    # actions. Stated here so a reviewer does not read the wildcard as
    # carelessness and try to narrow something AWS will not narrow.
    resources = ["*"]
  }

  statement {
    sid    = "ReadThePayersInvoices"
    effect = "Allow"

    actions = [
      # finops_providers/aws/invoices.py, FEAT-076, TASK-P10-003. AWS issues
      # invoices to the payer, so the management account is the one place they
      # can be read. A list, read only, constraint 6.
      "invoicing:ListInvoiceSummaries",
    ]

    # The call lists the payer's invoices and names no invoice up front, so
    # there is nothing to narrow it to. Unproved against a real account,
    # ISS-002 and ISS-003.
    resources = ["*"]
  }
}

resource "aws_iam_role" "org_reader" {
  name                 = var.role_name
  description          = "Read only access to the organization tree, for Meter. Assumed by the hub task role."
  assume_role_policy   = data.aws_iam_policy_document.trust.json
  max_session_duration = var.max_session_duration_seconds

  # A boundary on a role whose only policy is ten read actions looks like
  # belt and braces, and it is. It is here because this role lives in the
  # management account, where a future edit that widens the inline policy has
  # the largest blast radius in the organization.
  permissions_boundary = aws_iam_policy.boundary.arn
}

resource "aws_iam_policy" "boundary" {
  name = "${var.role_name}Boundary"
  # Still says Organizations although the cap now admits the invoice read too,
  # TASK-P10-003. A policy's description cannot be changed in place: editing it
  # replaces the policy, and this one is the role's boundary, so the replace
  # would fail on delete or leave the role briefly without its cap. The
  # statements in `org_read` are the truth; the description is a label.
  description = "Caps this role at Organizations reads, whatever a later edit attaches to it."
  policy      = data.aws_iam_policy_document.org_read.json
}

resource "aws_iam_role_policy" "org_read" {
  name   = "OrganizationsRead"
  role   = aws_iam_role.org_reader.id
  policy = data.aws_iam_policy_document.org_read.json
}
