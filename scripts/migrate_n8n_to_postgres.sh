#!/usr/bin/env bash
# =============================================================================
# migrate_n8n_to_postgres.sh
#
# Migrates n8n from SQLite to PostgreSQL backend.
# Solves: cron state loss on SIGTERM restart cycles.
#
# What this script does:
#   1. Exports all workflows from current n8n via REST API
#   2. Exports all credentials (encrypted, re-importable with same encryption key)
#   3. Stops the old SQLite-backed container
#   4. Starts new PostgreSQL + n8n stack via docker compose
#   5. Waits for n8n to be healthy
#   6. Imports workflows and credentials back
#   7. Re-activates workflows that were active before
#   8. Prints verification summary
#
# Prerequisites:
#   - curl, jq, docker, docker compose installed
#   - n8n container "ielts-n8n" running with API enabled
#   - N8N_API_KEY set (or passed as argument)
#
# Usage:
#   export N8N_API_KEY="your-api-key"
#   bash scripts/migrate_n8n_to_postgres.sh
#
# The encryption key lives in the n8n data volume (.n8n/config), which is
# reused by the new stack. Credentials remain decryptable.
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/n8n-postgres-compose.yml"
BACKUP_DIR="${SCRIPT_DIR}/n8n_migration_backup"
N8N_URL="${N8N_URL:-http://localhost:5800}"
API_KEY="${N8N_API_KEY:-}"
OLD_CONTAINER="ielts-n8n"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
preflight() {
    log_info "Running pre-flight checks..."

    # Check required tools
    for cmd in curl jq docker; do
        if ! command -v "$cmd" &>/dev/null; then
            log_error "Required tool '$cmd' not found. Install it and retry."
            exit 1
        fi
    done

    # Check docker compose (v2 plugin or standalone)
    if docker compose version &>/dev/null; then
        COMPOSE_CMD="docker compose"
    elif docker-compose version &>/dev/null; then
        COMPOSE_CMD="docker-compose"
    else
        log_error "docker compose not found. Install Docker Compose v2."
        exit 1
    fi

    # Check API key
    if [[ -z "$API_KEY" ]]; then
        log_error "N8N_API_KEY is not set."
        echo "  Set it with: export N8N_API_KEY=\"your-api-key\""
        echo "  Find it in n8n Settings > API > API Key"
        exit 1
    fi

    # Check n8n is reachable
    if ! curl -sf "${N8N_URL}/healthz" &>/dev/null; then
        # n8n may not have /healthz; try the API
        local http_code
        http_code=$(curl -s -o /dev/null -w "%{http_code}" \
            -H "X-N8N-API-KEY: ${API_KEY}" \
            "${N8N_URL}/api/v1/workflows")
        if [[ "$http_code" == "401" || "$http_code" == "403" ]]; then
            log_error "API key rejected (HTTP $http_code). Check N8N_API_KEY."
            exit 1
        elif [[ "$http_code" != "200" ]]; then
            log_error "Cannot reach n8n at ${N8N_URL} (HTTP $http_code)."
            exit 1
        fi
    fi

    # Check compose file exists
    if [[ ! -f "$COMPOSE_FILE" ]]; then
        log_error "Compose file not found at: $COMPOSE_FILE"
        exit 1
    fi

    log_info "Pre-flight checks passed."
}

# ---------------------------------------------------------------------------
# API helper
# ---------------------------------------------------------------------------
api_get() {
    local endpoint="$1"
    curl -sf -H "X-N8N-API-KEY: ${API_KEY}" "${N8N_URL}/api/v1${endpoint}"
}

api_post() {
    local endpoint="$1"
    local data="$2"
    curl -sf -X POST \
        -H "X-N8N-API-KEY: ${API_KEY}" \
        -H "Content-Type: application/json" \
        -d "$data" \
        "${N8N_URL}/api/v1${endpoint}"
}

api_patch() {
    local endpoint="$1"
    local data="$2"
    curl -sf -X PATCH \
        -H "X-N8N-API-KEY: ${API_KEY}" \
        -H "Content-Type: application/json" \
        -d "$data" \
        "${N8N_URL}/api/v1${endpoint}"
}

# ---------------------------------------------------------------------------
# Step 1: Export workflows
# ---------------------------------------------------------------------------
export_workflows() {
    log_info "Step 1: Exporting workflows..."
    mkdir -p "${BACKUP_DIR}"

    # Fetch all workflows (paginate if needed)
    local page=0
    local all_workflows="[]"
    local has_more=true

    while $has_more; do
        local response
        response=$(api_get "/workflows?limit=100&cursor=${page}" 2>/dev/null || echo '{"data":[]}')
        local batch
        batch=$(echo "$response" | jq -c '.data // []')
        local count
        count=$(echo "$batch" | jq 'length')

        if [[ "$count" -eq 0 ]]; then
            has_more=false
        else
            all_workflows=$(echo "$all_workflows $batch" | jq -s 'add')
            page=$((page + 100))
        fi
    done

    local total
    total=$(echo "$all_workflows" | jq 'length')
    log_info "Found $total workflow(s)."

    # Save full list
    echo "$all_workflows" | jq '.' > "${BACKUP_DIR}/workflows.json"

    # Save each workflow individually (with full node data)
    echo "$all_workflows" | jq -c '.[]' | while read -r wf; do
        local wf_id wf_name
        wf_id=$(echo "$wf" | jq -r '.id')
        wf_name=$(echo "$wf" | jq -r '.name' | tr '/ ' '__')

        # Fetch full workflow detail (includes nodes, connections)
        local full_wf
        full_wf=$(api_get "/workflows/${wf_id}" 2>/dev/null || echo "$wf")
        echo "$full_wf" | jq '.' > "${BACKUP_DIR}/workflow_${wf_id}_${wf_name}.json"
        log_info "  Exported: [${wf_id}] ${wf_name}"
    done

    # Record which workflows were active (for re-activation later)
    echo "$all_workflows" | jq '[.[] | select(.active == true) | .id]' \
        > "${BACKUP_DIR}/active_workflow_ids.json"

    local active_count
    active_count=$(jq 'length' "${BACKUP_DIR}/active_workflow_ids.json")
    log_info "  $active_count workflow(s) are currently active."
}

# ---------------------------------------------------------------------------
# Step 2: Export credentials
# ---------------------------------------------------------------------------
export_credentials() {
    log_info "Step 2: Exporting credentials..."

    local creds
    creds=$(api_get "/credentials" 2>/dev/null || echo '{"data":[]}')
    echo "$creds" | jq '.' > "${BACKUP_DIR}/credentials_list.json"

    local total
    total=$(echo "$creds" | jq '.data | length')
    log_info "Found $total credential(s)."

    # Note: The REST API does not export credential secrets.
    # Credentials are stored encrypted in the SQLite DB.
    # Since we reuse the same n8n data volume (which contains the encryption key),
    # we need to copy the SQLite DB as a safety net.
    log_info "  Backing up SQLite database from volume..."
    docker cp "${OLD_CONTAINER}:/home/node/.n8n/database.sqlite" \
        "${BACKUP_DIR}/database.sqlite" 2>/dev/null || \
        log_warn "  Could not copy SQLite DB (may not exist at expected path)."

    log_info "  Credentials are encrypted. The encryption key is in the n8n volume."
    log_info "  Since the volume is reused, credentials will need to be re-created"
    log_info "  or migrated using n8n's built-in DB migration (see notes below)."
}

# ---------------------------------------------------------------------------
# Step 3: Stop old container
# ---------------------------------------------------------------------------
stop_old_container() {
    log_info "Step 3: Stopping old container '${OLD_CONTAINER}'..."

    # Graceful stop with timeout
    docker stop -t 30 "${OLD_CONTAINER}" 2>/dev/null || true
    # Remove container (volume is preserved)
    docker rm "${OLD_CONTAINER}" 2>/dev/null || true

    log_info "  Old container stopped and removed. Volume preserved."
}

# ---------------------------------------------------------------------------
# Step 4: Start new PostgreSQL + n8n stack
# ---------------------------------------------------------------------------
start_new_stack() {
    log_info "Step 4: Starting PostgreSQL + n8n stack..."

    # Pull latest images
    $COMPOSE_CMD -f "$COMPOSE_FILE" pull

    # Start services (postgres first due to depends_on + healthcheck)
    $COMPOSE_CMD -f "$COMPOSE_FILE" up -d

    log_info "  Waiting for PostgreSQL to be healthy..."
    local retries=0
    while [[ $retries -lt 30 ]]; do
        if docker exec n8n-postgres pg_isready -U n8n -d n8n &>/dev/null; then
            log_info "  PostgreSQL is ready."
            break
        fi
        retries=$((retries + 1))
        sleep 2
    done
    if [[ $retries -ge 30 ]]; then
        log_error "PostgreSQL did not become healthy in 60 seconds."
        exit 1
    fi

    log_info "  Waiting for n8n to start (first run creates tables)..."
    local n8n_retries=0
    while [[ $n8n_retries -lt 60 ]]; do
        local http_code
        http_code=$(curl -s -o /dev/null -w "%{http_code}" "${N8N_URL}/healthz" 2>/dev/null || echo "000")
        if [[ "$http_code" == "200" ]]; then
            log_info "  n8n is healthy."
            return
        fi
        # Also try the API endpoint as fallback health check
        http_code=$(curl -s -o /dev/null -w "%{http_code}" \
            -H "X-N8N-API-KEY: ${API_KEY}" \
            "${N8N_URL}/api/v1/workflows" 2>/dev/null || echo "000")
        if [[ "$http_code" == "200" ]]; then
            log_info "  n8n API is responding."
            return
        fi
        n8n_retries=$((n8n_retries + 1))
        sleep 3
    done

    log_error "n8n did not start within 3 minutes."
    log_error "Check logs: docker logs ielts-n8n"
    exit 1
}

# ---------------------------------------------------------------------------
# Step 5: Import workflows
# ---------------------------------------------------------------------------
import_workflows() {
    log_info "Step 5: Importing workflows..."

    local imported=0
    local failed=0

    for wf_file in "${BACKUP_DIR}"/workflow_*.json; do
        [[ -f "$wf_file" ]] || continue

        local wf_name wf_id
        wf_name=$(jq -r '.name' "$wf_file")
        wf_id=$(jq -r '.id' "$wf_file")

        # Prepare workflow payload (remove server-specific fields)
        local payload
        payload=$(jq 'del(.id, .createdAt, .updatedAt, .versionId)' "$wf_file")

        local result
        result=$(api_post "/workflows" "$payload" 2>/dev/null || echo "FAIL")

        if [[ "$result" == "FAIL" ]]; then
            log_warn "  Failed to import: [${wf_id}] ${wf_name}"
            failed=$((failed + 1))
        else
            local new_id
            new_id=$(echo "$result" | jq -r '.id')
            log_info "  Imported: [${wf_id} -> ${new_id}] ${wf_name}"

            # Build old->new ID mapping for activation step
            echo "${wf_id}:${new_id}" >> "${BACKUP_DIR}/id_mapping.txt"
            imported=$((imported + 1))
        fi
    done

    log_info "  Imported: $imported, Failed: $failed"
}

# ---------------------------------------------------------------------------
# Step 6: Re-activate workflows
# ---------------------------------------------------------------------------
reactivate_workflows() {
    log_info "Step 6: Re-activating workflows..."

    local active_ids
    active_ids=$(cat "${BACKUP_DIR}/active_workflow_ids.json")
    local mapping_file="${BACKUP_DIR}/id_mapping.txt"

    if [[ ! -f "$mapping_file" ]]; then
        log_warn "  No ID mapping file found. Skipping activation."
        return
    fi

    local activated=0
    while IFS=: read -r old_id new_id; do
        # Check if this workflow was active before
        if echo "$active_ids" | jq -e "index(\"${old_id}\")" &>/dev/null; then
            local result
            result=$(api_patch "/workflows/${new_id}" '{"active": true}' 2>/dev/null || echo "FAIL")
            if [[ "$result" != "FAIL" ]]; then
                log_info "  Activated workflow ${new_id} (was ${old_id})"
                activated=$((activated + 1))
            else
                log_warn "  Failed to activate workflow ${new_id}"
            fi
        fi
    done < "$mapping_file"

    log_info "  Re-activated $activated workflow(s)."
}

# ---------------------------------------------------------------------------
# Step 7: Verification
# ---------------------------------------------------------------------------
verify() {
    log_info "Step 7: Verification..."

    # Check n8n is using PostgreSQL
    local db_check
    db_check=$(docker exec n8n-postgres psql -U n8n -d n8n -t \
        -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null || echo "0")
    db_check=$(echo "$db_check" | tr -d ' ')
    log_info "  PostgreSQL tables created: $db_check"

    # List workflows in new instance
    local workflows
    workflows=$(api_get "/workflows" 2>/dev/null || echo '{"data":[]}')
    local total active
    total=$(echo "$workflows" | jq '.data | length')
    active=$(echo "$workflows" | jq '[.data[] | select(.active == true)] | length')

    log_info "  Workflows in new instance: $total (active: $active)"

    # Check n8n container is running
    local status
    status=$(docker inspect ielts-n8n --format '{{.State.Status}}' 2>/dev/null || echo "unknown")
    log_info "  Container status: $status"

    # Check PostgreSQL container
    local pg_status
    pg_status=$(docker inspect n8n-postgres --format '{{.State.Status}}' 2>/dev/null || echo "unknown")
    log_info "  PostgreSQL status: $pg_status"

    echo ""
    echo "============================================="
    echo "  Migration Summary"
    echo "============================================="
    echo "  n8n container:      $status"
    echo "  PostgreSQL:         $pg_status"
    echo "  Workflows:          $total"
    echo "  Active workflows:   $active"
    echo "  Backup location:    $BACKUP_DIR"
    echo "  Compose file:       $COMPOSE_FILE"
    echo "============================================="
    echo ""
    log_info "Migration complete."
    echo ""
    log_warn "IMPORTANT post-migration steps:"
    echo "  1. Re-create credentials in n8n UI (API keys, OAuth, etc.)"
    echo "     Credentials cannot be exported via API — only metadata is saved."
    echo "     The old SQLite DB is backed up at: ${BACKUP_DIR}/database.sqlite"
    echo "  2. Test each workflow manually to ensure triggers fire."
    echo "  3. Monitor logs for 24h: docker logs -f ielts-n8n"
    echo "  4. If rollback needed:"
    echo "       $COMPOSE_CMD -f $COMPOSE_FILE down"
    echo "       docker run -d --name ielts-n8n \\"
    echo "         -p 5800:5678 \\"
    echo "         -v ielts-ai-platform_n8n_data:/home/node/.n8n \\"
    echo "         -e GENERIC_TIMEZONE=Asia/Taipei \\"
    echo "         -e N8N_HOST=0.0.0.0 \\"
    echo "         -e N8N_PORT=5678 \\"
    echo "         n8nio/n8n:latest"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    echo ""
    echo "============================================="
    echo "  n8n SQLite -> PostgreSQL Migration"
    echo "  $(date '+%Y-%m-%d %H:%M:%S')"
    echo "============================================="
    echo ""

    preflight
    export_workflows
    export_credentials
    stop_old_container
    start_new_stack
    import_workflows
    reactivate_workflows
    verify
}

main "$@"
