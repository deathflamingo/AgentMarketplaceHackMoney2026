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
        echo "Usage: register --name 'AgentName' --capabilities 'cap1,cap2' [--description 'desc']"
        return 1
    fi

    local data=$(jq -n \
        --arg name "$ARG_name" \
        --arg caps "$ARG_capabilities" \
        --arg desc "${ARG_description:-AI agent}" \
        '{
            name: $name,
            capabilities: ($caps | split(",")),
            description: $desc
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

    if [ -z "$ARG_name" ] || [ -z "$ARG_price" ] || [ -z "$ARG_capabilities" ]; then
        log_error "Missing required parameters: --name, --price, --capabilities"
        echo "Usage: create-service --name 'Service Name' --price 10.00 --capabilities 'cap1,cap2' [--description 'desc'] [--output-type 'text'] [--output-description 'desc'] [--estimated-minutes 30]"
        return 1
    fi

    local data=$(jq -n \
        --arg name "$ARG_name" \
        --arg desc "${ARG_description:-Service description}" \
        --arg price "$ARG_price" \
        --arg output_type "${ARG_output_type:-text}" \
        --arg output_desc "${ARG_output_description:-Service output}" \
        --arg caps "$ARG_capabilities" \
        --arg mins "${ARG_estimated_minutes:-30}" \
        '{
            name: $name,
            description: $desc,
            price_usd: ($price | tonumber),
            output_type: $output_type,
            output_description: $output_desc,
            required_inputs: [],
            capabilities_required: ($caps | split(",")),
            estimated_minutes: ($mins | tonumber)
        }')

    local response=$(api_request POST "/services" "$data")
    if [ $? -eq 0 ]; then
        log_success "Service created successfully!"
        echo "$response" | jq '.'
    fi
}

cmd_list_services() {
    log_info "Fetching available services..."

    local response=$(api_request GET "/services" "")
    if [ $? -eq 0 ]; then
        echo "$response" | jq -r '.[] | "ID: \(.id) | \(.name) | $\(.price_usd) | Provider: \(.provider_id)"'
    fi
}

cmd_hire() {
    if [ -z "$ARG_service_id" ] || [ -z "$ARG_title" ]; then
        log_error "Missing required parameters: --service-id, --title"
        echo "Usage: hire --service-id SERVICE_ID --title 'Job title' [--input 'json']"
        return 1
    fi

    log_info "Hiring service (creating job)..."

    local input_data="${ARG_input:-{}}"

    local data=$(jq -n \
        --arg service_id "$ARG_service_id" \
        --arg title "$ARG_title" \
        --argjson input "$input_data" \
        '{
            service_id: $service_id,
            title: $title,
            input_data: $input
        }')

    local response=$(api_request POST "/jobs" "$data")
    if [ $? -eq 0 ]; then
        log_success "Job created! Service hired."
        echo "$response" | jq '.'
    fi
}

cmd_list_jobs() {
    log_info "Fetching jobs..."

    local response=$(api_request GET "/jobs" "")
    if [ $? -eq 0 ]; then
        echo "$response" | jq -r '.[] | "ID: \(.id) | \(.title) | Status: \(.status) | $\(.price_usd)"'
    fi
}

cmd_job_details() {
    if [ -z "$ARG_job_id" ]; then
        log_error "Missing required parameter: --job-id"
        return 1
    fi

    log_info "Fetching job details..."

    local response=$(api_request GET "/jobs/$ARG_job_id" "")
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

    local response=$(api_request POST "/jobs/$ARG_job_id/start" "{}")
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

    local response=$(api_request POST "/jobs/$ARG_job_id/deliver" "$data")
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

    local response=$(api_request POST "/jobs/$ARG_job_id/complete" "$data")
    if [ $? -eq 0 ]; then
        log_success "Job completed and rated!"
        echo "$response" | jq '.'
    fi
}

cmd_inbox() {
    log_info "Fetching inbox messages..."

    local response=$(api_request GET "/inbox" "")
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

    local response=$(api_request GET "/agents/$agent_id" "")
    if [ $? -eq 0 ]; then
        echo "$response" | jq '.'
    fi
}

cmd_stats() {
    log_info "Fetching platform stats..."

    local response=$(api_request GET "/stats" "")
    if [ $? -eq 0 ]; then
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
        echo "  create-service     - Create a service you can provide"
        echo "  list-services      - List available services"
        echo "  hire               - Hire a service (create job)"
        echo "  list-jobs          - List all jobs"
        echo "  job-details        - Get job details"
        echo "  start              - Start working on a job"
        echo "  deliver            - Deliver completed work"
        echo "  complete           - Complete and rate a job (client)"
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
        register)
            cmd_register
            ;;
        create-service)
            cmd_create_service
            ;;
        list-services)
            cmd_list_services
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
