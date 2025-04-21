
# Fordham IT Document Search

A simple document search application using Chainlit for the frontend and Vertex AI Search for the backend.

## Features

- Natural language search through your documents
- AI-generated summaries with Gemini
- Source citations with clickable links
- Simple, clean interface

## Prerequisites

- Python 3.9+
- Google Cloud Platform account
- Vertex AI Search datastore with documents already ingested
- Google Cloud CLI installed and configured

## Setup

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/fordham-univ-vertex-chainlit.git
   cd fordham-univ-vertex-chainlit
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   
   # Verify chainlit is installed correctly
   chainlit --version
   ```

4. Create a `.env` file from the example:
   ```bash
   cp .env.example .env
   ```

5. Edit the `.env` file with your GCP project details:
   ```
   PROJECT_ID=your-project-id
   LOCATION=your-location
   DATA_STORE_ID=your-data-store-id
   ```

## Running Locally

Start the Chainlit application:

```bash
# Make sure you're in the project directory
python -m chainlit run main.py

# Alternatively, if the chainlit command is in your PATH
chainlit run main.py
```

The application will be available at http://localhost:8000

## One-Click Deployment to Cloud Run

The project includes a fully automated deployment script that handles all necessary steps to deploy the application to Google Cloud Run.

### Deployment Options

#### 1. Local Deployment

```bash
# Set required environment variables
export PROJECT_ID=your-project-id
export DATA_STORE_ID=your-data-store-id

# Optional environment variables
export REGION=us-central1  # Default: us-central1
export LOCATION=global     # Default: global
export APP_NAME=vertex-search-app  # Default: vertex-search-app

# Run the deployment script
./deploy.sh
```

#### 2. Google Cloud Shell Deployment

You can run the script directly in Google Cloud Shell:

```bash
# Clone the repository
git clone https://github.com/yourusername/fordham-univ-vertex-chainlit.git
cd fordham-univ-vertex-chainlit

# Set required environment variables
export PROJECT_ID=your-project-id
export DATA_STORE_ID=your-data-store-id

# Run the deployment script (confirmation will be skipped automatically in Cloud Shell)
./deploy.sh
```

#### 3. Non-Interactive Deployment

For CI/CD pipelines or automated deployments:

```bash
export PROJECT_ID=your-project-id
export DATA_STORE_ID=your-data-store-id

# Skip the confirmation prompt
./deploy.sh --skip-confirmation
```

### Features of the Deployment Script

- **Idempotent**: Can be run multiple times without causing errors
- **Robust Error Handling**: Detailed error messages and recovery options
- **Service Account Management**: Creates and configures service accounts with admin permissions (roles/discoveryengine.admin)
- **Resource Verification**: Checks if resources already exist before creating them
- **Automatic Dependency Installation**: Installs required tools like jq if needed
- **Non-Interactive Mode**: Can run in CI/CD pipelines with --skip-confirmation flag

## Dockerfile

For deployment, a simple Dockerfile is included:

```dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["python", "-m", "chainlit", "run", "main.py", "--host", "0.0.0.0", "--port", "8080"]
```

## License

MIT
