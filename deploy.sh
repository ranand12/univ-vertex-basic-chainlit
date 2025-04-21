#!/bin/bash
set -e

# Function to log messages
log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# Function to log errors
error() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') - ERROR: $1" >&2
}

# Function to check if a command exists
command_exists() {
  command -v "$1" >/dev/null 2>&1
}

# Parse command line arguments
SKIP_CONFIRMATION=false
while [[ "$#" -gt 0 ]]; do
  case $1 in
    --skip-confirmation) SKIP_CONFIRMATION=true; shift ;;
    *) error "Unknown parameter: $1"; exit 1 ;;
  esac
done

# Check if running in Cloud Shell
if [ -n "$CLOUD_SHELL" ]; then
  log "Running in Google Cloud Shell, setting skip-confirmation to true"
  SKIP_CONFIRMATION=true
fi

# Check for required tools
if ! command_exists jq; then
  log "jq is not installed. Attempting to install..."
  if command_exists apt-get; then
    sudo apt-get update && sudo apt-get install -y jq
  elif command_exists yum; then
    sudo yum install -y jq
  elif command_exists brew; then
    brew install jq
  else
    error "Could not install jq. Please install it manually and try again."
    exit 1
  fi
fi

# Check if required environment variables are set
if [ -z "$PROJECT_ID" ]; then
  error "PROJECT_ID environment variable is not set."
  error "Please set it with: export PROJECT_ID=your-project-id"
  exit 1
fi

if [ -z "$DATA_STORE_ID" ]; then
  error "DATA_STORE_ID environment variable is not set."
  error "Please set it with: export DATA_STORE_ID=your-data-store-id"
  exit 1
fi

# Set default values
REGION=${REGION:-"us-central1"}
LOCATION=${LOCATION:-"global"}
APP_NAME=${APP_NAME:-"vertex-search-app"}
SERVICE_ACCOUNT_NAME=${SERVICE_ACCOUNT_NAME:-"$APP_NAME-sa"}
REPOSITORY_NAME=${REPOSITORY_NAME:-"chainlit-apps"}

log "=== Fordham University Vertex AI Search Deployment ==="
log "Project ID: $PROJECT_ID"
log "Region: $REGION"
log "Location: $LOCATION"
log "Data Store ID: $DATA_STORE_ID"
log "Application Name: $APP_NAME"
log "Service Account: $SERVICE_ACCOUNT_NAME"
log ""
log "This script will:"
log "1. Enable required GCP services"
log "2. Create a service account with necessary permissions"
log "3. Create an Artifact Registry repository"
log "4. Build and push the Docker image"
log "5. Deploy the application to Cloud Run"
log ""

# Ask for confirmation if not skipped
if [ "$SKIP_CONFIRMATION" = false ]; then
  read -p "Continue? (y/n) " -n 1 -r
  echo ""
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log "Deployment cancelled."
    exit 1
  fi
fi

log ""
log "=== Enabling required services ==="
# Enable services idempotently
for service in run.googleapis.com artifactregistry.googleapis.com discoveryengine.googleapis.com; do
  if gcloud services list --enabled --filter="name:$service" --format="value(name)" | grep -q "$service"; then
    log "Service $service is already enabled."
  else
    log "Enabling service $service..."
    gcloud services enable $service
  fi
done

log ""
log "=== Creating service account ==="
# Check if service account already exists
if gcloud iam service-accounts describe "$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com" &>/dev/null; then
  log "Service account already exists."
else
  log "Creating new service account..."
  gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" \
    --display-name="Vertex Search App Service Account"
  
  # Wait for service account to be fully created and propagated
  log "Waiting for service account to be fully created..."
  sleep 15
fi

# Verify service account exists before granting permissions
MAX_RETRIES=3
RETRY_COUNT=0
while ! gcloud iam service-accounts describe "$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com" &>/dev/null; do
  RETRY_COUNT=$((RETRY_COUNT+1))
  if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
    error "Service account $SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com was not created successfully after $MAX_RETRIES attempts."
    error "Please check your permissions and try again."
    exit 1
  fi
  log "Service account not found yet. Waiting 10 seconds before retry ($RETRY_COUNT/$MAX_RETRIES)..."
  sleep 10
done

log ""
log "=== Granting permissions ==="
log "Adding Discovery Engine Admin role to service account..."

# Check if role is already assigned
ROLE_ASSIGNED=false
if command_exists jq; then
  if gcloud projects get-iam-policy "$PROJECT_ID" --format=json | \
     jq -e --arg sa "serviceAccount:$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com" \
        --arg role "roles/discoveryengine.admin" \
        '.bindings[] | select(.role == $role) | .members[] | select(. == $sa)' > /dev/null 2>&1; then
    ROLE_ASSIGNED=true
  fi
else
  # Fallback method if jq is not available
  if gcloud projects get-iam-policy "$PROJECT_ID" --format=text | \
     grep -q "role: roles/discoveryengine.admin" && \
     gcloud projects get-iam-policy "$PROJECT_ID" --format=text | \
     grep -q "serviceAccount:$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com"; then
    ROLE_ASSIGNED=true
  fi
fi

if [ "$ROLE_ASSIGNED" = true ]; then
  log "Role 'roles/discoveryengine.admin' is already assigned to the service account."
else
  log "Assigning 'roles/discoveryengine.admin' role to service account..."
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/discoveryengine.admin" || {
      error "Failed to grant permissions to service account."
      error "This may be due to insufficient permissions or a propagation delay."
      error "You can try running the script again or manually grant the permissions."
      exit 1
    }
fi

log ""
log "=== Creating Artifact Registry repository ==="
# Check if repository already exists
if gcloud artifacts repositories describe "$REPOSITORY_NAME" --location="$REGION" &>/dev/null; then
  log "Repository already exists."
else
  log "Creating new Artifact Registry repository..."
  gcloud artifacts repositories create "$REPOSITORY_NAME" \
    --repository-format=docker \
    --location="$REGION"
fi

log ""
log "=== Building and pushing Docker image ==="
log "This may take a few minutes..."
gcloud builds submit --tag "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY_NAME/$APP_NAME" --quiet

log ""
log "=== Deploying to Cloud Run ==="
gcloud run deploy "$APP_NAME" \
  --image "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY_NAME/$APP_NAME" \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated \
  --service-account "$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com" \
  --set-env-vars "PROJECT_ID=$PROJECT_ID,LOCATION=$LOCATION,DATA_STORE_ID=$DATA_STORE_ID" \
  --quiet

# Get the deployed service URL
SERVICE_URL=$(gcloud run services describe "$APP_NAME" --region="$REGION" --format="value(status.url)")

log ""
log "=== Deployment Complete ==="
log "Your application is now deployed to Cloud Run."
log "You can access it at: $SERVICE_URL"
