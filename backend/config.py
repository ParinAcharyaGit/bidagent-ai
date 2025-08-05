import os
from dotenv import load_dotenv

def load_config():
    """
    Load configuration from environment variables from .env and .env.local files.
    Values in .env.local will override values in .env.
    """
    # The .env files should be in the project root, which is the parent of the 'backend' directory
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    
    # Load base .env file
    dotenv_path = os.path.join(project_root, '.env')
    load_dotenv(dotenv_path=dotenv_path)
    
    # Load local override .env.local file
    dotenv_local_path = os.path.join(project_root, '.env.local')
    load_dotenv(dotenv_path=dotenv_local_path, override=True)
    
    # Required environment variables
    required_vars = [
        'GOOGLE_APPLICATION_CREDENTIALS',
        'FIREBASE_PROJECT_ID',
        'FIREBASE_STORAGE_BUCKET'
    ]
    
    # Check for missing required variables
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    # if missing_vars:
    #     raise EnvironmentError(f"Missing required environment variables: {', '.join(missing_vars)}")
    
    # Return dictionary of config values
    return {
        # General
        'FLASK_ENV': os.environ.get('FLASK_ENV', 'production'),
        
        # Azure Document Intelligence
        'AZURE_DOC_INTEL_ENDPOINT': os.environ.get('AZURE_DOC_INTEL_ENDPOINT'),
        'AZURE_DOC_INTEL_KEY': os.environ.get('AZURE_DOC_INTEL_KEY'),
        
        # Google Cloud & Firebase
        'GOOGLE_APPLICATION_CREDENTIALS': os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'), # Path to your service account key file
        'FIREBASE_PROJECT_ID': os.environ.get('FIREBASE_PROJECT_ID'),
        'FIREBASE_STORAGE_BUCKET': os.environ.get('FIREBASE_STORAGE_BUCKET'),
        
        # Document AI
        'DOCAI_PROJECT_ID': os.environ.get('DOCAI_PROJECT_ID'),
        'DOCAI_LOCATION': os.environ.get('DOCAI_LOCATION'), # e.g., 'us' or 'eu'
        'DOCAI_PROCESSOR_ID': os.environ.get('DOCAI_PROCESSOR_ID'), # For the Form Parser
        'DOCAI_OCR_PROCESSOR_ID': os.environ.get('DOCAI_OCR_PROCESSOR_ID'), # For the OCR Parser
        
        # SendGrid
        'SENDGRID_API_KEY': os.environ.get('SENDGRID_API_KEY'),
        
        # Sentry
        'SENTRY_DSN': os.environ.get('SENTRY_DSN'),
        'SENTRY_ENVIRONMENT': os.environ.get('SENTRY_ENVIRONMENT', 'development'),
        
        # Pub/Sub Topics
        'PUBSUB_TOPIC_DISCOVERY': os.environ.get('PUBSUB_TOPIC_DISCOVERY', 'bid-discovery'),
        'PUBSUB_TOPIC_DOWNLOAD': os.environ.get('PUBSUB_TOPIC_DOWNLOAD', 'bid-download'),
        'PUBSUB_TOPIC_ANALYSIS': os.environ.get('PUBSUB_TOPIC_ANALYSIS', 'bid-analysis'),
        'PUBSUB_TOPIC_PREFILL': os.environ.get('PUBSUB_TOPIC_PREFILL', 'bid-prefill'),
        'PUBSUB_TOPIC_NOTIFY': os.environ.get('PUBSUB_TOPIC_NOTIFY', 'bid-notify')
    }
