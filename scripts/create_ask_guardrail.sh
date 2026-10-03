#!/usr/bin/env bash
# Creates the Bedrock guardrail the Ask chat uses on questions and answers and publishes version 1.
# Prints the guardrail id to pass to `sam deploy` as AskGuardrailId.
set -euo pipefail
REGION="${AWS_REGION:-us-east-1}"
# Personal details are checked in questions only: answers name cities and companies from job posts.
PII=$(python3 -c 'import json; print(json.dumps({"piiEntitiesConfig": [
  {"type": t, "action": a, "inputAction": a, "outputAction": "NONE", "inputEnabled": True, "outputEnabled": False}
  for t, a in [("NAME", "ANONYMIZE"), ("EMAIL", "ANONYMIZE"), ("PHONE", "ANONYMIZE"), ("ADDRESS", "ANONYMIZE"),
               ("AGE", "ANONYMIZE"), ("US_SOCIAL_SECURITY_NUMBER", "BLOCK")]]}))')
ID=$(aws bedrock create-guardrail --region "$REGION" --name healthsurface-ask-guardrail \
  --description "Ask chat: no personal medical advice, diagnosis or dosing; mask personal details; block prompt attacks." \
  --blocked-input-messaging "BLOCKED_BY_GUARDRAIL" \
  --blocked-outputs-messaging "BLOCKED_BY_GUARDRAIL" \
  --topic-policy-config '{"topicsConfig":[
    {"name":"MedicalAdvice","definition":"Personalized medical advice, treatment or supplement recommendations, or medication dosing directed at a person.","examples":["Should I take magnesium for sleep?","You should take 500 mg twice a day.","What will help me lose weight?"],"type":"DENY"},
    {"name":"Diagnosis","definition":"Telling a person what condition or disease they have, or interpreting their symptoms or test results.","examples":["Do my symptoms mean I have diabetes?","What does my A1C of 7 mean for me?"],"type":"DENY"}]}' \
  --content-policy-config '{"filtersConfig":[{"type":"HATE","inputStrength":"MEDIUM","outputStrength":"MEDIUM"},{"type":"VIOLENCE","inputStrength":"MEDIUM","outputStrength":"MEDIUM"},{"type":"SEXUAL","inputStrength":"MEDIUM","outputStrength":"MEDIUM"},{"type":"INSULTS","inputStrength":"MEDIUM","outputStrength":"MEDIUM"},{"type":"MISCONDUCT","inputStrength":"MEDIUM","outputStrength":"MEDIUM"},{"type":"PROMPT_ATTACK","inputStrength":"HIGH","outputStrength":"NONE"}]}' \
  --sensitive-information-policy-config "$PII" \
  --query guardrailId --output text)
aws bedrock create-guardrail-version --region "$REGION" --guardrail-identifier "$ID" >/dev/null
echo "$ID"
