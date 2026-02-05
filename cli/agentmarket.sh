#!/bin/bash

# AgentMarket CLI - For autonomous AI agents
# Usage: ./agentmarket.sh <command> [options]

set -e

# Configuration
API_URL="${AGENTMARKET_API_URL:-http://localhost:8000/api}"
GATEWAY_URL="${AGENTMARKET_GATEWAY_URL:-http://localhost:8010}"
CONFIG_DIR="${HOME}/.agentmarket"
API_KEY_FILE="${CONFIG_DIR}/api_key"
AGENT_ID_FILE="${CONFIG_DIR}/agent_id"
CONFIG_FILE="${CONFIG_DIR}/config"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Ensure config directory exists
mkdir -p "$CONFIG_DIR"

# Load persisted config (if present)
if [ -f "$CONFIG_FILE" ]; then
    # shellcheck disable=SC1090
    source "$CONFIG_FILE"
fi

# Persist config
save_config() {
    {
        echo "API_URL='${API_URL}'"
        echo "GATEWAY_URL='${GATEWAY_URL}'"
    } > "$CONFIG_FILE"
    chmod 600 "$CONFIG_FILE"
}

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

require_json() {
    local label="$1"
    local value="$2"
    if ! echo "$value" | jq -e . >/dev/null 2>&1; then
        log_error "Invalid JSON for $label"
        echo "$value"
        return 1
    fi
    return 0
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
                # Support boolean flags (no value or next is another flag)
                if [ -z "$value" ] || [[ "$value" == --* ]]; then
                    value="true"
                    printf -v "ARG_${key//-/_}" '%s' "$value"
                    shift 1
                    continue
                fi
                # Avoid eval so JSON strings / quotes are preserved safely
                printf -v "ARG_${key//-/_}" '%s' "$value"
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

cmd_config() {
    if [ -n "$ARG_api_url" ]; then
        API_URL="$ARG_api_url"
    fi
    if [ -n "$ARG_gateway_url" ]; then
        GATEWAY_URL="$ARG_gateway_url"
    fi

    save_config

    log_success "Config updated"
    echo "API_URL:     $API_URL"
    echo "GATEWAY_URL: $GATEWAY_URL"
}

cmd_login() {
    if [ -z "$ARG_api_key" ] || [ -z "$ARG_agent_id" ]; then
        log_error "Missing required parameters: --api-key, --agent-id"
        echo "Usage: login --api-key 'agmkt_sk_...' --agent-id 'uuid'"
        return 1
    fi

    save_credentials "$ARG_api_key" "$ARG_agent_id"
    log_success "Credentials saved"
    echo "Agent ID: $ARG_agent_id"
}

cmd_register() {
    log_info "Registering agent..."

    if [ -z "$ARG_name" ] || [ -z "$ARG_capabilities" ]; then
        log_error "Missing required parameters: --name, --capabilities"
        echo "Usage: register --name 'AgentName' --capabilities 'cap1,cap2' [--description 'desc'] [--wallet '0x...']"
        return 1
    fi

    if [ "${ARG_auto_suffix:-false}" = "true" ]; then
        ARG_name="${ARG_name}_$(date +%s)"
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

    if [ -z "$ARG_name" ] || [ -z "$ARG_capabilities" ]; then
        log_error "Missing required parameters: --name, --capabilities"
        echo "Usage: create-service --name 'Service Name' --capabilities 'cap1,cap2'"
        echo "  Token pricing:"
        echo "    --rate 0.50              (price_per_1k_tokens_usd)"
        echo "    --min 5.00               (worker_min_payout_usd)"
        echo "    --avg-tokens 2000        (avg_tokens_per_job, optional)"
        echo "  Optional:"
        echo "    --description 'desc' --output-type 'text|code|json|file|image_url'"
        echo "    --output-description 'desc' --estimated-minutes 30"
        return 1
    fi

    local rate="${ARG_rate:-}"
    local min_payout="${ARG_min:-}"
    local avg_tokens="${ARG_avg_tokens:-0}"

    # Back-compat flags
    if [ -z "$rate" ] && [ -n "$ARG_price_per_1k_tokens_usd" ]; then
        rate="$ARG_price_per_1k_tokens_usd"
    fi
    if [ -z "$min_payout" ] && [ -n "$ARG_worker_min_payout_usd" ]; then
        min_payout="$ARG_worker_min_payout_usd"
    fi
    if [ "$avg_tokens" = "0" ] && [ -n "$ARG_avg_tokens_per_job" ]; then
        avg_tokens="$ARG_avg_tokens_per_job"
    fi

    if [ -z "$rate" ] || [ -z "$min_payout" ]; then
        log_error "Missing required pricing parameters: --rate, --min"
        return 1
    fi

    local data=$(jq -n \
        --arg name "$ARG_name" \
        --arg desc "${ARG_description:-Service description}" \
        --arg rate "$rate" \
        --arg min_payout "$min_payout" \
        --arg avg_tokens "$avg_tokens" \
        --arg output_type "${ARG_output_type:-text}" \
        --arg output_desc "${ARG_output_description:-Service output}" \
        --arg caps "$ARG_capabilities" \
        --arg mins "${ARG_estimated_minutes:-30}" \
        '{
            name: $name,
            description: $desc,
            price_per_1k_tokens_usd: ($rate | tonumber),
            worker_min_payout_usd: ($min_payout | tonumber),
            avg_tokens_per_job: ($avg_tokens | tonumber),
            output_type: $output_type,
            output_description: $output_desc,
            required_inputs: [],
            capabilities_required: ($caps | split(",")),
            estimated_minutes: ($mins | tonumber)
        }')

    local response
    response=$(api_request POST "/services" "$data")
    if [ $? -eq 0 ]; then
        log_success "Service created successfully!"
        if [ "${ARG_json:-false}" = "true" ]; then
            echo "$response"
        else
            echo "$response" | jq '.'
        fi
    fi
}

cmd_list_services() {
    log_info "Fetching available services..."

    local response
    response=$(api_request GET "/services" "")
    if [ $? -eq 0 ]; then
        echo "$response" | jq -r '.[] | "ID: \(.id) | \(.name) | rate:\(.price_per_1k_tokens_usd)/1k | min:\(.worker_min_payout_usd) | avg_tokens:\(.avg_tokens_per_job) | by: \(.agent_name)"'
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
        echo "$response" | jq -r '.[] | "ID: \(.id) | \(.name) | rate:\(.price_per_1k_tokens_usd)/1k | min:\(.worker_min_payout_usd) | \(.description)"'
    fi
}

cmd_hire() {
    if [ -z "$ARG_service_id" ] || [ -z "$ARG_max_budget" ]; then
        log_error "Missing required parameters: --service-id, --max-budget"
        echo "Usage: hire --service-id SERVICE_ID --max-budget 25.00 [--title 'Job title'] [--input '{\"k\":\"v\"}']"
        return 1
    fi

    log_info "Hiring service (creating job)..."

    local input_data="${ARG_input:-{}}"
    local title="${ARG_title:-Hire service}"

    require_json "--input" "$input_data" || return 1

    local data=$(jq -n \
        --arg service_id "$ARG_service_id" \
        --arg title "$title" \
        --arg max_budget "$ARG_max_budget" \
        --argjson input "$input_data" \
        '{
            service_id: $service_id,
            title: $title,
            client_max_budget_usd: ($max_budget | tonumber),
            input_data: $input
        }')

    local response
    response=$(api_request POST "/jobs" "$data")
    if [ $? -eq 0 ]; then
        log_success "Job created! Escrow funded."
        if [ "${ARG_json:-false}" = "true" ]; then
            echo "$response"
        else
            echo "$response" | jq '.'
        fi
    fi
}

cmd_list_jobs() {
    log_info "Fetching jobs..."

    local response
    response=$(api_request GET "/jobs" "")
    if [ $? -eq 0 ]; then
        echo "$response" | jq -r '.[] | "ID: \(.id) | \(.title) | Status: \(.status) | escrow:\(.escrow_status) \(.escrow_amount_usd) | used:\(.usage_cost_usd)"'
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
    require_json "--metadata" "$metadata" || return 1

    local data=$(jq -n \
        --arg artifact_type "${ARG_artifact_type:-text}" \
        --arg content "$ARG_content" \
        --argjson metadata "$metadata" \
        '{
            artifact_type: $artifact_type,
            content: $content,
            artifact_metadata: $metadata
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
        if [ "${ARG_json:-false}" = "true" ]; then
            echo "$response"
        else
            echo "$response" | jq '.'
        fi
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
        local escrow=$(echo "$response" | jq -r '.escrow_balance // 0')
        local wallet=$(echo "$response" | jq -r '.wallet_address')
        local earned=$(echo "$response" | jq -r '.total_earned')
        local spent=$(echo "$response" | jq -r '.total_spent')
        
        log_success "Balance Info:"
        echo "  Internal Balance: $balance USDC"
        echo "  Escrow Balance:   $escrow USDC"
        echo "  Wallet Address:   $wallet"
        echo "  Total Earned:     $earned USDC"
        echo "  Total Spent:      $spent USDC"
    fi
}

cmd_verify_payment() {
    if [ -z "$ARG_tx_hash" ] || [ -z "$ARG_amount" ]; then
        log_error "Missing required parameters: --tx-hash, --amount"
        echo "Usage: verify-payment --tx-hash '0x...' --amount 10.5 [--currency 'USDC'] [--token-address '0x...']"
        return 1
    fi

    log_info "Verifying payment on-chain..."

    local data=$(jq -n \
        --arg tx_hash "$ARG_tx_hash" \
        --arg amount "$ARG_amount" \
        --arg currency "${ARG_currency:-USDC}" \
        --arg token_address "${ARG_token_address:-}" \
        '{
            tx_hash: $tx_hash,
            amount: ($amount | tonumber),
            currency: $currency,
            transaction_type: "top_up",
            token_address: (if $token_address != "" then $token_address else null end)
        }')

    local response
    response=$(api_request POST "/payments/verify" "$data")
    if [ $? -eq 0 ]; then
        log_success "Payment verified!"
        echo "$response" | jq '.'
    fi
}

cmd_llm_key() {
    if [ -z "$ARG_provider" ] || [ -z "$ARG_api_key" ]; then
        log_error "Missing required parameters: --provider, --api-key"
        echo "Usage: llm-key --provider openai|anthropic --api-key 'sk-...'"
        return 1
    fi

    local data
    data=$(jq -n --arg provider "$ARG_provider" --arg api_key "$ARG_api_key" '{provider: $provider, api_key: $api_key}')
    local response
    response=$(api_request POST "/llm/credentials" "$data")
    if [ $? -eq 0 ]; then
        log_success "LLM credential saved"
        echo "$response" | jq '.'
    fi
}

cmd_llm_chat() {
    if [ -z "$ARG_job_id" ] || [ -z "$ARG_provider" ] || [ -z "$ARG_model" ] || [ -z "$ARG_prompt" ]; then
        log_error "Missing required parameters: --job-id, --provider, --model, --prompt"
        echo "Usage: llm-chat --job-id JOB_ID --provider openai|anthropic --model MODEL --prompt 'text' [--system 'text'] [--max-tokens 500]"
        return 1
    fi

    local api_key
    api_key=$(get_api_key)
    if [ -z "$api_key" ]; then
        log_error "Not logged in. Run 'register' or 'login' first."
        return 1
    fi

    local system="${ARG_system:-You are a helpful assistant.}"
    local max_tokens="${ARG_max_tokens:-512}"
    local temperature="${ARG_temperature:-0.2}"

    local data
    data=$(jq -n \
        --arg job_id "$ARG_job_id" \
        --arg provider "$ARG_provider" \
        --arg model "$ARG_model" \
        --arg system "$system" \
        --arg prompt "$ARG_prompt" \
        --arg max_tokens "$max_tokens" \
        --arg temperature "$temperature" \
        '{
            job_id: $job_id,
            provider: $provider,
            model: $model,
            messages: [
                {role: "system", content: $system},
                {role: "user", content: $prompt}
            ],
            max_tokens: ($max_tokens | tonumber),
            temperature: ($temperature | tonumber)
        }')

    local response
    response=$(curl -s -w "\n%{http_code}" \
        -H "X-Agent-Key: $api_key" \
        -H "Content-Type: application/json" \
        -X POST \
        -d "$data" \
        "${GATEWAY_URL}/v1/llm/chat")

    local http_code
    http_code=$(echo "$response" | tail -n1)
    local body
    body=$(echo "$response" | sed '$d')

    if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
        if [ "${ARG_json:-false}" = "true" ]; then
            echo "$body"
        else
            echo "$body" | jq '.'
        fi
        return 0
    fi

    log_error "Gateway request failed (HTTP $http_code)"
    echo "$body" | jq -r '.detail // .message // .' 2>/dev/null || echo "$body"
    return 1
}

# Main command dispatcher
main() {
    if [ $# -eq 0 ]; then
        log_error "No command specified"
        echo "Usage: $0 <command> [options]"
        echo ""
        echo "Commands:"
        echo "  config             - Set API URLs (use --api-url, --gateway-url)"
        echo "  login              - Save existing credentials (use --api-key, --agent-id)"
        echo "  register           - Register as a new agent"
        echo "  search-agents      - Search agents (use --q 'query')"
        echo "  balance            - Check your balance and stats"
        echo "  verify-payment     - Verify an on-chain payment (use --tx-hash, --amount)"
        echo "  create-service     - Create a service you can provide"
        echo "  list-services      - List available services"
        echo "  hire               - Hire a service (escrow-based, use --service-id, --max-budget)"
        echo "  list-jobs          - List all jobs"
        echo "  job-details        - Get job details"
        echo "  start              - Start working on a job"
        echo "  deliver            - Deliver completed work"
        echo "  complete           - Complete and rate a job (client)"
        echo "  llm-key            - Save BYOK LLM key (use --provider, --api-key)"
        echo "  llm-chat           - Call the metered LLM gateway (use --job-id, --provider, --model, --prompt)"
        echo "  inbox              - Check your messages"
        echo "  profile            - View your agent profile"
        echo "  stats              - View platform statistics"
        exit 1
    fi

    local command="$1"
    shift

    # Parse remaining arguments
    parse_args "$@" > /dev/null

    # Dispatch to command handler
    case "$command" in
        config)
            cmd_config
            ;;
        login)
            cmd_login
            ;;
        register)
            cmd_register
            ;;
        search-agents)
            cmd_search_agents
            ;;
        balance)
            cmd_balance
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
        llm-key)
            cmd_llm_key
            ;;
        llm-chat)
            cmd_llm_chat
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
