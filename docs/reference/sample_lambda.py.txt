"""
Grafana Query Cost Audit - Lambda Function
===========================================

Scans every Amazon Managed Grafana (AMG) workspace across one or more AWS
accounts / regions, inspects each dashboard and its panels (and, best-effort,
Grafana-managed alert rules), and reports for every query:

  * The query the panel/alert runs (Logs Insights / CloudWatch metric search /
    Metric Insights SQL / PromQL).
  * The dashboard auto-refresh interval (e.g. 10s, 1m).
  * The dashboard time frame / window (e.g. now-6h, now-7d).
  * The target it reads (log group(s) for Logs Insights, namespace for metrics).
  * A MODELLED monthly cost and per-run scan size.
  * A WHY explanation of what drives the cost/risk.

Cost model (all rates + assumptions are configurable via env vars):
  * Logs Insights  -> billed per GB SCANNED. scan/run is modelled from the log
    group ingestion rate x the dashboard window; monthly cost =
    scan_per_run_GB x runs/day x 30 x $/GB.
  * Metric search / Metric Insights -> billed per metric requested per call;
    monthly cost = metrics/call x runs/day x 30 x ($/1000 metrics)/1000.
  * Panel queries only run while a dashboard is open, so runs/day uses an
    assumed VIEWING_HOURS_PER_DAY. Alert-rule queries run 24x7 on their own
    interval regardless of viewers.

Numbers in the report are MODELLED (hatched bars) unless a measured source is
wired in. They rank queries reliably but do not reconcile to your bill.

Runtime      : Python 3.12  (stdlib + boto3 only, no external packages)
Entry point  : lambda_handler
"""

import boto3
import json
import os
import logging
import hashlib
import urllib.request
import urllib.error
import re
from collections import defaultdict
from datetime import datetime, timezone, timedelta

try:
    from botocore.config import Config as _BotoConfig
except Exception:  # pragma: no cover
    _BotoConfig = None

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Fail fast instead of hanging when the network path is broken (e.g. VPC with no
# route to a service endpoint). Without this, a private-subnet Lambda with no
# NAT / VPC endpoint will silently block until the whole function times out.
BOTO_CFG = _BotoConfig(
    connect_timeout=int(os.environ.get('AWS_CONNECT_TIMEOUT', '10')),
    read_timeout=int(os.environ.get('AWS_READ_TIMEOUT', '30')),
    retries={'max_attempts': 2, 'mode': 'standard'},
) if _BotoConfig else None


def aws_client(session, service, region=None):
    """boto3 client with sane timeouts so broken network paths fail fast."""
    kwargs = {}
    if region:
        kwargs['region_name'] = region
    if BOTO_CFG is not None:
        kwargs['config'] = BOTO_CFG
    return session.client(service, **kwargs)


# ============================================================
# Configuration (read from environment variables)
# ============================================================
def load_config():
    """Build runtime configuration from environment variables."""
    accounts_raw = os.environ.get('GRAFANA_ACCOUNTS', '').strip()
    default_regions = [
        r.strip() for r in os.environ.get('REGIONS', '').split(',') if r.strip()
    ]
    if not default_regions:
        default_regions = [os.environ.get('AWS_REGION', 'eu-west-1')]

    if accounts_raw:
        try:
            parsed = json.loads(accounts_raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "GRAFANA_ACCOUNTS is set but is not valid JSON. It must be a JSON "
                "array of objects, e.g. "
                '[{"account_id":"111111111111","role_arn":"arn:aws:iam::111111111111:role/grafana-audit","regions":["eu-west-1"]}]. '
                "For single-account use, leave GRAFANA_ACCOUNTS unset. "
                f"Parse error: {exc}"
            )
        # Accept a single object for convenience; wrap it in a list.
        if isinstance(parsed, dict):
            parsed = [parsed]
        if not isinstance(parsed, list) or not all(isinstance(a, dict) for a in parsed):
            raise ValueError(
                "GRAFANA_ACCOUNTS must be a JSON ARRAY of account objects (or a single "
                "object). Got a %s. Example: "
                '[{"account_id":"111111111111","regions":["eu-west-1"]}]. '
                "For single-account use, leave GRAFANA_ACCOUNTS unset."
                % type(parsed).__name__
            )
        accounts = parsed
        for acct in accounts:
            if not acct.get('regions'):
                acct['regions'] = default_regions
    else:
        accounts = [{'account_id': None, 'role_arn': None, 'regions': default_regions}]

    def _f(name, default):
        return float(os.environ.get(name, default))

    def _i(name, default):
        return int(os.environ.get(name, default))

    return {
        'accounts': accounts,
        's3_bucket': os.environ.get('S3_BUCKET'),
        's3_prefix': os.environ.get('S3_PREFIX', 'grafana-query-audit/'),
        'sns_topic_arn': os.environ.get('SNS_TOPIC_ARN'),
        # optional server-side encryption to satisfy a bucket policy that denies
        # unencrypted PutObject. S3_SSE = 'AES256' or 'aws:kms'; S3_SSE_KMS_KEY_ID
        # required when using aws:kms.
        's3_sse': os.environ.get('S3_SSE'),
        's3_sse_kms_key_id': os.environ.get('S3_SSE_KMS_KEY_ID'),
        'http_timeout': _i('HTTP_TIMEOUT_SECONDS', 20),
        # Preferred auth: a pre-provisioned Grafana token in Secrets Manager
        # (same pattern as the grafana-dashboard-manager Lambda). If set, this is
        # used instead of minting temporary workspace service accounts, which
        # avoids workspace-RBAC 403s. Value is the secret NAME or ARN.
        'grafana_token_secret': os.environ.get('GRAFANA_API_KEY_SECRET_NAME'),
        # Optional: provide the Grafana token directly via env var (e.g. for
        # testing without Secrets Manager access). Prefer the secret above.
        # Set GRAFANA_API_TOKEN in the Lambda console; do NOT hardcode in source.
        'grafana_token_direct': os.environ.get('GRAFANA_API_TOKEN'),
        # Optional: target a Grafana workspace endpoint DIRECTLY instead of
        # discovering via grafana:ListWorkspaces (which may return nothing or be
        # denied). Same idea as the dashboard-manager's GRAFANA_WORKSPACE_URL.
        # Accepts a full URL or a bare host; comma-separate for multiple.
        'grafana_workspace_url': os.environ.get('GRAFANA_WORKSPACE_URL', '').strip(),

        # --- cost model assumptions (all tunable) ---
        'viewing_hours_per_day': _f('VIEWING_HOURS_PER_DAY', 2.0),
        'manual_loads_per_day': _f('MANUAL_LOADS_PER_DAY', 4.0),
        'metrics_per_call': _f('METRICS_PER_CALL', 1.0),
        'default_ingest_gb_per_day': _f('DEFAULT_INGEST_GB_PER_DAY', 50.0),
        'measure_ingestion': os.environ.get('MEASURE_INGESTION', 'true').lower() == 'true',

        # --- measured execution data (CloudTrail) ---
        'measure_executions': os.environ.get('MEASURE_EXECUTIONS', 'true').lower() == 'true',
        'measure_lookback_days': _i('MEASURE_LOOKBACK_DAYS', 7),

        # --- Logs Insights query history (REAL bytes scanned) ---
        'measure_logs_history': os.environ.get('MEASURE_LOGS_HISTORY', 'true').lower() == 'true',
        'logs_history_max_queries': _i('LOGS_HISTORY_MAX_QUERIES', 500),

        # --- actual billing (Cost Explorer) + CloudWatch capacity ---
        'billing_enabled': os.environ.get('BILLING_ENABLED', 'true').lower() == 'true',
        'capacity_enabled': os.environ.get('CAPACITY_ENABLED', 'true').lower() == 'true',

        # --- history + trend detection ---
        'history_enabled': os.environ.get('HISTORY_ENABLED', 'true').lower() == 'true',
        'trend_cadence_days': _i('TREND_CADENCE_DAYS', 3),   # highlight every Nth day
        'trend_window_days': _i('TREND_WINDOW_DAYS', 7),      # look back up to N days
        'trend_min_days': _i('TREND_MIN_DAYS', 3),            # severe on >= N days = trending
        'force_trend': os.environ.get('FORCE_TREND', 'false').lower() == 'true',
        # which severities to track for trending (default CRITICAL + MEDIUM + HIGH)
        'trend_severities': [
            s.strip().upper() for s in
            os.environ.get('TREND_SEVERITIES', 'CRITICAL,HIGH,MEDIUM').split(',')
            if s.strip()
        ],

        # --- CloudWatch service-quota defaults (for quota-impact estimate) ---
        'quota_logs_concurrent': _i('QUOTA_LOGS_CONCURRENT_QUERIES', 30),
        'quota_getmetricdata_tps': _i('QUOTA_GETMETRICDATA_TPS', 50),
        'assumed_query_seconds': _f('ASSUMED_QUERY_SECONDS', 5.0),

        # --- price rates (us-east-1 list price defaults; override per region) ---
        'logs_scan_price_per_gb': _f('LOGS_SCAN_PRICE_PER_GB', 0.005),
        'metrics_price_per_1000': _f('METRICS_PRICE_PER_1000', 0.01),
        'price_region_note': os.environ.get('PRICE_REGION_NOTE', 'us-east-1 list price'),

        # --- risk thresholds (drive the WHY text + bar colour) ---
        'refresh_warn_seconds': _i('REFRESH_WARN_SECONDS', 60),
        'refresh_crit_seconds': _i('REFRESH_CRIT_SECONDS', 30),
        'timerange_warn_hours': _f('TIMERANGE_WARN_HOURS', 24),
        'timerange_crit_hours': _f('TIMERANGE_CRIT_HOURS', 168),
    }


# ============================================================
# AWS sessions / role assumption
# ============================================================
def build_session(role_arn):
    if not role_arn:
        return boto3.Session()
    sts = aws_client(boto3.Session(), 'sts')
    resp = sts.assume_role(
        RoleArn=role_arn,
        RoleSessionName='grafana-query-audit',
        DurationSeconds=3600,
    )
    creds = resp['Credentials']
    return boto3.Session(
        aws_access_key_id=creds['AccessKeyId'],
        aws_secret_access_key=creds['SecretAccessKey'],
        aws_session_token=creds['SessionToken'],
    )


def get_account_id(session):
    try:
        logger.info("Resolving account id via STS ...")
        acct = aws_client(session, 'sts').get_caller_identity()['Account']
        logger.info("Account id: %s", acct)
        return acct
    except Exception as exc:
        logger.warning("Could not resolve account id via STS: %s", exc)
        return 'unknown'


# ============================================================
# AMG workspace discovery + auth
# ============================================================
def _endpoint_from_url(url):
    """Normalise a full URL or bare host into a Grafana API host (no scheme)."""
    u = url.strip()
    if not u:
        return None
    u = u.replace('https://', '').replace('http://', '')
    return u.rstrip('/')


def discover_workspaces(session, region, cfg=None):
    # 1) If a workspace URL is configured, use it DIRECTLY (no ListWorkspaces).
    #    This is the reliable path in restricted accounts.
    direct = (cfg or {}).get('grafana_workspace_url') if cfg else None
    if direct:
        wss = []
        for i, raw in enumerate(direct.split(',')):
            ep = _endpoint_from_url(raw)
            if ep:
                wss.append({'id': f'direct-{i}', 'name': ep.split('.')[0],
                            'endpoint': ep, 'status': 'ACTIVE'})
        logger.info("Using %d directly-configured Grafana workspace(s).", len(wss))
        return wss

    # 2) Otherwise discover via the AMG API.
    logger.info("Discovering Grafana workspaces in %s ...", region)
    client = aws_client(session, 'grafana', region)
    workspaces = []
    try:
        paginator = client.get_paginator('list_workspaces')
        for page in paginator.paginate():
            workspaces.extend(page.get('workspaces', []))
    except Exception:
        try:
            resp = client.list_workspaces()
            workspaces.extend(resp.get('workspaces', []))
        except Exception as exc:
            logger.warning("Could not list workspaces in %s: %s", region, exc)
    logger.info("Found %d workspace(s) in %s.", len(workspaces), region)
    return workspaces


# Fixed names for the throwaway auth identities this Lambda creates. The cleanup
# guardrail will ONLY delete resources whose name matches these exactly, so it
# can never remove a pre-existing service account / API key.
TEMP_SA_NAME = 'query-audit-temp'
TEMP_APIKEY_NAME = 'query-audit-temp'


def get_grafana_secret_token(session, region, secret_id):
    """Fetch a pre-provisioned Grafana token from Secrets Manager."""
    sm = aws_client(session, 'secretsmanager', region)
    resp = sm.get_secret_value(SecretId=secret_id)
    val = resp.get('SecretString') or ''
    # Support either a raw token or a JSON blob like {"token": "..."}.
    val = val.strip()
    if val.startswith('{'):
        try:
            obj = json.loads(val)
            for k in ('token', 'apiKey', 'api_key', 'key', 'value'):
                if obj.get(k):
                    return obj[k]
        except Exception:
            pass
    return val


def get_grafana_token(session, region, workspace_id, cfg):
    """
    Return (token, cleanup) for the Grafana HTTP API.

    Preferred: a pre-provisioned token from Secrets Manager (GRAFANA_API_KEY_SECRET_NAME),
    which matches the working grafana-dashboard-manager auth and avoids the
    workspace-RBAC 403 that temporary service accounts hit. Cleanup is a no-op
    for the secret path (we don't own the token's lifecycle).

    Fallback: mint a short-lived workspace service account / API key.
    """
    # 1) Direct token from env var (testing convenience; not committed to source).
    direct = cfg.get('grafana_token_direct')
    if direct:
        logger.info("Using Grafana token from GRAFANA_API_TOKEN env var for %s.", workspace_id)
        return direct, (lambda: None)

    # 2) Token from Secrets Manager.
    secret_id = cfg.get('grafana_token_secret')
    if secret_id:
        try:
            token = get_grafana_secret_token(session, region, secret_id)
            if token:
                logger.info("Using Grafana token from Secrets Manager for %s.", workspace_id)
                return token, (lambda: None)
            logger.warning("Grafana secret %s was empty; falling back to service account.",
                           secret_id)
        except Exception as exc:
            logger.warning("Could not read Grafana token secret %s (%s); "
                           "falling back to service account.", secret_id, exc)

    return create_workspace_token(session, region, workspace_id)


def create_workspace_token(session, region, workspace_id):
    """
    Create a short-lived Grafana admin token. Returns (token, cleanup).

    GUARDRAIL: cleanup deletes ONLY the exact resource this function just
    created (by id) and only after re-confirming its name equals our temp name.
    It never touches pre-existing service accounts or keys.
    """
    client = session.client('grafana', region_name=region)
    try:
        sa = client.create_workspace_service_account(
            workspaceId=workspace_id, grafanaRole='ADMIN', name=TEMP_SA_NAME,
        )
        sa_id = sa['id']
        created_name = sa.get('name', TEMP_SA_NAME)
        token = client.create_workspace_service_account_token(
            workspaceId=workspace_id, serviceAccountId=sa_id,
            name='query-audit-token', secondsToLive=600,
        )
        key = token['serviceAccountToken']['key']

        def cleanup():
            # Guardrail: only delete the identity we just created, and only if
            # its name is still our temp name. Refuse anything else.
            if created_name != TEMP_SA_NAME:
                logger.warning(
                    "Refusing to delete service account %s in %s: name '%s' is not "
                    "the temp name '%s'.", sa_id, workspace_id, created_name, TEMP_SA_NAME)
                return
            try:
                client.delete_workspace_service_account(
                    workspaceId=workspace_id, serviceAccountId=sa_id)
                logger.info("Deleted temp service account %s in %s.", sa_id, workspace_id)
            except Exception as exc:
                logger.warning("Failed to delete temp service account %s: %s", sa_id, exc)

        return key, cleanup
    except Exception as exc:
        logger.info("Service account flow unavailable for %s (%s); trying API key.",
                    workspace_id, exc)

    try:
        resp = client.create_workspace_api_key(
            keyName=TEMP_APIKEY_NAME, keyRole='ADMIN',
            secondsToLive=600, workspaceId=workspace_id,
        )
        key = resp['key']

        def cleanup():
            # Guardrail: delete only our fixed-named temp key.
            try:
                client.delete_workspace_api_key(
                    keyName=TEMP_APIKEY_NAME, workspaceId=workspace_id)
                logger.info("Deleted temp API key in %s.", workspace_id)
            except Exception as exc:
                logger.warning("Failed to delete temp API key: %s", exc)

        return key, cleanup
    except Exception as exc:
        logger.warning("Could not obtain a Grafana token for %s: %s", workspace_id, exc)
        return None, (lambda: None)


# ============================================================
# Grafana HTTP API
# ============================================================
def grafana_api_get(endpoint, token, path, timeout):
    url = f"https://{endpoint}{path}"
    req = urllib.request.Request(url, headers={
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json',
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        # Surface the Grafana response body — it explains WHY (e.g. 403 reason).
        body = ''
        try:
            body = exc.read().decode('utf-8', 'replace')[:300]
        except Exception:
            pass
        logger.warning("Grafana API %s -> HTTP %s %s | body: %s",
                       path, exc.code, exc.reason, body)
        raise


def list_dashboards(endpoint, token, timeout):
    try:
        return grafana_api_get(endpoint, token, '/api/search?type=dash-db&limit=5000', timeout)
    except Exception as exc:
        logger.warning("dashboard search failed for %s: %s", endpoint, exc)
        return []


def get_dashboard(endpoint, token, uid, timeout):
    try:
        return grafana_api_get(endpoint, token, f'/api/dashboards/uid/{uid}', timeout)
    except Exception as exc:
        logger.warning("dashboard fetch failed for uid=%s: %s", uid, exc)
        return None


def list_alert_rules(endpoint, token, timeout):
    """Best-effort fetch of Grafana-managed alert rules."""
    try:
        return grafana_api_get(endpoint, token, '/api/v1/provisioning/alert-rules', timeout)
    except Exception as exc:
        logger.info("alert-rule fetch unavailable for %s: %s", endpoint, exc)
        return []


# ============================================================
# Time-range / refresh parsing
# ============================================================
_UNIT_SECONDS = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800,
                 'M': 2592000, 'y': 31536000}
_REL_RE = re.compile(r'now\s*-\s*(\d+)\s*([smhdwMy])')
_DUR_RE = re.compile(r'^(\d+)\s*([smhdwMy])$')


def parse_relative_range_seconds(time_from):
    if not time_from or not isinstance(time_from, str):
        return None
    m = _REL_RE.search(time_from)
    if m:
        return int(m.group(1)) * _UNIT_SECONDS.get(m.group(2), 0)
    if time_from.strip() == 'now/d':
        return 86400
    if time_from.strip() == 'now/w':
        return 604800
    return None


def parse_refresh_seconds(refresh):
    if not refresh or not isinstance(refresh, str):
        return 0
    m = _DUR_RE.match(refresh.strip())
    if m:
        return int(m.group(1)) * _UNIT_SECONDS.get(m.group(2), 0)
    return 0


def human_refresh(seconds):
    if not seconds:
        return "—"
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def human_window(seconds):
    if seconds is None:
        return "abs"
    for label, size in [('y', 31536000), ('w', 604800), ('d', 86400),
                        ('h', 3600), ('m', 60), ('s', 1)]:
        if seconds >= size and seconds % size == 0:
            return f"{seconds // size}{label}"
    return f"{seconds}s"


def human_bytes(n):
    if not n:
        return "0 B"
    units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    i = 0
    size = float(n)
    while size >= 1024 and i < len(units) - 1:
        size /= 1024
        i += 1
    return f"{size:,.1f} {units[i]}" if i else f"{int(size)} {units[i]}"


# ============================================================
# Query classification + target extraction
# ============================================================
def _extract_log_groups(target):
    """Return a list of log group names/arns referenced by a CloudWatch target."""
    groups = []
    lg = target.get('logGroups')
    if isinstance(lg, list):
        for g in lg:
            if isinstance(g, dict):
                groups.append(g.get('name') or g.get('arn') or '')
            elif isinstance(g, str):
                groups.append(g)
    names = target.get('logGroupNames')
    if isinstance(names, list):
        groups.extend([n for n in names if isinstance(n, str)])
    single = target.get('logGroupName')
    if isinstance(single, str) and single:
        groups.append(single)
    # strip empties + dedupe, keep order
    seen, out = set(), []
    for g in groups:
        g = (g or '').strip()
        if g and g not in seen:
            seen.add(g)
            out.append(g)
    return out


def classify_target(target, panel_datasource):
    """Return engine, query text, target (log groups/namespace), region."""
    ds = target.get('datasource') or panel_datasource or {}
    ds_type = (ds.get('type') if isinstance(ds, dict) else str(ds)) or 'unknown'

    info = {
        'engine': ds_type,
        'query': '',
        'region': target.get('region'),
        'log_groups': [],
        'namespace': None,
        'target_label': '',
    }

    if ds_type == 'cloudwatch':
        query_mode = (target.get('queryMode') or '').lower()
        expr = target.get('expression') or ''
        is_logs = (
            query_mode == 'logs'
            or 'fields ' in expr.lower()
            or 'filter ' in expr.lower()
            or bool(_extract_log_groups(target))
        )
        if is_logs:
            info['engine'] = 'logs_insights'
            info['query'] = (expr or target.get('query') or '').strip()
            info['log_groups'] = _extract_log_groups(target)
            info['target_label'] = ', '.join(info['log_groups']) or '(log groups not specified)'
        elif target.get('metricQueryType') == 1 or target.get('sqlExpression'):
            info['engine'] = 'metrics_insights'
            info['query'] = (target.get('sqlExpression') or expr or '').strip()
            info['namespace'] = target.get('namespace')
            info['target_label'] = target.get('namespace') or 'Metric Insights (SQL)'
        else:
            info['engine'] = 'metric_search'
            info['namespace'] = target.get('namespace')
            metric = target.get('metricName') or ''
            info['query'] = (expr or metric or '').strip()
            info['target_label'] = ' '.join(
                x for x in [target.get('namespace'), metric] if x
            ) or 'CloudWatch metric'
    elif ds_type == 'prometheus':
        info['engine'] = 'prometheus'
        info['query'] = (target.get('expr') or '').strip()
        info['target_label'] = 'Prometheus'
    else:
        info['query'] = (
            target.get('expr') or target.get('expression')
            or target.get('query') or target.get('rawSql') or ''
        ).strip()
        info['target_label'] = ds_type

    return info


# ============================================================
# Ingestion-rate measurement (for Logs Insights scan modelling)
# ============================================================
def get_log_group_ingest_gb_per_hour(session, region, log_group, cache, cfg):
    """
    Measure average ingestion (GB/hour) for a log group over the last 7 days
    using the AWS/Logs IncomingBytes metric. Falls back to an assumption.
    """
    key = (region, log_group)
    if key in cache:
        return cache[key]

    fallback = (cfg['default_ingest_gb_per_day'] / 24.0)

    if not cfg['measure_ingestion'] or not log_group:
        cache[key] = fallback
        return fallback

    try:
        cw = aws_client(session, 'cloudwatch', region)
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=7)
        resp = cw.get_metric_statistics(
            Namespace='AWS/Logs', MetricName='IncomingBytes',
            Dimensions=[{'Name': 'LogGroupName', 'Value': log_group}],
            StartTime=start, EndTime=end, Period=86400, Statistics=['Sum'],
        )
        pts = resp.get('Datapoints', [])
        if pts:
            total_bytes = sum(p['Sum'] for p in pts)
            gb_per_hour = (total_bytes / (1024 ** 3)) / (len(pts) * 24.0)
            cache[key] = gb_per_hour
            return gb_per_hour
    except Exception as exc:
        logger.info("ingest measure failed for %s/%s: %s", region, log_group, exc)

    cache[key] = fallback
    return fallback


# ============================================================
# Measured executions (CloudTrail lookup)
# ============================================================
# Logs Insights StartQuery events carry the query string, so we can attribute
# real run counts + bytes scanned back to specific dashboard queries. Metric
# queries (GetMetricData) are attributed at the account/region level only,
# because the CloudTrail event does not identify the Grafana panel.

_WS_RE = re.compile(r'\s+')


def normalise_query(text):
    """Whitespace-normalise a query string so equivalent queries match."""
    return _WS_RE.sub(' ', (text or '').strip()).lower()


# Grafana template variables: ${var}, $var, [[var]]
_TEMPLATE_VAR_RE = re.compile(r'(\$\{[^}]+\}|\$[A-Za-z_][A-Za-z0-9_]*|\[\[[^\]]+\]\])')


def template_key(text):
    """
    Normalised query with template variables collapsed to a placeholder, so a
    templated panel query fingerprints CONSISTENTLY regardless of which value a
    variable resolves to (fixes $region/$namespace fragmentation).
    """
    collapsed = _TEMPLATE_VAR_RE.sub('\u0001', text or '')
    return normalise_query(collapsed)


def has_template_vars(text):
    return bool(_TEMPLATE_VAR_RE.search(text or ''))


def query_match_regex(text):
    """
    Build a regex that matches a RESOLVED execution of a templated query back to
    its template. Template variables become '.+?' (non-greedy) and the rest is
    escaped. Used to attribute real Logs Insights executions to a panel query
    even though the panel stores '$region' and the execution has 'eu-west-1'.
    """
    parts = _TEMPLATE_VAR_RE.split(text or '')
    out = []
    for i, part in enumerate(parts):
        if i % 2 == 1:  # a captured template var
            out.append(r'\S+')
        else:
            out.append(re.escape(_WS_RE.sub(' ', part.strip().lower())))
    pattern = r'\s*'.join(p for p in out if p != '')
    try:
        return re.compile(pattern) if pattern else None
    except re.error:
        return None


def query_fingerprint(finding):
    """
    Stable identifier for a query across days, so we can trend it over time.
    Combines account, workspace, dashboard uid, panel, refId and a
    TEMPLATE-AWARE query key (variables collapsed), so templated dashboards do
    not fragment across variable values.
    """
    parts = [
        str(finding.get('account_id', '')),
        str(finding.get('workspace_name', '')),
        str(finding.get('dashboard_uid', '') or finding.get('dashboard', '')),
        str(finding.get('panel', '')),
        str(finding.get('ref_id', '')),
        template_key(finding.get('query', '')),
    ]
    return hashlib.sha1('|'.join(parts).encode('utf-8')).hexdigest()[:16]


def _extract_ct_user(detail):
    """Pull a human-readable principal from a CloudTrail event."""
    ui = detail.get('userIdentity') or {}
    # session context (assumed roles / SSO) carries the friendly name
    sc = (ui.get('sessionContext') or {}).get('sessionIssuer') or {}
    return (
        ui.get('userName')
        or ui.get('principalId', '').split(':')[-1]
        or sc.get('userName')
        or ui.get('arn', '').split('/')[-1]
        or ui.get('type')
        or None
    )


def collect_measured_executions(session, region, cfg):
    """
    Read CloudTrail for the lookback window and return a measurement bundle:

      {
        'logs': { normalised_query: {'runs': N, 'bytes': B, 'log_groups': set()} },
        'getmetricdata_calls': int,   # total GetMetricData calls in window
        'lookback_days': int,
        'available': bool,
        'note': str | None,
      }

    Uses CloudTrail LookupEvents (management events, no extra setup). This can
    be slow/paginated in busy accounts, so it is best-effort and degrades
    gracefully.
    """
    result = {
        'logs': {},                    # normalised_query -> {runs, bytes, log_groups}
        'gmd_by_metric': defaultdict(int),  # "namespace|metric" -> call count
        'getmetricdata_calls': 0,
        'lookback_days': cfg['measure_lookback_days'],
        'available': False,
        'logs_history_available': False,
        'note': None,
    }

    # --- 1) Logs Insights query HISTORY: real bytes scanned per execution ---
    # This is the authoritative source for Logs Insights cost (bytesScanned),
    # independent of CloudTrail. Preferred over modelled bytes.
    if cfg['measure_logs_history']:
        try:
            logs_client = aws_client(session, 'logs', region)
            hist = _collect_logs_query_history(logs_client, region, cfg)
            if hist:
                result['logs'] = hist
                result['logs_history_available'] = True
                result['available'] = True
        except Exception as exc:
            logger.info("Logs query history unavailable in %s: %s", region, exc)

    if not cfg['measure_executions']:
        if not result['available']:
            result['note'] = 'execution measurement disabled (MEASURE_EXECUTIONS=false)'
        return result

    # --- 2) CloudTrail: run counts + GetMetricData attribution ---
    try:
        ct = aws_client(session, 'cloudtrail', region)
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=cfg['measure_lookback_days'])

        # Only fall back to CloudTrail for Logs runs if history gave us nothing.
        logs_agg = defaultdict(lambda: {'runs': 0, 'bytes': 0.0, 'log_groups': set()})
        gmd_calls = 0

        for event_name in ('StartQuery', 'GetMetricData'):
            paginator = ct.get_paginator('lookup_events')
            pages = paginator.paginate(
                LookupAttributes=[{
                    'AttributeKey': 'EventName', 'AttributeValue': event_name,
                }],
                StartTime=start, EndTime=end,
            )
            for page in pages:
                for ev in page.get('Events', []):
                    try:
                        detail = json.loads(ev.get('CloudTrailEvent', '{}'))
                    except Exception:
                        detail = {}
                    req = detail.get('requestParameters') or {}

                    if event_name == 'GetMetricData':
                        gmd_calls += 1
                        # attribute to the metric(s) requested in the call
                        for md in (req.get('metricDataQueries') or []):
                            stat = (md.get('metricStat') or {})
                            metric = (stat.get('metric') or {})
                            ns = metric.get('namespace')
                            mn = metric.get('metricName')
                            if ns and mn:
                                result['gmd_by_metric'][f"{ns}|{mn}".lower()] += 1
                        continue

                    # StartQuery
                    qstr = req.get('queryString') or req.get('queryDefinitionString') or ''
                    if not qstr:
                        continue
                    key = normalise_query(qstr)
                    agg = logs_agg[key]
                    agg['runs'] += 1
                    for g in (req.get('logGroupNames')
                              or ([req.get('logGroupName')] if req.get('logGroupName') else [])):
                        if g:
                            agg['log_groups'].add(g)
                    # who ran it (for ad-hoc attribution)
                    user = _extract_ct_user(detail)
                    if user:
                        agg.setdefault('users', {})
                        agg['users'][user] = agg['users'].get(user, 0) + 1

        # Merge CloudTrail runs + user info into the logs map. If query history
        # already measured this query (richer bytes), keep its bytes but attach
        # the user list from CloudTrail.
        for key, agg in logs_agg.items():
            if key not in result['logs']:
                result['logs'][key] = agg
            else:
                result['logs'][key].setdefault('users', {})
                for u, n in agg.get('users', {}).items():
                    result['logs'][key]['users'][u] = result['logs'][key]['users'].get(u, 0) + n
                if not result['logs'][key].get('log_groups'):
                    result['logs'][key]['log_groups'] = agg.get('log_groups', set())
        result['getmetricdata_calls'] = gmd_calls
        result['available'] = True
    except Exception as exc:
        logger.info("CloudTrail measurement unavailable in %s: %s", region, exc)
        if not result['available']:
            result['note'] = f'CloudTrail lookup failed: {exc}'

    return result


def _collect_logs_query_history(logs_client, region, cfg):
    """
    Pull recent Logs Insights query executions and aggregate REAL bytes scanned
    per normalised query string using DescribeQueries + GetQueryResults.

    Returns {normalised_query: {'runs': N, 'bytes': total_bytes, 'runs_bytes':
    [per-run bytes], 'log_groups': set()}} or {} if unavailable.
    """
    agg = defaultdict(lambda: {'runs': 0, 'bytes': 0.0, 'runs_bytes': [],
                               'log_groups': set()})
    seen = 0
    try:
        paginator = logs_client.get_paginator('describe_queries')
        page_iter = paginator.paginate()
    except Exception:
        # describe_queries may not support pagination in all SDKs
        page_iter = [logs_client.describe_queries()]

    for page in page_iter:
        for q in page.get('queries', []):
            if seen >= cfg['logs_history_max_queries']:
                break
            seen += 1
            qstr = q.get('queryString', '')
            if not qstr:
                continue
            key = normalise_query(qstr)
            entry = agg[key]
            entry['runs'] += 1
            qid = q.get('queryId')
            # GetQueryResults carries statistics.bytesScanned for the execution
            try:
                res = logs_client.get_query_results(queryId=qid)
                stats = res.get('statistics') or {}
                b = float(stats.get('bytesScanned', 0) or 0)
                entry['bytes'] += b
                entry['runs_bytes'].append(b)
            except Exception:
                pass
        if seen >= cfg['logs_history_max_queries']:
            break

    return {k: v for k, v in agg.items() if v['runs'] > 0}


def _match_measured_logs(query, measured):
    """
    Find the measured-execution bundle for a panel query. Handles templated
    queries by matching resolved executions with a regex; otherwise exact
    normalised match. Records matched keys in measured['_matched_keys'] so the
    remainder can be reported as ad-hoc queries. Returns aggregate or None.
    """
    logs = measured.get('logs') or {}
    if not logs:
        return None
    matched = measured.setdefault('_matched_keys', set())

    # exact normalised match first (cheap, most common)
    nk = normalise_query(query)
    exact = logs.get(nk)
    if exact:
        matched.add(nk)
        return exact

    # templated query: match resolved executions by regex and merge them
    if has_template_vars(query):
        rx = query_match_regex(query)
        if rx:
            merged = {'runs': 0, 'bytes': 0.0, 'runs_bytes': [], 'log_groups': set()}
            hit = False
            for key, agg in logs.items():
                if rx.fullmatch(key) or rx.match(key):
                    hit = True
                    matched.add(key)
                    merged['runs'] += agg.get('runs', 0)
                    merged['bytes'] += agg.get('bytes', 0.0)
                    merged['runs_bytes'].extend(agg.get('runs_bytes', []))
                    merged['log_groups'] |= agg.get('log_groups', set())
            if hit:
                return merged
    return None


def apply_measured_to_finding(finding, measured, cfg):
    """
    Override modelled runs/day and — when Logs Insights query history is
    available — REAL bytes scanned and cost. Marks the finding measured and
    records the basis in the WHY list.
    """
    if not measured or not measured.get('available'):
        return finding

    # --- metric queries: attribute GetMetricData calls by namespace|metric ---
    if finding['engine'] in ('metric_search', 'metrics_insights'):
        gmd = measured.get('gmd_by_metric') or {}
        ns = (finding.get('namespace') or '').lower()
        # target_label often carries "namespace metric"; derive a metric name
        label = (finding.get('target_label') or '').lower()
        key = None
        for k in gmd:
            k_ns = k.split('|', 1)[0]
            if ns and k_ns == ns and (k.split('|', 1)[1] in label or not label):
                key = k
                break
        if key and gmd[key] > 0:
            days = max(measured['lookback_days'], 1)
            calls = gmd[key]
            finding['measured_runs_total'] = calls
            finding['runs_per_day'] = calls / days
            finding['cost_month'] = (cfg['metrics_per_call'] * finding['runs_per_day']
                                     * 30.0 * cfg['metrics_price_per_1000'] / 1000.0)
            finding['cost_day'] = finding['cost_month'] / 30.0
            finding['measured'] = True
            finding.setdefault('why', []).insert(
                0, f"GetMetricData calls MEASURED from CloudTrail ({calls} in {days}d).")
        return finding

    if finding['engine'] != 'logs_insights':
        return finding

    obs = _match_measured_logs(finding['query'], measured)
    if not obs or obs.get('runs', 0) <= 0:
        return finding

    days = max(measured['lookback_days'], 1)
    finding['measured_runs_total'] = obs['runs']
    finding['runs_per_day'] = obs['runs'] / days

    real_bytes = obs.get('bytes', 0.0)
    runs_bytes = obs.get('runs_bytes') or []
    if real_bytes > 0 and runs_bytes:
        # REAL bytes scanned per run (average of observed executions)
        avg_bytes_per_run = real_bytes / len(runs_bytes)
        finding['bytes_per_run'] = avg_bytes_per_run
        finding['bytes_measured'] = True
        gb_per_run = avg_bytes_per_run / (1024 ** 3)
        finding['cost_month'] = (gb_per_run * finding['runs_per_day'] * 30.0
                                 * cfg['logs_scan_price_per_gb'])
        finding['cost_day'] = finding['cost_month'] / 30.0
        finding['measured'] = True
        finding.setdefault('why', []).insert(
            0, f"Bytes scanned + runs MEASURED from Logs Insights query history "
               f"({obs['runs']} runs, {human_bytes(avg_bytes_per_run)}/run).")
    else:
        # runs measured (CloudTrail) but bytes still modelled
        gb_per_run = finding['bytes_per_run'] / (1024 ** 3) if finding['bytes_per_run'] else 0.0
        finding['cost_month'] = (gb_per_run * finding['runs_per_day'] * 30.0
                                 * cfg['logs_scan_price_per_gb'])
        finding['cost_day'] = finding['cost_month'] / 30.0
        finding['measured'] = True
        finding.setdefault('why', []).insert(
            0, f"Runs/day MEASURED ({obs['runs']} runs over {days}d); bytes modelled.")
    return finding


def extract_adhoc_queries(measured, cfg):
    """
    Ad-hoc queries = measured Logs Insights executions that did NOT match any
    dashboard panel or alert rule (i.e. run by a human/tool directly, e.g. in
    the console or via the SDK). Returns a list with data scanned + cost + who.
    Must be called AFTER all findings for the region are analyzed (so
    _matched_keys is populated).
    """
    logs = measured.get('logs') or {}
    matched = measured.get('_matched_keys') or set()
    days = max(measured.get('lookback_days', 1), 1)
    adhoc = []
    for key, agg in logs.items():
        if key in matched:
            continue
        runs = agg.get('runs', 0)
        if runs <= 0:
            continue
        bytes_total = agg.get('bytes', 0.0)
        bytes_measured = bytes_total > 0
        gb_total = bytes_total / (1024 ** 3)
        # cost over the observed executions (real bytes when available)
        cost = gb_total * cfg['logs_scan_price_per_gb']
        users = agg.get('users', {}) or {}
        top_users = sorted(users.items(), key=lambda kv: kv[1], reverse=True)
        adhoc.append({
            'query': key,
            'runs': runs,
            'runs_per_day': runs / days,
            'bytes_total': bytes_total,
            'bytes_per_run': (bytes_total / runs) if (bytes_measured and runs) else 0.0,
            'bytes_measured': bytes_measured,
            'cost': cost,
            'users': top_users,
            'log_groups': sorted(agg.get('log_groups', set())),
        })
    adhoc.sort(key=lambda a: (a['cost'], a['runs']), reverse=True)
    return adhoc


# ============================================================
# Cost model + WHY reasons
# ============================================================
def compute_runs_per_day(refresh_seconds, origin, refresh_interval_seconds, cfg):
    """Panels run only while viewed; alerts run 24x7 on their interval."""
    if origin == 'alert':
        interval = refresh_interval_seconds or 60
        return 86400.0 / interval
    if refresh_seconds and refresh_seconds > 0:
        return (cfg['viewing_hours_per_day'] * 3600.0) / refresh_seconds
    return cfg['manual_loads_per_day']


def model_query_cost(finding, session, region, ingest_cache, cfg):
    """Fill in scan/run bytes, runs/day, monthly cost, and WHY reasons."""
    engine = finding['engine']
    window_seconds = finding['range_seconds']
    window_hours = (window_seconds / 3600.0) if window_seconds else None
    runs_per_day = finding['runs_per_day']

    bytes_per_run = 0.0
    cost_month = 0.0
    reasons = []

    if engine == 'logs_insights':
        # scan/run = sum over log groups of (ingest GB/hour x window hours)
        gb_per_run = 0.0
        wh = window_hours if window_hours is not None else 1.0
        groups = finding['log_groups'] or ['(unspecified)']
        for g in groups:
            gph = get_log_group_ingest_gb_per_hour(session, region, g, ingest_cache, cfg)
            gb_per_run += gph * wh
        bytes_per_run = gb_per_run * (1024 ** 3)
        cost_month = gb_per_run * runs_per_day * 30.0 * cfg['logs_scan_price_per_gb']
        reasons.append("Logs Insights is billed per GB scanned.")
        if window_hours and window_hours >= cfg['timerange_crit_hours']:
            reasons.append(f"Very wide window ({human_window(window_seconds)}) scans a large volume each run.")
        elif window_hours and window_hours >= cfg['timerange_warn_hours']:
            reasons.append(f"Wide window ({human_window(window_seconds)}) increases scan per run.")

    elif engine in ('metric_search', 'metrics_insights'):
        metrics_per_call = cfg['metrics_per_call']
        cost_month = (metrics_per_call * runs_per_day * 30.0
                      * cfg['metrics_price_per_1000'] / 1000.0)
        reasons.append("Billed per metric requested per GetMetricData call.")
        if engine == 'metrics_insights':
            reasons.append("Metric Insights (SQL) can scan many metrics per run.")

    elif engine == 'prometheus':
        reasons.append("Prometheus/AMP query — no CloudWatch scan cost.")

    # refresh-driven multiplier reason
    rs = finding['refresh_seconds']
    if finding['origin'] == 'alert':
        reasons.append("Alert rule: runs 24x7 regardless of viewers.")
    elif rs and rs <= cfg['refresh_crit_seconds']:
        reasons.append(f"Very fast auto-refresh ({human_refresh(rs)}) re-runs the query continuously.")
    elif rs and rs <= cfg['refresh_warn_seconds']:
        reasons.append(f"Fast auto-refresh ({human_refresh(rs)}) multiplies run count.")
    elif not rs and finding['origin'] == 'panel':
        reasons.append("No auto-refresh; assumed manual loads/day.")

    finding['bytes_per_run'] = bytes_per_run
    finding['cost_month'] = cost_month
    finding['cost_day'] = cost_month / 30.0
    finding['why'] = reasons

    # --- service-quota impact estimate ---
    # Logs Insights: concurrent-query quota. A query at runs/day, each lasting
    # ~assumed_query_seconds, occupies query-seconds/day; expressed as a % of the
    # concurrent-query budget (quota x seconds/day).
    quota = {'kind': None, 'pct': 0.0, 'detail': ''}
    if engine == 'logs_insights':
        query_seconds_per_day = runs_per_day * cfg['assumed_query_seconds']
        budget = cfg['quota_logs_concurrent'] * 86400.0
        pct = (query_seconds_per_day / budget * 100.0) if budget else 0.0
        quota = {
            'kind': 'Logs Insights concurrency',
            'pct': pct,
            'detail': (f"~{runs_per_day:,.0f} runs/day x {cfg['assumed_query_seconds']:g}s "
                       f"vs {cfg['quota_logs_concurrent']} concurrent-query quota"),
        }
    elif engine in ('metric_search', 'metrics_insights'):
        calls_per_sec = runs_per_day / 86400.0
        pct = (calls_per_sec / cfg['quota_getmetricdata_tps'] * 100.0) if cfg['quota_getmetricdata_tps'] else 0.0
        quota = {
            'kind': 'GetMetricData TPS',
            'pct': pct,
            'detail': (f"~{calls_per_sec:.3f} calls/s vs "
                       f"{cfg['quota_getmetricdata_tps']} TPS quota"),
        }
    finding['quota_impact'] = quota
    return finding


def risk_level_from_cost(cost_month, engine, refresh_seconds, window_seconds, origin, cfg):
    """A simple level to colour the burn bar and rank rows."""
    score = 0
    if engine == 'logs_insights':
        score += 40
    elif engine == 'metrics_insights':
        score += 25
    elif engine == 'metric_search':
        score += 12
    if window_seconds:
        wh = window_seconds / 3600.0
        if wh >= cfg['timerange_crit_hours']:
            score += 30
        elif wh >= cfg['timerange_warn_hours']:
            score += 15
    if origin == 'alert':
        score += 20
    elif refresh_seconds and refresh_seconds <= cfg['refresh_crit_seconds']:
        score += 30
    elif refresh_seconds and refresh_seconds <= cfg['refresh_warn_seconds']:
        score += 15
    if score >= 80:
        return 'CRITICAL'
    if score >= 55:
        return 'HIGH'
    if score >= 30:
        return 'MEDIUM'
    return 'LOW'


# ============================================================
# Panel iteration + dashboard analysis
# ============================================================
def iter_panels(panels):
    for p in panels or []:
        if p.get('type') == 'row':
            yield from iter_panels(p.get('panels', []))
        else:
            yield p


def analyze_dashboard(dash_wrapper, session, region, ingest_cache, cfg, measured=None):
    dashboard = (dash_wrapper or {}).get('dashboard', {})
    meta = (dash_wrapper or {}).get('meta', {})
    title = dashboard.get('title', 'Untitled')
    uid = dashboard.get('uid', '')
    folder = meta.get('folderTitle', 'General')

    refresh_seconds = parse_refresh_seconds(dashboard.get('refresh'))
    range_seconds = parse_relative_range_seconds((dashboard.get('time') or {}).get('from'))

    findings = []
    for panel in iter_panels(dashboard.get('panels', [])):
        panel_title = panel.get('title', '(untitled panel)')
        panel_ds = panel.get('datasource')
        for idx, target in enumerate(panel.get('targets', []) or []):
            if target.get('hide'):
                continue
            qinfo = classify_target(target, panel_ds)
            if not qinfo['query'] and qinfo['engine'] == 'unknown':
                continue
            runs_per_day = compute_runs_per_day(refresh_seconds, 'panel', None, cfg)
            finding = {
                'dashboard': title, 'dashboard_uid': uid, 'folder': folder,
                'panel': panel_title, 'ref_id': target.get('refId', chr(65 + idx)),
                'engine': qinfo['engine'], 'origin': 'panel',
                'region': qinfo['region'] or region,
                'query': qinfo['query'], 'log_groups': qinfo['log_groups'],
                'namespace': qinfo['namespace'], 'target_label': qinfo['target_label'],
                'refresh_seconds': refresh_seconds, 'range_seconds': range_seconds,
                'runs_per_day': runs_per_day,
            }
            model_query_cost(finding, session, region, ingest_cache, cfg)
            finding['measured'] = False
            finding['bytes_measured'] = False
            finding['measured_runs_total'] = 0
            apply_measured_to_finding(finding, measured, cfg)
            finding['risk_level'] = risk_level_from_cost(
                finding['cost_month'], finding['engine'], refresh_seconds,
                range_seconds, 'panel', cfg)
            findings.append(finding)

    return {'title': title, 'uid': uid, 'folder': folder,
            'refresh_seconds': refresh_seconds, 'range_seconds': range_seconds,
            'findings': findings}


def analyze_alert_rules(rules, session, region, ingest_cache, cfg, measured=None):
    """Best-effort: turn Grafana-managed alert rules into findings."""
    findings = []
    for rule in rules or []:
        title = rule.get('title', '(alert rule)')
        interval = parse_refresh_seconds(rule.get('interval') or '') or 60
        window_seconds = None
        for data in rule.get('data', []) or []:
            model = data.get('model', {}) or {}
            ds = model.get('datasource') or {}
            qinfo = classify_target(model, ds)
            if not qinfo['query'] and qinfo['engine'] in ('unknown', '__expr__'):
                continue
            rel = model.get('relativeTimeRange') or {}
            if rel.get('from'):
                window_seconds = int(rel['from'])
            runs_per_day = compute_runs_per_day(0, 'alert', interval, cfg)
            finding = {
                'dashboard': '(alert rule)', 'dashboard_uid': '', 'folder': rule.get('folderUID', ''),
                'panel': title, 'ref_id': model.get('refId', 'A'),
                'engine': qinfo['engine'], 'origin': 'alert',
                'region': qinfo['region'] or region,
                'query': qinfo['query'], 'log_groups': qinfo['log_groups'],
                'namespace': qinfo['namespace'], 'target_label': qinfo['target_label'],
                'refresh_seconds': interval, 'range_seconds': window_seconds,
                'runs_per_day': runs_per_day,
            }
            model_query_cost(finding, session, region, ingest_cache, cfg)
            finding['measured'] = False
            finding['bytes_measured'] = False
            finding['measured_runs_total'] = 0
            apply_measured_to_finding(finding, measured, cfg)
            finding['risk_level'] = risk_level_from_cost(
                finding['cost_month'], finding['engine'], interval,
                window_seconds, 'alert', cfg)
            findings.append(finding)
    return findings


# ============================================================
# Orchestration
# ============================================================
def audit_workspace(session, region, ws, ingest_cache, cfg, measured=None):
    endpoint = ws.get('endpoint')
    workspace_id = ws.get('id')
    name = ws.get('name', workspace_id)
    result = {
        'workspace_id': workspace_id, 'workspace_name': name, 'endpoint': endpoint,
        'region': region, 'status': ws.get('status'), 'dashboards': [],
        'alert_findings': [], 'error': None,
    }
    if not endpoint:
        result['error'] = 'workspace has no endpoint (may still be provisioning)'
        return result

    # Prefer a pre-provisioned token from Secrets Manager (avoids RBAC 403s).
    # Fall back to minting a temporary workspace service account.
    token, cleanup = get_grafana_token(session, region, workspace_id, cfg)
    if not token:
        result['error'] = 'could not obtain a Grafana API token'
        return result

    try:
        for hit in list_dashboards(endpoint, token, cfg['http_timeout']):
            uid = hit.get('uid')
            if not uid:
                continue
            dash = get_dashboard(endpoint, token, uid, cfg['http_timeout'])
            if dash:
                result['dashboards'].append(
                    analyze_dashboard(dash, session, region, ingest_cache, cfg, measured))
        rules = list_alert_rules(endpoint, token, cfg['http_timeout'])
        result['alert_findings'] = analyze_alert_rules(
            rules, session, region, ingest_cache, cfg, measured)
    except Exception as exc:
        result['error'] = f'audit failed: {exc}'
    finally:
        cleanup()
    return result


def run_audit(cfg):
    audit = {
        'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
        'accounts': [],
    }
    for acct in cfg['accounts']:
        role_arn = acct.get('role_arn')
        try:
            session = build_session(role_arn)
        except Exception as exc:
            audit['accounts'].append({
                'account_id': acct.get('account_id') or 'unknown',
                'error': f'could not assume role {role_arn}: {exc}', 'regions': []})
            continue

        account_id = acct.get('account_id') or get_account_id(session)
        acct_result = {'account_id': account_id, 'error': None, 'regions': []}
        for region in acct['regions']:
            ingest_cache = {}
            measured = collect_measured_executions(session, region, cfg)
            region_result = {
                'region': region, 'workspaces': [],
                'getmetricdata_calls': measured.get('getmetricdata_calls', 0),
                'measure_lookback_days': measured.get('lookback_days'),
                'measure_available': measured.get('available', False),
                'measure_note': measured.get('note'),
            }
            for ws in discover_workspaces(session, region, cfg):
                region_result['workspaces'].append(
                    audit_workspace(session, region, ws, ingest_cache, cfg, measured))
            # ad-hoc = measured Logs executions not matched to any panel/alert
            region_result['adhoc'] = extract_adhoc_queries(measured, cfg)
            acct_result['regions'].append(region_result)
        audit['accounts'].append(acct_result)

    # Actual billing (Cost Explorer) + CloudWatch capacity, per account.
    audit['billing'] = collect_billing_and_capacity(cfg)
    return audit


# ============================================================
# Actual billing (Cost Explorer) + CloudWatch capacity/quota/storage
# ============================================================
# This is the AUTHORITATIVE spend view. Cost Explorer (ce:GetCostAndUsage) is a
# global endpoint (us-east-1) and reports real charges. We break CloudWatch
# spend down by usage type so Logs Insights, GetMetricData, log storage, log
# ingestion, alarms, dashboards, etc. are visible separately.

# Map raw CUR/Cost Explorer usage-type fragments to friendly component names.
_USAGE_TYPE_COMPONENTS = [
    ('DataScanned-Bytes', 'Logs Insights (data scanned)'),
    ('DataProcessing-Bytes', 'Logs ingestion'),
    ('S3-Egress', 'Logs data transfer'),
    ('TimedStorage-ByteHrs', 'Logs storage'),
    ('VendedLog-Bytes', 'Vended logs ingestion'),
    ('CW:GMD-Metrics', 'GetMetricData (metrics)'),
    ('CW:MetricMonitorUsage', 'Custom metrics'),
    ('CW:AlarmMonitorUsage', 'Alarms'),
    ('CW:Requests', 'API requests'),
    ('CW:Dashboards', 'Dashboards'),
    ('CW:GMWD-Metrics', 'GetMetricWidgetImage'),
    ('Contributor', 'Contributor Insights'),
    ('Synthetics', 'Synthetics canaries'),
    ('CW:Metrics', 'Metrics'),
]


def _friendly_usage_type(usage_type):
    for frag, name in _USAGE_TYPE_COMPONENTS:
        if frag in usage_type:
            return name
    # Fall back to the tail of the usage type (strip region prefix like EUW1-).
    return usage_type.split('-', 1)[-1] if '-' in usage_type else usage_type


def _month_bounds(today):
    """Return (this_month_start, today_str, last_month_start, last_month_end)."""
    first_this = today.replace(day=1)
    last_month_end = first_this  # exclusive end for last month
    prev = first_this - timedelta(days=1)
    first_prev = prev.replace(day=1)
    return (first_this.strftime('%Y-%m-%d'), today.strftime('%Y-%m-%d'),
            first_prev.strftime('%Y-%m-%d'), last_month_end.strftime('%Y-%m-%d'))


def get_cost_by_usage_type(ce, start, end):
    """Return {friendly_component: cost} for CloudWatch over [start, end)."""
    components = defaultdict(float)
    total = 0.0
    try:
        kwargs = dict(
            TimePeriod={'Start': start, 'End': end},
            Granularity='MONTHLY',
            Metrics=['UnblendedCost'],
            GroupBy=[{'Type': 'DIMENSION', 'Key': 'USAGE_TYPE'}],
            Filter={'Dimensions': {'Key': 'SERVICE',
                    'Values': ['AmazonCloudWatch', 'AmazonCloudWatchLogs',
                               'AWSCloudWatchLogs', 'CloudWatch Logs']}},
        )
        token = None
        while True:
            if token:
                kwargs['NextPageToken'] = token
            resp = ce.get_cost_and_usage(**kwargs)
            for result in resp.get('ResultsByTime', []):
                for grp in result.get('Groups', []):
                    ut = grp['Keys'][0]
                    amt = float(grp['Metrics']['UnblendedCost']['Amount'])
                    components[_friendly_usage_type(ut)] += amt
                    total += amt
            token = resp.get('NextPageToken')
            if not token:
                break
    except Exception as exc:
        logger.warning("Cost Explorer query failed: %s", exc)
        return None, None
    return dict(components), total


def get_daily_cloudwatch_cost(ce, start, end):
    """Return [(date, cost)] daily CloudWatch spend over [start, end)."""
    series = []
    try:
        resp = ce.get_cost_and_usage(
            TimePeriod={'Start': start, 'End': end},
            Granularity='DAILY',
            Metrics=['UnblendedCost'],
            Filter={'Dimensions': {'Key': 'SERVICE',
                    'Values': ['AmazonCloudWatch', 'AmazonCloudWatchLogs',
                               'AWSCloudWatchLogs', 'CloudWatch Logs']}},
        )
        for result in resp.get('ResultsByTime', []):
            d = result['TimePeriod']['Start']
            amt = float(result['Total']['UnblendedCost']['Amount'])
            series.append((d, amt))
    except Exception as exc:
        logger.info("Daily cost query failed: %s", exc)
    return series


def collect_capacity(session, regions):
    """CloudWatch resource counts + log storage/ingestion per region."""
    out = []
    for region in regions:
        entry = {'region': region, 'error': None}
        try:
            cw = aws_client(session, 'cloudwatch', region)
            logs = aws_client(session, 'logs', region)

            alarms = 0
            p = cw.get_paginator('describe_alarms')
            for page in p.paginate(AlarmTypes=['MetricAlarm', 'CompositeAlarm']):
                alarms += len(page.get('MetricAlarms', [])) + len(page.get('CompositeAlarms', []))

            dashboards = 0
            p = cw.get_paginator('list_dashboards')
            for page in p.paginate():
                dashboards += len(page.get('DashboardEntries', []))

            log_groups = 0
            storage_bytes = 0
            p = logs.get_paginator('describe_log_groups')
            for page in p.paginate():
                for lg in page.get('logGroups', []):
                    log_groups += 1
                    storage_bytes += lg.get('storedBytes', 0)

            # 24h ingestion via AWS/Logs IncomingBytes
            ingest_bytes = 0
            try:
                end = datetime.now(timezone.utc)
                start = end - timedelta(hours=24)
                resp = cw.get_metric_statistics(
                    Namespace='AWS/Logs', MetricName='IncomingBytes',
                    StartTime=start, EndTime=end, Period=86400, Statistics=['Sum'])
                pts = resp.get('Datapoints', [])
                if pts:
                    ingest_bytes = pts[0].get('Sum', 0)
            except Exception:
                pass

            entry.update({
                'alarms': alarms, 'dashboards': dashboards,
                'log_groups': log_groups, 'storage_bytes': storage_bytes,
                'ingest_bytes_24h': ingest_bytes,
            })
        except Exception as exc:
            entry['error'] = str(exc)
        out.append(entry)
    return out


def collect_billing_and_capacity(cfg):
    """
    Per account: actual CloudWatch spend (this month + last month, by component,
    plus a daily series) and CloudWatch capacity/quota/storage per region.
    """
    billing = {'enabled': cfg['billing_enabled'] or cfg['capacity_enabled'],
               'accounts': [], 'note': None}
    if not (cfg['billing_enabled'] or cfg['capacity_enabled']):
        return billing

    today = datetime.now(timezone.utc).date()
    this_start, this_end, last_start, last_end = _month_bounds(today)

    for acct in cfg['accounts']:
        role_arn = acct.get('role_arn')
        try:
            session = build_session(role_arn)
        except Exception as exc:
            billing['accounts'].append({
                'account_id': acct.get('account_id') or 'unknown',
                'error': f'assume role failed: {exc}'})
            continue

        account_id = acct.get('account_id') or get_account_id(session)
        rec = {'account_id': account_id, 'error': None,
               'this_month': None, 'last_month': None,
               'this_month_total': 0.0, 'last_month_total': 0.0,
               'daily': [], 'capacity': []}

        if cfg['billing_enabled']:
            try:
                # Cost Explorer is global; use us-east-1 endpoint.
                ce = aws_client(session, 'ce', 'us-east-1')
                comp_this, total_this = get_cost_by_usage_type(ce, this_start, this_end)
                comp_last, total_last = get_cost_by_usage_type(ce, last_start, last_end)
                rec['this_month'] = comp_this
                rec['last_month'] = comp_last
                rec['this_month_total'] = total_this or 0.0
                rec['last_month_total'] = total_last or 0.0
                rec['daily'] = get_daily_cloudwatch_cost(ce, this_start, this_end)
                rec['period_this'] = f"{this_start} to {this_end}"
                rec['period_last'] = f"{last_start} to {last_end}"
                if comp_this is None:
                    rec['error'] = 'Cost Explorer unavailable (check ce:GetCostAndUsage + that CE is enabled)'
            except Exception as exc:
                rec['error'] = f'billing query failed: {exc}'

        if cfg['capacity_enabled']:
            rec['capacity'] = collect_capacity(session, acct['regions'])

        billing['accounts'].append(rec)

    return billing


# ============================================================
# Aggregation
# ============================================================
RISK_ORDER = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
BAR_CLASS = {'CRITICAL': 'b', 'HIGH': 'h', 'MEDIUM': 'w', 'LOW': ''}


def flatten_findings(audit):
    rows = []
    for acct in audit['accounts']:
        for region in acct.get('regions', []):
            for ws in region.get('workspaces', []):
                for dash in ws.get('dashboards', []):
                    for f in dash.get('findings', []):
                        r = dict(f)
                        r['account_id'] = acct['account_id']
                        r['workspace_name'] = ws['workspace_name']
                        r['fingerprint'] = query_fingerprint(r)
                        rows.append(r)
                for f in ws.get('alert_findings', []):
                    r = dict(f)
                    r['account_id'] = acct['account_id']
                    r['workspace_name'] = ws['workspace_name']
                    r['fingerprint'] = query_fingerprint(r)
                    rows.append(r)
    return rows


def summarize(audit):
    rows = flatten_findings(audit)
    total_cost = sum(r['cost_month'] for r in rows)
    logs_count = sum(1 for r in rows if r['engine'] == 'logs_insights')
    always_on = sum(1 for r in rows if r['origin'] == 'alert')

    ranked = sorted(rows, key=lambda r: r['cost_month'], reverse=True)
    top10_cost = sum(r['cost_month'] for r in ranked[:10])
    concentration = (top10_cost / total_cost * 100.0) if total_cost > 0 else 0.0

    measured_query_count = sum(1 for r in rows if r.get('measured'))

    workspace_count = sum(
        len(reg.get('workspaces', []))
        for acct in audit['accounts'] for reg in acct.get('regions', []))
    dashboard_uids = set()
    for acct in audit['accounts']:
        for reg in acct.get('regions', []):
            for ws in reg.get('workspaces', []):
                for d in ws.get('dashboards', []):
                    dashboard_uids.add((ws['workspace_name'], d['uid']))

    # Measured GetMetricData spend (account/region level, not per-panel).
    gmd_calls = 0
    measure_available = False
    lookback_days = None
    for acct in audit['accounts']:
        for reg in acct.get('regions', []):
            gmd_calls += reg.get('getmetricdata_calls', 0) or 0
            if reg.get('measure_available'):
                measure_available = True
            lookback_days = reg.get('measure_lookback_days') or lookback_days

    return {
        'rows': rows,
        'total_cost': total_cost,
        'logs_count': logs_count,
        'always_on': always_on,
        'concentration': concentration,
        'workspace_count': workspace_count,
        'dashboard_count': len(dashboard_uids),
        'query_count': len(rows),
        'measured_query_count': measured_query_count,
        'measured_getmetricdata_calls': gmd_calls,
        'measure_available': measure_available,
        'measure_lookback_days': lookback_days,
    }


# ============================================================
# History persistence + trend detection
# ============================================================
# Each run writes a compact JSON snapshot of that day's critical queries to S3
# under <prefix>/history/YYYY-MM-DD.json. To compute trends we read back the
# snapshots for the last N days and count, per fingerprint, on how many distinct
# days a query was critical.

def _history_prefix(cfg):
    return cfg['s3_prefix'].rstrip('/') + '/history/'


def build_snapshot(summary, run_date, cfg):
    """
    Compact snapshot of today's tracked-severity queries for trend history.
    Stores per-day cost so trend runs can ACCUMULATE cost over the window.
    """
    sev = set(cfg['trend_severities'])
    tracked = [r for r in summary['rows'] if r['risk_level'] in sev]
    return {
        'date': run_date,
        'queries': [
            {
                'fingerprint': r['fingerprint'],
                'dashboard': r['dashboard'],
                'panel': r['panel'],
                'workspace_name': r['workspace_name'],
                'account_id': r['account_id'],
                'engine': r['engine'],
                'risk_level': r['risk_level'],
                'cost_month': round(r['cost_month'], 2),
                'cost_day': round(r.get('cost_day', r['cost_month'] / 30.0), 2),
                'quota_pct': round((r.get('quota_impact') or {}).get('pct', 0.0), 2),
            }
            for r in tracked
        ],
        # keep the old key for backward-compat with older snapshots
        'critical': [
            {'fingerprint': r['fingerprint'], 'cost_month': round(r['cost_month'], 2)}
            for r in tracked if r['risk_level'] == 'CRITICAL'
        ],
    }


def save_snapshot(cfg, snapshot):
    if not cfg['history_enabled'] or not cfg['s3_bucket']:
        return None
    key = _history_prefix(cfg) + f"{snapshot['date']}.json"
    try:
        aws_client(boto3.Session(), 's3').put_object(
            Bucket=cfg['s3_bucket'], Key=key,
            Body=json.dumps(snapshot).encode('utf-8'),
            ContentType='application/json')
        logger.info("Saved history snapshot to s3://%s/%s", cfg['s3_bucket'], key)
        return key
    except Exception as exc:
        logger.warning("Failed to save history snapshot: %s", exc)
        return None


def load_history(cfg, run_date):
    """Load snapshots for the last trend_window_days days (excluding today)."""
    if not cfg['history_enabled'] or not cfg['s3_bucket']:
        return []
    s3 = aws_client(boto3.Session(), 's3')
    snapshots = []
    today = datetime.strptime(run_date, '%Y-%m-%d').date()
    for delta in range(1, cfg['trend_window_days'] + 1):
        day = (today - timedelta(days=delta)).strftime('%Y-%m-%d')
        key = _history_prefix(cfg) + f"{day}.json"
        try:
            obj = s3.get_object(Bucket=cfg['s3_bucket'], Key=key)
            snapshots.append(json.loads(obj['Body'].read().decode('utf-8')))
        except Exception:
            continue  # missing day is fine
    return snapshots


def compute_rogue_cost(cfg, summary, run_date):
    """
    For every currently-tracked-severity query, sum the estimated cost it has
    generated since it FIRST went 'rogue' (first appeared at a tracked severity
    within the history window). Annotates each row in-place with:
      row['rogue_since']       -> first date seen (YYYY-MM-DD) or today
      row['rogue_days']        -> number of days it has been rogue (incl. today)
      row['rogue_cost']        -> accumulated estimated cost over those days
    This runs EVERY day (not just trend days) so the table column is always
    populated.
    """
    sev = set(cfg['trend_severities'])
    history = load_history(cfg, run_date)

    daily_cost = defaultdict(dict)   # fp -> {date: cost_day}
    for snap in history:
        d = snap['date']
        for q in snap.get('queries', []):
            if q.get('risk_level') in sev:
                daily_cost[q['fingerprint']][d] = q.get(
                    'cost_day', q.get('cost_month', 0.0) / 30.0)
        if 'queries' not in snap:  # legacy snapshots
            for c in snap.get('critical', []):
                daily_cost[c['fingerprint']][d] = c.get('cost_month', 0.0) / 30.0

    for r in summary['rows']:
        if r['risk_level'] not in sev:
            r['rogue_days'] = 0
            r['rogue_cost'] = 0.0
            r['rogue_since'] = None
            continue
        fp = r['fingerprint']
        daily_cost[fp][run_date] = r.get('cost_day', r['cost_month'] / 30.0)
        days_sorted = sorted(daily_cost[fp].keys())
        r['rogue_since'] = days_sorted[0]
        r['rogue_days'] = len(days_sorted)
        r['rogue_cost'] = sum(daily_cost[fp].values())


def is_trend_day(cfg, run_date):
    """True on every trend_cadence_days-th day (based on ordinal date)."""
    if cfg['force_trend']:
        return True
    if cfg['trend_cadence_days'] <= 1:
        return True
    ordinal = datetime.strptime(run_date, '%Y-%m-%d').date().toordinal()
    return ordinal % cfg['trend_cadence_days'] == 0


def compute_trends(cfg, summary, run_date):
    """
    On a trend day, mark today's CRITICAL queries that were ALSO critical on
    >= trend_min_days distinct days within the trend window. Returns a list of
    trending records and annotates the matching rows in-place.
    """
    result = {
        'is_trend_day': is_trend_day(cfg, run_date),
        'window_days': cfg['trend_window_days'],
        'min_days': cfg['trend_min_days'],
        'severities': cfg['trend_severities'],
        'trending': [],
    }
    if not result['is_trend_day']:
        return result

    sev = set(cfg['trend_severities'])
    history = load_history(cfg, run_date)

    # Per fingerprint: which days it appeared (at a tracked severity), plus the
    # per-day cost and severity seen on each of those days.
    days_seen = defaultdict(set)
    daily_cost = defaultdict(dict)      # fp -> {date: cost_day}
    sev_by_day = defaultdict(dict)      # fp -> {date: risk_level}
    quota_by_day = defaultdict(dict)    # fp -> {date: quota_pct}
    for snap in history:
        d = snap['date']
        # new-format snapshots
        for q in snap.get('queries', []):
            if q.get('risk_level') not in sev:
                continue
            fp = q['fingerprint']
            days_seen[fp].add(d)
            daily_cost[fp][d] = q.get('cost_day', q.get('cost_month', 0.0) / 30.0)
            sev_by_day[fp][d] = q.get('risk_level')
            quota_by_day[fp][d] = q.get('quota_pct', 0.0)
        # legacy-format fallback (older snapshots only had 'critical')
        if 'queries' not in snap:
            for c in snap.get('critical', []):
                fp = c['fingerprint']
                days_seen[fp].add(d)
                daily_cost[fp][d] = c.get('cost_month', 0.0) / 30.0
                sev_by_day[fp][d] = 'CRITICAL'

    today_tracked = {r['fingerprint']: r for r in summary['rows']
                     if r['risk_level'] in sev}

    for fp, row in today_tracked.items():
        # include today's data point
        days_seen[fp].add(run_date)
        daily_cost[fp][run_date] = row.get('cost_day', row['cost_month'] / 30.0)
        sev_by_day[fp][run_date] = row['risk_level']
        quota_by_day[fp][run_date] = (row.get('quota_impact') or {}).get('pct', 0.0)

        total_days = len(days_seen[fp])
        if total_days < cfg['trend_min_days']:
            continue

        # accumulated cost generated across the window (sum of per-day costs)
        window_cost = sum(daily_cost[fp].values())
        ordered_days = sorted(daily_cost[fp].keys())
        first_cost = daily_cost[fp][ordered_days[0]]
        last_cost = daily_cost[fp][ordered_days[-1]]
        direction = 'rising' if last_cost >= first_cost else 'easing'
        worst_sev = 'CRITICAL' if 'CRITICAL' in sev_by_day[fp].values() else (
            'HIGH' if 'HIGH' in sev_by_day[fp].values() else 'MEDIUM')
        max_quota = max(quota_by_day[fp].values(), default=0.0)

        row['trending'] = True
        row['trending_days'] = total_days
        row['trending_window_cost'] = window_cost
        result['trending'].append({
            'fingerprint': fp,
            'dashboard': row['dashboard'],
            'panel': row['panel'],
            'workspace_name': row['workspace_name'],
            'account_id': row['account_id'],
            'engine': row['engine'],
            'risk_level': row['risk_level'],
            'worst_severity': worst_sev,
            'cost_month': row['cost_month'],
            'cost_day': row.get('cost_day', row['cost_month'] / 30.0),
            'window_cost': window_cost,
            'days': total_days,
            'direction': direction,
            'quota_kind': (row.get('quota_impact') or {}).get('kind'),
            'quota_pct': max_quota,
        })

    # worst severity first, then most days, then biggest accumulated cost
    sev_rank = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
    result['trending'].sort(
        key=lambda x: (sev_rank.get(x['worst_severity'], 9), -x['days'], -x['window_cost']))
    return result


# ============================================================
# HTML report (white background, colour accents retained)
# ============================================================
def _esc(text):
    if text is None:
        return ''
    return (str(text).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;').replace("'", '&#x27;'))


def _rogue_cell(r):
    """Accumulated cost since a query first went 'rogue' (tracked severity)."""
    cost = r.get('rogue_cost', 0.0)
    days = r.get('rogue_days', 0)
    since = r.get('rogue_since')
    if not days or cost <= 0:
        return '<span class="muted">—</span>'
    return (f'<b>${cost:,.2f}</b>'
            f'<div class="muted" style="font-size:10px">since {_esc(since)} ({days}d)</div>')


def _quota_cell(r):
    """Render the service-quota impact cell for a query."""
    q = r.get('quota_impact') or {}
    kind = q.get('kind')
    pct = q.get('pct', 0.0)
    if not kind:
        return '<span class="muted">—</span>'
    gcls = 'b' if pct >= 40 else 'h' if pct >= 20 else 'w' if pct >= 5 else ''
    return (f'<div class="gauge" title="{_esc(q.get("detail", ""))}">'
            f'<i class="{gcls}" style="width:{min(pct, 100):.1f}%"></i></div>'
            f'<div class="muted" style="font-size:10px">{pct:.1f}% {_esc(kind)}</div>')


def _seen_cell(r):
    """Render the 'Runs seen' cell from measured CloudTrail data."""
    n = r.get('measured_runs_total', 0)
    if n and n > 0:
        return f'{n:,} <span class="muted">obs</span>'
    return '<span class="muted">—</span>'


def _row_html(r, max_cost, engine_tag, bar):
    """Render a single query row (shared by the critical + full tables)."""
    search_blob = ' '.join(str(x) for x in [
        r['dashboard'], r['folder'], r['panel'], r['engine'],
        r['region'], r['target_label']]).lower()
    why_html = ''.join(f'<li>{_esc(x)}</li>' for x in r.get('why', []))
    dash_name = r['dashboard'] if r['origin'] != 'alert' else '(alert rule)'
    trending = r.get('trending')
    fire = (f'<span class="fire" title="critical on {r.get("trending_days")} of the '
            f'last days">&#128293; {r.get("trending_days")}d</span> '
            if trending else '')
    tr_class = []
    if r['risk_level'] == 'CRITICAL':
        tr_class.append('crit')
    if trending:
        tr_class.append('trending')
    cls_attr = f' class="{" ".join(tr_class)}"' if tr_class else ''
    return (
        f'<tr{cls_attr} data-search="{_esc(search_blob)}" '
        f'data-engine="{_esc(r["engine"])}" data-origin="{_esc(r["origin"])}" '
        f'data-cost="{r["cost_month"]}" data-runs="{r["runs_per_day"]}" '
        f'data-bytes="{r["bytes_per_run"]}" data-seen="{r.get("measured_runs_total", 0)}" '
        f'data-rogue="{r.get("rogue_cost", 0.0)}" '
        f'data-quota="{(r.get("quota_impact") or {}).get("pct", 0.0)}">'
        f'<td><span class="risk {r["risk_level"]}">{r["risk_level"]}</span></td>'
        f'<td><div class="name">{fire}{_esc(dash_name)}</div>'
        f'<div class="muted">{_esc(r["folder"])} &middot; {_esc(r["workspace_name"])}</div></td>'
        f'<td><div>{_esc(r["panel"])} <span class="muted">[{_esc(r["ref_id"])}]</span></div>'
        f'<div>{engine_tag(r["engine"], r["origin"])}</div></td>'
        f'<td class="num">{human_refresh(r["refresh_seconds"])}</td>'
        f'<td class="num">{human_window(r["range_seconds"])}</td>'
        f'<td class="num">{r["runs_per_day"]:,.0f}</td>'
        f'<td class="num hide-sm">{human_bytes(r["bytes_per_run"])}</td>'
        f'<td class="num hide-sm">{_seen_cell(r)}</td>'
        f'<td>{bar(r)}</td>'
        f'<td class="num hide-sm">{_rogue_cell(r)}</td>'
        f'<td class="num hide-sm">{_quota_cell(r)}</td>'
        f'<td class="hide-sm"><ul class="why">{why_html}</ul></td>'
        f'<td class="hide-sm"><div class="muted">{_esc(r["target_label"])}</div>'
        f'<details><summary>query</summary>'
        f'<div class="muted" style="margin-top:4px">{_esc(r["account_id"])} &middot; {_esc(r["region"])}</div>'
        f'<pre>{_esc(r["query"] or "(no expression captured)")}</pre></details></td>'
        f'</tr>')


def _table_head():
    return ('<table id="{tid}"><thead><tr>'
            '<th>Risk</th><th>Dashboard</th><th>Panel / query</th>'
            '<th class="num">Refresh</th><th class="num">Window</th>'
            '<th class="num" data-sort="runs">Runs/day</th>'
            '<th class="num hide-sm" data-sort="bytes">Scan/run</th>'
            '<th class="num hide-sm" data-sort="seen">Runs seen</th>'
            '<th data-sort="cost">Cost/month</th>'
            '<th class="num hide-sm" data-sort="rogue">Cost consumed</th>'
            '<th class="num hide-sm" data-sort="quota">Quota impact</th>'
            '<th class="hide-sm">Why</th>'
            '<th class="hide-sm">Target / query</th>'
            '</tr></thead><tbody>')


def build_html(audit, summary, cfg, trends=None):
    trends = trends or {'is_trend_day': False, 'trending': []}
    rows = sorted(summary['rows'], key=lambda r: r['cost_month'], reverse=True)
    max_cost = max((r['cost_month'] for r in rows), default=0.0)

    # Measured GetMetricData spend, extrapolated from the lookback to a month.
    lookback = summary.get('measure_lookback_days') or cfg['measure_lookback_days']
    gmd_calls = summary.get('measured_getmetricdata_calls', 0)
    measured_metric_month = (
        gmd_calls * cfg['metrics_per_call'] * cfg['metrics_price_per_1000'] / 1000.0
        * (30.0 / max(lookback, 1))
    )

    def engine_tag(engine, origin):
        cls = {'logs_insights': 'logs', 'metric_search': 'metrics',
               'metrics_insights': 'metrics'}.get(engine, '')
        tags = ''
        if origin == 'alert':
            tags += '<span class="tag alert">alert 24x7</span> '
        tags += f'<span class="tag {cls}">{_esc(engine)}</span>'
        return tags

    def bar(r):
        pct = (r['cost_month'] / max_cost * 100.0) if max_cost > 0 else 0.0
        pct = max(pct, 1.0) if r['cost_month'] > 0 else 0.0
        cls = BAR_CLASS.get(r['risk_level'], '')
        dash = '' if r['measured'] else ' dash'
        if r.get('bytes_measured'):
            label = 'measured (real bytes)'
        elif r['measured']:
            label = 'measured (runs)'
        else:
            label = 'estimated'
        return (
            f'<div class="bar {cls}{dash}"><i style="width:{pct:.1f}%"></i>'
            f'<span>${r["cost_month"]:,.2f}</span></div>'
            f'<div class="muted" style="font-size:10px;margin-top:2px">{label}</div>'
        )

    h = []
    h.append('<!doctype html><html lang="en"><head><meta charset="utf-8">')
    h.append('<meta name="viewport" content="width=device-width,initial-scale=1">')
    h.append('<title>Grafana query cost audit</title><style>')
    h.append('''
:root{
  --bg:#FFFFFF; --panel:#F6F8FA; --panel-2:#EEF1F4; --rule:#D9DEE4;
  --text:#1E2A33; --dim:#5B6B78; --bright:#0B1015;
  --cold:#2B6CB0; --warm:#B7791F; --hot:#C05621; --burn:#C53030;
  --mono: ui-monospace, "SF Mono", "JetBrains Mono", "Cascadia Mono", Consolas, monospace;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-family:var(--mono);
     font-size:13px;line-height:1.45;-webkit-font-smoothing:antialiased}
a{color:var(--cold)}
.wrap{max-width:1600px;margin:0 auto;padding:28px 20px 80px}
header{border-bottom:2px solid var(--rule);padding-bottom:18px;margin-bottom:22px}
h1{font-size:13px;font-weight:700;letter-spacing:.34em;text-transform:uppercase;
   margin:0 0 6px;color:var(--bright)}
.sub{color:var(--dim);font-size:12px}
.meters{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));
        gap:1px;background:var(--rule);border:1px solid var(--rule);margin-bottom:8px}
.meter{background:var(--panel);padding:14px 16px}
.meter .k{font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:var(--dim)}
.meter .v{font-size:22px;font-weight:700;color:var(--bright);margin-top:6px;
          font-variant-numeric:tabular-nums}
.meter .n{font-size:11px;color:var(--dim);margin-top:2px}
.caveat{border-left:3px solid var(--warm);background:#FFF8E6;
        padding:10px 14px;margin:18px 0 22px;color:var(--text);font-size:12px}
.caveat b{color:var(--warm);font-weight:700}
.section{font-size:12px;font-weight:700;letter-spacing:.18em;text-transform:uppercase;
         color:var(--bright);margin:26px 0 10px}
.trend{border-left:3px solid var(--burn);background:#FDECEC;padding:12px 14px;margin:8px 0 22px}
.trend b{color:var(--burn)}
.controls{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:12px}
input[type=search],select{background:#FFFFFF;border:1px solid var(--rule);
  color:var(--text);font-family:var(--mono);font-size:12px;padding:7px 10px}
input[type=search]{min-width:280px}
input:focus,select:focus{outline:2px solid var(--cold);outline-offset:1px}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;
      border:1px solid var(--rule)}
thead th{position:sticky;top:0;background:var(--panel-2);border-bottom:2px solid var(--rule);
  text-align:left;font-size:10px;letter-spacing:.16em;text-transform:uppercase;
  color:var(--dim);padding:9px 8px;cursor:pointer;white-space:nowrap}
thead th:hover{color:var(--bright)}
tbody td{border-bottom:1px solid var(--rule);padding:8px;vertical-align:top}
tbody tr:hover{background:var(--panel)}
tbody tr.crit{background:#FDF1F1}
tbody tr.crit:hover{background:#FBE6E6}
tbody tr.trending{box-shadow:inset 3px 0 0 var(--burn)}
.num{text-align:right;white-space:nowrap}
.name{color:var(--bright);font-weight:600}
.muted{color:var(--dim)}
.why{font-size:11px;color:var(--text);margin:0;padding-left:15px}
.why li{margin:1px 0}
.risk{display:inline-block;font-size:10px;letter-spacing:.08em;font-weight:700;
      padding:1px 6px;border-radius:3px;color:#fff;white-space:nowrap}
.risk.CRITICAL{background:var(--burn)} .risk.HIGH{background:var(--hot)}
.risk.MEDIUM{background:var(--warm)} .risk.LOW{background:#38A169}
.fire{color:var(--burn);font-weight:700}
.tag{display:inline-block;font-size:10px;letter-spacing:.1em;text-transform:uppercase;
     padding:1px 6px;border:1px solid var(--rule);color:var(--dim);white-space:nowrap}
.tag.alert{border-color:var(--burn);color:var(--burn)}
.tag.logs{border-color:var(--hot);color:var(--hot)}
.tag.metrics{border-color:var(--cold);color:var(--cold)}
.bar{position:relative;height:16px;min-width:120px;background:var(--panel-2);
     border:1px solid var(--rule)}
.bar i{display:block;height:100%;background:var(--cold)}
.bar.w i{background:var(--warm)} .bar.h i{background:var(--hot)} .bar.b i{background:var(--burn)}
.bar span{position:absolute;right:4px;top:0;line-height:14px;font-size:10px;
          color:var(--bright);font-weight:600}
.bar.dash{background-image:repeating-linear-gradient(45deg,transparent,transparent 3px,
  rgba(91,107,120,.16) 3px,rgba(91,107,120,.16) 6px)}
details summary{cursor:pointer;color:var(--dim);font-size:11px}
pre{white-space:pre-wrap;word-break:break-word;background:var(--panel-2);
    border:1px solid var(--rule);padding:8px;margin:6px 0 0;font-size:11px;color:var(--text)}
footer{margin-top:30px;color:var(--dim);font-size:11px;border-top:1px solid var(--rule);padding-top:14px}
.tabs{display:flex;gap:2px;margin:18px 0 22px;border-bottom:2px solid var(--rule)}
.tab-btn{background:none;border:none;border-bottom:3px solid transparent;
  font-family:var(--mono);font-size:12px;font-weight:700;letter-spacing:.1em;
  text-transform:uppercase;color:var(--dim);padding:10px 16px;cursor:pointer;margin-bottom:-2px}
.tab-btn:hover{color:var(--bright)}
.tab-btn.active{color:var(--cold);border-bottom-color:var(--cold)}
.tab-pane{display:none} .tab-pane.active{display:block}
.gauge{height:8px;background:var(--panel-2);border:1px solid var(--rule);
  border-radius:4px;overflow:hidden;min-width:120px}
.gauge i{display:block;height:100%;background:var(--cold)}
.gauge i.w{background:var(--warm)} .gauge i.h{background:var(--hot)} .gauge i.b{background:var(--burn)}
.spark{display:flex;align-items:flex-end;gap:2px;height:40px}
.spark i{flex:1;background:var(--cold);min-width:3px}
@media (max-width:900px){.hide-sm{display:none}}
''')
    h.append('</style></head><body><div class="wrap">')

    # header
    h.append('<header><h1>Grafana &rarr; CloudWatch query cost audit</h1>')
    h.append(f'<div class="sub">generated {_esc(audit["generated_at"])} &middot; '
             f'{summary["query_count"]} queries across {summary["dashboard_count"]} '
             f'dashboards &middot; {summary["workspace_count"]} workspaces</div></header>')

    # tab navigation
    h.append('<div class="tabs">'
             '<button class="tab-btn active" data-tab="queries">Query cost audit</button>'
             '<button class="tab-btn" data-tab="inventory">Inventory</button>'
             '<button class="tab-btn" data-tab="adhoc">Ad-hoc queries</button>'
             '<button class="tab-btn" data-tab="billing">Billing &amp; capacity</button>'
             '</div>')
    h.append('<div class="tab-pane active" id="tab-queries">')

    # meters
    h.append('<div class="meters">')
    h.append(f'<div class="meter"><div class="k">Estimated spend</div>'
             f'<div class="v">${summary["total_cost"]:,.0f}</div>'
             f'<div class="n">per month, all queries</div></div>')
    if summary.get('measure_available'):
        h.append(f'<div class="meter"><div class="k">Measured metric spend</div>'
                 f'<div class="v">${measured_metric_month:,.2f}</div>'
                 f'<div class="n">{gmd_calls:,} GetMetricData calls / {lookback:g}d, '
                 f'per month</div></div>')
        h.append(f'<div class="meter"><div class="k">Measured queries</div>'
                 f'<div class="v">{summary["measured_query_count"]}</div>'
                 f'<div class="n">runs seen in CloudTrail ({lookback:g}d)</div></div>')
    else:
        h.append(f'<div class="meter"><div class="k">Measured spend</div>'
                 f'<div class="v muted">n/a</div>'
                 f'<div class="n">CloudTrail lookup unavailable</div></div>')
    h.append(f'<div class="meter"><div class="k">Concentration</div>'
             f'<div class="v">{summary["concentration"]:.0f}%</div>'
             f'<div class="n">of spend in the top 10 queries</div></div>')
    h.append(f'<div class="meter"><div class="k">Always-on</div>'
             f'<div class="v">{summary["always_on"]}</div>'
             f'<div class="n">alert queries firing 24x7</div></div>')
    h.append(f'<div class="meter"><div class="k">Logs Insights</div>'
             f'<div class="v">{summary["logs_count"]}</div>'
             f'<div class="n">queries billed per GB scanned</div></div>')
    h.append('</div>')

    # caveat
    h.append('<div class="caveat"><b>Read this before quoting a number.</b> '
             'Bars labelled <b>measured (real bytes)</b> use actual bytes scanned + run '
             'counts from the Logs Insights query history — those are billing-accurate. '
             '<b>measured (runs)</b> means run count is real but bytes are still estimated. '
             '<b>estimated</b> (hatched) means no execution was observed, so runs assume '
             f'{cfg["viewing_hours_per_day"]:g} viewing-hours/day and bytes come from '
             'log-group ingestion x the window. Metric costs use measured GetMetricData '
             f'calls where available, else {cfg["metrics_per_call"]:g} metric(s)/call. '
             'Alert-rule queries run on their own interval regardless of viewers.</div>')

    # trend banner + trending table (only on trend days)
    if trends.get('is_trend_day'):
        tr_list = trends.get('trending', [])
        sev_str = ' + '.join(trends.get('severities', ['CRITICAL']))
        if tr_list:
            window_total = sum(t['window_cost'] for t in tr_list)
            h.append(f'<div class="trend"><b>&#128293; Trend alert.</b> '
                     f'{len(tr_list)} quer{"y" if len(tr_list)==1 else "ies"} '
                     f'({_esc(sev_str)}) persisted on {trends["min_days"]}+ of the last '
                     f'{trends["window_days"]} days, generating ~<b>${window_total:,.2f}</b> '
                     f'in estimated cost over the window. These are recurring offenders, '
                     f'not one-off spikes.</div>')
            # dedicated trending table with window cost + quota impact
            h.append('<div class="section">Trending queries '
                     f'&middot; last {trends["window_days"]} days</div>')
            h.append('<table><thead><tr>'
                     '<th>Severity</th><th>Dashboard / panel</th><th>Engine</th>'
                     '<th class="num">Days</th><th class="num">Trend</th>'
                     '<th class="num">Cost in window</th><th class="num">Cost/day</th>'
                     '<th class="num">Cost/month</th><th class="num">Quota impact</th>'
                     '</tr></thead><tbody>')
            for t in tr_list:
                qk = t.get('quota_kind')
                qpct = t.get('quota_pct', 0.0)
                gcls = 'b' if qpct >= 40 else 'h' if qpct >= 20 else 'w' if qpct >= 5 else ''
                quota_cell = (
                    f'<div class="gauge"><i class="{gcls}" style="width:{min(qpct,100):.1f}%"></i></div>'
                    f'<div class="muted" style="font-size:10px">{qpct:.1f}% {_esc(qk or "")}</div>'
                    if qk else '<span class="muted">—</span>')
                arrow = '&#9650;' if t['direction'] == 'rising' else '&#9660;'
                h.append(
                    f'<tr class="crit trending">'
                    f'<td><span class="risk {t["worst_severity"]}">{t["worst_severity"]}</span></td>'
                    f'<td><div class="name">&#128293; {_esc(t["dashboard"])}</div>'
                    f'<div class="muted">{_esc(t["panel"])} &middot; {_esc(t["workspace_name"])}</div></td>'
                    f'<td>{_esc(t["engine"])}</td>'
                    f'<td class="num">{t["days"]}</td>'
                    f'<td class="num">{arrow} {_esc(t["direction"])}</td>'
                    f'<td class="num"><b>${t["window_cost"]:,.2f}</b></td>'
                    f'<td class="num">${t["cost_day"]:,.2f}</td>'
                    f'<td class="num">${t["cost_month"]:,.2f}</td>'
                    f'<td class="num">{quota_cell}</td>'
                    f'</tr>')
            h.append('</tbody></table>')
        else:
            h.append(f'<div class="trend"><b>Trend check ({trends["window_days"]}d):</b> '
                     f'no {_esc(sev_str)} query has persisted for {trends["min_days"]}+ days. '
                     f'Nothing trending.</div>')

    # critical section (always present)
    crit_rows = [r for r in rows if r['risk_level'] == 'CRITICAL']
    h.append('<div class="section">Critical queries today'
             f' &middot; {len(crit_rows)}</div>')
    if crit_rows:
        h.append(_table_head().replace('{tid}', 'tcrit'))
        for r in crit_rows:
            h.append(_row_html(r, max_cost, engine_tag, bar))
        h.append('</tbody></table>')
    else:
        h.append('<div class="caveat">No CRITICAL queries in this run.</div>')

    # controls + full table
    h.append('<div class="section">All analyzed queries</div>')
    h.append('<div class="controls">'
             '<input type="search" id="q" placeholder="filter by dashboard, panel, log group, namespace…">'
             '<select id="f"><option value="">all queries</option>'
             '<option value="logs_insights">Logs Insights only</option>'
             '<option value="metrics_insights">Metrics Insights only</option>'
             '<option value="metric_search">Metric search only</option>'
             '<option value="alert">alert rules only</option></select>'
             '<span class="muted">click a column heading to sort</span></div>')

    h.append(_table_head().replace('{tid}', 't'))
    for r in rows:
        h.append(_row_html(r, max_cost, engine_tag, bar))
    h.append('</tbody></table>')

    # warnings
    errs = []
    for acct in audit['accounts']:
        if acct.get('error'):
            errs.append(f"account {acct['account_id']}: {acct['error']}")
        for reg in acct.get('regions', []):
            for ws in reg.get('workspaces', []):
                if ws.get('error'):
                    errs.append(f"{acct['account_id']} / {reg['region']} / "
                                f"{ws['workspace_name']}: {ws['error']}")
    if errs:
        h.append('<div class="caveat"><b>Warnings.</b><ul class="why">')
        for e in errs:
            h.append(f'<li>{_esc(e)}</li>')
        h.append('</ul></div>')

    h.append('</div>')  # close #tab-queries

    # ---- Inventory tab ----
    h.append('<div class="tab-pane" id="tab-inventory">')
    h.extend(build_inventory_tab(audit, summary))
    h.append('</div>')

    # ---- Ad-hoc queries tab ----
    h.append('<div class="tab-pane" id="tab-adhoc">')
    h.extend(build_adhoc_tab(audit, cfg))
    h.append('</div>')

    # ---- Billing & capacity tab ----
    h.append('<div class="tab-pane" id="tab-billing">')
    h.extend(build_billing_tab(audit.get('billing'), cfg))
    h.append('</div>')  # close #tab-billing

    # footer
    h.append(
        f'<footer>Rates: ${cfg["logs_scan_price_per_gb"]:g}/GB scanned '
        f'(Logs Insights), ${cfg["metrics_price_per_1000"]:g}/1,000 metrics '
        f'(GetMetricData), {_esc(cfg["price_region_note"])}. The Billing tab shows '
        f'ACTUAL charges from AWS Cost Explorer. Estimated figures are projections, '
        f'not your bill.</footer>')

    # script (tabs + sort + filter)
    h.append('''<script>
document.querySelectorAll('.tab-btn').forEach(btn=>{
  btn.addEventListener('click',()=>{
    document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p=>p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-'+btn.dataset.tab).classList.add('active');
  });
});
const tbl=document.getElementById('t'), tb=tbl.tBodies[0];
const rows=[...tb.rows];
function apply(){
  const q=document.getElementById('q').value.toLowerCase();
  const f=document.getElementById('f').value;
  rows.forEach(r=>{
    const okQ=!q||r.dataset.search.includes(q);
    const okF=!f||r.dataset.engine===f||r.dataset.origin===f;
    r.style.display=(okQ&&okF)?'':'none';
  });
}
document.getElementById('q').addEventListener('input',apply);
document.getElementById('f').addEventListener('change',apply);
[...tbl.tHead.rows[0].cells].forEach((th,i)=>{
  th.addEventListener('click',()=>{
    const dir=th.dataset.dir==='asc'?-1:1; th.dataset.dir=dir===1?'asc':'desc';
    const key=th.dataset.sort;
    rows.sort((a,b)=>{
      const av=key?parseFloat(a.dataset[key]||0):a.cells[i].innerText;
      const bv=key?parseFloat(b.dataset[key]||0):b.cells[i].innerText;
      return (av<bv?-1:av>bv?1:0)*dir;
    });
    rows.forEach(r=>tb.appendChild(r));
  });
});
</script></body></html>''')
    return '\n'.join(h)


def build_inventory_tab(audit, summary):
    """
    Full inventory: every dashboard with its panels and the queries each panel
    runs (refresh / window / runs/day), plus rollup counts.
    """
    h = []

    # Build dashboard -> panels -> queries structure from findings.
    # findings already carry dashboard/panel/query/refresh/window/runs.
    dash_map = {}  # (workspace, account, dashboard_uid|title) -> {meta, panels{}}
    for acct in audit['accounts']:
        for reg in acct.get('regions', []):
            for ws in reg.get('workspaces', []):
                for d in ws.get('dashboards', []):
                    dkey = (ws['workspace_name'], acct['account_id'], d['uid'] or d['title'])
                    entry = dash_map.setdefault(dkey, {
                        'title': d['title'], 'folder': d['folder'],
                        'workspace': ws['workspace_name'], 'account': acct['account_id'],
                        'refresh': d['refresh_seconds'], 'window': d['range_seconds'],
                        'panels': {}})
                    for f in d.get('findings', []):
                        p = entry['panels'].setdefault(f['panel'], [])
                        p.append(f)

    # rollup meters
    total_dashboards = len(dash_map)
    total_panels = sum(len(v['panels']) for v in dash_map.values())
    total_queries = sum(len(q) for v in dash_map.values() for q in v['panels'].values())
    h.append('<div class="caveat"><b>Inventory.</b> Every dashboard, its panels, and '
             'the queries each panel runs, with refresh, window, and estimated runs/day. '
             'Use this to see how many dashboards/panels/queries exist and how hard each '
             'runs.</div>')
    h.append('<div class="meters">')
    h.append(f'<div class="meter"><div class="k">Dashboards</div>'
             f'<div class="v">{total_dashboards}</div><div class="n">with query panels</div></div>')
    h.append(f'<div class="meter"><div class="k">Panels</div>'
             f'<div class="v">{total_panels}</div><div class="n">across all dashboards</div></div>')
    h.append(f'<div class="meter"><div class="k">Queries</div>'
             f'<div class="v">{total_queries}</div><div class="n">total targets</div></div>')
    h.append(f'<div class="meter"><div class="k">Workspaces</div>'
             f'<div class="v">{summary["workspace_count"]}</div><div class="n">scanned</div></div>')
    h.append('</div>')

    # per-dashboard tables
    for dkey, d in sorted(dash_map.items(), key=lambda kv: (-len(kv[1]['panels']),)):
        h.append(f'<div class="section">{_esc(d["title"])} '
                 f'&middot; {len(d["panels"])} panels &middot; '
                 f'{sum(len(q) for q in d["panels"].values())} queries</div>')
        h.append(f'<div class="muted" style="margin:-4px 0 8px">'
                 f'{_esc(d["folder"])} &middot; {_esc(d["workspace"])} &middot; '
                 f'refresh {human_refresh(d["refresh"])} &middot; '
                 f'window {human_window(d["window"])}</div>')
        h.append('<table><thead><tr><th>Panel</th><th>Ref</th><th>Engine</th>'
                 '<th class="num">Refresh</th><th class="num">Window</th>'
                 '<th class="num">Runs/day</th><th>Target / query</th>'
                 '</tr></thead><tbody>')
        for panel, queries in d['panels'].items():
            for f in queries:
                h.append(
                    f'<tr><td class="name">{_esc(panel)}</td>'
                    f'<td class="muted">{_esc(f["ref_id"])}</td>'
                    f'<td>{_esc(f["engine"])}</td>'
                    f'<td class="num">{human_refresh(f["refresh_seconds"])}</td>'
                    f'<td class="num">{human_window(f["range_seconds"])}</td>'
                    f'<td class="num">{f["runs_per_day"]:,.0f}</td>'
                    f'<td class="muted">{_esc(f["target_label"])}'
                    f'<details><summary>query</summary><pre>{_esc(f["query"] or "(none)")}</pre>'
                    f'</details></td></tr>')
        h.append('</tbody></table>')

    if not dash_map:
        h.append('<div class="caveat">No dashboards with queries found.</div>')
    return h


def build_adhoc_tab(audit, cfg):
    """
    Ad-hoc queries: Logs Insights executions that did not map to any dashboard
    panel or alert rule, with who ran them, data scanned, and cost.
    """
    h = []
    # gather across all accounts/regions
    all_adhoc = []
    any_measure = False
    for acct in audit['accounts']:
        for reg in acct.get('regions', []):
            if reg.get('measure_available'):
                any_measure = True
            for a in reg.get('adhoc', []) or []:
                a = dict(a)
                a['account_id'] = acct['account_id']
                a['region'] = reg['region']
                all_adhoc.append(a)

    if not any_measure:
        h.append('<div class="caveat"><b>Ad-hoc queries.</b> Requires measured '
                 'execution data (Logs Insights query history / CloudTrail). None was '
                 'available this run, so ad-hoc activity cannot be shown.</div>')
        return h

    all_adhoc.sort(key=lambda a: (a['cost'], a['runs']), reverse=True)
    total_cost = sum(a['cost'] for a in all_adhoc)
    total_runs = sum(a['runs'] for a in all_adhoc)
    total_bytes = sum(a['bytes_total'] for a in all_adhoc)

    h.append('<div class="caveat"><b>Ad-hoc queries.</b> Logs Insights runs that did '
             'NOT come from a dashboard panel or alert rule — i.e. run directly by a '
             'person or tool (console, SDK, CLI). Cost uses real bytes scanned from '
             'query history where available.</div>')
    h.append('<div class="meters">')
    h.append(f'<div class="meter"><div class="k">Ad-hoc queries</div>'
             f'<div class="v">{len(all_adhoc)}</div><div class="n">distinct, in window</div></div>')
    h.append(f'<div class="meter"><div class="k">Ad-hoc runs</div>'
             f'<div class="v">{total_runs:,}</div><div class="n">executions seen</div></div>')
    h.append(f'<div class="meter"><div class="k">Data scanned</div>'
             f'<div class="v">{human_bytes(total_bytes)}</div><div class="n">by ad-hoc runs</div></div>')
    h.append(f'<div class="meter"><div class="k">Ad-hoc cost</div>'
             f'<div class="v">${total_cost:,.2f}</div><div class="n">over the window</div></div>')
    h.append('</div>')

    if not all_adhoc:
        h.append('<div class="caveat">No ad-hoc queries detected — all measured '
                 'executions mapped to dashboard panels or alerts.</div>')
        return h

    # ---- per-user rollup ----
    # Attribute each ad-hoc query's runs / bytes / cost to its users in
    # proportion to how many of that query's runs each user is credited with.
    user_agg = defaultdict(lambda: {'runs': 0, 'bytes': 0.0, 'cost': 0.0, 'queries': 0})
    for a in all_adhoc:
        users = a.get('users') or []
        total_user_runs = sum(n for _, n in users)
        if total_user_runs > 0:
            for u, n in users:
                share = n / total_user_runs
                ua = user_agg[u]
                ua['runs'] += n
                ua['bytes'] += a['bytes_total'] * share
                ua['cost'] += a['cost'] * share
                ua['queries'] += 1
        else:
            ua = user_agg['unknown']
            ua['runs'] += a['runs']
            ua['bytes'] += a['bytes_total']
            ua['cost'] += a['cost']
            ua['queries'] += 1

    ranked_users = sorted(user_agg.items(), key=lambda kv: kv[1]['cost'], reverse=True)
    max_user_cost = max((u['cost'] for _, u in ranked_users), default=0.0)

    h.append('<div class="section">Ad-hoc spend by user</div>')
    h.append('<table><thead><tr><th>Who</th><th class="num">Distinct queries</th>'
             '<th class="num">Runs</th><th class="num">Data scanned</th>'
             '<th class="num">Cost</th><th>Share of ad-hoc cost</th>'
             '</tr></thead><tbody>')
    for user, u in ranked_users:
        pct = (u['cost'] / max_user_cost * 100.0) if max_user_cost > 0 else 0.0
        pct = max(pct, 1.0) if u['cost'] > 0 else 0.0
        gcls = 'b' if u['cost'] >= 0.4 * total_cost else 'h' if u['cost'] >= 0.2 * total_cost else 'w' if u['cost'] >= 0.05 * total_cost else ''
        h.append(
            f'<tr><td class="name">{_esc(user)}</td>'
            f'<td class="num">{u["queries"]:,}</td>'
            f'<td class="num">{u["runs"]:,}</td>'
            f'<td class="num">{human_bytes(u["bytes"])}</td>'
            f'<td class="num"><b>${u["cost"]:,.2f}</b></td>'
            f'<td><div class="bar {gcls}"><i style="width:{pct:.1f}%"></i></div></td>'
            f'</tr>')
    h.append('</tbody></table>')

    h.append('<div class="section">Ad-hoc query detail</div>')
    h.append('<table><thead><tr><th>Who ran it</th><th class="num">Runs</th>'
             '<th class="num">Data scanned</th><th class="num">Scan/run</th>'
             '<th class="num">Cost</th><th>Query</th></tr></thead><tbody>')
    for a in all_adhoc:
        users = ', '.join(f'{_esc(u)} ({n})' for u, n in a['users']) or '<span class="muted">unknown</span>'
        bmark = '' if a['bytes_measured'] else ' <span class="muted">(est)</span>'
        h.append(
            f'<tr><td class="name">{users}</td>'
            f'<td class="num">{a["runs"]:,}</td>'
            f'<td class="num">{human_bytes(a["bytes_total"])}{bmark}</td>'
            f'<td class="num">{human_bytes(a["bytes_per_run"])}</td>'
            f'<td class="num"><b>${a["cost"]:,.2f}</b></td>'
            f'<td class="muted"><div>{_esc(a["region"])} &middot; {_esc(a["account_id"])}</div>'
            f'<details><summary>query</summary><pre>{_esc(a["query"])}</pre></details></td>'
            f'</tr>')
    h.append('</tbody></table>')
    return h


def build_billing_tab(billing, cfg):
    """Render the actual-billing + CloudWatch capacity tab."""
    h = []
    if not billing or not billing.get('enabled'):
        h.append('<div class="caveat">Billing tab disabled '
                 '(set BILLING_ENABLED / CAPACITY_ENABLED).</div>')
        return h

    h.append('<div class="caveat"><b>This tab is your ACTUAL spend.</b> Figures '
             'come from AWS Cost Explorer (real charges), unlike the estimated '
             'projections on the Query tab. "This month" is month-to-date; '
             '"last month" is the previous full billing month.</div>')

    for acct in billing.get('accounts', []):
        h.append(f'<div class="section">Account {_esc(acct["account_id"])}</div>')
        if acct.get('error'):
            h.append(f'<div class="caveat"><b>Billing warning.</b> {_esc(acct["error"])}</div>')

        # spend meters
        h.append('<div class="meters">')
        h.append(f'<div class="meter"><div class="k">CloudWatch this month</div>'
                 f'<div class="v">${acct.get("this_month_total", 0):,.2f}</div>'
                 f'<div class="n">{_esc(acct.get("period_this", "month-to-date"))}</div></div>')
        h.append(f'<div class="meter"><div class="k">CloudWatch last month</div>'
                 f'<div class="v">${acct.get("last_month_total", 0):,.2f}</div>'
                 f'<div class="n">{_esc(acct.get("period_last", "previous month"))}</div></div>')
        # daily sparkline
        daily = acct.get('daily') or []
        if daily:
            mx = max((c for _, c in daily), default=0.0) or 1.0
            bars = ''.join(
                f'<i style="height:{max(2, c/mx*100):.0f}%" title="{_esc(d)}: ${c:,.2f}"></i>'
                for d, c in daily)
            last_day = daily[-1]
            h.append(f'<div class="meter"><div class="k">Daily trend (this month)</div>'
                     f'<div class="spark">{bars}</div>'
                     f'<div class="n">latest {_esc(last_day[0])}: ${last_day[1]:,.2f}</div></div>')
        h.append('</div>')

        # component breakdown table
        comp = acct.get('this_month') or {}
        comp_last = acct.get('last_month') or {}
        if comp:
            h.append('<div class="section">Spend by CloudWatch component</div>')
            h.append('<table><thead><tr><th>Component</th>'
                     '<th class="num">This month</th><th class="num">Last month</th>'
                     '<th class="num">Share</th><th>This month</th></tr></thead><tbody>')
            total = acct.get('this_month_total', 0) or 1.0
            for name, cost in sorted(comp.items(), key=lambda kv: kv[1], reverse=True):
                share = cost / total * 100.0
                gcls = 'b' if share >= 40 else 'h' if share >= 20 else 'w' if share >= 5 else ''
                last_c = comp_last.get(name, 0.0)
                h.append(
                    f'<tr><td class="name">{_esc(name)}</td>'
                    f'<td class="num">${cost:,.2f}</td>'
                    f'<td class="num muted">${last_c:,.2f}</td>'
                    f'<td class="num">{share:.1f}%</td>'
                    f'<td><div class="gauge"><i class="{gcls}" style="width:{share:.1f}%"></i></div></td>'
                    f'</tr>')
            h.append('</tbody></table>')

        # capacity table
        cap = acct.get('capacity') or []
        if cap:
            h.append('<div class="section">CloudWatch capacity &amp; storage by region</div>')
            h.append('<table><thead><tr><th>Region</th>'
                     '<th class="num">Alarms</th><th class="num">Dashboards</th>'
                     '<th class="num">Log groups</th><th class="num">Log storage</th>'
                     '<th class="num">Ingestion (24h)</th></tr></thead><tbody>')
            for c in cap:
                if c.get('error'):
                    h.append(f'<tr><td class="name">{_esc(c["region"])}</td>'
                             f'<td colspan="5" class="muted">{_esc(c["error"])}</td></tr>')
                    continue
                h.append(
                    f'<tr><td class="name">{_esc(c["region"])}</td>'
                    f'<td class="num">{c.get("alarms", 0):,}</td>'
                    f'<td class="num">{c.get("dashboards", 0):,}</td>'
                    f'<td class="num">{c.get("log_groups", 0):,}</td>'
                    f'<td class="num">{human_bytes(c.get("storage_bytes", 0))}</td>'
                    f'<td class="num">{human_bytes(c.get("ingest_bytes_24h", 0))}</td>'
                    f'</tr>')
            h.append('</tbody></table>')

    return h


def build_sns_text(audit, summary, s3_uri, trends=None):
    rows = sorted(summary['rows'], key=lambda r: r['cost_month'], reverse=True)
    crit_rows = [r for r in rows if r['risk_level'] == 'CRITICAL']
    lines = [
        "Grafana Query Cost Audit",
        f"Generated: {audit['generated_at']}",
        "",
        f"Workspaces scanned : {summary['workspace_count']}",
        f"Dashboards scanned : {summary['dashboard_count']}",
        f"Queries analyzed   : {summary['query_count']}",
        f"CRITICAL queries   : {len(crit_rows)}",
        f"Estimated spend    : ${summary['total_cost']:,.2f}/month (all queries)",
        f"Top-10 concentration: {summary['concentration']:.0f}%",
        f"Logs Insights qs   : {summary['logs_count']}",
        f"Always-on alerts   : {summary['always_on']}",
        (f"Measured queries   : {summary['measured_query_count']} "
         f"(runs seen in CloudTrail, {summary.get('measure_lookback_days') or '?'}d)"
         if summary.get('measure_available')
         else "Measured queries   : n/a (CloudTrail lookup unavailable)"),
        f"GetMetricData calls: {summary['measured_getmetricdata_calls']:,} in lookback window",
    ]

    # Trending section (trend days only)
    if trends and trends.get('is_trend_day'):
        tr = trends.get('trending', [])
        lines.append("")
        if tr:
            sev_str = ' + '.join(trends.get('severities', ['CRITICAL']))
            window_total = sum(t['window_cost'] for t in tr)
            lines.append(f"*** TRENDING {sev_str} (persisted {trends['min_days']}+ of "
                         f"last {trends['window_days']} days) ***")
            lines.append(f"    ~${window_total:,.2f} estimated cost generated over the window")
            for t in tr:
                q = f" quota {t['quota_pct']:.0f}%" if t.get('quota_kind') else ""
                lines.append(
                    f"  [{t['worst_severity']:<8}] {t['days']}d {t['direction']:>6}  "
                    f"win ${t['window_cost']:>11,.2f}  mo ${t['cost_month']:>11,.2f}{q}  "
                    f"{t['workspace_name']} / {t['dashboard']} / {t['panel']}")
        else:
            sev_str = ' + '.join(trends.get('severities', ['CRITICAL']))
            lines.append(f"Trend check: no {sev_str} query persisted "
                         f"{trends['min_days']}+ of last {trends['window_days']} days.")

    lines.append("")
    lines.append("Top cost drivers:")
    for r in rows[:10]:
        tag = 'measured' if r.get('measured') else 'estimated'
        fire = ' [TRENDING]' if r.get('trending') else ''
        lines.append(
            f"  ${r['cost_month']:>12,.2f}/mo  [{r['engine']}/{tag}]{fire} "
            f"{r['workspace_name']} / {r['dashboard']} / {r['panel']} "
            f"(refresh {human_refresh(r['refresh_seconds'])}, window {human_window(r['range_seconds'])})")
    if s3_uri:
        lines.append("")
        lines.append(f"Full HTML report: {s3_uri}")
    lines.append("")
    lines.append("NOTE: 'measured' rows use real run counts / bytes; 'estimated' rows "
                 "are projections, not reconciled to your bill.")
    return "\n".join(lines)


# ============================================================
# Delivery: S3 + SNS
# ============================================================
def upload_to_s3(cfg, html):
    if not cfg['s3_bucket']:
        logger.info("S3_BUCKET not set; skipping S3 upload.")
        return None
    key = (cfg['s3_prefix'].rstrip('/') + '/'
           + datetime.now(timezone.utc).strftime(
               '%Y/%m/%d/grafana-query-audit-%Y%m%dT%H%M%SZ.html'))
    params = dict(
        Bucket=cfg['s3_bucket'], Key=key, Body=html.encode('utf-8'),
        ContentType='text/html; charset=utf-8')
    # Add server-side encryption if the bucket policy requires it.
    if cfg.get('s3_sse'):
        params['ServerSideEncryption'] = cfg['s3_sse']
        if cfg['s3_sse'] == 'aws:kms' and cfg.get('s3_sse_kms_key_id'):
            params['SSEKMSKeyId'] = cfg['s3_sse_kms_key_id']
    aws_client(boto3.Session(), 's3').put_object(**params)
    uri = f"s3://{cfg['s3_bucket']}/{key}"
    logger.info("Uploaded report to %s", uri)
    return uri


def publish_to_sns(cfg, subject, message):
    if not cfg['sns_topic_arn']:
        logger.info("SNS_TOPIC_ARN not set; skipping SNS publish.")
        return
    aws_client(boto3.Session(), 'sns').publish(
        TopicArn=cfg['sns_topic_arn'], Subject=subject[:100], Message=message)
    logger.info("Published report summary to SNS.")


# ============================================================
# Lambda entry point
# ============================================================
def lambda_handler(event, context):
    cfg = load_config()
    run_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    n_accts = len(cfg['accounts'])
    auth_mode = ('env-var token' if cfg.get('grafana_token_direct')
                 else 'secrets-manager token' if cfg.get('grafana_token_secret')
                 else 'temp service account')
    logger.info("Grafana audit starting: %d account-config(s), regions=%s, auth=%s, "
                "billing=%s, measure_history=%s",
                n_accts, [a.get('regions') for a in cfg['accounts']], auth_mode,
                cfg['billing_enabled'], cfg['measure_logs_history'])

    audit = run_audit(cfg)
    summary = summarize(audit)

    # Trend detection + rogue-cost accumulation (read history) BEFORE saving today.
    compute_rogue_cost(cfg, summary, run_date)
    trends = compute_trends(cfg, summary, run_date)
    # Persist today's snapshot (tracked severities) for future trend runs.
    save_snapshot(cfg, build_snapshot(summary, run_date, cfg))

    html = build_html(audit, summary, cfg, trends)
    s3_uri = upload_to_s3(cfg, html)

    crit_count = sum(1 for r in summary['rows'] if r['risk_level'] == 'CRITICAL')
    subject = (f"Grafana Query Cost Audit {run_date} - {crit_count} critical, "
               f"${summary['total_cost']:,.0f}/mo modelled")
    publish_to_sns(cfg, subject, build_sns_text(audit, summary, s3_uri, trends))
    return {
        'statusCode': 200,
        'run_date': run_date,
        'modelled_monthly_cost': round(summary['total_cost'], 2),
        'critical_queries': crit_count,
        'workspaces': summary['workspace_count'],
        'dashboards': summary['dashboard_count'],
        'queries': summary['query_count'],
        'logs_insights_queries': summary['logs_count'],
        'always_on_alerts': summary['always_on'],
        'measured_queries': summary['measured_query_count'],
        'measured_getmetricdata_calls': summary['measured_getmetricdata_calls'],
        'is_trend_day': trends['is_trend_day'],
        'trending_queries': len(trends['trending']),
        's3_uri': s3_uri,
    }


# ============================================================
# Run locally for testing
# ============================================================
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Grafana Query Cost Audit')
    parser.add_argument('--region', default=None, help='AWS region to scan')
    parser.add_argument('--profile', default=None, help='AWS CLI profile name')
    parser.add_argument('--out', default='grafana-query-audit.html', help='Local HTML output path')
    args = parser.parse_args()

    if args.profile:
        boto3.setup_default_session(profile_name=args.profile)
    if args.region:
        os.environ['REGIONS'] = args.region

    cfg = load_config()
    run_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    audit = run_audit(cfg)
    summary = summarize(audit)
    compute_rogue_cost(cfg, summary, run_date)
    trends = compute_trends(cfg, summary, run_date)
    save_snapshot(cfg, build_snapshot(summary, run_date, cfg))
    html = build_html(audit, summary, cfg, trends)
    if cfg['s3_bucket']:
        print(upload_to_s3(cfg, html))
    else:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"Wrote {args.out}")
    print(build_sns_text(audit, summary, None, trends))
