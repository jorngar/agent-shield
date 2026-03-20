import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as targets from 'aws-cdk-lib/aws-elasticloadbalancingv2-targets';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import { Construct } from 'constructs';

export class AgentShieldStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const projectName = 'agent-shield';
    const backendPort = 3000;

    const vpc = new ec2.Vpc(this, 'AgentShieldVPC', {
      cidr: '10.0.0.0/16',
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
        secretStringTemplate: JSON.stringify({ username: 'admin' }),
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
      internetFacing: true,
      loadBalancerName: `${projectName}-alb`,
    });

    const listener = alb.addListener('BackendListener', {
      port: 80,
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

    const backendInstance = new ec2.Instance(this, 'BackendInstance', {
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MICRO),
      role: backendInstanceRole,
      securityGroup: backendSecurityGroup,
      machineImage: ec2.MachineImage.latestAmazonLinux2023(),
    });

    // Allow ALB -> instance connectivity.
    backendInstance.connections.allowFrom(alb, ec2.Port.tcp(backendPort));

    backendInstance.addUserData(
      '#!/bin/bash -xe',
      'export DEBIAN_FRONTEND=noninteractive',
      'yum update -y',
      'yum install -y git curl jq',
      // Install Node.js (LTS) via NodeSource.
      'curl -fsSL https://rpm.nodesource.com/setup_20.x | bash -',
      'yum install -y nodejs',
      'npm --version',
      'mkdir -p /opt',
      'cd /opt',
      // Pull GitHub token from Secrets Manager.
      `GITHUB_TOKEN=$(aws secretsmanager get-secret-value --secret-id ${gitHubTokenSecretArn.valueAsString} --query SecretString --output text)`,
      // Use `$GITHUB_TOKEN` from the shell (not a TS interpolation).
      `git clone --depth 1 https://x-access-token:$GITHUB_TOKEN@github.com/${gitHubRepo.valueAsString}.git agent-shield`,
      'cd agent-shield',
      // Install deps (workspaces)
      'npm install',
      // Start backend (Express) on port 3000.
      `export PORT=${backendPort}`,
      `export DATABASE_HOST=${database.instanceEndpoint.hostname}`,
      'export DATABASE_PORT=5432',
      'export DATABASE_NAME=agentshield',
      'export DATABASE_USERNAME=admin',
      `export DATABASE_PASSWORD=$(aws secretsmanager get-secret-value --secret-id ${dbSecret.secretArn} --query SecretString --output text | jq -r .password)`,
      'export OLLAMA_HOST=http://localhost:11434',
      `export FIREBASE_SERVICE_ACCOUNT_SECRET_ARN=${firebaseServiceAccountSecretArn.valueAsString}`,
      `export BEDROCK_FOUNDATION_MODEL_ARN=${bedrockFoundationModelArn.valueAsString}`,
      // Keep server alive
      `nohup npm run start --workspace=server > /var/log/agent-shield-backend.log 2>&1 &`,
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

    const api = new apigateway.RestApi(this, 'AgentShieldApi', {
      restApiName: `${projectName}-api`,
      description: 'Agent Shield API',
      defaultCorsPreflightOptions: {
        allowOrigins: apigateway.Cors.ALL_ORIGINS,
        allowMethods: apigateway.Cors.ALL_METHODS,
      },
    });

    const apiIntegration = new apigateway.Integration({
      type: apigateway.IntegrationType.HTTP_PROXY,
      uri: `http://${alb.loadBalancerDnsName}/`,
      integrationHttpMethod: 'ANY',
    });

    api.root.addMethod('ANY', apiIntegration);
    api.root.addProxy({
      defaultIntegration: apiIntegration,
    });

    new cdk.CfnOutput(this, 'ApiEndpoint', {
      value: api.url,
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
      description: 'Load Balancer DNS',
    });
  }
}
