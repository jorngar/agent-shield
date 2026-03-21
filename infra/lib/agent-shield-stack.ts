import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as targets from 'aws-cdk-lib/aws-elasticloadbalancingv2-targets';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as apigwv2 from 'aws-cdk-lib/aws-apigatewayv2';
import * as apigwv2Integrations from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import { Construct } from 'constructs';

export class AgentShieldStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const projectName = 'agent-shield';
    const backendPort = 3000;
    const dbUsername = 'agentshield_app';
    const installDir = '/opt/agent-shield';

    const vpc = new ec2.Vpc(this, 'AgentShieldVPC', {
      ipAddresses: ec2.IpAddresses.cidr('10.0.0.0/16'),
      maxAzs: 2,
      natGateways: 1,
      subnetConfiguration: [
        {
          cidrMask: 24,
          name: 'Public',
          subnetType: ec2.SubnetType.PUBLIC,
        },
        {
          cidrMask: 24,
          name: 'Private',
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
        },
      ],
    });

    const dbSecret = new secretsmanager.Secret(this, 'DatabaseSecret', {
      secretName: `${projectName}/db-credentials`,
      generateSecretString: {
        secretStringTemplate: JSON.stringify({ username: dbUsername }),
        excludePunctuation: true,
        includeSpace: false,
        generateStringKey: 'password',
        passwordLength: 16,
      },
    });

    const database = new rds.DatabaseInstance(this, 'AgentShieldDatabase', {
      engine: rds.DatabaseInstanceEngine.postgres({
        version: rds.PostgresEngineVersion.VER_15,
      }),
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MICRO),
      vpc,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
      },
      credentials: rds.Credentials.fromSecret(dbSecret),
      databaseName: 'agentshield',
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    const alb = new elbv2.ApplicationLoadBalancer(this, 'BackendALB', {
      vpc,
      internetFacing: false,
      loadBalancerName: `${projectName}-alb`,
    });

    const listener = alb.addListener('BackendListener', {
      port: 80,
      open: false,
    });

    const gitHubRepo = new cdk.CfnParameter(this, 'GitHubRepo', {
      type: 'String',
      description: 'Private GitHub repo in the format owner/repo (HTTPS clone)',
    });

    const gitHubTokenSecretArn = new cdk.CfnParameter(this, 'GitHubTokenSecretArn', {
      type: 'String',
      description: 'Secrets Manager secret ARN containing a GitHub token (SecretString should be the token)',
    });

    const firebaseServiceAccountSecretArn = new cdk.CfnParameter(
      this,
      'FirebaseServiceAccountSecretArn',
      {
        type: 'String',
        description:
          'Secrets Manager secret ARN containing the Firebase service account JSON (SecretString should be the JSON)',
      },
    );

    const tinyfishApiKeySecretArn = new cdk.CfnParameter(this, 'TinyfishApiKeySecretArn', {
      type: 'String',
      description:
        'Secrets Manager secret ARN containing the Tinyfish API key (SecretString should be the raw key)',
    });

    const bedrockFoundationModelArn = new cdk.CfnParameter(this, 'BedrockFoundationModelArn', {
      type: 'String',
      description: 'Bedrock foundation model ARN to allow for InvokeModel',
    });

    const backendInstanceRole = new iam.Role(this, 'BackendInstanceRole', {
      assumedBy: new iam.ServicePrincipal('ec2.amazonaws.com'),
    });

    backendInstanceRole.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSSMManagedInstanceCore'),
    );

    // Allow backend to read Secrets Manager values (GitHub token + Firebase service account + DB password).
    backendInstanceRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ['secretsmanager:GetSecretValue'],
        resources: [
          dbSecret.secretArn,
          gitHubTokenSecretArn.valueAsString,
          firebaseServiceAccountSecretArn.valueAsString,
          tinyfishApiKeySecretArn.valueAsString,
        ],
      }),
    );

    // Allow backend to call Bedrock.
    backendInstanceRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ['bedrock:InvokeModel'],
        resources: [bedrockFoundationModelArn.valueAsString],
      }),
    );

    const backendSecurityGroup = new ec2.SecurityGroup(this, 'BackendInstanceSG', {
      vpc,
      allowAllOutbound: true,
    });

    // Keep backend bootstrap replaceable so broken first-boot user data can be
    // recovered by redeploying the stack instead of hand-repairing the host.
    const backendInstance = new ec2.Instance(this, 'BackendInstanceV3', {
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MICRO),
      role: backendInstanceRole,
      securityGroup: backendSecurityGroup,
      machineImage: ec2.MachineImage.latestAmazonLinux2023(),
      userDataCausesReplacement: true,
    });

    // Allow ALB -> instance connectivity.
    backendInstance.connections.allowFrom(alb, ec2.Port.tcp(backendPort));
    database.connections.allowDefaultPortFrom(
      backendInstance,
      'Allow backend instance to connect to Postgres',
    );

    backendInstance.addUserData(
      'set -xeuo pipefail',
      'exec > >(tee /var/log/agent-shield-bootstrap.log | logger -t user-data -s 2>/dev/console) 2>&1',
      'export DEBIAN_FRONTEND=noninteractive',
      'yum update -y',
      'yum install -y git jq',
      // Install Node.js (LTS) via NodeSource.
      'curl -fsSL https://rpm.nodesource.com/setup_20.x | bash -',
      'yum install -y nodejs',
      'npm --version',
      'mkdir -p /opt',
      'cd /opt',
      // Pull GitHub token from Secrets Manager.
      `GITHUB_TOKEN=$(aws secretsmanager get-secret-value --secret-id ${gitHubTokenSecretArn.valueAsString} --query SecretString --output text)`,
      `TINYFISH_API_KEY=$(aws secretsmanager get-secret-value --secret-id ${tinyfishApiKeySecretArn.valueAsString} --query SecretString --output text)`,
      // Use `$GITHUB_TOKEN` from the shell (not a TS interpolation).
      `rm -rf ${installDir}`,
      `git clone --depth 1 https://x-access-token:$GITHUB_TOKEN@github.com/${gitHubRepo.valueAsString}.git ${installDir}`,
      `cd ${installDir}/server`,
      // Install backend deps.
      'npm install',
      `cat <<EOF > /etc/agent-shield-backend.env`,
      `PORT=${backendPort}`,
      `DATABASE_HOST=${database.instanceEndpoint.hostname}`,
      'DATABASE_PORT=5432',
      'DATABASE_NAME=agentshield',
      `DATABASE_USERNAME=${dbUsername}`,
      `DATABASE_PASSWORD=$(aws secretsmanager get-secret-value --secret-id ${dbSecret.secretArn} --query SecretString --output text | jq -r .password)`,
      `FIREBASE_SERVICE_ACCOUNT_SECRET_ARN=${firebaseServiceAccountSecretArn.valueAsString}`,
      'TINYFISH_API_KEY=$TINYFISH_API_KEY',
      'TINYFISH_RESEARCH_URL=https://www.google.com/',
      'TINYFISH_BROWSER_PROFILE=lite',
      'VULNERABILITY_REFRESH_LIMIT=100',
      'VULNERABILITY_INTEL_TABLE=agent_vulnerability_intel',
      `BEDROCK_FOUNDATION_MODEL_ARN=${bedrockFoundationModelArn.valueAsString}`,
      'EOF',
      `cat <<'EOF' > /etc/systemd/system/agent-shield-backend.service`,
      '[Unit]',
      'Description=Agent Shield backend',
      'After=network-online.target',
      'Wants=network-online.target',
      '',
      '[Service]',
      'Type=simple',
      `WorkingDirectory=${installDir}/server`,
      'EnvironmentFile=/etc/agent-shield-backend.env',
      'ExecStart=/usr/bin/npm run start',
      'Restart=always',
      'RestartSec=5',
      'StandardOutput=append:/var/log/agent-shield-backend.log',
      'StandardError=append:/var/log/agent-shield-backend.log',
      '',
      '[Install]',
      'WantedBy=multi-user.target',
      'EOF',
      `cat <<'EOF' > /etc/systemd/system/agent-shield-vulnerability-refresh.service`,
      '[Unit]',
      'Description=Agent Shield vulnerability intel refresh',
      'After=network-online.target agent-shield-backend.service',
      'Wants=network-online.target',
      '',
      '[Service]',
      'Type=oneshot',
      `WorkingDirectory=${installDir}/server`,
      'EnvironmentFile=/etc/agent-shield-backend.env',
      'ExecStart=/usr/bin/npm run vulnerabilities:refresh',
      'StandardOutput=append:/var/log/agent-shield-vulnerability-refresh.log',
      'StandardError=append:/var/log/agent-shield-vulnerability-refresh.log',
      'EOF',
      `cat <<'EOF' > /etc/systemd/system/agent-shield-vulnerability-refresh.timer`,
      '[Unit]',
      'Description=Run Agent Shield vulnerability intel refresh every 2 days',
      '',
      '[Timer]',
      'OnBootSec=10min',
      'OnUnitActiveSec=2d',
      'Persistent=true',
      'Unit=agent-shield-vulnerability-refresh.service',
      '',
      '[Install]',
      'WantedBy=timers.target',
      'EOF',
      'systemctl daemon-reload',
      'systemctl enable --now agent-shield-backend.service',
      'systemctl enable --now agent-shield-vulnerability-refresh.timer',
      'systemctl status --no-pager agent-shield-backend.service',
      'systemctl status --no-pager agent-shield-vulnerability-refresh.timer || true',
    );

    listener.addTargets('BackendTargets', {
      port: backendPort,
      protocol: elbv2.ApplicationProtocol.HTTP,
      targets: [new targets.InstanceTarget(backendInstance, backendPort)],
      healthCheck: {
        path: '/api/health',
        interval: cdk.Duration.seconds(30),
      },
    });

    const apiGatewayVpcLinkSG = new ec2.SecurityGroup(this, 'ApiGatewayVpcLinkSG', {
      vpc,
      allowAllOutbound: true,
      description: 'Security group for API Gateway VPC link ENIs',
    });

    alb.connections.allowFrom(
      apiGatewayVpcLinkSG,
      ec2.Port.tcp(80),
      'Allow API Gateway VPC link to reach internal ALB',
    );

    const vpcLink = new apigwv2.VpcLink(this, 'BackendVpcLink', {
      vpc,
      subnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      securityGroups: [apiGatewayVpcLinkSG],
      vpcLinkName: `${projectName}-api-vpc-link`,
    });

    const api = new apigwv2.HttpApi(this, 'AgentShieldApi', {
      apiName: `${projectName}-api`,
      description: 'Agent Shield API',
      corsPreflight: {
        allowHeaders: ['*'],
        allowMethods: [apigwv2.CorsHttpMethod.ANY],
        allowOrigins: ['*'],
      },
    });

    const apiIntegration = new apigwv2Integrations.HttpAlbIntegration(
      'BackendAlbIntegration',
      listener,
      {
        vpcLink,
      },
    );

    api.addRoutes({
      path: '/',
      methods: [apigwv2.HttpMethod.ANY],
      integration: apiIntegration,
    });

    api.addRoutes({
      path: '/{proxy+}',
      methods: [apigwv2.HttpMethod.ANY],
      integration: apiIntegration,
    });

    new cdk.CfnOutput(this, 'ApiEndpoint', {
      value: api.apiEndpoint,
      description: 'Agent Shield API Endpoint',
    });

    new cdk.CfnOutput(this, 'DatabaseEndpoint', {
      value: database.instanceEndpoint.hostname,
      description: 'Database Endpoint',
    });

    new cdk.CfnOutput(this, 'ClusterName', {
      value: backendInstance.instanceId,
      description: 'Backend instance id',
    });

    new cdk.CfnOutput(this, 'LoadBalancerDns', {
      value: alb.loadBalancerDnsName,
      description: 'Internal Load Balancer DNS',
    });
  }
}
