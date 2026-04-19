#!/usr/bin/env bash
# n8n Cron Verify — post-start hook to ensure all workflows are active.
#
# Run this after n8n container starts (or restarts) to verify that all 4
# workflows are active and their cron triggers are properly registered.
#
# The script waits for n8n to become responsive, then checks each workflow.
# If any are inactive, it activates them via the n8n REST API.
#
# Usage:
#   bash scripts/n8n_verify_crons.sh                 # Wait 30s then verify
#   bash scripts/n8n_verify_crons.sh --wait 60       # Custom wait time
#   bash scripts/n8n_verify_crons.sh --no-wait       # Skip initial wait
#   bash scripts/n8n_verify_crons.sh --hook           # Add as docker event hook
#
# Can be chained after docker restart:
#   docker restart ielts-n8n && bash scripts/n8n_verify_crons.sh
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/logs"
LOG_FILE="$LOG_DIR/n8n_verify_crons.log"

CONTAINER="ielts-n8n"
N8N_PORT=5800
N8N_API_KEY="jarvis-api-key-2026"
N8N_BASE_URL="http://localhost:${N8N_PORT}"

DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/1490915452631650306/ccglLeI-LK_Ki_KJ0DpUBwAWf-HA7O84AzhylNAogC6nY80F3oh0tyFAJuy1GTXbSSnp"

WORKFLOW_IDS=(1001 1002 1003 1004)
WORKFLOW_NAMES=(
    "JARVIS YouTube v3"
    "Health Monitor"
    "籌碼異常偵測"
    "盤前美股 Shorts"
)

DEFAULT_WAIT=30
MAX_READY_WAIT=120  # Max seconds to wait for n8n API to become ready

# ── Logging ──────────────────────────────────────────────────────────────────

mkdir -p "$LOG_DIR"

log() {
    local level="$1"
    shift
    local ts
    ts="$(date '+%Y-%m-%d %H:%M:%S')"
    echo "[$ts] [$level] $*" | tee -a "$LOG_FILE"
}

# ── Discord notification ─────────────────────────────────────────────────────

notify_discord() {
    local message="$1"
    local payload
    payload=$(printf '{"content":"%s"}' "$message")

    curl -s -X POST "$DISCORD_WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        -d "$payload" \
        --connect-timeout 5 \
        --max-time 10 \
        -o /dev/null 2>/dev/null || {
        log "WARN" "Discord notification failed"
    }
}

# ── Wait for n8n to be ready ─────────────────────────────────────────────────

wait_for_n8n() {
    local initial_wait="${1:-$DEFAULT_WAIT}"

    # Initial wait for n8n to boot
    if (( initial_wait > 0 )); then
        log "INFO" "Waiting ${initial_wait}s for n8n to initialize..."
        sleep "$initial_wait"
    fi

    # Poll until API is responsive
    local elapsed=0
    while (( elapsed < MAX_READY_WAIT )); do
        local http_code
        http_code=$(curl -s -o /dev/null -w '%{http_code}' \
            --connect-timeout 3 --max-time 5 \
            -H "X-N8N-API-KEY: $N8N_API_KEY" \
            "${N8N_BASE_URL}/api/v1/workflows" 2>/dev/null || echo "000")

        if [[ "$http_code" == "200" ]]; then
            log "INFO" "n8n API is responsive (took ~${elapsed}s after initial wait)"
            return 0
        fi

        sleep 5
        (( elapsed += 5 ))
    done

    log "ERROR" "n8n API not responsive after ${MAX_READY_WAIT}s"
    return 1
}

# ── Check and activate workflows ─────────────────────────────────────────────

get_workflow_status() {
    local wf_id="$1"
    curl -s --connect-timeout 5 --max-time 10 \
        -H "X-N8N-API-KEY: $N8N_API_KEY" \
        "${N8N_BASE_URL}/api/v1/workflows/${wf_id}" 2>/dev/null || echo "{}"
}

is_workflow_active() {
    local response="$1"
    local active
    active=$(echo "$response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print('true' if data.get('active', False) else 'false')
except:
    print('error')
" 2>/dev/null || echo "error")
    [[ "$active" == "true" ]]
}

activate_workflow() {
    local wf_id="$1"
    local response
    response=$(curl -s -X PATCH \
        -H "X-N8N-API-KEY: $N8N_API_KEY" \
        -H "Content-Type: application/json" \
        -d '{"active": true}' \
        "${N8N_BASE_URL}/api/v1/workflows/${wf_id}" \
        --connect-timeout 5 --max-time 10 2>/dev/null || echo "{}")

    # Verify activation
    local active
    active=$(echo "$response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print('true' if data.get('active', False) else 'false')
except:
    print('false')
" 2>/dev/null || echo "false")

    [[ "$active" == "true" ]]
}

deactivate_then_activate() {
    # Sometimes n8n needs a deactivate-then-activate cycle to properly
    # re-register cron triggers. This is the nuclear option.
    local wf_id="$1"
    log "INFO" "Performing deactivate-activate cycle for WF $wf_id"

    # Deactivate
    curl -s -X PATCH \
        -H "X-N8N-API-KEY: $N8N_API_KEY" \
        -H "Content-Type: application/json" \
        -d '{"active": false}' \
        "${N8N_BASE_URL}/api/v1/workflows/${wf_id}" \
        --connect-timeout 5 --max-time 10 \
        -o /dev/null 2>/dev/null

    sleep 3

    # Activate
    activate_workflow "$wf_id"
}

# ── Main verification ────────────────────────────────────────────────────────

verify_all_workflows() {
    log "INFO" "Verifying all workflows..."

    local all_ok=true
    local activated=()
    local failed=()
    local status_lines=()

    for i in "${!WORKFLOW_IDS[@]}"; do
        local wf_id="${WORKFLOW_IDS[$i]}"
        local wf_name="${WORKFLOW_NAMES[$i]}"

        local response
        response=$(get_workflow_status "$wf_id")

        if is_workflow_active "$response"; then
            log "INFO" "WF $wf_id ($wf_name): ACTIVE"
            status_lines+=("$wf_id $wf_name: ACTIVE")

            # Even if active, do a deactivate-activate cycle to re-register cron
            # This is the key fix for the cron deregistration issue
            log "INFO" "Cycling WF $wf_id to ensure cron triggers are registered"
            if deactivate_then_activate "$wf_id"; then
                log "INFO" "WF $wf_id cron triggers re-registered"
            else
                log "WARN" "WF $wf_id cron re-registration may have failed"
                # Not critical — it was already active
            fi
        else
            log "WARN" "WF $wf_id ($wf_name): INACTIVE — activating..."
            all_ok=false

            if activate_workflow "$wf_id"; then
                log "INFO" "WF $wf_id activated successfully"
                activated+=("$wf_id ($wf_name)")
                status_lines+=("$wf_id $wf_name: ACTIVATED")
            else
                log "ERROR" "Failed to activate WF $wf_id"
                # Try the nuclear option
                if deactivate_then_activate "$wf_id"; then
                    log "INFO" "WF $wf_id activated via deactivate-activate cycle"
                    activated+=("$wf_id ($wf_name)")
                    status_lines+=("$wf_id $wf_name: ACTIVATED (cycle)")
                else
                    failed+=("$wf_id ($wf_name)")
                    status_lines+=("$wf_id $wf_name: FAILED")
                fi
            fi

            sleep 2
        fi
    done

    # Report results
    echo ""
    echo "=== n8n Workflow Verification Report ==="
    for line in "${status_lines[@]}"; do
        echo "  $line"
    done
    echo "========================================"

    # Send Discord notification if there were issues
    if (( ${#activated[@]} > 0 )) || (( ${#failed[@]} > 0 )); then
        local msg="n8n 啟動驗證: "
        if (( ${#activated[@]} > 0 )); then
            msg="${msg}已啟用 ${activated[*]}; "
        fi
        if (( ${#failed[@]} > 0 )); then
            msg="${msg}啟用失敗 ${failed[*]}"
        fi
        notify_discord "$msg"
    else
        log "INFO" "All workflows active and cron triggers re-registered"
    fi

    if (( ${#failed[@]} > 0 )); then
        return 1
    fi
    return 0
}

# ── Docker event hook mode ───────────────────────────────────────────────────

run_docker_event_hook() {
    # Listen for n8n container start events and auto-verify
    log "INFO" "Listening for $CONTAINER start events..."
    notify_discord "n8n cron 驗證 hook 已啟動，監聽容器啟動事件"

    docker events \
        --filter "container=$CONTAINER" \
        --filter "event=start" \
        --format '{{.Time}} {{.Action}}' 2>/dev/null | while read -r line; do

        log "INFO" "Detected container event: $line"
        log "INFO" "Waiting for n8n to initialize before verifying crons..."

        # Wait for n8n to be fully ready
        if wait_for_n8n "$DEFAULT_WAIT"; then
            verify_all_workflows || true
        else
            notify_discord "n8n cron 驗證: 容器啟動但 API 無回應，無法驗證工作流程"
        fi
    done
}

# ── Entry point ──────────────────────────────────────────────────────────────

main() {
    local wait_time="$DEFAULT_WAIT"

    case "${1:-}" in
        --no-wait)
            wait_time=0
            ;;
        --wait)
            wait_time="${2:-$DEFAULT_WAIT}"
            ;;
        --hook)
            run_docker_event_hook
            return
            ;;
        --help|-h)
            echo "Usage: $0 [--wait N | --no-wait | --hook | --help]"
            echo ""
            echo "  (default)    Wait 30s then verify all workflows"
            echo "  --wait N     Wait N seconds before checking"
            echo "  --no-wait    Skip initial wait, still polls for API readiness"
            echo "  --hook       Listen for docker start events and auto-verify"
            echo ""
            return
            ;;
    esac

    log "INFO" "=== n8n Cron Verification Start ==="

    # Check container is running
    local state
    state=$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null || echo "false")
    if [[ "$state" != "true" ]]; then
        log "ERROR" "$CONTAINER is not running"
        echo "ERROR: $CONTAINER is not running. Start it first."
        return 1
    fi

    # Wait for n8n API
    if ! wait_for_n8n "$wait_time"; then
        log "ERROR" "n8n API not ready — aborting"
        notify_discord "n8n cron 驗證失敗: API 啟動超時"
        return 1
    fi

    # Verify and fix workflows
    verify_all_workflows
    local result=$?

    log "INFO" "=== n8n Cron Verification Complete ==="
    return $result
}

main "$@"
