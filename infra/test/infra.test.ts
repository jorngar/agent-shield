import * as cdk from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
import { AgentShieldStack } from '../lib/agent-shield-stack';

const synthTemplate = (): Template => {
  const app = new cdk.App();
  const stack = new AgentShieldStack(app, 'TestAgentShieldStack', {
    env: { account: '123456789012', region: 'ap-southeast-1' },
  });
  return Template.fromStack(stack);
};

describe('AgentShieldStack', () => {
  test('creates API Gateway HTTP API with VPC link integration', () => {
    const template = synthTemplate();

    template.resourceCountIs('AWS::ApiGatewayV2::Api', 1);
    template.resourceCountIs('AWS::ApiGatewayV2::VpcLink', 1);
    template.hasResourceProperties('AWS::ApiGatewayV2::Integration', {
      ConnectionType: 'VPC_LINK',
      IntegrationType: 'HTTP_PROXY',
    });
  });

  test('uses an internal ALB and keeps Ollama local-only', () => {
    const template = synthTemplate();

    template.hasResourceProperties('AWS::ElasticLoadBalancingV2::LoadBalancer', {
      Scheme: 'internal',
      Type: 'application',
    });

    const renderedTemplate = JSON.stringify(template.toJSON());
    expect(renderedTemplate).not.toContain('OLLAMA_HOST');
    expect(renderedTemplate).not.toContain(`"username":"admin"`);
    expect(renderedTemplate).toContain('agentshield_app');
    expect(renderedTemplate).toContain('BEDROCK_FOUNDATION_MODEL_ID');
    expect(renderedTemplate).toContain('foundation-model/');
    expect(renderedTemplate).toContain('FIREBASE_SERVICE_ACCOUNT_SECRET_ARN');
    expect(renderedTemplate).toContain('TINYFISH_API_KEY');
    expect(renderedTemplate).toContain('VULNERABILITY_INTEL_TABLE');
  });

  test('bootstraps the backend with fail-fast logging and systemd', () => {
    const template = synthTemplate();
    const renderedTemplate = JSON.stringify(template.toJSON());

    expect(renderedTemplate).toContain('set -xeuo pipefail');
    expect(renderedTemplate).toContain('/var/log/agent-shield-bootstrap.log');
    expect(renderedTemplate).toContain('yum install -y git jq');
    expect(renderedTemplate).not.toContain('yum install -y git curl jq');
    expect(renderedTemplate).toContain('/etc/systemd/system/agent-shield-backend.service');
    expect(renderedTemplate).toContain('/etc/systemd/system/agent-shield-vulnerability-refresh.service');
    expect(renderedTemplate).toContain('/etc/systemd/system/agent-shield-vulnerability-refresh.timer');
    expect(renderedTemplate).toContain('systemctl enable --now agent-shield-backend.service');
    expect(renderedTemplate).toContain('systemctl enable --now agent-shield-vulnerability-refresh.timer');
    expect(renderedTemplate).toContain('OnUnitActiveSec=2d');
    expect(renderedTemplate).toContain('WorkingDirectory=/opt/agent-shield/server');
    expect(renderedTemplate).toContain('ExecStart=/usr/bin/npm run vulnerabilities:refresh');
    expect(renderedTemplate).not.toContain('ExecStart=/usr/bin/npm run start --workspace=server');
    expect(renderedTemplate).toContain('TinyfishApiKeySecretArn');
    expect(renderedTemplate).toContain('aws secretsmanager get-secret-value --secret-id');
  });
});
