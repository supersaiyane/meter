# The recorded resource types, in Terraform, reviewable in a diff.
#
# This list is the cost decision. AWS Config charges per configuration item recorded,
# and recording every supported type across an organization is the five figure monthly
# line item ISS-012 warns about. Selective recording was decided on 2026-09-20, and this
# is that decision expressed as something a reviewer can argue with rather than a
# paragraph somebody has to trust.
#
# **Adding a type here costs money.** COST.md carries the working, and the per item price
# means the marginal cost of a type is the number of those resources in the estate times
# the number of times each one changes in a month. A type nobody queries is a type paying
# for itself nothing.
#
# The list is grouped by what it is for, and each group says which feature needs it. A
# type with no feature behind it is a type to remove.

locals {
  # FEAT-031's network graph. The chain the topology map exists to draw, from a VPC down
  # to an instance, plus the four kinds of cross account edge FEAT-030 supplements.
  network_types = [
    "AWS::EC2::VPC",
    "AWS::EC2::Subnet",
    "AWS::EC2::RouteTable",
    "AWS::EC2::SecurityGroup",
    "AWS::EC2::NetworkInterface",
    "AWS::EC2::NatGateway",
    "AWS::EC2::EIP",
    "AWS::EC2::TransitGateway",
    "AWS::EC2::TransitGatewayAttachment",
    "AWS::EC2::VPCPeeringConnection",
    "AWS::EC2::VPCEndpoint",
    "AWS::EC2::VPCEndpointService",
    "AWS::ElasticLoadBalancingV2::LoadBalancer",
    "AWS::ElasticLoadBalancingV2::TargetGroup",
  ]

  # FEAT-027 and FEAT-028's waste findings. These are the resources a rightsizing or
  # orphan finding is about, so a finding with no configuration item behind it would be a
  # recommendation about a resource Meter cannot describe.
  compute_and_storage_types = [
    "AWS::EC2::Instance",
    "AWS::EC2::Volume",
    "AWS::AutoScaling::AutoScalingGroup",
    "AWS::RDS::DBInstance",
    "AWS::ElastiCache::CacheCluster",
    "AWS::Lambda::Function",
  ]

  # FEAT-031's cross account trust edges. Global resources, recorded once in the home
  # region by `include_global_resource_types` below rather than eleven times.
  identity_types = [
    "AWS::IAM::Role",
    "AWS::IAM::Policy",
  ]

  # What the recorders are told to record. One list, assembled from the three above, so
  # the count in COST.md is derived from the same place the recorders read.
  recorded_resource_types = concat(
    local.network_types,
    local.compute_and_storage_types,
    local.identity_types,
  )

  # Deliberately absent, and the reason is the point of the whole file. Each of these is
  # a type AWS Config supports and Meter has no consumer for, so recording it would be
  # paying per configuration item for a row nothing reads:
  #
  #   AWS::EC2::Snapshot        thousands per account, and FEAT-027 finds orphaned
  #                             snapshots from the billing export instead
  #   AWS::S3::Bucket           no topology edge and no waste finding needs it in P4
  #   AWS::CloudFormation::*    describes how the estate was made, not what it is
  #   AWS::SSM::*              inventory of software, which is a different product
  #   AWS::Config::*           the recorders recording themselves
  #
  # A type moved out of this comment and into a list above needs a feature named beside
  # it and a line in COST.md.
  excluded_for_cost = [
    "AWS::EC2::Snapshot",
    "AWS::S3::Bucket",
    "AWS::CloudFormation::Stack",
    "AWS::SSM::ManagedInstanceInventory",
  ]
}
