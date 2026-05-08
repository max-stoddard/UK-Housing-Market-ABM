# Recommended AWS Setup
Author: Max Stoddard

Last updated: 2026-05-08

## Credential Note
This setup assumes AWS CLI v2 is authenticated with `aws login --remote` using the account's AWS Management Console session credentials. Do not enable IAM Identity Center, run `aws configure sso`, or switch this account to an SSO-based CLI setup during the starter-credit phase, because the current account must preserve access to its free account credits.

## How Agents Execute This Plan
This document is organized into numbered execution phases. Each phase is intended to be small enough for a future agent to execute from a prompt like:

```text
execute phase <n> of docs/cloud/recommended-aws-setup.md
```

The numbered phases are authoritative. The later "Supporting Reference" sections preserve the detailed AWS setup guidance for agents to consult while executing those phases.

Every phase must optimize for security, minimum cost, and fail-safe recovery before convenience:

- use least-privilege IAM and minimal network exposure
- avoid private-data, generated-output, environment-file, and git-metadata leaks
- avoid unnecessary always-on resources and all prohibited v1 resources
- work only from the dedicated AWS rollout worktree created in Phase 1
- verify explicit acceptance gates before moving on
- stop or roll back if cost, security, or validation checks fail
- update `docs/cloud/aws-execution-notes.md` with complete operational details before the next phase

At every phase, use as many GPT-5.5 xhigh subagents as are practical for independent read-only inspection, verification, log review, and checklist auditing so the main agent context stays small. Give each subagent a narrow task, require concise findings, and keep every subagent within the Phase 1 AWS rollout worktree and this repository's privacy rules.

Do not write secrets, passwords, AWS access keys, session tokens, or private dataset contents into docs.

## Purpose
This document defines a first AWS deployment target for the UK Housing Model dashboard and remote experiment workflow.

The goal is to move off Render with the smallest useful AWS footprint that does not compromise model reproducibility:

- static frontend hosted from S3 through CloudFront
- lightweight dashboard API hosted on standard ECS/Fargate behind an ALB
- experiment artifacts stored in S3 as private archive/evidence storage
- one manually started EC2 experiment runner, stopped by default

This setup does not change Java model logic or calibration behavior. It can improve the model workflow by separating always-on dashboard/API hosting from expensive experiment compute, but only if remote runs include strict run metadata, output hashes, and cost controls.

## Current Recommendation
Use `eu-west-2` (London) unless there is a specific cost or quota reason not to.

For a new AWS account, use standard ECS/Fargate with an ALB for the API. This is the numbered-phase primary path because it is easier to validate, secure, and cost-check in this repository. AWS App Runner is no longer a safe primary recommendation for new accounts: AWS documentation states that App Runner closes to new customers starting 2026-04-30, while existing App Runner customers can continue using it. ECS Express Mode remains a supporting-reference option only unless a future plan adds the required ECS infrastructure role and `create-express-gateway-service` workflow.

Recommended v1 architecture:

```text
CloudFront default domain
  -> CloudFront distribution
       -> private S3 frontend bucket
       -> optional /api/* behavior to ECS/ALB API origin

Standard ECS/Fargate + ALB
  -> ECR image built from dashboard/Dockerfile.api
  -> dashboard API with model execution disabled

S3 artifacts bucket
  -> private remote-run archives, logs, manifests, output hashes

EC2 experiment runner
  -> stopped by default
  -> started only for remote runs
  -> accessed through Systems Manager Session Manager
  -> syncs current-run outputs and manifest to S3
```

Do not run model experiments inside the public API service. The current dashboard deployment is already designed this way: production API runtime keeps model execution disabled unless explicitly configured, and the existing API Docker image is intended to exclude Java, Maven, git, private datasets, and baseline `Results/` outputs.

## Starter Budget And Domains
Create AWS Budgets before creating compute. Verify all prices in AWS Pricing Calculator before provisioning, because AWS pricing and free-tier credit rules can change.

Current starter-cost assumptions checked on 2026-05-07:

| Item | Current London assumption | Starter impact |
| --- | --- | --- |
| EC2 `c7i.8xlarge` | about 1.6968 USD/hour | 20 hours is about 33.94 USD |
| EBS gp3 root volume | about 0.0928 USD/GB-month | 200 GiB is about 18.56 USD/month while the instance exists |
| ECS Fargate API task | 0.5 vCPU / 1 GB runs continuously if min task count is 1 | small but fixed monthly cost |
| Application Load Balancer | billed while running plus LCU usage | meaningful fixed monthly cost even at tiny traffic |
| ECS/Fargate + ALB combined | roughly 40+ USD/month at tiny traffic before EC2, EBS, S3, logs, and DNS | the main fixed-cost risk |
| S3 + CloudFront | usually low at small traffic | depends on artifact volume, requests, and data transfer |
| Route 53 hosted zone | 0.50 USD/month for the first 25 hosted zones | small fixed cost if using Route 53 DNS |

If usage is well under 20 EC2 hours/month, the biggest starter-credit risk is not the experiment runner. It is fixed always-on infrastructure: the API service, ALB, EBS, logs, DNS, and retained artifacts.

Starter defaults for a 100 USD credit:

- Use a 50-100 GiB gp3 root volume first; resize only after runs prove they need more.
- Do not allocate an Elastic IP for the runner.
- Add automatic runner stop controls before the first long run.
- Alert before 20 EC2 running hours/month, not only after.
- Keep S3 lifecycle rules aggressive for temporary and manual run outputs.
- Start with CloudFront's default domain during the credit-constrained phase.
- Add a custom domain only if public presentation needs it.

There is no free AWS-registered custom domain. You can use AWS-provided service hostnames without buying a domain, for example CloudFront `*.cloudfront.net` for the frontend and, for grandfathered App Runner accounts only, App Runner `*.awsapprunner.com` for the API. A human-friendly custom domain requires a domain you already own or a new registration. Route 53 domain registration is billed annually by TLD, Route 53 hosted zones are billed monthly, and AWS credits cannot be used to pay the fee for registering a new domain with Route 53.

Recommended alerts:

| Budget | Thresholds |
| --- | --- |
| Monthly actual cost | 25 USD, 50 USD, 80 USD, 95 USD |
| Monthly forecasted cost | 50 USD, 80 USD |
| EC2 running hours | alert at 5, 10, 15, and 20 hours/month during starter phase |

Avoid in v1:

- NAT Gateway
- RDS
- Elastic IPs unless a concrete requirement appears
- public S3 buckets
- always-on experiment compute
- running experiments inside the public API service

## AWS Resources
Use these names unless a global AWS name conflict requires adding the account ID suffix.

| Resource | Name | Purpose |
| --- | --- | --- |
| Region | `eu-west-2` | UK-local default region |
| ECR repository | `uk-housing-market-abm-api` | stores the dashboard API image |
| ECS cluster | `uk-housing-market-abm-prod` | API runtime cluster |
| ECS service | `uk-housing-market-abm-api-prod` | always-on lightweight API |
| ALB | `uk-housing-market-abm-api-prod` | API load balancer for ECS/Fargate |
| S3 frontend bucket | `uk-housing-market-abm-web-prod-<account-id>` | private built frontend assets |
| S3 artifacts bucket | `uk-housing-market-abm-artifacts-prod-<account-id>` | remote run outputs, logs, manifests, result bundles |
| CloudFront distribution | `uk-housing-market-abm-web-prod` | public HTTPS frontend |
| EC2 smoke runner | `uk-housing-market-abm-runner-c7i-xlarge` | smaller manually started runner for bootstrap and smoke validation |
| EC2 high-core runner | `uk-housing-market-abm-runner-c7i8xlarge` | later runner only when high-core sharded sweeps need it |
| IAM role for EC2 | `uk-housing-market-abm-runner-role` | Session Manager plus scoped S3 access |
| IAM role for ECS task execution | `uk-housing-market-abm-ecs-task-execution-role` | pulls ECR image and writes task logs |
| AWS Budget | `uk-housing-market-abm-monthly-credit-burn-guardrail` | alerts before starter-credit burn exceeds guardrails |

Required tags for all taggable resources:

```text
Project=uk-housing-market-abm
Environment=prod
Owner=MaxStoddard
ManagedBy=manual-v1
```

## Phase 1: Repo And Notes Setup
Goal: verify repo deployment hygiene and create the durable execution notes before touching AWS.

Prerequisites:

- Start from the repository root in the main checkout only long enough to create or verify the dedicated AWS rollout worktree.
- Do not read `agents/`.
- Do not read CSV contents under `private-datasets/`.

Execute:

```bash
git status --short
git worktree list

export AWS_ROLLOUT_BRANCH="${AWS_ROLLOUT_BRANCH:-aws/manual-v1-rollout}"
export AWS_ROLLOUT_WORKTREE="${AWS_ROLLOUT_WORKTREE:-../uk-housing-model-individual-project-aws-rollout}"

# Create this once. If it already exists, verify it points at the intended branch and reuse it.
if [ ! -e "$AWS_ROLLOUT_WORKTREE/.git" ]; then
  if git show-ref --verify --quiet "refs/heads/$AWS_ROLLOUT_BRANCH"; then
    git worktree add "$AWS_ROLLOUT_WORKTREE" "$AWS_ROLLOUT_BRANCH"
  else
    git worktree add -b "$AWS_ROLLOUT_BRANCH" "$AWS_ROLLOUT_WORKTREE"
  fi
fi
cd "$AWS_ROLLOUT_WORKTREE"
test "$(git branch --show-current)" = "$AWS_ROLLOUT_BRANCH"
git status --short

sed -n '1,220p' .dockerignore
sed -n '1,220p' dashboard/Dockerfile.api
sed -n '1,120p' dashboard/package.json
sed -n '1,40p' dashboard/.nvmrc
sed -n '1,120p' pom.xml
```

Run local checks when local dependencies are already installed:

```bash
cd dashboard
npm run lint
npm run build
npm run test:smoke
cd ..
docker build --platform linux/amd64 -f dashboard/Dockerfile.api -t uk-housing-model-dashboard-api:local-check .
```

If dependencies are missing, record that Phase 9 will verify them on the runner. Do not install unnecessary local tooling only for this phase.

Worktree rule:

- All AWS rollout planning, documentation edits, scripts, command output review, validation, and cloud execution after this point must happen from `$AWS_ROLLOUT_WORKTREE`.
- Agents may assume they are not alone in the main repository checkout, but they should be alone in the AWS rollout worktree.
- Do not edit or run AWS rollout commands from the main checkout after the worktree exists.
- Do not merge the rollout worktree branch back into the main checkout until every executed phase is complete, validated, documented in `docs/cloud/aws-execution-notes.md`, and reviewed for cost, security, and model-workflow regressions.

Subagent rule:

- At every phase, delegate independent context-heavy checks to GPT-5.5 xhigh subagents when available, including AWS documentation checks, command review, IAM/security review, budget/cost review, Docker hygiene review, CloudFront/API routing review, and notes consistency checks.
- Keep subagents bounded to read-only inspection or explicitly assigned implementation work inside `$AWS_ROLLOUT_WORKTREE`.
- Require each subagent to return only findings, evidence, and recommended changes needed for the phase acceptance gate.
- Do not pass secrets, AWS tokens, private dataset contents, or broad repository-reading assignments to subagents.

Acceptance gate:

- `docs/cloud/aws-execution-notes.md` exists and has a Phase 1 entry.
- Dedicated AWS rollout worktree exists, the current shell is inside it, and notes record the worktree path and branch.
- `.dockerignore` excludes private, generated, local dependency, local env, git, and operational agent material.
- `dashboard/Dockerfile.api` still builds only the lightweight API/runtime surface plus `input-data-versions/`.
- Node 22 and Java 25 requirements are recorded.
- No Java model, calibration, or input-data behavior changed.

Cost check:

- No AWS resources are created.

Security check:

- Confirm no private datasets, generated `Results/`, env files, git metadata, or operational notes can enter the API build context or image.

Rollback/stop condition:

- If Docker hygiene is unsafe, stop before Phase 2 and fix the repo hygiene first.

## Phase 2: AWS CLI Login And Shell Usability
Goal: make AWS usable from the command line without switching the account to SSO.

Prerequisites:

- Phase 1 accepted.
- AWS console access is available for the target account.

Execute:

```bash
aws --version
aws login --remote
export AWS_REGION=eu-west-2
export AWS_PAGER=
aws configure set region "$AWS_REGION"
aws sts get-caller-identity
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
printf 'ACCOUNT_ID=%s\nAWS_REGION=%s\n' "$ACCOUNT_ID" "$AWS_REGION"
docker --version
```

Verify ECR login readiness without creating resources:

```bash
aws ecr get-login-password --region "$AWS_REGION" >/dev/null
```

Acceptance gate:

- AWS CLI v2 works.
- `aws sts get-caller-identity` succeeds for the intended account.
- `AWS_REGION=eu-west-2` is set.
- ECR login password retrieval succeeds.
- Notes record account ID, region, and CLI version without secrets.

Cost check:

- No AWS resources are created.

Security check:

- Do not write AWS credentials, login tokens, or command output containing secrets into docs.
- Confirm no `aws configure sso` or IAM Identity Center setup was used.

Rollback/stop condition:

- If `aws sts get-caller-identity` does not show the intended account, stop and do not create resources.

## Phase 3: Cost And Safety Guardrails Before Compute
Goal: create cost alarms and record forbidden-resource checks before provisioning paid compute.

Prerequisites:

- Phase 2 accepted.
- Set the alert recipient outside the repo:

```bash
export BUDGET_EMAIL='<cost-alert-email>'
test -n "$BUDGET_EMAIL"
```

Execute:

- Verify current prices in AWS Pricing Calculator or current AWS pricing pages and record the verification date.
- Create monthly actual credit-burn cost alerts at 25, 50, 80, and 95 USD.
- Create monthly forecasted credit-burn cost alerts at 50 and 80 USD.
- Create EC2 running-hour alerts at 5, 10, 15, and 20 hours/month.
- If AWS Budgets CLI rejects the usage-budget filter shape, create the equivalent budget in the console and record the exact settings.
- Optionally add a separate net-bill budget with credits included later, but keep the starter guardrail focused on pre-credit burn.

CLI starter shape for the primary monthly credit-burn cost budget. This must be a `COST` budget with `IncludeCredit=false`; do not use a `USAGE` budget for this guardrail because usage budgets cannot use `CostTypes`:

```bash
export BURN_BUDGET_NAME=uk-housing-market-abm-monthly-credit-burn-guardrail
export EC2_HOURS_BUDGET_NAME=uk-housing-market-abm-ec2-hours-guardrail

cat >/tmp/uk-housing-monthly-budget.json <<EOF
{
  "BudgetName": "uk-housing-market-abm-monthly-credit-burn-guardrail",
  "BudgetLimit": { "Amount": "100", "Unit": "USD" },
  "TimeUnit": "MONTHLY",
  "BudgetType": "COST",
  "CostFilters": {},
  "CostTypes": {
    "IncludeTax": true,
    "IncludeSubscription": true,
    "UseBlended": false,
    "IncludeRefund": false,
    "IncludeCredit": false,
    "IncludeUpfront": true,
    "IncludeRecurring": true,
    "IncludeOtherSubscription": true,
    "IncludeSupport": true,
    "IncludeDiscount": true,
    "UseAmortized": false
  }
}
EOF

cat >/tmp/uk-housing-budget-subscribers.json <<EOF
[
  { "SubscriptionType": "EMAIL", "Address": "$BUDGET_EMAIL" }
]
EOF

create_budget_if_absent() {
  local budget_name="$1"
  local budget_file="$2"
  local output status

  if output="$(aws budgets describe-budget \
    --account-id "$ACCOUNT_ID" \
    --budget-name "$budget_name" 2>&1)"; then
    printf 'Budget already exists: %s\n' "$budget_name"
    return 0
  else
    status=$?
  fi

  if ! printf '%s\n' "$output" | grep -q 'NotFoundException'; then
    printf '%s\n' "$output" >&2
    return "$status"
  fi

  if output="$(aws budgets create-budget \
    --account-id "$ACCOUNT_ID" \
    --budget "file://$budget_file" 2>&1)"; then
    printf 'Created budget: %s\n' "$budget_name"
    return 0
  else
    status=$?
  fi

  if printf '%s\n' "$output" | grep -q 'DuplicateRecordException'; then
    printf 'Budget appeared during create: %s\n' "$budget_name"
    return 0
  fi

  printf '%s\n' "$output" >&2
  return "$status"
}

create_notification_if_absent() {
  local budget_name="$1"
  local notification_type="$2"
  local threshold="$3"
  local existing_count notification output status

  if ! existing_count="$(aws budgets describe-notifications-for-budget \
    --account-id "$ACCOUNT_ID" \
    --budget-name "$budget_name" \
    --query "length(Notifications[?NotificationType=='$notification_type' && Threshold==\`$threshold\` && ThresholdType=='ABSOLUTE_VALUE'])" \
    --output text 2>&1)"; then
    printf '%s\n' "$existing_count" >&2
    return 1
  fi

  if [ "$existing_count" != "0" ]; then
    printf 'Notification already exists: %s %s %s\n' "$budget_name" "$notification_type" "$threshold"
    return 0
  fi

  notification="NotificationType=$notification_type,ComparisonOperator=GREATER_THAN,Threshold=$threshold,ThresholdType=ABSOLUTE_VALUE"

  if output="$(aws budgets create-notification \
    --account-id "$ACCOUNT_ID" \
    --budget-name "$budget_name" \
    --notification "$notification" \
    --subscribers file:///tmp/uk-housing-budget-subscribers.json 2>&1)"; then
    printf 'Created %s notification at %s for %s\n' "$notification_type" "$threshold" "$budget_name"
    return 0
  else
    status=$?
  fi

  if printf '%s\n' "$output" | grep -q 'DuplicateRecordException'; then
    printf 'Notification already exists: %s %s %s\n' "$budget_name" "$notification_type" "$threshold"
    return 0
  fi

  printf '%s\n' "$output" >&2
  return "$status"
}

create_budget_if_absent "$BURN_BUDGET_NAME" /tmp/uk-housing-monthly-budget.json

for threshold in 25 50 80 95; do
  create_notification_if_absent "$BURN_BUDGET_NAME" ACTUAL "$threshold"
done

for threshold in 50 80; do
  create_notification_if_absent "$BURN_BUDGET_NAME" FORECASTED "$threshold"
done

aws budgets describe-budget \
  --account-id "$ACCOUNT_ID" \
  --budget-name "$BURN_BUDGET_NAME"

aws budgets describe-notifications-for-budget \
  --account-id "$ACCOUNT_ID" \
  --budget-name "$BURN_BUDGET_NAME"
```

CLI starter shape for the EC2 usage budget. Keep this as a separate `USAGE` budget and do not add `CostTypes`. If this filter is not accepted for the account, create an equivalent EC2 running-hours budget in the console and record the exact settings:

```bash
cat >/tmp/uk-housing-ec2-hours-budget.json <<EOF
{
  "BudgetName": "uk-housing-market-abm-ec2-hours-guardrail",
  "BudgetLimit": { "Amount": "20", "Unit": "Hrs" },
  "TimeUnit": "MONTHLY",
  "BudgetType": "USAGE",
  "CostFilters": {
    "Service": ["Amazon Elastic Compute Cloud - Compute"]
  }
}
EOF

create_budget_if_absent "$EC2_HOURS_BUDGET_NAME" /tmp/uk-housing-ec2-hours-budget.json

for threshold in 5 10 15 20; do
  create_notification_if_absent "$EC2_HOURS_BUDGET_NAME" ACTUAL "$threshold"
done

aws budgets describe-budget \
  --account-id "$ACCOUNT_ID" \
  --budget-name "$EC2_HOURS_BUDGET_NAME"

aws budgets describe-notifications-for-budget \
  --account-id "$ACCOUNT_ID" \
  --budget-name "$EC2_HOURS_BUDGET_NAME"
```

Forbidden-resource check:

```bash
aws ec2 describe-nat-gateways --region "$AWS_REGION" --query 'NatGateways[].NatGatewayId' --output text
aws rds describe-db-instances --region "$AWS_REGION" --query 'DBInstances[].DBInstanceIdentifier' --output text || true
aws ec2 describe-addresses --region "$AWS_REGION" --query 'Addresses[].AllocationId' --output text
```

Acceptance gate:

- Actual, forecasted, and EC2 running-hour alerts exist.
- Notes record the alert destination, pricing check date, and forbidden-resource check result.
- Notes state that v1 still has no NAT Gateway, RDS, Elastic IP, public S3 bucket, custom domain, Route 53 hosted zone, or always-on experiment compute.

Cost check:

- Budgets are in place before any compute.
- No compute resources are created in this phase.

Security check:

- No broad IAM permissions are created.

Rollback/stop condition:

- If budget creation fails and equivalent alerts are not created manually, stop before compute.

## Phase 4: Storage And IAM Foundation
Goal: create private artifact storage and least-privilege roles for later API and runner phases.

Prerequisites:

- Phase 3 accepted.

Execute:

```bash
export ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
export AWS_REGION=eu-west-2
export ARTIFACTS_BUCKET="uk-housing-market-abm-artifacts-prod-$ACCOUNT_ID"
export FRONTEND_BUCKET="uk-housing-market-abm-web-prod-$ACCOUNT_ID"
```

Create the private artifacts bucket:

```bash
aws s3api create-bucket \
  --bucket "$ARTIFACTS_BUCKET" \
  --region "$AWS_REGION" \
  --create-bucket-configuration LocationConstraint="$AWS_REGION" || true

aws s3api put-public-access-block \
  --bucket "$ARTIFACTS_BUCKET" \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

aws s3api put-bucket-encryption \
  --bucket "$ARTIFACTS_BUCKET" \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

aws s3api put-bucket-versioning \
  --bucket "$ARTIFACTS_BUCKET" \
  --versioning-configuration Status=Enabled
```

- Create the private artifacts bucket with S3 Block Public Access, SSE-S3 encryption, versioning, and lifecycle rules.
- Use the artifact key layout in the S3 artifacts supporting reference.
- Create `uk-housing-market-abm-runner-role` with `AmazonSSMManagedInstanceCore`.
- Add only scoped S3 access for `experiments/manual/*`, `logs/ec2-runner/*`, and `tmp/*`; reserve `DeleteObject` for `tmp/*`.
- Create `uk-housing-market-abm-runner-profile`.
- Create `uk-housing-market-abm-ecs-task-execution-role` with `AmazonECSTaskExecutionRolePolicy`.

Acceptance gate:

- Artifacts bucket exists and is private, encrypted, versioned, and lifecycle-managed.
- EC2 runner role and ECS task execution role exist.
- Runner role cannot broadly delete experiment evidence.
- Notes include bucket name, role ARNs, policy summaries, and lifecycle settings.

Cost check:

- S3 storage, requests, and retained versions begin.
- IAM roles have no direct cost.
- No compute is created.

Security check:

- Public access is blocked.
- IAM is prefix-scoped.
- No public or private-data bucket policy is created.

Rollback/stop condition:

- If bucket public-access block, encryption, lifecycle, or scoped IAM policy fails, stop before API image or compute phases.

## Phase 5: API Image Build And ECR Push
Goal: build and publish the public dashboard API image.

Prerequisites:

- Phase 4 accepted.
- Docker is running locally.

Execute:

```bash
export AWS_REGION=eu-west-2
export ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
export ECR_REPO=uk-housing-market-abm-api
export IMAGE_TAG="$(git rev-parse --short HEAD)"
export IMAGE="$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:$IMAGE_TAG"

aws ecr create-repository \
  --repository-name "$ECR_REPO" \
  --image-scanning-configuration scanOnPush=true \
  --region "$AWS_REGION" || true

aws ecr put-image-tag-mutability \
  --repository-name "$ECR_REPO" \
  --image-tag-mutability IMMUTABLE \
  --region "$AWS_REGION" || true

aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

docker build --platform linux/amd64 -f dashboard/Dockerfile.api -t "$IMAGE" .
docker push "$IMAGE"

aws ecr describe-images \
  --repository-name "$ECR_REPO" \
  --image-ids imageTag="$IMAGE_TAG" \
  --region "$AWS_REGION" \
  --query 'imageDetails[0].imageDigest' \
  --output text
```

Acceptance gate:

- ECR image is pushed with the current commit tag.
- Image digest is recorded in notes.
- Image scan-on-push and immutable tags are enabled where supported.

Cost check:

- ECR storage begins.
- Keep only needed tags during starter-credit phase.

Security check:

- Image excludes Java, Maven, git metadata, `private-datasets/`, local `node_modules`, generated `Results/`, local build outputs, and operational notes.

Rollback/stop condition:

- If image hygiene fails, delete the pushed image if any was pushed and stop.

## Phase 6: API Runtime Launch
Goal: launch the lightweight dashboard API with model execution disabled.

Prerequisites:

- Phase 5 accepted.

Implementation path:

- Use standard ECS/Fargate + ALB for the numbered phases.
- Do not use App Runner in the numbered phases; keep it only as a legacy/grandfathered supporting-reference path.
- Do not use ECS Express Mode in the numbered phases unless a future plan adds the ECS infrastructure role, executor `iam:PassRole`, and `aws ecs create-express-gateway-service` workflow.
- Do not choose a larger ECS task or more than one task during starter-credit phase.

ECS/Fargate runtime settings:

```text
NODE_ENV=production
PORT=8080
DASHBOARD_CORS_ORIGIN=https://<frontend-origin>
DASHBOARD_ENABLE_MODEL_RUNS=false
DASHBOARD_LOG_MEMORY=false
```

Standard ECS/Fargate starter settings:

- `512` CPU / `1024` MiB memory
- desired count `1` only if the API must be online
- max tasks `1`
- container and target group port `8080`
- health check path `/healthz`
- task logs retention 7 days

Create the log group and cluster before task/service creation:

```bash
aws logs create-log-group \
  --log-group-name /ecs/uk-housing-market-abm-api-prod \
  --region "$AWS_REGION" || true
aws logs put-retention-policy \
  --log-group-name /ecs/uk-housing-market-abm-api-prod \
  --retention-in-days 7 \
  --region "$AWS_REGION"

aws ecs create-cluster \
  --cluster-name uk-housing-market-abm-prod \
  --tags key=Project,value=uk-housing-market-abm key=Environment,value=prod key=Owner,value=MaxStoddard key=ManagedBy,value=manual-v1 \
  --region "$AWS_REGION" || true
```

Networking rules:

- Prefer existing default VPC public subnets for v1 to avoid NAT Gateway.
- Do not create a NAT Gateway.
- Restrict ECS task inbound to the ALB security group only.
- Do not require public ALB response validation before CloudFront exists.
- If ECS tasks need public IPs for ECR and CloudWatch without NAT or VPC endpoints, record the public IPv4 cost tradeoff. Do not open task inbound from the internet.

Validation:

```bash
aws ecs wait services-stable \
  --cluster uk-housing-market-abm-prod \
  --services uk-housing-market-abm-api-prod \
  --region "$AWS_REGION"

aws ecs describe-services \
  --cluster uk-housing-market-abm-prod \
  --services uk-housing-market-abm-api-prod \
  --region "$AWS_REGION"

aws elbv2 describe-target-health \
  --target-group-arn <target-group-arn> \
  --region "$AWS_REGION"
```

Optional direct ALB HTTP validation, only if the ECS and ELB API checks are insufficient:

```bash
EXECUTOR_CIDR="$(curl -fsS https://checkip.amazonaws.com)/32"

aws ec2 authorize-security-group-ingress \
  --group-id <alb-security-group-id> \
  --protocol tcp \
  --port 80 \
  --cidr "$EXECUTOR_CIDR" \
  --region "$AWS_REGION"

curl "http://<alb-dns-name>/healthz"
curl "http://<alb-dns-name>/api/runtime-deps"

aws ec2 revoke-security-group-ingress \
  --group-id <alb-security-group-id> \
  --protocol tcp \
  --port 80 \
  --cidr "$EXECUTOR_CIDR" \
  --region "$AWS_REGION"
```

Acceptance gate:

- ECS service is stable.
- ALB target health is healthy, with the target group health check path set to `/healthz`.
- If optional direct ALB HTTP validation is performed, `/healthz` succeeds, `/api/runtime-deps` behaves as expected, and the temporary executor-IP ingress rule is revoked.
- Public write/model-run actions fail closed.
- Notes record task definition ARN, service ARN, target group ARN, ALB DNS name, security groups, any temporary ingress rule and its removal, logs, and costs.

Cost check:

- Record expected ALB hourly cost, Fargate monthly cost, CloudWatch Logs cost, and any public IPv4 cost.
- If combined always-on cost exceeds the starter budget expectation, stop and ask whether to keep the API always on.

Security check:

- `DASHBOARD_ENABLE_MODEL_RUNS=false`.
- No write credentials are configured for public v1.
- Logs have short retention.

Rollback/stop condition:

- If unhealthy or cost/security posture is unacceptable, scale service desired count to `0` or delete the service and record cleanup.

## Phase 7: Frontend S3 And CloudFront Launch
Goal: publish the React dashboard through private S3 and the no-domain-fee CloudFront default HTTPS hostname.

Prerequisites:

- Phase 6 accepted, unless deliberately using the legacy/grandfathered App Runner path.
- No custom domain for v1.

Execute:

```bash
export ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
export AWS_REGION=eu-west-2
export FRONTEND_BUCKET="uk-housing-market-abm-web-prod-$ACCOUNT_ID"
```

```bash
aws s3api create-bucket \
  --bucket "$FRONTEND_BUCKET" \
  --region "$AWS_REGION" \
  --create-bucket-configuration LocationConstraint="$AWS_REGION" || true

aws s3api put-public-access-block \
  --bucket "$FRONTEND_BUCKET" \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

aws s3api put-bucket-encryption \
  --bucket "$FRONTEND_BUCKET" \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
```

- Create the private frontend bucket with Block Public Access and SSE-S3 encryption.
- Create CloudFront with OAC, default root object `index.html`, HTTP-to-HTTPS redirect, and SPA error mapping from S3 `403` and `404` to `/index.html` with HTTP `200`.
- If using ALB API origin, add CloudFront behaviors for `/api/*` and `/healthz`.
- After the CloudFront API behaviors exist, restrict ALB inbound HTTP to the AWS-managed CloudFront origin-facing prefix list when available.
- Disable CloudFront access logs by default to avoid extra storage cost unless debugging requires them.

Build and upload:

```bash
cd dashboard
npm ci --include=dev
npm run build:client
cd ..

aws s3 sync dashboard/dist "s3://$FRONTEND_BUCKET/" --delete --region "$AWS_REGION"
aws cloudfront create-invalidation --distribution-id <distribution-id> --paths "/*"

curl "https://<cloudfront-domain>/healthz"
curl "https://<cloudfront-domain>/api/runtime-deps"
```

Acceptance gate:

- CloudFront default hostname serves the frontend over HTTPS.
- CloudFront routes `/healthz` and `/api/runtime-deps` to the API when using an ALB origin.
- S3 direct object access is blocked.
- SPA fallback is configured.
- Notes record bucket name, distribution ID, CloudFront domain, OAC ID, API-origin behavior, and ALB CloudFront-prefix-list restriction.

Cost check:

- S3 and CloudFront low variable costs begin.
- No Route 53 hosted zone, ACM custom certificate, or custom domain registration is created.

Security check:

- Frontend bucket remains private with Block Public Access.
- CloudFront OAC is the only read path.
- No private datasets, `Results/`, or env files are uploaded.

Rollback/stop condition:

- If CloudFront cannot read through OAC, do not make the bucket public. Fix OAC or bucket policy.

## Phase 8: Public Launch Verification
Goal: verify the public site and API before provisioning runner compute.

Prerequisites:

- Phase 7 accepted.

Execute:

```bash
export SITE_URL="https://<cloudfront-domain>"

curl -I "$SITE_URL"
curl "$SITE_URL/healthz"
curl "$SITE_URL/api/runtime-deps"
curl "$SITE_URL/api/versions"

# Direct S3 access should fail.
curl -I "https://$FRONTEND_BUCKET.s3.$AWS_REGION.amazonaws.com/index.html"
```

Browser checks:

- Dashboard loads.
- Read-only pages load data.
- Experiment/model-run write actions are disabled or fail closed in production.

Acceptance gate:

- Frontend loads at `https://<cloudfront-domain>`.
- API calls work through HTTPS.
- `/healthz` and `/api/runtime-deps` behave as expected.
- Direct S3 reads are blocked.
- Notes include final public URL and launch verification results.

Cost check:

- Record current always-on API cost estimate.
- Record that no custom domain, hosted zone, NAT Gateway, RDS, Elastic IP, public S3, or always-on experiment compute exists.

Security check:

- Browser API calls use HTTPS.
- Public API model runs are disabled.
- No public write credentials are configured.

Rollback/stop condition:

- If public routing fails, keep the API service running only long enough to debug. If no fix is available, scale API desired count to `0` and record cleanup.

## Phase 9: EC2 Runner Bootstrap
Goal: provision and validate a stopped-by-default runner without SSH or unnecessary high-core cost.

Prerequisites:

- Phase 8 accepted.
- Phase 4 runner role and instance profile exist.

Starter runner:

| Setting | Value |
| --- | --- |
| Instance type | `c7i.xlarge` for bootstrap and smoke |
| Scale-up type | `c7i.8xlarge` only for justified sharded sweeps |
| Architecture | `x86_64` |
| AMI | Ubuntu 24.04 LTS |
| Root EBS | `50 GiB gp3` |
| Public inbound ports | none |
| Elastic IP | none |
| Access | Systems Manager Session Manager |
| Start policy | stopped by default |

Execute:

- Create a security group with no inbound rules.
- Allow outbound HTTPS. Temporarily allow outbound TCP 80 only if Ubuntu apt mirrors require it, then remove it if possible.
- Configure EventBridge Scheduler or SSM Automation automatic stop for runner instances tagged `Project=uk-housing-market-abm` and `Role=experiment-runner`.
- Install/verify AWS CLI v2, SSM, Node 22, Java 25, Maven 3.8.7, Python basics, git, jq, and build tools.
- Clone the repo and run `mvn -q test`, dashboard `npm run build`, and `npm run test:smoke`.
- Stop the instance after bootstrap.

Acceptance gate:

- Runner can be started, accessed through Session Manager, validated, and stopped.
- No public inbound ports and no Elastic IP.
- Auto-stop control exists.
- Notes record instance ID, AMI ID, instance type, root volume size, role, security group, bootstrap results, and stopped state.

Cost check:

- Record instance hourly cost, EBS monthly cost, and bootstrap runtime.
- Stop the instance immediately after validation.

Security check:

- Session Manager works without SSH.
- Runner role writes only intended S3 prefixes.

Rollback/stop condition:

- If bootstrap fails, sync useful logs to `s3://<artifacts-bucket>/logs/ec2-runner/<date>/` if possible, then stop the instance.

## Phase 10: First Runner Smoke Simulation
Goal: validate the remote-run evidence workflow with bounded cost. This is not performance evidence.

Prerequisites:

- Phase 9 accepted.
- Runner starts from stopped state.

Execute on the runner:

```bash
cd ~/uk-housing-model-individual-project
git pull --ff-only
git status --short
git rev-parse HEAD

RUN_ID="$(date +%F)-runner-smoke-$(git rev-parse --short HEAD)"
RUN_ROOT="$HOME/remote-runs/$RUN_ID"
mkdir -p "$RUN_ROOT/logs"

bash scripts/model/run-speed-benchmark.sh \
  --snapshot v0 \
  --mode core-minimal-10k-s1 \
  --repeat 1 \
  --warmup 0 \
  --cooldown 0 \
  --pin-cpu 0 \
  --active-processor-count 1 \
  --output-root "$RUN_ROOT/model-speed/benchmarks" \
  2>&1 | tee "$RUN_ROOT/logs/command.log"
```

Then write `run-manifest.json`, write `output-manifest.sha256`, sync only `$RUN_ROOT` to:

```text
s3://uk-housing-market-abm-artifacts-prod-<account-id>/experiments/manual/<yyyy-mm-dd>/<run-id>/
```

Stop after sync:

```bash
aws ec2 stop-instances --instance-ids <instance-id> --region eu-west-2
aws ec2 describe-instances --instance-ids <instance-id> --region eu-west-2 --query 'Reservations[].Instances[].State.Name' --output text
```

Acceptance gate:

- `run-manifest.json`, `output-manifest.sha256`, command log, and smoke outputs exist in S3.
- Only the current run root was synced.
- The instance is stopped.
- Notes state that this smoke run is not performance evidence.

Cost check:

- Record start time, stop time, elapsed runtime, and estimated instance/EBS cost.

Security check:

- Do not sync the whole repository or full `Results/`.
- Do not upload `private-datasets/`.

Rollback/stop condition:

- On failure, write a failure manifest if possible, sync logs if possible, and stop the instance.

## Phase 11: Simulation Readiness Handoff
Goal: leave future agents with repeatable, secure, cheap, and fail-safe simulation instructions.

Prerequisites:

- Phase 10 accepted.

Document in `docs/cloud/aws-execution-notes.md`:

- exact full-run command templates
- artifact bucket and prefix pattern
- instance IDs and when to use each size
- stop/failure procedure
- S3 evidence requirements
- Python dependency capture rules
- criteria before trusting cloud simulation output

Full model-speed correctness and benchmark templates:

```bash
bash scripts/model/run-speed-regression.sh \
  --snapshot v0 \
  --mode e2e-default-5k-s1 \
  --contract exact \
  --baseline-manifest docs/model-speed/baselines/v0-e2e-default-5k-s1.exact.sha256 \
  --repeat 3 \
  --pin-cpu 0 \
  --active-processor-count 1 \
  --output-root "$RUN_ROOT/model-speed/regressions"

bash scripts/model/run-speed-benchmark.sh \
  --snapshot v0 \
  --mode core-minimal-20k-s1 \
  --repeat 10 \
  --warmup 0 \
  --cooldown 0 \
  --pin-cpu 0 \
  --active-processor-count 1 \
  --output-root "$RUN_ROOT/model-speed/benchmarks"
```

Python workflow rule:

- There is no repo-wide `requirements.txt` or `pyproject.toml` for all `scripts/python` workflows.
- Before a Python calibration/validation run, identify the exact script, create a venv, install only required packages, and save `pip freeze` under the run root before syncing to S3.
- Do not run Python workflows against `private-datasets/` unless the task explicitly requires it and the notes record privacy controls.

Acceptance gate:

- Future agents can execute a full simulation phase without rediscovering resource IDs, commands, or safety constraints.
- Every runner state is recorded as stopped or intentionally running with an explicit reason.
- Notes explicitly state the Phase 10 smoke run is not performance evidence.

Cost check:

- No runner may remain running after handoff.
- Scale to `c7i.8xlarge` only for deterministic sharded parallel work.

Security check:

- Future simulation commands sync only current run roots.
- Evidence includes commit, branch, dirty status, command, input snapshot, tool versions, output hashes, logs, and S3 prefix.

Rollback/stop condition:

- If a future full run fails, stop the instance after syncing logs and a failure manifest.

## Supporting Reference: Frontend S3 + CloudFront
Build the dashboard client and upload only the generated static assets.

Recommended settings:

- S3 bucket is private.
- S3 Block Public Access stays enabled.
- Do not use S3 static website hosting for production.
- CloudFront uses the S3 bucket as a normal S3 origin with Origin Access Control (OAC).
- CloudFront viewer protocol policy redirects HTTP to HTTPS.
- CloudFront custom error responses map S3 `403` and `404` to `/index.html` with HTTP `200`, because the React app uses client-side routes and the S3 bucket is private.
- ACM certificate for CloudFront must be in `us-east-1` if using a custom domain.
- Route 53 is optional. Use it only if a custom domain is worth the extra fixed cost.
- If using standard ECS/Fargate + ALB without a custom API domain, add CloudFront behaviors for `/api/*` and `/healthz` that route to the ALB origin. This keeps browser requests same-origin over CloudFront HTTPS and avoids mixed-content failures from calling an HTTP-only ALB DNS name directly.

Build and deploy:

```bash
cd dashboard
npm ci --include=dev

# Choose exactly one build mode.

# Same-origin CloudFront /api/* path:
npm run build:client

# Separate HTTPS API origin:
VITE_API_BASE_URL=https://<api-endpoint> npm run build:client
aws s3 sync dist s3://uk-housing-market-abm-web-prod-<account-id>/ --delete --region eu-west-2
aws cloudfront create-invalidation --distribution-id <distribution-id> --paths "/*"
```

Frontend environment when using a separate HTTPS API origin:

```text
VITE_API_BASE_URL=https://<api-endpoint>
```

For the lowest-cost ECS starter phase without a custom API domain, leave `VITE_API_BASE_URL` unset and route `/api/*` through the same CloudFront distribution to the ALB origin. With a grandfathered App Runner default HTTPS endpoint or a custom API domain, set `VITE_API_BASE_URL` to that HTTPS API origin.

Acceptance checks:

```bash
curl -I https://<cloudfront-domain-or-custom-domain>
# Same-origin CloudFront API behavior only:
curl https://<cloudfront-domain-or-custom-domain>/healthz
curl https://<cloudfront-domain-or-custom-domain>/api/runtime-deps
# Separate HTTPS API origin only:
curl https://<api-endpoint>/healthz
curl https://<api-endpoint>/api/runtime-deps
```

## Supporting Reference: API ECS/Fargate Primary Path
Host the existing lightweight dashboard API from an ECR image on standard ECS/Fargate with an ALB. This is the primary path for the numbered phases because it is CLI-debuggable, compatible with same-origin CloudFront routing, and straightforward to validate with ECS and ELB APIs.

Use the existing API Dockerfile:

```text
dashboard/Dockerfile.api
```

Before building the public API image, tighten Docker build hygiene. The build context is the repo root, so `.dockerignore` must exclude at least:

```text
.git/**
.env*
agents/**
AGENTS*.md
private-datasets/**
Results/**
tmp/**
target/**
dashboard/node_modules/**
dashboard/dist/**
dashboard/dist-server/**
dashboard/.smoke-dist/**
```

The public API image should copy only the dashboard API/runtime source needed by `dashboard/Dockerfile.api` plus `input-data-versions/`. It must not include `private-datasets/`, generated `Results/`, Java, Maven, git metadata, local `node_modules`, or local build output. If the Dockerfile is later refactored, prefer explicit `COPY` statements over copying the entire `dashboard/` directory.

Build and push the API image:

```bash
AWS_REGION=eu-west-2
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO=uk-housing-market-abm-api
IMAGE="$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:$(git rev-parse --short HEAD)"

aws ecr create-repository --repository-name "$ECR_REPO" --region "$AWS_REGION" || true
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
docker build --platform linux/amd64 -f dashboard/Dockerfile.api -t "$IMAGE" .
docker push "$IMAGE"
```

Recommended ECS/Fargate configuration:

| Setting | Value |
| --- | --- |
| Source | ECR private image |
| Task size | `0.5 vCPU / 1 GB` for starter phase |
| Desired count / min tasks | `1` if the API must be always-on |
| Max tasks | `1` while on starter credit |
| Container port | `8080` |
| Target group port | `8080` |
| Health check path | `/healthz` |
| ALB listener | HTTP behind CloudFront for no-custom-domain starter use, or HTTPS if using a custom API domain |
| Public API domain | same-origin CloudFront `/api/*`, or `api.<domain>` if using a custom domain |

ECS Express Mode is a supporting-reference option only. Use it only if a future plan adds an ECS infrastructure role with `AmazonECSInfrastructureRoleforExpressGatewayServices`, grants the executor scoped `iam:PassRole` for both the task execution and infrastructure roles, and replaces the Phase 6 service creation path with `aws ecs create-express-gateway-service`. If that future path is used, explicitly override CPU to `512`, memory to `1024`, primary container port to `8080`, health check path to `/healthz`, min tasks to `1`, and max tasks to `1`.

API environment variables:

```text
NODE_ENV=production
PORT=8080
DASHBOARD_CORS_ORIGIN=https://<frontend-origin>
DASHBOARD_ENABLE_MODEL_RUNS=false
DASHBOARD_LOG_MEMORY=false
```

Do not set `DASHBOARD_WRITE_USERNAME` or `DASHBOARD_WRITE_PASSWORD` for the public v1 unless remote write actions are deliberately being enabled. Model execution must remain disabled in the public API.

If the frontend and API are served same-origin through CloudFront, CORS is not needed for browser traffic, but keeping `DASHBOARD_CORS_ORIGIN` set to the frontend origin is still a reasonable defensive default.

Acceptance checks:

```bash
aws ecs wait services-stable \
  --cluster uk-housing-market-abm-prod \
  --services uk-housing-market-abm-api-prod \
  --region eu-west-2

aws elbv2 describe-target-health \
  --target-group-arn <target-group-arn> \
  --region eu-west-2

# After CloudFront API behaviors exist:
curl https://<cloudfront-domain-or-custom-domain>/healthz
curl https://<cloudfront-domain-or-custom-domain>/api/runtime-deps
```

Expected production behavior:

- `/healthz` returns success.
- `/api/runtime-deps` may report Java/Maven missing. That is acceptable because `DASHBOARD_ENABLE_MODEL_RUNS=false`.
- Dashboard read routes work.
- Model execution routes remain disabled.
- Experiment routes may be visible in the UI, but write/run actions fail closed in production.
- No `private-datasets/` or generated `Results/` content is copied into the public API image.

## Supporting Reference: API App Runner Legacy Option
Use App Runner only if the target AWS account is already an App Runner customer and can create App Runner services.

Preflight command:

```bash
aws apprunner list-services --region eu-west-2
```

If App Runner is available, it can still host the same ECR image with lower operational burden and possibly lower starter cost than ECS/Fargate plus an ALB. Keep the security policy equivalent to the ECS production policy, but use App Runner-specific port handling:

| Setting | Value |
| --- | --- |
| Source | ECR private image |
| Image port | `8787` |
| CPU / memory | `0.5 vCPU / 1 GB` |
| Auto deploy | enabled after first manual image push |
| Auto scaling min size | `1` |
| Auto scaling max size | `1` while on starter credit |
| Max concurrency | `80` |
| Health check protocol | HTTP |
| Health check path | `/healthz` |
| Custom domain | optional; use default service URL if avoiding domain cost |

App Runner environment variables:

```text
NODE_ENV=production
DASHBOARD_CORS_ORIGIN=https://<frontend-origin>
DASHBOARD_ENABLE_MODEL_RUNS=false
DASHBOARD_LOG_MEMORY=false
```

Do not add `PORT` manually as a user-defined App Runner environment variable; App Runner reserves that name. If the account is not grandfathered for App Runner, do not spend setup time on this path.

The App Runner port differs from the ECS path intentionally: App Runner uses the image's default API fallback port `8787`, while ECS overrides the process with `PORT=8080` so it matches the ECS container and target-group port mapping.

## Supporting Reference: S3 Artifacts Bucket
Create a separate private artifacts bucket for experiment output and future dashboard result bundles.

For v1, the artifacts bucket is archive/evidence storage only. The public dashboard will not browse S3 experiment results until a later S3-backed read-only result API is implemented. Do not make the Java model depend on mutable cloud artifacts without adding explicit reproducibility checks.

Recommended bucket settings:

- S3 Block Public Access enabled.
- Server-side encryption enabled with SSE-S3 for v1.
- Versioning enabled for evidence preservation, or at minimum immutable unique run prefixes if versioning is deliberately deferred.
- Lifecycle rules:
  - keep `experiments/manual/` current outputs in S3 Standard for 30 days, then transition to Standard-IA or Glacier Flexible Retrieval depending on expected retrieval needs
  - transition `experiments/archive/` objects to Glacier Flexible Retrieval after 90 days
  - expire `tmp/` objects after 14 days
  - expire incomplete multipart uploads after 7 days

Recommended key layout:

```text
s3://uk-housing-market-abm-artifacts-prod-<account-id>/
  experiments/
    manual/
      <yyyy-mm-dd>/<run-id>/
        run-manifest.json
        output-manifest.sha256
        Results/
        logs/
  input-data-versions/
    <version>/
  logs/
    ec2-runner/
  tmp/
```

The normal EC2 runner role should not have broad delete access. Scope writes to run-output prefixes and reserve deletes for `tmp/` unless there is a deliberate cleanup workflow.

IAM role for the instance:

- attach AWS managed policy `AmazonSSMManagedInstanceCore`
- add an inline policy scoped to the artifacts bucket:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket"
      ],
      "Resource": "arn:aws:s3:::uk-housing-market-abm-artifacts-prod-<account-id>",
      "Condition": {
        "StringLike": {
          "s3:prefix": [
            "experiments/manual/*",
            "logs/ec2-runner/*",
            "tmp/*"
          ]
        }
      }
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject"
      ],
      "Resource": [
        "arn:aws:s3:::uk-housing-market-abm-artifacts-prod-<account-id>/experiments/manual/*",
        "arn:aws:s3:::uk-housing-market-abm-artifacts-prod-<account-id>/logs/ec2-runner/*",
        "arn:aws:s3:::uk-housing-market-abm-artifacts-prod-<account-id>/tmp/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::uk-housing-market-abm-artifacts-prod-<account-id>/tmp/*"
    }
  ]
}
```

## Supporting Reference: Experiment Runner EC2
Use one manually started EC2 instance for the first remote experiment runner. Start with a smaller root disk and only use a large instance when the selected experiment can actually use the cores.

Recommended starter instance:

| Setting | Value |
| --- | --- |
| Instance type | `c7i.8xlarge` only when high-core sharded sweeps need it; otherwise start smaller |
| vCPU / RAM for `c7i.8xlarge` | `32 vCPU / 64 GiB` |
| Architecture | `x86_64` |
| AMI | Ubuntu 24.04 LTS |
| Root EBS | `50-100 GiB gp3` starter default; resize only if measured runs need more |
| Public inbound ports | none |
| Elastic IP | none |
| Access | AWS Systems Manager Session Manager |
| Start policy | stopped by default |
| Stop policy | automatic stop plus manual stop after syncing outputs |

Use `c7i.8xlarge` first instead of ARM-based `c7g.8xlarge` only when validating Java, Maven, Node, Python, and native Python dependencies on x86_64 matters. Revisit Graviton after exact/regression checks prove output compatibility and performance is acceptable.

Security group:

```text
Inbound: none
Outbound: HTTPS allowed after bootstrap
```

Ubuntu `apt-get` may use HTTP mirrors. During bootstrap, either temporarily allow outbound TCP 80, force HTTPS apt sources, or bake a runner AMI with dependencies preinstalled.

Required cost control:

- Add an EventBridge rule or SSM Automation that stops tagged runner instances after a conservative maximum runtime.
- Keep AWS Budget running-hour alerts at 5, 10, 15, and 20 hours/month.
- Check instance state after each run.
- Stop the instance even if an experiment fails after partial output sync.

Initial machine bootstrap checklist:

```bash
sudo apt-get update
sudo apt-get install -y git curl unzip zip jq build-essential python3 python3-venv python3-pip

# Install AWS CLI v2, then verify.
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
aws --version

# Verify SSM agent status on Ubuntu 24.04.
sudo systemctl status snap.amazon-ssm-agent.amazon-ssm-agent.service --no-pager || true
aws sts get-caller-identity

# Install Node 22 with nvm, then verify against dashboard/.nvmrc.
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"

# Install Java 25 and Maven 3.8.7 with SDKMAN, then verify.
curl -s "https://get.sdkman.io" | bash
export SDKMAN_DIR="$HOME/.sdkman"
[ -s "$SDKMAN_DIR/bin/sdkman-init.sh" ] && . "$SDKMAN_DIR/bin/sdkman-init.sh"
sdk install java 25.0.2-tem
sdk install maven 3.8.7
java -version
mvn --version

cd ~
git clone <repo-url> uk-housing-model-individual-project
cd uk-housing-model-individual-project
mvn -q test
cd dashboard
nvm install
node --version
npm --version
npm ci --include=dev
npm run build
npm run test:smoke
```

Python calibration and validation scripts may need packages such as NumPy, pandas, matplotlib, and openpyxl, but this repository does not currently expose a single `requirements.txt` or `pyproject.toml` for all `scripts/python` workflows. Before using EC2 for Python calibration work, identify the exact script and install its dependencies into a venv with a captured package list.

Remote run workflow:

```bash
# Start the instance from local machine or AWS console.
aws ec2 start-instances --instance-ids <instance-id> --region eu-west-2

# Connect through Session Manager.
aws ssm start-session --target <instance-id> --region eu-west-2

# On the instance, pull latest code and confirm the exact revision.
cd ~/uk-housing-model-individual-project
git pull --ff-only
git status --short
git rev-parse HEAD

# Choose the exact experiment command from docs/model-speed/README.md or the relevant script docs.
# Do not trust cloud performance or output changes until exact/regression checks pass.

RUN_ID=<yyyy-mm-dd>-<short-description>-<commit-short-sha>
RUN_ROOT="$HOME/remote-runs/$RUN_ID"
mkdir -p "$RUN_ROOT/Results" "$RUN_ROOT/logs"

# Run the selected command so output lands under the current run directory when the harness supports it.
# Example for model-speed benchmark:
bash scripts/model/run-speed-benchmark.sh \
  --snapshot v0 \
  --mode core-minimal-20k-s1 \
  --repeat 10 \
  --warmup 0 \
  --cooldown 0 \
  --pin-cpu 0 \
  --active-processor-count 1 \
  --output-root "$RUN_ROOT/model-speed/benchmarks" \
  2>&1 | tee "$RUN_ROOT/logs/command.log"

# Write a run manifest before syncing.
S3_PREFIX="s3://uk-housing-market-abm-artifacts-prod-<account-id>/experiments/manual/<yyyy-mm-dd>/$RUN_ID/"
INSTANCE_TYPE="$(
  TOKEN="$(curl -sX PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')"
  curl -sH "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-type
)"
jq -n \
  --arg runId "$RUN_ID" \
  --arg commit "$(git rev-parse HEAD)" \
  --arg branch "$(git branch --show-current)" \
  --arg dirtyStatus "$(git status --short)" \
  --arg command "bash scripts/model/run-speed-benchmark.sh ...; see logs/command.log" \
  --arg inputSnapshot "v0" \
  --arg instanceType "$INSTANCE_TYPE" \
  --arg java "$(java -version 2>&1 | head -1)" \
  --arg maven "$(mvn --version | head -1)" \
  --arg node "$(node --version 2>/dev/null || true)" \
  --arg python "$(python3 --version 2>/dev/null || true)" \
  --arg s3Prefix "$S3_PREFIX" \
  '{
    runId: $runId,
    commit: $commit,
    branch: $branch,
    dirtyStatus: $dirtyStatus,
    command: $command,
    inputSnapshot: $inputSnapshot,
    instanceType: $instanceType,
    java: $java,
    maven: $maven,
    node: $node,
    python: $python,
    s3Prefix: $s3Prefix
  }' > "$RUN_ROOT/run-manifest.json"

# Record output hashes for the current run only, excluding the hash file itself.
find "$RUN_ROOT" -type f ! -name output-manifest.sha256 -print0 \
  | sort -z | xargs -0 sha256sum > "$RUN_ROOT/output-manifest.sha256"

# Sync only this run, not the whole repository Results/ directory.
aws s3 sync "$RUN_ROOT/" "$S3_PREFIX" --region eu-west-2

# Stop the instance from local machine after outputs are synced.
aws ec2 stop-instances --instance-ids <instance-id> --region eu-west-2
```

Important operating rules:

- Never leave the experiment runner running idle.
- Sync outputs and manifests to S3 before stopping or terminating.
- Do not rely on instance store for persistent outputs.
- Do not upload `private-datasets/` to the public frontend bucket, public API image, or artifacts bucket unless a task explicitly requires a private-data workflow.
- Run model-speed and regression checks serially in one workspace because Maven/classpath state is shared.
- Use `c7i.8xlarge` only when the run is actually parallelized through deterministic sharding, independent worktrees, or independent containers.
- For long independent sweeps, move to AWS Batch later with deterministic sharding and up to 20 workers, matching the project agent guidance.

## Supporting Reference: Operational Checks
Minimum observability before treating the setup as operational:

- AWS Budgets actual and forecast alerts.
- EC2 running-hour alerts.
- EventBridge/SSM automatic stop rule for the tagged runner.
- ECS task logs with retention set to a short starter value such as 7-14 days.
- ALB 5xx and target health alarms if ECS/Fargate is public.
- CloudFront access logs only if needed; avoid adding logging cost by default.
- S3 bucket lifecycle and incomplete multipart cleanup enabled.
- Session Manager works without SSH or public inbound ports.

## Future Upgrade Path
After the v1 system is stable:

1. Add infrastructure-as-code with AWS CDK or Terraform.
2. Add GitHub Actions deployment for frontend and API using OIDC, ECR push, S3 sync, CloudFront invalidation, and ECS service update.
3. Add dashboard read-only result browsing from the S3 artifacts bucket.
4. Move EC2 manual runs to AWS Batch using the same experiment container and S3 artifact layout.
5. Consider Graviton (`c7g.8xlarge`) only after regression checks prove cloud-run output compatibility.

## Operational Completion Checklist
The setup is complete when:

- frontend loads at `https://<cloudfront-domain-or-custom-domain>`
- frontend calls the API endpoint successfully
- no-custom-domain ECS deployments route browser API calls through same-origin CloudFront behaviors instead of direct HTTP ALB calls
- ECS/Fargate or grandfathered App Runner returns healthy `/healthz`
- production API has `DASHBOARD_ENABLE_MODEL_RUNS=false`
- `.dockerignore` excludes private datasets, generated outputs, local dependency folders, local env files, and operational agent material before public image builds
- API image excludes Java, Maven, git, `private-datasets/`, local `node_modules`, and generated `Results/`
- CloudFront cannot be bypassed to read frontend bucket objects directly
- CloudFront SPA fallback maps `403` and `404` to `/index.html`
- artifacts bucket is private, lifecycle-managed, and versioned or uses immutable run prefixes
- EC2 runner can be started, accessed through Session Manager, and stopped without SSH
- AWS CLI v2 is installed and verified on the runner
- SSM agent/session readiness is verified on the runner
- runner role can write only the intended artifacts prefixes and cannot delete experiment evidence broadly
- every remote run uploads `run-manifest.json` and `output-manifest.sha256`
- sync commands upload only the current run output, not all of `Results/`
- AWS Budget alerts and EC2 running-hour alerts are configured
- EventBridge/SSM automatic stop is configured for the runner
- no NAT Gateway, RDS, Elastic IP, public S3 bucket, or always-on experiment compute exists in v1

## References
- AWS App Runner availability change: <https://docs.aws.amazon.com/apprunner/latest/dg/apprunner-availability-change.html>
- AWS App Runner source image services: <https://docs.aws.amazon.com/apprunner/latest/dg/service-source-image.html>
- AWS App Runner environment variables and secrets: <https://docs.aws.amazon.com/apprunner/latest/dg/env-variable.html>
- Amazon ECS pricing: <https://aws.amazon.com/ecs/pricing/>
- Amazon ECS Express Mode migration from App Runner: <https://docs.aws.amazon.com/apprunner/latest/dg/apprunner-availability-change.html>
- Elastic Load Balancing pricing: <https://aws.amazon.com/elasticloadbalancing/pricing/>
- Amazon ECR private registry: <https://docs.aws.amazon.com/AmazonECR/latest/userguide/Registries.html>
- Pushing images to Amazon ECR: <https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-push.html>
- CloudFront OAC for private S3 origins: <https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html>
- S3 pricing: <https://aws.amazon.com/s3/pricing/>
- S3 Lifecycle management: <https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lifecycle-mgmt.html>
- EC2 On-Demand pricing: <https://aws.amazon.com/ec2/pricing/on-demand/>
- EC2 C7i instance specs: <https://aws.amazon.com/ec2/instance-types/c7i/>
- EC2 stop/start behavior: <https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/Stop_Start.html>
- Systems Manager Session Manager: <https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html>
- AWS Budgets: <https://aws.amazon.com/documentation-overview/budgets/>
- Route 53 pricing: <https://aws.amazon.com/route53/pricing/>
- Route 53 domain registration and AWS credits note: <https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/domain-register.html>
- AWS Pricing Calculator: <https://aws.amazon.com/aws-cost-management/aws-pricing-calculator/pricing/>
