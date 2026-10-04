import type {
  ApiClusters,
  ApiContainerCost,
  ApiContainerWaste,
  ApiEnvelope,
  ApiMeta,
} from '../types';

/**
 * The P6 surfaces, offline. FEAT-035, FEAT-036 and FEAT-037.
 *
 * The routes are live, so `resolveSurface` never reaches these, as with the quota fixtures.
 * They are the typed example the screens' own tests render, which keeps those tests from
 * inventing a shape the routes cannot produce.
 *
 * **Deliberately unflattering, the way the estate is.** One cluster cannot publish requests
 * and says why, one workload has been killed for running out of memory, one namespace
 * requests five times its use, one is sized correctly so a screen that flags everything
 * fails, and one cluster is Fargate and has no fleet at all. A fixture where every cluster
 * was measurable would leave the half of each screen that matters rendered by nothing.
 */

const AS_OF = '2026-10-04T06:00:00Z';
const COLLECTED_AT = '2026-10-04T06:05:00Z';
const REGION = 'eu-west-1';

function metaWith(visible: number, total: number, unit: string): ApiMeta {
  return {
    as_of: AS_OF,
    collected_at: COLLECTED_AT,
    scope_coverage: { visible, total, is_partial: visible < total, unit },
    degraded: visible < total,
    failures: [],
  };
}

export function containerWasteFixture(): ApiEnvelope<ApiContainerWaste> {
  return {
    data: {
      clusters: [
        {
          cluster_name: 'platform-eks',
          account_id: 'fake-platform-a',
          region_id: REGION,
          platform: 'EKS',
          enhanced_observability: true,
          request_unavailable_reason: null,
          workloads: [
            {
              namespace: 'ledger',
              workload: 'ledger-api',
              workload_kind: 'Deployment',
              launch_type: 'EC2',
              cpu_requested_millicores: '1000',
              cpu_used_p99_millicores: '190',
              memory_requested_mib: '2048',
              memory_used_peak_mib: '400',
              oom_status: 'NOT_KILLED',
              observation_days: 30,
            },
            {
              namespace: 'channels',
              workload: 'web-bff',
              workload_kind: 'Deployment',
              launch_type: 'EC2',
              cpu_requested_millicores: '400',
              cpu_used_p99_millicores: '380',
              memory_requested_mib: '512',
              memory_used_peak_mib: '470',
              oom_status: 'NOT_KILLED',
              observation_days: 30,
            },
            {
              namespace: 'payments',
              workload: 'payments-api',
              workload_kind: 'Deployment',
              launch_type: 'EC2',
              cpu_requested_millicores: '500',
              cpu_used_p99_millicores: '450',
              memory_requested_mib: '1024',
              memory_used_peak_mib: '1100',
              oom_status: 'KILLED',
              observation_days: 30,
            },
          ],
        },
        {
          cluster_name: 'batch-eks',
          account_id: 'fake-platform-b',
          region_id: REGION,
          platform: 'EKS',
          enhanced_observability: false,
          request_unavailable_reason:
            'Enhanced observability is not enabled, so pod requests are not published',
          workloads: [
            {
              namespace: 'risk',
              workload: 'risk-batch',
              workload_kind: 'Job',
              launch_type: 'EC2',
              cpu_requested_millicores: null,
              cpu_used_p99_millicores: '1800',
              memory_requested_mib: null,
              memory_used_peak_mib: '3100',
              oom_status: 'UNOBSERVED',
              observation_days: 30,
            },
          ],
        },
        {
          cluster_name: 'product-ecs',
          account_id: 'fake-product-a',
          region_id: REGION,
          platform: 'ECS',
          enhanced_observability: true,
          request_unavailable_reason: null,
          workloads: [
            {
              namespace: 'default',
              workload: 'statements-renderer',
              workload_kind: 'Service',
              launch_type: 'FARGATE',
              cpu_requested_millicores: '4000',
              cpu_used_p99_millicores: '600',
              memory_requested_mib: '16384',
              memory_used_peak_mib: '1700',
              oom_status: 'NOT_KILLED',
              observation_days: 30,
            },
          ],
        },
      ],
      measured_count: 2,
      found_count: 3,
    },
    meta: metaWith(2, 3, 'clusters'),
  };
}

export function containerCostFixture(): ApiEnvelope<ApiContainerCost> {
  return {
    data: {
      clusters: [
        {
          cluster_name: 'platform-eks',
          total: '1240.00',
          allocated: '1140.80',
          unallocated: '99.20',
          workloads: [
            {
              namespace: 'ledger',
              workload_name: 'ledger-api',
              workload_type: 'Deployment',
              cost: '612.40',
              line_items: 30,
            },
            {
              namespace: 'payments',
              workload_name: 'payments-api',
              workload_type: 'Deployment',
              cost: '391.20',
              line_items: 30,
            },
            {
              namespace: 'channels',
              workload_name: 'web-bff',
              workload_type: 'Deployment',
              cost: '137.20',
              line_items: 30,
            },
          ],
          breakdown_available: true,
          unmeasurable_reason: null,
        },
        {
          cluster_name: 'batch-eks',
          total: '880.00',
          allocated: '809.60',
          unallocated: '70.40',
          workloads: [
            {
              namespace: 'risk',
              workload_name: 'risk-batch',
              workload_type: 'Job',
              cost: '809.60',
              line_items: 30,
            },
          ],
          breakdown_available: true,
          unmeasurable_reason: null,
        },
      ],
      measured_count: 2,
      found_count: 2,
    },
    meta: metaWith(2, 2, 'clusters'),
  };
}

export function clustersFixture(): ApiEnvelope<ApiClusters> {
  return {
    data: {
      clusters: [
        {
          cluster_name: 'platform-eks',
          account_id: 'fake-platform-a',
          region_id: REGION,
          platform: 'EKS',
          enhanced_observability: true,
          node_count: 5,
          spot_ratio: '0.4000',
          packing_efficiency: '0.6300',
          unmeasurable_reason: null,
        },
        {
          cluster_name: 'batch-eks',
          account_id: 'fake-platform-b',
          region_id: REGION,
          platform: 'EKS',
          enhanced_observability: false,
          node_count: 2,
          spot_ratio: '1.0000',
          packing_efficiency: null,
          unmeasurable_reason:
            'Enhanced observability is not enabled, so pod requests are not published',
        },
        {
          cluster_name: 'product-ecs',
          account_id: 'fake-product-a',
          region_id: REGION,
          platform: 'ECS',
          enhanced_observability: true,
          node_count: null,
          spot_ratio: null,
          packing_efficiency: null,
          unmeasurable_reason:
            'Fargate runs tasks without nodes, so there is no fleet to pack and none to price on Spot',
        },
      ],
      measured_count: 1,
      found_count: 2,
    },
    meta: metaWith(1, 2, 'clusters'),
  };
}
