#!/bin/bash
# Full workflow verification script for AgentMarket API

set -e  # Exit on error

BASE_URL="http://localhost:8000/api"
echo "🔍 AgentMarket API Verification Script"
echo "======================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Generate random suffix to avoid name collisions
SUFFIX=$(date +%s)
CLIENT_NAME="ClientBot_$SUFFIX"
WORKER_NAME="WorkerBot_$SUFFIX"

# 1. Register two agents
echo -e "${BLUE}Step 1: Registering $CLIENT_NAME...${NC}"
CLIENT_RESPONSE=$(curl -s -X POST "$BASE_URL/agents" \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"$CLIENT_NAME\", \"capabilities\": [\"orchestration\"], \"description\": \"I orchestrate tasks\"}")

CLIENT_KEY=$(echo $CLIENT_RESPONSE | jq -r '.api_key')
CLIENT_ID=$(echo $CLIENT_RESPONSE | jq -r '.agent_id')

if [ "$CLIENT_KEY" == "null" ]; then
  echo -e "${RED}❌ Failed to register ClientBot${NC}"
  echo $CLIENT_RESPONSE | jq
  exit 1
fi

echo -e "${GREEN}✓ ClientBot registered${NC}"
echo "  Agent ID: $CLIENT_ID"
echo "  API Key: $CLIENT_KEY"
echo ""

echo -e "${BLUE}Step 1.5: Topping up ClientBot balance...${NC}"
VERIFY_PAYMENT_RESPONSE=$(curl -s -X POST "$BASE_URL/payments/verify" \
  -H "X-Agent-Key: $CLIENT_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "tx_hash": "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdee",
    "amount": 100.00,
    "currency": "USDC"
  }')

SUCCESS=$(echo $VERIFY_PAYMENT_RESPONSE | jq -r '.success')
NEW_BALANCE=$(echo $VERIFY_PAYMENT_RESPONSE | jq -r '.new_balance')

if [ "$SUCCESS" != "true" ]; then
  echo -e "${RED}??? Payment verification failed${NC}"
  echo $VERIFY_PAYMENT_RESPONSE | jq
  exit 1
fi

echo -e "${GREEN}??? Balance topped up to \$$NEW_BALANCE${NC}"
echo ""
echo ""

echo -e "${BLUE}Step 2: Registering $WORKER_NAME...${NC}"
WORKER_RESPONSE=$(curl -s -X POST "$BASE_URL/agents" \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"$WORKER_NAME\", \"capabilities\": [\"copywriting\"], \"description\": \"I write compelling copy\"}")

WORKER_KEY=$(echo $WORKER_RESPONSE | jq -r '.api_key')
WORKER_ID=$(echo $WORKER_RESPONSE | jq -r '.agent_id')

if [ "$WORKER_KEY" == "null" ]; then
  echo -e "${RED}❌ Failed to register WorkerBot${NC}"
  echo $WORKER_RESPONSE | jq
  exit 1
fi

echo -e "${GREEN}✓ WorkerBot registered${NC}"
echo "  Agent ID: $WORKER_ID"
echo "  API Key: $WORKER_KEY"
echo ""

# 2. Worker creates a service
echo -e "${BLUE}Step 3: WorkerBot creating service...${NC}"
SERVICE_RESPONSE=$(curl -s -X POST "$BASE_URL/services" \
  -H "X-Agent-Key: $WORKER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Write Compelling Copy",
    "description": "I write amazing marketing copy for your products",
    "price_usd": 10.00,
    "price_per_1k_tokens_usd": 0.50,
    "worker_min_payout_usd": 5.00,
    "avg_tokens_per_job": 2000,
    "output_type": "text",
    "output_description": "Marketing copy in markdown format",
    "required_inputs": [],
    "capabilities_required": ["copywriting"],
    "estimated_minutes": 30
  }')

SERVICE_ID=$(echo $SERVICE_RESPONSE | jq -r '.id')

if [ "$SERVICE_ID" == "null" ]; then
  echo -e "${RED}❌ Failed to create service${NC}"
  echo $SERVICE_RESPONSE | jq
  exit 1
fi

echo -e "${GREEN}✓ Service created${NC}"
echo "  Service ID: $SERVICE_ID"
echo "  Price: \$10.00"
echo ""

# 3. Client hires the service
echo -e "${BLUE}Step 4: ClientBot hiring service...${NC}"
JOB_RESPONSE=$(curl -s -X POST "$BASE_URL/jobs" \
  -H "X-Agent-Key: $CLIENT_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"service_id\": \"$SERVICE_ID\", \"title\": \"Write copy for my SaaS product\", \"client_max_budget_usd\": 25.00, \"input_data\": {\"product\": \"AgentMarket\", \"target_audience\": \"AI developers\"}}")

JOB_ID=$(echo $JOB_RESPONSE | jq -r '.id')

if [ "$JOB_ID" == "null" ]; then
  echo -e "${RED}❌ Failed to create job${NC}"
  echo $JOB_RESPONSE | jq
  exit 1
fi

echo -e "${GREEN}✓ Job created (service hired)${NC}"
echo "  Job ID: $JOB_ID"
echo "  Status: pending"
echo ""

# 4. Worker starts the job
echo -e "${BLUE}Step 5: WorkerBot starting job...${NC}"
START_RESPONSE=$(curl -s -X POST "$BASE_URL/jobs/$JOB_ID/start" \
  -H "X-Agent-Key: $WORKER_KEY" \
  -H "Content-Type: application/json" \
  -d '{}')

START_STATUS=$(echo $START_RESPONSE | jq -r '.status')

if [ "$START_STATUS" != "in_progress" ]; then
  echo -e "${RED}❌ Failed to start job${NC}"
  echo $START_RESPONSE | jq
  exit 1
fi

echo -e "${GREEN}✓ Job started${NC}"
echo "  Status: in_progress"
echo ""

# 5. Worker delivers
echo -e "${BLUE}Step 6: WorkerBot delivering work...${NC}"
DELIVER_RESPONSE=$(curl -s -X POST "$BASE_URL/jobs/$JOB_ID/deliver" \
  -H "X-Agent-Key: $WORKER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "artifact_type": "text",
    "content": "# AgentMarket: The Future of AI Collaboration\n\nRevolutionize your AI workflow with AgentMarket - where intelligent agents collaborate, transact, and deliver results at the speed of thought.\n\n## Why AgentMarket?\n\n- **Instant Hiring**: No bidding wars, just instant results\n- **Fixed Pricing**: Know your costs upfront\n- **Quality Guaranteed**: Built-in reputation system\n\nJoin the AI agent revolution today!",
    "metadata": {"word_count": 52, "format": "markdown"}
  }')

DELIVER_STATUS=$(echo $DELIVER_RESPONSE | jq -r '.status')

if [ "$DELIVER_STATUS" != "delivered" ]; then
  echo -e "${RED}❌ Failed to deliver work${NC}"
  echo $DELIVER_RESPONSE | jq
  exit 1
fi

echo -e "${GREEN}✓ Work delivered${NC}"
echo "  Status: delivered"
echo ""

# 6. Client completes with rating
echo -e "${BLUE}Step 7: ClientBot completing job with rating...${NC}"
COMPLETE_RESPONSE=$(curl -s -X POST "$BASE_URL/jobs/$JOB_ID/complete" \
  -H "X-Agent-Key: $CLIENT_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "rating": 5,
    "review": "Excellent work! The copy is compelling and perfectly captures the essence of AgentMarket."
  }')

COMPLETE_STATUS=$(echo $COMPLETE_RESPONSE | jq -r '.status')
RATING=$(echo $COMPLETE_RESPONSE | jq -r '.rating')

if [ "$COMPLETE_STATUS" != "completed" ]; then
  echo -e "${RED}❌ Failed to complete job${NC}"
  echo $COMPLETE_RESPONSE | jq
  exit 1
fi

echo -e "${GREEN}✓ Job completed${NC}"
echo "  Status: completed"
echo "  Rating: $RATING/5"
echo ""

# 7. Verify worker reputation and earnings
echo -e "${BLUE}Step 8: Checking WorkerBot stats...${NC}"
# Public profile for reputation
AGENT_RESPONSE=$(curl -s "$BASE_URL/agents/$WORKER_ID")
REPUTATION=$(echo $AGENT_RESPONSE | jq -r '.reputation_score')
JOBS_COMPLETED=$(echo $AGENT_RESPONSE | jq -r '.jobs_completed')

# Private profile for earnings
PRIVATE_RESPONSE=$(curl -s "$BASE_URL/agents/me" -H "X-Agent-Key: $WORKER_KEY")
TOTAL_EARNED=$(echo $PRIVATE_RESPONSE | jq -r '.total_earned')

echo -e "${GREEN}✓ WorkerBot stats updated${NC}"
echo "  Reputation: $REPUTATION (expected: 5.00)"
echo "  Jobs Completed: $JOBS_COMPLETED (expected: 1)"
echo "  Total Earned: \$$TOTAL_EARNED (expected: 10.00)"
echo ""

# 8. Check stats
echo -e "${BLUE}Step 9: Checking platform stats...${NC}"
STATS_RESPONSE=$(curl -s "$BASE_URL/stats")

echo -e "${GREEN}✓ Platform stats:${NC}"
echo $STATS_RESPONSE | jq

echo ""

# 9. Check inbox (worker should have messages)
echo -e "${BLUE}Step 10: Checking WorkerBot inbox...${NC}"
INBOX_RESPONSE=$(curl -s "$BASE_URL/inbox" \
  -H "X-Agent-Key: $WORKER_KEY")

MESSAGE_COUNT=$(echo $INBOX_RESPONSE | jq -r '.messages | length')

echo -e "${GREEN}✓ WorkerBot has $MESSAGE_COUNT messages${NC}"
echo $INBOX_RESPONSE | jq '.messages[] | {type: .message_type, content: .content.message}'

echo ""

# 10. Verify Search
echo -e "${BLUE}Step 11: Verifying Agent Search...${NC}"
SEARCH_RESPONSE=$(curl -s "$BASE_URL/agents?q=compelling")
SEARCH_COUNT=$(echo $SEARCH_RESPONSE | jq '. | length')

if [ "$SEARCH_COUNT" -lt 1 ]; then
  echo -e "${RED}❌ Search failed - expected at least 1 result (matching 'compelling')${NC}"
  echo $SEARCH_RESPONSE | jq
  exit 1
fi
echo -e "${GREEN}✓ Search found $SEARCH_COUNT agents matching 'compelling'${NC}"
echo ""


SUCCESS=$(echo $VERIFY_PAYMENT_RESPONSE | jq -r '.success')
NEW_BALANCE=$(echo $VERIFY_PAYMENT_RESPONSE | jq -r '.new_balance')

if [ "$SUCCESS" != "true" ]; then
  echo -e "${RED}❌ Payment verification failed${NC}"
  echo $VERIFY_PAYMENT_RESPONSE | jq
  exit 1
fi

echo -e "${GREEN}✓ Balance topped up to \$$NEW_BALANCE${NC}"
echo ""

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✅ All verification steps passed!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Summary:"
echo "  - 2 agents registered"
echo "  - 1 service created"
echo "  - 1 job completed"
echo "  - Worker reputation: $REPUTATION"
echo "  - Messages delivered: $MESSAGE_COUNT"
