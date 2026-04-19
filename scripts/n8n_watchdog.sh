#!/usr/bin/env bash
# n8n Cron Watchdog — detects stalled workflows and auto-restarts n8n.
#
# Runs every 30 minutes (via Task Scheduler or loop).
# Checks if n8n is running and if WF 1001 has executed recently during
# business hours (08:00-20:00 Asia/Taipei). If stalled, restarts n8n
# and sends a Discord webhook notification.
#
# Usage:
#   bash scripts/n8n_watchdog.sh              # Single check
#   bash scripts/n8n_watchdog.sh --loop       # Run forever every 30 min
#   bash scripts/n8n_watchdog.sh --install    # Install Windows Task Scheduler job
#
# Requirements: docker, curl, sqlite3 (bundled with Git Bash)
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/logs"
LOG_FILE="$LOG_DIR/n8n_watchdog.log"

CONTAINER="ielts-n8n"
N8N_PORT=5800
N8N_API_KEY="jarvis-api-key-2026"
N8N_BASE_URL="http://localhost:${N8N_PORT}"

# Discord webhook for notifications
DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/1490915452631650306/ccglLeI-LK_Ki_KJ0DpUBwAWf-HA7O84AzhylNAogC6nY80F3oh0tyFAJuy1GTXbSSnp"

# Workflow IDs to monitor
WORKFLOW_IDS=(1001 1002 1003 1004)
# WF 1001 is the main YouTube pipeline — check for recent executions
PRIMARY_WF=1001
# Max hours since last successful execution before alerting (during business hours)
STALE_THRESHOLD_HOURS=3
# Business hours (Asia/Taipei) — only alert during these hours
BIZ_HOUR_START=8
BIZ_HOUR_END=20

LOOP_INTERVAL=1800  # 30 minutes

# ── Logging ──────────────────────────────────────────────────────────────────

mkdir -p "$LOG_DIR"

log() {
    local level="$1"
    shift
    local msg="$*"
    local ts
    ts="$(date '+%Y-%m-%d %H:%M:%S')"
    echo "[$ts] [$level] $msg" | tee -a "$LOG_FILE"
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
        log "WARN" "Failed to send Discord notification"
    }
}

# ── Container checks ────────────────────────────────────────────────────────

is_container_running() {
    local state
    state=$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null || echo "false")
    [[ "$state" == "true" ]]
}

is_n8n_responsive() {
    # Check if the n8n editor UI is accessible (does not require API key).
    # The /healthz endpoint returns 200 when n8n is ready.
    # Fallback: check the editor page returns 200.
    local http_code
    http_code=$(curl -s -o /dev/null -w '%{http_code}' \
        --connect-timeout 5 --max-time 10 \
        "${N8N_BASE_URL}/healthz" 2>/dev/null || echo "000")
    if [[ "$http_code" == "200" ]]; then
        return 0
    fi
    # Fallback: try the editor page
    http_code=$(curl -s -o /dev/null -w '%{http_code}' \
        --connect-timeout 5 --max-time 10 \
        "${N8N_BASE_URL}/" 2>/dev/null || echo "000")
    [[ "$http_code" == "200" || "$http_code" == "301" || "$http_code" == "302" ]]
}

restart_container() {
    log "WARN" "Restarting $CONTAINER..."
    docker restart "$CONTAINER" 2>/dev/null

    # Wait up to 60 seconds for n8n to become responsive
    local attempts=0
    while (( attempts < 12 )); do
        sleep 5
        if is_n8n_responsive; then
            log "INFO" "$CONTAINER restarted and responsive"
            return 0
        fi
        (( attempts++ ))
    done

    log "ERROR" "$CONTAINER restarted but not responsive after 60s"
    return 1
}

# ── Workflow checks ──────────────────────────────────────────────────────────

check_workflow_active() {
    local wf_id="$1"
    # Use docker exec + n8n CLI to check workflow status (API key auth broken in n8n 2.x)
    local output
    output=$(docker exec "$CONTAINER" n8n list:workflow 2>/dev/null || echo "")

    if [[ -z "$output" ]]; then
        log "WARN" "Could not list workflows via CLI"
        return 1
    fi

    # n8n list:workflow outputs "ID|Name" for active workflows
    echo "$output" | grep -q "^${wf_id}|"
}

activate_workflow() {
    local wf_id="$1"
    # Use n8n CLI to set workflow active, then restart container for it to take effect
    docker exec "$CONTAINER" n8n update:workflow --id="$wf_id" --active=true 2>/dev/null || {
        log "WARN" "Failed to activate WF $wf_id via CLI"
        return 1
    }
    log "INFO" "WF $wf_id set to active via CLI (restart needed to take effect)"
}

check_recent_execution() {
    # Check if WF has had a successful execution in the last N hours.
    # Uses n8n event log files inside the container (API key auth broken in n8n 2.x).
    local wf_id="$1"
    local hours="$2"

    local has_recent
    has_recent=$(docker exec "$CONTAINER" sh -c "cat /home/node/.n8n/n8nEventLog.log 2>/dev/null" \
        | grep "workflow.success" \
        | grep "\"workflowId\":\"${wf_id}\"" \
        | tail -1 \
        | python -c "
import sys, json
from datetime import datetime, timedelta, timezone

try:
    line = sys.stdin.readline().strip()
    if not line:
        print('no_executions')
        sys.exit(0)
    data = json.loads(line)
    ts = data.get('ts', '')
    if not ts:
        print('no_timestamp')
        sys.exit(0)
    finished_dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=${hours})
    if finished_dt >= cutoff:
        print('recent')
    else:
        print('stale')
except Exception as e:
    print(f'error:{e}')
" 2>/dev/null || echo "error")

    [[ "$has_recent" == "recent" ]]
}

# ── Timezone check ───────────────────────────────────────────────────────────

is_business_hours() {
    local hour
    hour=$(TZ='Asia/Taipei' date '+%H' 2>/dev/null || date '+%H')
    hour=$((10#$hour))  # Remove leading zero
    (( hour >= BIZ_HOUR_START && hour < BIZ_HOUR_END ))
}

container_uptime_hours() {
    # Returns how many hours the container has been running.
    # Returns 999 if unable to determine (assume long uptime).
    local started_at
    started_at=$(docker inspect -f '{{.State.StartedAt}}' "$CONTAINER" 2>/dev/null || echo "")
    if [[ -z "$started_at" ]]; then
        echo "999"
        return
    fi
    python -c "
from datetime import datetime, timezone
try:
    started = datetime.fromisoformat('${started_at}'.replace('Z', '+00:00'))
    now = datetime.now(timezone.utc)
    hours = (now - started).total_seconds() / 3600
    print(int(hours))
except:
    print(999)
" 2>/dev/null || echo "999"
}

# ── Main check cycle ────────────────────────────────────────────────────────

run_check() {
    log "INFO" "Starting n8n watchdog check cycle"

    # 1. Check if container is running
    if ! is_container_running; then
        log "ERROR" "$CONTAINER is NOT running"
        notify_discord "n8n Watchdog: $CONTAINER 容器未執行，正在重啟..."

        if restart_container; then
            notify_discord "n8n Watchdog: $CONTAINER 已自動重啟成功"
        else
            notify_discord "n8n Watchdog: $CONTAINER 重啟失敗！需要手動處理"
            return 1
        fi
    fi

    # 2. Check if n8n API is responsive
    if ! is_n8n_responsive; then
        log "WARN" "n8n API not responsive, restarting..."
        notify_discord "n8n Watchdog: n8n API 無回應，正在重啟容器..."

        if restart_container; then
            notify_discord "n8n Watchdog: n8n 重啟後 API 恢復正常"
        else
            notify_discord "n8n Watchdog: n8n 重啟後 API 仍然無回應"
            return 1
        fi
    fi

    # 3. Check all workflows are active
    local inactive_wfs=()
    local reactivated_wfs=()

    for wf_id in "${WORKFLOW_IDS[@]}"; do
        if ! check_workflow_active "$wf_id"; then
            log "WARN" "Workflow $wf_id is INACTIVE"
            inactive_wfs+=("$wf_id")

            # Try to reactivate
            activate_workflow "$wf_id"
            sleep 2

            if check_workflow_active "$wf_id"; then
                log "INFO" "Workflow $wf_id reactivated successfully"
                reactivated_wfs+=("$wf_id")
            else
                log "ERROR" "Failed to reactivate workflow $wf_id"
            fi
        fi
    done

    if (( ${#inactive_wfs[@]} > 0 )); then
        local msg="n8n Watchdog: 偵測到停用的工作流程: ${inactive_wfs[*]}"
        if (( ${#reactivated_wfs[@]} > 0 )); then
            msg="$msg | 已重新啟用: ${reactivated_wfs[*]}"
        fi
        local failed_count=$(( ${#inactive_wfs[@]} - ${#reactivated_wfs[@]} ))
        if (( failed_count > 0 )); then
            msg="$msg | 啟用失敗: ${failed_count} 個"
        fi
        notify_discord "$msg"
    fi

    # 4. Check if primary workflow has recent executions (business hours only)
    if is_business_hours; then
        # Skip stale-execution check if container was recently started/restarted
        local uptime
        uptime=$(container_uptime_hours)
        if (( uptime < STALE_THRESHOLD_HOURS )); then
            log "INFO" "Container uptime ${uptime}h < ${STALE_THRESHOLD_HOURS}h threshold — skipping stale execution check"
        elif ! check_recent_execution "$PRIMARY_WF" "$STALE_THRESHOLD_HOURS"; then
            log "WARN" "WF $PRIMARY_WF has no successful execution in last ${STALE_THRESHOLD_HOURS}h"

            # Check if the workflow is at least active
            if check_workflow_active "$PRIMARY_WF"; then
                # Workflow is active but no recent execution — might be stalled cron
                log "WARN" "WF $PRIMARY_WF is active but no recent execution — restarting container to reset cron triggers"
                notify_discord "n8n Watchdog: WF ${PRIMARY_WF} 已 ${STALE_THRESHOLD_HOURS} 小時沒有成功執行，cron 可能卡住，正在重啟..."

                if restart_container; then
                    # Verify workflows are active after restart
                    sleep 10
                    local post_restart_inactive=()
                    for wf_id in "${WORKFLOW_IDS[@]}"; do
                        if ! check_workflow_active "$wf_id"; then
                            post_restart_inactive+=("$wf_id")
                            activate_workflow "$wf_id"
                            sleep 2
                        fi
                    done

                    if (( ${#post_restart_inactive[@]} > 0 )); then
                        notify_discord "n8n Watchdog: 重啟後以下 WF 需要重新啟用: ${post_restart_inactive[*]} — 已嘗試啟用"
                    fi
                    notify_discord "n8n Watchdog: n8n 已重啟，cron triggers 應已重新註冊"
                else
                    notify_discord "n8n Watchdog: n8n 重啟失敗！cron triggers 可能仍然卡住"
                fi
            else
                log "WARN" "WF $PRIMARY_WF is inactive — activating"
                activate_workflow "$PRIMARY_WF"
                notify_discord "n8n Watchdog: WF ${PRIMARY_WF} 停用中，已嘗試重新啟用"
            fi
        else
            log "INFO" "WF $PRIMARY_WF has recent successful execution — OK"
        fi
    else
        log "INFO" "Outside business hours — skipping execution freshness check"
    fi

    log "INFO" "Check cycle complete"
}

# ── Task Scheduler install ───────────────────────────────────────────────────

install_task_scheduler() {
    local script_path
    script_path=$(cygpath -w "$SCRIPT_DIR/n8n_watchdog.sh" 2>/dev/null || echo "$SCRIPT_DIR/n8n_watchdog.sh")

    local git_bash
    git_bash="C:\\Program Files\\Git\\bin\\bash.exe"

    echo "Installing Windows Task Scheduler job: N8N_Cron_Watchdog"
    echo "  Runs every 30 minutes"

    schtasks //create //tn "N8N_Cron_Watchdog" \
        //tr "\"$git_bash\" \"$script_path\"" \
        //sc minute //mo 30 \
        //ru "$(whoami)" \
        //rl highest //f 2>&1

    if [[ $? -eq 0 ]]; then
        echo "Installed successfully: N8N_Cron_Watchdog"
    else
        echo "Failed to install Task Scheduler job"
    fi
}

# ── Entry point ──────────────────────────────────────────────────────────────

main() {
    case "${1:-}" in
        --loop)
            log "INFO" "n8n Watchdog started in loop mode (interval: ${LOOP_INTERVAL}s)"
            notify_discord "n8n Watchdog: 監控服務已啟動 (每 30 分鐘檢查一次)"
            while true; do
                run_check || true
                sleep "$LOOP_INTERVAL"
            done
            ;;
        --install)
            install_task_scheduler
            ;;
        *)
            run_check
            ;;
    esac
}

main "$@"
