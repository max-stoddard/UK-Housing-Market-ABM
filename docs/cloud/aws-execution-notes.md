# AWS Execution Notes
Author: Max Stoddard

Last updated: 2026-05-08

## Purpose
This file is the durable handoff log for `docs/cloud/recommended-aws-setup.md`.

Every agent executing an AWS rollout phase must update this file before moving to the next phase. Do not write secrets, AWS access keys, session tokens, passwords, private dataset contents, or sensitive personal details here.

## Global State
- AWS account ID:
- Region: `eu-west-2`
- Public site URL:
- API endpoint:
- Artifacts bucket:
- Frontend bucket:
- CloudFront distribution ID:
- ECR repository:
- ECS cluster/service:
- Runner instance IDs:
- Current runner state:
- Current always-on monthly cost estimate:
- Last forbidden-resource check:

## Phase Entry Template
Copy this section for each executed phase.

```text
## Phase <n>: <title>
- Date:
- Executor:
- AWS account ID:
- Region:
- Git commit:
- Starting state:
- Commands run:
- Resources created or changed:
- Resource IDs, ARNs, URLs, image digests:
- Cost check:
- Security check:
- Validation summary:
- Rollback, cleanup, or stop action:
- Acceptance gate result:
- Open blockers:
- Next-phase readiness:
```

## Phase 1: Repo And Notes Setup
- Date:
- Executor:
- AWS account ID:
- Region:
- Git commit:
- Starting state:
- Commands run:
- Resources created or changed:
- Resource IDs, ARNs, URLs, image digests:
- Cost check:
- Security check:
- Validation summary:
- Rollback, cleanup, or stop action:
- Acceptance gate result:
- Open blockers:
- Next-phase readiness:
