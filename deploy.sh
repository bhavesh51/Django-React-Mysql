#!/usr/bin/env bash
# =============================================================================
# deploy.sh  —  End-to-end OpenShift deployment for PayGate POC
#
# Usage:
#   ./deploy.sh [OPTIONS]
#
# Options:
#   --namespace   NAMESPACE     OpenShift project name          (default: paygate)
#   --db-password PASSWORD      MySQL app user password         (REQUIRED)
#   --db-root-password PASSWORD MySQL root password             (REQUIRED)
#   --django-secret SECRET      Django SECRET_KEY               (REQUIRED)
#   --skip-build                Skip image builds (use existing images)
#   --teardown                  Delete everything in the namespace
#   --help                      Show this help message
#
# Prerequisites:
#   - oc (OpenShift CLI) installed and logged in  →  oc login <cluster>
#   - Sufficient permissions to create projects, builds, routes
#
# Example:
#   ./deploy.sh \
#     --namespace paygate \
#     --db-password "S3cur3DB!" \
#     --db-root-password "R00tS3cur3!" \
#     --django-secret "$(openssl rand -base64 48)"
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
header()  { echo -e "\n${BOLD}${CYAN}══════════════════════════════════════════${RESET}"; \
            echo -e "${BOLD}${CYAN}  $*${RESET}"; \
            echo -e "${BOLD}${CYAN}══════════════════════════════════════════${RESET}"; }

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
NAMESPACE="paygate"
DB_PASSWORD=""
DB_ROOT_PASSWORD=""
DJANGO_SECRET=""
SKIP_BUILD=false
TEARDOWN=false
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFESTS_DIR="${SCRIPT_DIR}/openshift"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
usage() {
  sed -n '3,30p' "$0" | sed 's/^# \?//'
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --namespace)       NAMESPACE="$2";         shift 2 ;;
    --db-password)     DB_PASSWORD="$2";       shift 2 ;;
    --db-root-password) DB_ROOT_PASSWORD="$2"; shift 2 ;;
    --django-secret)   DJANGO_SECRET="$2";     shift 2 ;;
    --skip-build)      SKIP_BUILD=true;        shift   ;;
    --teardown)        TEARDOWN=true;          shift   ;;
    --help|-h)         usage ;;
    *) error "Unknown option: $1"; usage ;;
  esac
done

# ---------------------------------------------------------------------------
# Tear-down mode
# ---------------------------------------------------------------------------
if [[ "${TEARDOWN}" == true ]]; then
  header "TEARDOWN: deleting namespace ${NAMESPACE}"
  oc delete project "${NAMESPACE}" --ignore-not-found
  success "Namespace ${NAMESPACE} deleted."
  exit 0
fi

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
header "Pre-flight checks"

if ! command -v oc &>/dev/null; then
  error "'oc' CLI not found. Install it from https://mirror.openshift.com/pub/openshift-v4/clients/ocp/"
  exit 1
fi

if ! oc whoami &>/dev/null; then
  error "Not logged in to OpenShift. Run: oc login <cluster-url>"
  exit 1
fi

if [[ -z "${DB_PASSWORD}" || -z "${DB_ROOT_PASSWORD}" || -z "${DJANGO_SECRET}" ]]; then
  error "Required flags missing. Run with --help for usage."
  exit 1
fi

success "oc is available and logged in as: $(oc whoami)"
success "Target namespace: ${NAMESPACE}"

# ---------------------------------------------------------------------------
# Helper: wait for a deployment to be fully rolled out
# ---------------------------------------------------------------------------
wait_for_deployment() {
  local name="$1"
  local timeout="${2:-300s}"
  info "Waiting for deployment/${name} to be ready (timeout: ${timeout}) ..."
  oc rollout status deployment/"${name}" -n "${NAMESPACE}" --timeout="${timeout}" \
    || { error "Deployment ${name} did not become ready in time."; exit 1; }
  success "deployment/${name} is ready."
}

# ---------------------------------------------------------------------------
# Helper: wait for a build to complete
# ---------------------------------------------------------------------------
wait_for_build() {
  local bc_name="$1"
  info "Waiting for BuildConfig/${bc_name} to finish ..."
  local build_name
  build_name=$(oc get builds -n "${NAMESPACE}" \
    --selector=buildconfig="${bc_name}" \
    --sort-by='.metadata.creationTimestamp' \
    -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null || echo "")

  if [[ -z "${build_name}" ]]; then
    warn "No build found for ${bc_name} yet; waiting 10 s ..."
    sleep 10
    build_name=$(oc get builds -n "${NAMESPACE}" \
      --selector=buildconfig="${bc_name}" \
      --sort-by='.metadata.creationTimestamp' \
      -o jsonpath='{.items[-1].metadata.name}')
  fi

  oc wait "build/${build_name}" -n "${NAMESPACE}" \
    --for=condition=Complete --timeout=600s \
    || { error "Build ${build_name} failed. Run: oc logs build/${build_name} -n ${NAMESPACE}"; exit 1; }
  success "Build ${build_name} completed."
}

# ---------------------------------------------------------------------------
# STEP 1 — Create / switch to the project
# ---------------------------------------------------------------------------
header "Step 1 — Project (namespace: ${NAMESPACE})"

if oc get project "${NAMESPACE}" &>/dev/null; then
  info "Project '${NAMESPACE}' already exists. Switching ..."
  oc project "${NAMESPACE}"
else
  info "Creating project '${NAMESPACE}' ..."
  oc new-project "${NAMESPACE}" \
    --description="PayGate POC — Payment Gateway" \
    --display-name="PayGate POC"
fi
success "Project ready."

# ---------------------------------------------------------------------------
# STEP 2 — Apply Namespace labels (idempotent)
# ---------------------------------------------------------------------------
oc apply -f "${MANIFESTS_DIR}/00-namespace.yaml"

# ---------------------------------------------------------------------------
# STEP 3 — Create / update Secret with real values
# ---------------------------------------------------------------------------
header "Step 2 — Secrets"

b64() { printf '%s' "$1" | base64; }

# Build the secret as a patch so the file placeholders are never used directly
oc create secret generic paygate-secret \
  --from-literal=db-name="payment_gateway" \
  --from-literal=db-user="pguser" \
  --from-literal=db-password="${DB_PASSWORD}" \
  --from-literal=db-root-password="${DB_ROOT_PASSWORD}" \
  --from-literal=django-secret-key="${DJANGO_SECRET}" \
  -n "${NAMESPACE}" \
  --dry-run=client -o yaml | oc apply -f -
success "Secret paygate-secret applied."

# ---------------------------------------------------------------------------
# STEP 4 — Apply ConfigMap
# ---------------------------------------------------------------------------
header "Step 3 — ConfigMap"
oc apply -f "${MANIFESTS_DIR}/02-configmap.yaml"
success "ConfigMap paygate-config applied."

# ---------------------------------------------------------------------------
# STEP 5 — Deploy MySQL
# ---------------------------------------------------------------------------
header "Step 4 — MySQL"
oc apply -f "${MANIFESTS_DIR}/03-mysql.yaml"
wait_for_deployment "paygate-mysql" "300s"

# ---------------------------------------------------------------------------
# STEP 6 — Build backend image
# ---------------------------------------------------------------------------
header "Step 5 — Build backend image"

if [[ "${SKIP_BUILD}" == false ]]; then
  # Apply the ImageStream + BuildConfig
  oc apply -f "${MANIFESTS_DIR}/04-backend.yaml"

  # Start a binary build uploading the backend directory
  info "Starting backend Docker build (uploading ${SCRIPT_DIR}/backend/) ..."
  oc start-build paygate-backend \
    --from-dir="${SCRIPT_DIR}/backend" \
    --follow=false \
    -n "${NAMESPACE}"
  wait_for_build "paygate-backend"
else
  warn "--skip-build: skipping backend image build."
  oc apply -f "${MANIFESTS_DIR}/04-backend.yaml"
fi

# ---------------------------------------------------------------------------
# STEP 7 — Build frontend image
# ---------------------------------------------------------------------------
header "Step 6 — Build frontend image"

if [[ "${SKIP_BUILD}" == false ]]; then
  oc apply -f "${MANIFESTS_DIR}/05-frontend.yaml"

  info "Starting frontend Docker build (uploading ${SCRIPT_DIR}/frontend/) ..."
  oc start-build paygate-frontend \
    --from-dir="${SCRIPT_DIR}/frontend" \
    --follow=false \
    -n "${NAMESPACE}"
  wait_for_build "paygate-frontend"
else
  warn "--skip-build: skipping frontend image build."
  oc apply -f "${MANIFESTS_DIR}/05-frontend.yaml"
fi

# ---------------------------------------------------------------------------
# STEP 8 — Deploy backend + frontend
# ---------------------------------------------------------------------------
header "Step 7 — Deploy backend & frontend"
wait_for_deployment "paygate-backend"  "300s"
wait_for_deployment "paygate-frontend" "180s"

# ---------------------------------------------------------------------------
# STEP 9 — Apply HPA and NetworkPolicy
# ---------------------------------------------------------------------------
header "Step 8 — HPA & NetworkPolicy"
oc apply -f "${MANIFESTS_DIR}/06-hpa.yaml"
oc apply -f "${MANIFESTS_DIR}/07-networkpolicy.yaml"
success "HPA and NetworkPolicy applied."

# ---------------------------------------------------------------------------
# STEP 10 — Discover routes and patch CORS
# ---------------------------------------------------------------------------
header "Step 9 — Route discovery & CORS patch"

BACKEND_HOST=$(oc get route paygate-backend  -n "${NAMESPACE}" \
  -o jsonpath='{.spec.host}' 2>/dev/null || echo "")
FRONTEND_HOST=$(oc get route paygate-frontend -n "${NAMESPACE}" \
  -o jsonpath='{.spec.host}' 2>/dev/null || echo "")

if [[ -n "${BACKEND_HOST}" && -n "${FRONTEND_HOST}" ]]; then
  FRONTEND_URL="https://${FRONTEND_HOST}"
  info "Backend  route : https://${BACKEND_HOST}"
  info "Frontend route : ${FRONTEND_URL}"

  # Patch the ConfigMap so Django's CORS_EXTRA_ORIGINS includes the
  # OpenShift frontend URL, then trigger a backend rollout
  oc patch configmap paygate-config -n "${NAMESPACE}" \
    --type merge \
    -p "{\"data\":{\"CORS_EXTRA_ORIGINS\":\"${FRONTEND_URL}\",\"DJANGO_ALLOWED_HOSTS\":\"paygate-backend,paygate-backend.paygate.svc.cluster.local,${BACKEND_HOST},localhost\"}}"

  info "Rolling out backend with updated CORS config ..."
  oc rollout restart deployment/paygate-backend -n "${NAMESPACE}"
  wait_for_deployment "paygate-backend" "180s"
  success "CORS patched. Backend allows origin: ${FRONTEND_URL}"
else
  warn "Could not discover routes — CORS not patched automatically."
  warn "After deployment, run:"
  warn "  oc patch configmap paygate-config -n ${NAMESPACE} \\"
  warn "    --type merge \\"
  warn "    -p '{\"data\":{\"CORS_EXTRA_ORIGINS\":\"https://<FRONTEND_HOST>\"}}'"
  warn "  oc rollout restart deployment/paygate-backend -n ${NAMESPACE}"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
header "Deployment Complete"

BACKEND_ROUTE="${BACKEND_HOST:+https://${BACKEND_HOST}}"
FRONTEND_ROUTE="${FRONTEND_HOST:+https://${FRONTEND_HOST}}"

echo ""
echo -e "${BOLD}  Services deployed in namespace: ${NAMESPACE}${RESET}"
echo ""
printf "  %-20s %s\n" "MySQL:"    "paygate-mysql.${NAMESPACE}.svc.cluster.local:3306"
printf "  %-20s %s\n" "Backend:"  "${BACKEND_ROUTE:-'run: oc get route paygate-backend  -n ${NAMESPACE}'}"
printf "  %-20s %s\n" "Frontend:" "${FRONTEND_ROUTE:-'run: oc get route paygate-frontend -n ${NAMESPACE}'}"
echo ""
echo -e "${BOLD}  Useful commands:${RESET}"
echo "  oc get pods    -n ${NAMESPACE}"
echo "  oc get routes  -n ${NAMESPACE}"
echo "  oc logs -f deployment/paygate-backend  -n ${NAMESPACE}"
echo "  oc logs -f deployment/paygate-frontend -n ${NAMESPACE}"
echo ""
echo -e "${GREEN}${BOLD}  All done!${RESET}"
