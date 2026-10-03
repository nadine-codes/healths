#!/usr/bin/env bash
# Creates the Bedrock guardrail HealthSurface uses on model output and publishes version 1.
# Prints the guardrail id to pass to `sam deploy` as GuardrailId.
set -euo pipefail
REGION="${AWS_REGION:-us-east-1}"
ID=$(aws bedrock create-guardrail --region "$REGION" --name healthsurface-guardrail \
  --description "No medical advice or dosing in summaries; block harmful content." \
  --blocked-input-messaging "This content cannot be processed." \
  --blocked-outputs-messaging "BLOCKED_BY_GUARDRAIL" \
  --topic-policy-config '{"topicsConfig":[{"name":"MedicalAdvice","definition":"Personalized medical advice, diagnosis, treatment recommendations, or medication dosing instructions directed at a reader.","examples":["You should take 500 mg twice a day.","Stop taking your medication and try this instead.","Ask your doctor for this drug, it will cure you."],"type":"DENY"}]}' \
  --content-policy-config '{"filtersConfig":[{"type":"HATE","inputStrength":"MEDIUM","outputStrength":"MEDIUM"},{"type":"VIOLENCE","inputStrength":"MEDIUM","outputStrength":"MEDIUM"},{"type":"SEXUAL","inputStrength":"MEDIUM","outputStrength":"MEDIUM"},{"type":"INSULTS","inputStrength":"MEDIUM","outputStrength":"MEDIUM"},{"type":"MISCONDUCT","inputStrength":"MEDIUM","outputStrength":"MEDIUM"},{"type":"PROMPT_ATTACK","inputStrength":"HIGH","outputStrength":"NONE"}]}' \
  --query guardrailId --output text)
aws bedrock create-guardrail-version --region "$REGION" --guardrail-identifier "$ID" >/dev/null
echo "$ID"
