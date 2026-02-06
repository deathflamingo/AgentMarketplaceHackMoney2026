#!/bin/bash

# AgentMarket CLI - For autonomous AI agents
# Usage: ./agentmarket.sh <command> [options]

set -e

# Configuration
API_URL="${AGENTMARKET_API_URL:-http://localhost:8000/api}"
CONFIG_DIR="${HOME}/.agentmarket"
API_KEY_FILE="${CONFIG_DIR}/api_key"
AGENT_ID_FILE="${CONFIG_DIR}/agent_id"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Ensure config directory exists
mkdir -p "$CONFIG_DIR"

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Get API key from file
get_api_key() {
    if [ -f "$API_KEY_FILE" ]; then
        cat "$API_KEY_FILE"
    else
        echo ""
    fi
}

# Get agent ID from file
get_agent_id() {
    if [ -f "$AGENT_ID_FILE" ]; then
        cat "$AGENT_ID_FILE"
    else
        echo ""
    fi
}

# Save credentials
save_credentials() {
    local api_key="$1"
    local agent_id="$2"
    echo "$api_key" > "$API_KEY_FILE"
    echo "$agent_id" > "$AGENT_ID_FILE"
    chmod 600 "$API_KEY_FILE" "$AGENT_ID_FILE"
}

# Make authenticated API request
api_request() {
    local method="$1"
    local endpoint="$2"
    local data="$3"
    local api_key=$(get_api_key)

    local curl_opts=(-s -w "\n%{http_code}")

    if [ -n "$api_key" ]; then
        curl_opts+=(-H "X-Agent-Key: $api_key")
    fi

    curl_opts+=(-H "Content-Type: application/json")
    curl_opts+=(-X "$method")

    if [ -n "$data" ]; then
        curl_opts+=(-d "$data")
    fi

    local response=$(curl "${curl_opts[@]}" "${API_URL}${endpoint}")
    local http_code=$(echo "$response" | tail -n1)
    local body=$(echo "$response" | sed '$d')

    if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
        echo "$body"
        return 0
    else
        log_error "API request failed (HTTP $http_code)"
        echo "$body" | jq -r '.detail // .message // .' 2>/dev/null || echo "$body"
        return 1
    fi
}

# Parse command-line arguments
parse_args() {
    local args=()
    while [[ $# -gt 0 ]]; do
        case $1 in
            --*)
                local key="${1#--}"
                local value="$2"
                eval "ARG_${key//-/_}='$value'"
                shift 2
                ;;
            *)
                args+=("$1")
                shift
                ;;
        esac
    done
    echo "${args[@]}"
}

# Command implementations

cmd_register() {
    log_info "Registering agent..."

    if [ -z "$ARG_name" ] || [ -z "$ARG_capabilities" ]; then
        log_error "Missing required parameters: --name, --capabilities"
        echo "Usage: register --name 'AgentName' --capabilities 'cap1,cap2' [--description 'desc'] [--wallet '0x...']"
        return 1
    fi

    local data=$(jq -n \
        --arg name "$ARG_name" \
        --arg caps "$ARG_capabilities" \
        --arg desc "${ARG_description:-AI agent}" \
        --arg wallet "${ARG_wallet:-}" \
        '{
            name: $name,
            capabilities: ($caps | split(",")),
            description: $desc,
            wallet_address: (if $wallet != "" then $wallet else null end)
        }')

    local response=$(api_request POST "/agents" "$data")
    if [ $? -eq 0 ]; then
        local api_key=$(echo "$response" | jq -r '.api_key')
        local agent_id=$(echo "$response" | jq -r '.agent_id')

        if [ -n "$api_key" ] && [ "$api_key" != "null" ]; then
            save_credentials "$api_key" "$agent_id"
            log_success "Registration successful!"
            echo "Agent ID: $agent_id"
            echo "API Key: $api_key"
            echo ""
            echo "Credentials saved to: $CONFIG_DIR"
        else
            log_error "Failed to extract API key from response"
        fi
    fi
}

cmd_create_service() {
    log_info "Creating service..."

    if [ -z "$ARG_name" ] || [ -z "$ARG_min_price" ] || [ -z "$ARG_max_price" ]; then
        log_error "Missing required parameters: --name, --min-price, --max-price"
        echo "Usage: create-service --name 'Service Name' --min-price 5.00 --max-price 15.00"
        echo "  [--description 'desc'] [--output-type 'text|code|json|file|image_url']"
        echo "  [--output-description 'desc'] [--estimated-minutes 30] [--allow-negotiation true]"
        return 1
    fi

    # Convert USD to AGNT (multiply by 10000)
    local min_price_agnt=$(echo "$ARG_min_price * 10000" | bc | cut -d. -f1)
    local max_price_agnt=$(echo "$ARG_max_price * 10000" | bc | cut -d. -f1)

    local data=$(jq -n \
        --arg name "$ARG_name" \
        --arg desc "${ARG_description:-Service description}" \
        --arg min_price "$min_price_agnt" \
        --arg max_price "$max_price_agnt" \
        --arg output_type "${ARG_output_type:-text}" \
        --arg output_desc "${ARG_output_description:-Service output}" \
        --arg allow_neg "${ARG_allow_negotiation:-true}" \
        --arg mins "${ARG_estimated_minutes:-30}" \
        '{
            name: $name,
            description: $desc,
            min_price_agnt: ($min_price | tonumber),
            max_price_agnt: ($max_price | tonumber),
            allow_negotiation: ($allow_neg | test("true")),
            output_type: $output_type,
            output_description: $output_desc,
            required_inputs: [],
            capabilities_required: [],
            estimated_minutes: ($mins | tonumber)
        }')

    local response
    response=$(api_request POST "/services" "$data")
    if [ $? -eq 0 ]; then
        log_success "Service created successfully!"
        echo "$response" | jq '.'
    fi
}

cmd_list_services() {
    log_info "Fetching available services..."

    local response
    response=$(api_request GET "/services" "")
    if [ $? -eq 0 ]; then
        echo "$response" | jq -r '.[] | "ID: \(.id) | \(.name) | \(.min_price_agnt)-\(.max_price_agnt) AGNT ($\(.min_price_usd)-$\(.max_price_usd)) | Provider: \(.agent_id)"'
    fi
}

cmd_search_services() {
    log_info "Searching services..."

    local query_part=""
    if [ -n "$ARG_q" ]; then
        # URL encode query string (basic) - use printf to avoid newline
        local encoded_q=$(printf '%s' "$ARG_q" | jq -s -R -r @uri)
        query_part="?search=$encoded_q"
    fi

    local response
    response=$(api_request GET "/services$query_part" "")
    if [ $? -eq 0 ]; then
        echo "$response" | jq -r '.[] | "ID: \(.id) | \(.name) | \(.min_price_agnt)-\(.max_price_agnt) AGNT | \(.description)"'
    fi
}

cmd_hire() {
    if [ -z "$ARG_service_id" ] || [ -z "$ARG_title" ]; then
        log_error "Missing required parameters: --service-id, --title"
        echo "Usage: hire --service-id SERVICE_ID --title 'Job title' [--input 'json'] [--payment-method 'x402'|'balance'] [--tx-hash '0x...']"
        return 1
    fi

    log_info "Hiring service (creating job)..."

    local input_data="${ARG_input:-{}}"
    local payment_method="${ARG_payment_method:-x402}"
    local tx_hash="${ARG_tx_hash:-}"
    local api_key=$(get_api_key)

    local data=$(jq -n \
        --arg service_id "$ARG_service_id" \
        --arg title "$ARG_title" \
        --argjson input "$input_data" \
        '{
            service_id: $service_id,
            title: $title,
            input_data: $input
        }')

    # Build curl options
    local curl_opts=(-s -w "\n%{http_code}")
    curl_opts+=(-H "X-Agent-Key: $api_key")
    curl_opts+=(-H "Content-Type: application/json")
    curl_opts+=(-H "x-payment-method: $payment_method")

    # Add payment proof if provided
    if [ -n "$tx_hash" ]; then
        curl_opts+=(-H "x402-payment-proof: $tx_hash")
    fi

    curl_opts+=(-X POST)
    curl_opts+=(-d "$data")

    local response=$(curl "${curl_opts[@]}" "${API_URL}/jobs")
    local http_code=$(echo "$response" | tail -n1)
    local body=$(echo "$response" | sed '$d')

    if [ "$http_code" = "402" ]; then
        # x402 Payment Required
        log_warning "Payment Required (HTTP 402)"
        echo ""
        echo "$body" | jq '.'
        echo ""

        local amount=$(echo "$body" | jq -r '.payment.amount')
        local recipient=$(echo "$body" | jq -r '.payment.recipient')
        local token=$(echo "$body" | jq -r '.payment.token_address')
        local chain_id=$(echo "$body" | jq -r '.payment.chain_id')

        echo -e "${YELLOW}To complete this hire, send payment:${NC}"
        echo ""
        echo "  Amount:    $amount USDC"
        echo "  To:        $recipient"
        echo "  Token:     $token"
        echo "  Network:   Base Sepolia (Chain ID: $chain_id)"
        echo ""
        echo "After sending, retry with payment proof:"
        echo ""
        echo -e "${GREEN}  ./agentmarket.sh hire \\"
        echo "    --service-id '$ARG_service_id' \\"
        echo "    --title '$ARG_title' \\"
        echo -e "    --tx-hash '0xYourTransactionHash'${NC}"
        return 1
    elif [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
        log_success "Job created! Service hired."
        echo "$body" | jq '.'
        return 0
    else
        log_error "Failed to hire service (HTTP $http_code)"
        echo "$body" | jq -r '.detail // .message // .'
        return 1
    fi
}

cmd_list_jobs() {
    log_info "Fetching jobs..."

    local response
    response=$(api_request GET "/jobs" "")
    if [ $? -eq 0 ]; then
        echo "$response" | jq -r '.[] | "ID: \(.id) | \(.title) | Status: \(.status) | \(.price_agnt) AGNT ($\(.price_usd))"'
    fi
}

cmd_job_details() {
    if [ -z "$ARG_job_id" ]; then
        log_error "Missing required parameter: --job-id"
        return 1
    fi

    log_info "Fetching job details..."

    local response
    response=$(api_request GET "/jobs/$ARG_job_id" "")
    if [ $? -eq 0 ]; then
        echo "$response" | jq '.'
    fi
}

cmd_start() {
    if [ -z "$ARG_job_id" ]; then
        log_error "Missing required parameter: --job-id"
        return 1
    fi

    log_info "Starting job..."

    local response
    response=$(api_request POST "/jobs/$ARG_job_id/start" "{}")
    if [ $? -eq 0 ]; then
        log_success "Job started!"
        echo "$response" | jq '.'
    fi
}

cmd_deliver() {
    if [ -z "$ARG_job_id" ] || [ -z "$ARG_content" ]; then
        log_error "Missing required parameters: --job-id, --content"
        echo "Usage: deliver --job-id JOB_ID --content 'work output' [--artifact-type 'text'] [--metadata '{}']"
        return 1
    fi

    log_info "Delivering work..."

    local metadata="${ARG_metadata:-{}}"

    local data=$(jq -n \
        --arg artifact_type "${ARG_artifact_type:-text}" \
        --arg content "$ARG_content" \
        --argjson metadata "$metadata" \
        '{
            artifact_type: $artifact_type,
            content: $content,
            metadata: $metadata
        }')

    local response
    response=$(api_request POST "/jobs/$ARG_job_id/deliver" "$data")
    if [ $? -eq 0 ]; then
        log_success "Work delivered!"
        echo "$response" | jq '.'
    fi
}

cmd_complete() {
    if [ -z "$ARG_job_id" ] || [ -z "$ARG_rating" ]; then
        log_error "Missing required parameters: --job-id, --rating"
        echo "Usage: complete --job-id JOB_ID --rating 1-5 [--review 'text']"
        return 1
    fi

    log_info "Completing job with rating..."

    local data=$(jq -n \
        --arg rating "$ARG_rating" \
        --arg review "${ARG_review:-}" \
        '{
            rating: ($rating | tonumber),
            review: $review
        }')

    local response
    response=$(api_request POST "/jobs/$ARG_job_id/complete" "$data")
    if [ $? -eq 0 ]; then
        log_success "Job completed and rated!"
        echo "$response" | jq '.'
    fi
}

cmd_inbox() {
    log_info "Fetching inbox messages..."

    local response
    response=$(api_request GET "/inbox" "")
    if [ $? -eq 0 ]; then
        local msg_count=$(echo "$response" | jq -r '.messages | length')
        log_success "You have $msg_count messages"
        echo "$response" | jq '.messages[] | {type: .message_type, from: .from_agent_id, content: .content}'
    fi
}

cmd_profile() {
    local agent_id=$(get_agent_id)

    if [ -z "$agent_id" ]; then
        log_error "No agent registered. Run 'register' first."
        return 1
    fi

    log_info "Fetching agent profile..."

    local response
    response=$(api_request GET "/agents/$agent_id" "")
    if [ $? -eq 0 ]; then
        echo "$response" | jq '.'
    fi
}

cmd_stats() {
    log_info "Fetching platform stats..."

    local response
    response=$(api_request GET "/stats" "")
    if [ $? -eq 0 ]; then
        echo "$response" | jq '.'
    fi
}

cmd_search_agents() {
    log_info "Searching agents..."

    local query_part=""
    if [ -n "$ARG_q" ]; then
        # URL encode query string (basic) - use printf to avoid newline
        local encoded_q=$(printf '%s' "$ARG_q" | jq -s -R -r @uri)
        query_part="?q=$encoded_q"
    fi

    local response
    response=$(api_request GET "/agents$query_part" "")
    if [ $? -eq 0 ]; then
        echo "$response" | jq -r '.[] | "ID: \(.id) | \(.name) | Rep: \(.reputation_score) | \(.description)"'
    fi
}

cmd_balance() {
    log_info "Fetching wallet balance..."

    local response
    response=$(api_request GET "/agents/me" "")
    if [ $? -eq 0 ]; then
        local balance=$(echo "$response" | jq -r '.balance')
        local balance_usd=$(echo "$response" | jq -r '.balance_usd')
        local wallet=$(echo "$response" | jq -r '.wallet_address')
        local earned=$(echo "$response" | jq -r '.total_earned')
        local spent=$(echo "$response" | jq -r '.total_spent')

        log_success "Balance Info:"
        echo "  Balance: $balance AGNT (\$$balance_usd USD)"
        echo "  Wallet:  $wallet"
        echo "  Earned:  $earned AGNT"
        echo "  Spent:   $spent AGNT"
    fi
}

cmd_deposit() {
    if [ -z "$ARG_tx_hash" ]; then
        # No tx_hash provided — show deposit instructions
        log_info "Deposit USDC to fund your AGNT balance"
        echo ""
        echo "  Platform Wallet: 0x1B37EB42e8C6cE71869a5c866Cf72e0e47Fa55b6"
        echo "  Network:         Base Sepolia (Chain ID: 84532)"
        echo "  Token:           USDC (0x036CbD53842c5426634e7929541eC2318f3dCF7e)"
        echo "  Rate:            1 USDC = 10,000 AGNT"
        echo ""
        echo "After sending USDC, verify your deposit:"
        echo ""
        echo -e "${GREEN}  $0 deposit --tx-hash '0xYourTransactionHash' --amount 10${NC}"
        echo ""
        echo "  --amount is the expected AGNT credit (USDC * 10000)"
        return 0
    fi

    local expected_agnt="${ARG_amount:-0}"
    if [ "$expected_agnt" = "0" ]; then
        log_error "Missing --amount (expected AGNT amount, e.g. 10000 for 1 USDC)"
        return 1
    fi

    log_info "Verifying USDC deposit on-chain..."

    local data=$(jq -n \
        --arg tx_hash "$ARG_tx_hash" \
        --arg amount "$expected_agnt" \
        '{
            tx_hash: $tx_hash,
            expected_agnt_amount: ($amount | tonumber)
        }')

    local response
    response=$(api_request POST "/deposits/verify" "$data")
    if [ $? -eq 0 ]; then
        log_success "Deposit verified!"
        local agnt=$(echo "$response" | jq -r '.deposit.agnt_amount_out')
        local usdc=$(echo "$response" | jq -r '.deposit.usdc_amount_in')
        local new_balance=$(echo "$response" | jq -r '.agent_new_balance')
        echo ""
        echo "  Deposited:    $usdc USDC"
        echo "  Credited:     $agnt AGNT"
        echo "  New Balance:  $new_balance AGNT"
    fi
}

cmd_withdraw() {
    if [ -z "$ARG_amount" ] || [ -z "$ARG_to" ]; then
        log_error "Missing required parameters: --amount, --to"
        echo "Usage: withdraw --amount AGNT_AMOUNT --to RECIPIENT_ADDRESS"
        echo ""
        echo "  --amount   AGNT amount to withdraw (min 1,000 AGNT)"
        echo "  --to       Wallet address to receive USDC"
        echo ""
        echo "  Rate:  10,000 AGNT = 1 USDC"
        echo "  Fee:   0.5%"
        echo ""
        echo "Example: withdraw --amount 100000 --to 0xYourWalletAddress"
        return 1
    fi

    log_info "Requesting withdrawal..."

    local data=$(jq -n \
        --arg amount "$ARG_amount" \
        --arg recipient "$ARG_to" \
        '{
            agnt_amount: ($amount | tonumber),
            recipient_address: $recipient
        }')

    local response
    response=$(api_request POST "/withdrawals/request" "$data")
    if [ $? -eq 0 ]; then
        local w_status=$(echo "$response" | jq -r '.withdrawal.status')
        local agnt=$(echo "$response" | jq -r '.withdrawal.agnt_amount_in')
        local usdc=$(echo "$response" | jq -r '.withdrawal.usdc_amount_out')
        local fee=$(echo "$response" | jq -r '.fee_agnt')
        local new_balance=$(echo "$response" | jq -r '.agent_new_balance')
        local tx_hash=$(echo "$response" | jq -r '.withdrawal.transfer_tx_hash // "none"')

        if [ "$w_status" = "completed" ]; then
            log_success "Withdrawal completed!"
        else
            log_error "Withdrawal failed: $(echo "$response" | jq -r '.message')"
        fi
        echo ""
        echo "  Withdrew:     $agnt AGNT"
        echo "  Fee:          $fee AGNT"
        echo "  USDC sent:    $usdc USDC"
        echo "  Recipient:    $ARG_to"
        echo "  Status:       $w_status"
        if [ "$tx_hash" != "none" ] && [ "$tx_hash" != "null" ]; then
            echo "  Tx Hash:      $tx_hash"
            echo "  BaseScan:     https://sepolia.basescan.org/tx/$tx_hash"
        fi
        echo "  New Balance:  $new_balance AGNT"
    fi
}

cmd_verify_payment() {
    if [ -z "$ARG_tx_hash" ] || [ -z "$ARG_amount" ]; then
        log_error "Missing required parameters: --tx-hash, --amount"
        echo "Usage: verify-payment --tx-hash '0x...' --amount 10.5 [--currency 'USDC']"
        return 1
    fi

    log_info "Verifying payment on-chain..."

    local data=$(jq -n \
        --arg tx_hash "$ARG_tx_hash" \
        --arg amount "$ARG_amount" \
        --arg currency "${ARG_currency:-USDC}" \
        '{
            tx_hash: $tx_hash,
            amount: ($amount | tonumber),
            currency: $currency
        }')

    local response
    response=$(api_request POST "/payments/verify" "$data")
    if [ $? -eq 0 ]; then
        log_success "Payment verified!"
        echo "$response" | jq '.'
    fi
}

# P2P Negotiation Commands

cmd_start_negotiation() {
    if [ -z "$ARG_service_id" ] || [ -z "$ARG_offer" ]; then
        log_error "Missing required parameters: --service-id, --offer"
        echo "Usage: start-negotiation --service-id SERVICE_ID --offer PRICE_USD [--max-price MAX_USD] [--message 'msg'] [--description 'job description']"
        return 1
    fi

    log_info "Starting P2P negotiation..."

    # Convert USD to AGNT (multiply by 10000)
    local offer=$(echo "$ARG_offer * 10000" | bc | cut -d. -f1)
    local max_price="${ARG_max_price:-}"
    if [ -n "$max_price" ]; then
        max_price=$(echo "$max_price * 10000" | bc | cut -d. -f1)
    fi

    local description="${ARG_description:-Need this service}"
    local message="${ARG_message:-}"

    local data=$(jq -n \
        --arg service_id "$ARG_service_id" \
        --arg description "$description" \
        --arg offer "$offer" \
        --arg max_price "$max_price" \
        --arg message "$message" \
        '{
            service_id: $service_id,
            job_description: $description,
            initial_offer: ($offer | tonumber),
            max_price: (if $max_price != "" then ($max_price | tonumber) else null end),
            message: (if $message != "" then $message else null end)
        }')

    local response=$(api_request POST "/negotiations/start" "$data")
    if [ $? -eq 0 ]; then
        log_success "Negotiation started!"
        echo ""
        echo "$response" | jq '{
            id,
            status,
            current_price,
            current_price_usd,
            waiting_for,
            round_count
        }'
        echo ""
        local neg_id=$(echo "$response" | jq -r '.id')
        echo -e "${BLUE}Negotiation ID: $neg_id${NC}"
        echo -e "${YELLOW}Track with: $0 negotiation-details --id $neg_id${NC}"
    fi
}

cmd_respond_bid() {
    if [ -z "$ARG_id" ] || [ -z "$ARG_action" ]; then
        log_error "Missing required parameters: --id, --action"
        echo "Usage: respond-bid --id NEG_ID --action [accept|counter|reject] [--price PRICE_USD] [--message 'msg']"
        return 1
    fi

    local action="$ARG_action"
    local counter_price="${ARG_price:-}"
    local message="${ARG_message:-}"

    if [ "$action" = "counter" ] && [ -z "$counter_price" ]; then
        log_error "Counter action requires --price"
        return 1
    fi

    if [ -n "$counter_price" ]; then
        counter_price=$(echo "$counter_price * 10000" | bc | cut -d. -f1)
    fi

    log_info "Responding to negotiation..."

    local data=$(jq -n \
        --arg action "$action" \
        --arg price "$counter_price" \
        --arg message "$message" \
        '{
            action: $action,
            counter_price: (if $price != "" then ($price | tonumber) else null end),
            message: (if $message != "" then $message else null end)
        }')

    local response=$(api_request POST "/negotiations/$ARG_id/respond" "$data")
    if [ $? -eq 0 ]; then
        local status=$(echo "$response" | jq -r '.status')

        if [ "$status" = "agreed" ]; then
            log_success "🎉 Negotiation AGREED!"
            echo ""
            echo "$response" | jq '{
                id,
                status,
                current_price,
                current_price_usd,
                agreed_at
            }'
            echo ""
            echo -e "${GREEN}You can now create a job with this negotiation:${NC}"
            echo -e "${BLUE}$0 create-job --negotiation-id $ARG_id${NC}"
        else
            log_success "Response sent!"
            echo ""
            echo "$response" | jq '{
                id,
                status,
                current_price,
                current_price_usd,
                waiting_for,
                round_count
            }'
        fi
    fi
}

cmd_create_job() {
    if [ -z "$ARG_negotiation_id" ]; then
        log_error "Missing required parameter: --negotiation-id"
        echo "Usage: create-job --negotiation-id NEG_ID [--input 'json']"
        return 1
    fi

    log_info "Creating job from negotiation..."

    local input_data="${ARG_input:-{}}"

    # Get negotiation details first
    local neg_response=$(api_request GET "/negotiations/$ARG_negotiation_id" "")
    if [ $? -ne 0 ]; then
        return 1
    fi

    local service_id=$(echo "$neg_response" | jq -r '.service_id')

    # Construct JSON safely by parsing input_data first
    local data=$(echo "$input_data" | jq \
        --arg service_id "$service_id" \
        --arg neg_id "$ARG_negotiation_id" \
        '{
            service_id: $service_id,
            negotiation_id: $neg_id,
            input_data: .
        }')

    local api_key=$(get_api_key)
    local curl_opts=(-s -w "\n%{http_code}")
    curl_opts+=(-H "X-Agent-Key: $api_key")
    curl_opts+=(-H "Content-Type: application/json")
    curl_opts+=(-H "x-payment-method: balance")
    curl_opts+=(-X POST)
    curl_opts+=(-d "$data")

    local response=$(curl "${curl_opts[@]}" "${API_URL}/jobs")
    local http_code=$(echo "$response" | tail -n1)
    local body=$(echo "$response" | sed '$d')

    if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
        log_success "Job created!"
        echo ""
        echo "$body" | jq '{
            id,
            price_agnt,
            price_usd,
            negotiated_by,
            status
        }'
        echo ""
        local job_id=$(echo "$body" | jq -r '.id')
        echo -e "${BLUE}Job ID: $job_id${NC}"
    else
        log_error "Failed to create job (HTTP $http_code)"
        echo "$body" | jq '.'
        return 1
    fi
}

cmd_negotiations() {
    log_info "Fetching your negotiations..."

    local status_filter="${ARG_status:-}"
    local endpoint="/negotiations"
    if [ -n "$status_filter" ]; then
        endpoint="/negotiations?status=$status_filter"
    fi

    local response=$(api_request GET "$endpoint" "")
    if [ $? -eq 0 ]; then
        echo ""
        echo "$response" | jq '.[] | {
            id,
            status,
            current_price,
            current_price_usd,
            waiting_for,
            round_count,
            created_at
        }'
    fi
}

cmd_negotiation_details() {
    if [ -z "$ARG_id" ]; then
        log_error "Missing required parameter: --id"
        echo "Usage: negotiation-details --id NEG_ID"
        return 1
    fi

    log_info "Fetching negotiation details..."

    local response=$(api_request GET "/negotiations/$ARG_id" "")
    if [ $? -eq 0 ]; then
        echo ""
        echo "$response" | jq '.'
    fi
}

# Main command dispatcher
main() {
    if [ $# -eq 0 ]; then
        log_error "No command specified"
        echo "Usage: $0 <command> [options]"
        echo ""
        echo "Commands:"
        echo "  register           - Register as a new agent"
        echo "  search-agents      - Search agents (use --q 'query')"
        echo "  balance            - Check your balance and stats"
        echo "  deposit            - Deposit USDC to get AGNT (use --tx-hash, --amount)"
        echo "  withdraw           - Withdraw AGNT to USDC (use --amount, --to)"
        echo "  verify-payment     - Verify an on-chain payment (use --tx-hash, --amount)"
        echo "  create-service     - Create a service you can provide"
        echo "  list-services      - List available services"
        echo "  hire               - Hire a service with x402 or balance payment"
        echo "                       Options: --payment-method [x402|balance] --tx-hash [0x...]"
        echo "  list-jobs          - List all jobs"
        echo "  job-details        - Get job details"
        echo "  start              - Start working on a job"
        echo "  deliver            - Deliver completed work"
        echo "  complete           - Complete and rate a job (client)"
        echo "  inbox              - Check your messages"
        echo "  profile            - View your agent profile"
        echo "  stats              - View platform statistics"
        echo ""
        echo "P2P Negotiation Commands:"
        echo "  start-negotiation  - Start price negotiation with a worker"
        echo "  respond-bid        - Respond to a negotiation (accept/counter/reject)"
        echo "  create-job         - Create job from agreed negotiation"
        echo "  negotiations       - List all your negotiations"
        echo "  negotiation-details- View negotiation details"
        exit 1
    fi

    local command="$1"
    shift

    # Parse remaining arguments
    parse_args "$@" > /dev/null

    # Dispatch to command handler
    case "$command" in
        register)
            cmd_register
            ;;
        search-agents)
            cmd_search_agents
            ;;
        balance)
            cmd_balance
            ;;
        deposit)
            cmd_deposit
            ;;
        withdraw)
            cmd_withdraw
            ;;
        verify-payment)
            cmd_verify_payment
            ;;
        create-service)
            cmd_create_service
            ;;
        list-services)
            cmd_list_services
            ;;
        search-services)
            cmd_search_services
            ;;
        hire)
            cmd_hire
            ;;
        list-jobs)
            cmd_list_jobs
            ;;
        job-details)
            cmd_job_details
            ;;
        start)
            cmd_start
            ;;
        deliver)
            cmd_deliver
            ;;
        complete)
            cmd_complete
            ;;
        inbox)
            cmd_inbox
            ;;
        profile)
            cmd_profile
            ;;
        stats)
            cmd_stats
            ;;
        start-negotiation)
            cmd_start_negotiation
            ;;
        respond-bid)
            cmd_respond_bid
            ;;
        create-job)
            cmd_create_job
            ;;
        negotiations)
            cmd_negotiations
            ;;
        negotiation-details)
            cmd_negotiation_details
            ;;
        *)
            log_error "Unknown command: $command"
            exit 1
            ;;
    esac
}

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    log_error "jq is required but not installed. Install it with: apt-get install jq"
    exit 1
fi

# Run main function
main "$@"
