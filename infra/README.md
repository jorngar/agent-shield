# infra (AWS CDK)

This CDK app deploys the AWS backend for Agent Shield with:
- API Gateway HTTP API
- VPC Link to an internal ALB
- private EC2 backend (Node.js/Express)
- private RDS Postgres
- a systemd timer that refreshes Tinyfish vulnerability intel every 2 days

The local `ai-agent` wrapper (running with local Ollama) calls this backend for second-stage validation and policy/knowledge checks.

## Deploy

From repo root:
1. `cd infra`
2. `npm install`
3. `npm run build`
4. `npm test`
5. `npx cdk synth`
6. `npx cdk deploy AgentShieldStack`

## Required environment

CDK typically relies on:
- `CDK_DEFAULT_ACCOUNT`
- `CDK_DEFAULT_REGION`

## Required CDK parameters (passed to the stack)

The backend EC2 instance needs:
- `GitHubRepo`: `owner/repo`
- `GitHubTokenSecretArn`: Secrets Manager secret ARN containing a GitHub token (`SecretString` should be the token)
- `FirebaseServiceAccountSecretArn`: Secrets Manager secret ARN containing the Firebase service account JSON (`SecretString` should be the JSON)
- `TinyfishApiKeySecretArn`: Secrets Manager secret ARN containing the Tinyfish API key (`SecretString` should be the raw key)
- `BedrockFoundationModelArn`: the Bedrock foundation model ARN to allow for `bedrock:InvokeModel`

## Current stack (what it provisions)

Flat summary:
- VPC (public + private subnets)
- EC2 instance running the backend (clones private GitHub + runs `npm install` + starts `server/`)
- Internal Application Load Balancer (ALB) + health check at `/api/health`
- API Gateway HTTP API with VPC Link private integration to ALB
- RDS Postgres + Secrets Manager secret for database password
- systemd timer/service on the backend host for scheduled vulnerability refresh

## Runtime note

This stack does **not** deploy Ollama in AWS. Keep Ollama local with the wrapper, and only expose backend validation APIs through API Gateway.
