#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib/core';
import { AgentShieldStack } from '../lib/agent-shield-stack';

const app = new cdk.App();

const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT || process.env.AWS_ACCOUNT_ID,
  region: process.env.CDK_DEFAULT_REGION || 'us-east-1',
};

new AgentShieldStack(app, 'AgentShieldStack', {
  env,
  description: 'Agent Shield Infrastructure',
});
