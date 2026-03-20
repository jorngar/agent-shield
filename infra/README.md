# infra (AWS CDK)

This CDK app deploys an **EC2 backend** behind an **ALB** plus an **API Gateway** proxy, along with an **RDS Postgres** instance.

It is intended to support the local `ai-agent` wrapper’s approval flow by exposing backend API routes (in this repo the local backend is the Express service).

## Deploy

From repo root:
1. `cd infra`
2. `npm install`
3. `npm run build`
4. `npx cdk synth`
5. `npx cdk deploy`

## Required environment

CDK typically relies on:
- `CDK_DEFAULT_ACCOUNT`
- `CDK_DEFAULT_REGION`

The backend container receives:
- `OLLAMA_HOST` (optional; falls back to `http://localhost:11434` in the current stack)

## Required CDK parameters (passed to the stack)

The backend EC2 instance needs:
- `GitHubRepo`: `owner/repo`
- `GitHubTokenSecretArn`: Secrets Manager secret ARN containing a GitHub token (`SecretString` should be the token)
- `FirebaseServiceAccountSecretArn`: Secrets Manager secret ARN containing the Firebase service account JSON (`SecretString` should be the JSON)
- `BedrockFoundationModelArn`: the Bedrock foundation model ARN to allow for `bedrock:InvokeModel`

## Current stack (what it provisions)

Flat summary:
- VPC (public + private subnets)
- EC2 instance running the backend (clones private GitHub + runs `npm install` + starts `server/`)
- Application Load Balancer (ALB) + health check at `/api/health`
- API Gateway REST API that proxies `/{proxy+}` to the ALB
- RDS Postgres + Secrets Manager secret for database password

## Bedrock + Firebase note (important)

This repo’s current `infra/` stack does not yet create AWS Bedrock resources or any Firebase integration.
If/when that is added, it should be implemented in `infra/lib/agent-shield-stack.ts`.

### Current implementation note

The stack currently:
- grants the EC2 instance permission to invoke Bedrock (`bedrock:InvokeModel`) for the provided model ARN
- passes Firebase integration via a Secrets Manager secret ARN for the service account JSON

You still need to ensure the backend runtime code uses those env vars and initializes Firebase + Bedrock accordingly.
