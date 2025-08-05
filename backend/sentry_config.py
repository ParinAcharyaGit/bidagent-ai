import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration
import logging
from .config import load_config

def init_sentry():
    """
    Initialize Sentry for error tracking and performance monitoring
    """
    try:
        config = load_config()
        sentry_dsn = config.get('SENTRY_DSN')
        
        if not sentry_dsn:
            print("Warning: SENTRY_DSN not configured. Sentry error tracking disabled.")
            return False
        
        # Configure logging integration
        logging_integration = LoggingIntegration(
            level=logging.INFO,        # Capture info and above as breadcrumbs
            event_level=logging.ERROR  # Send errors as events
        )
        
        sentry_sdk.init(
            dsn=sentry_dsn,
            environment=config.get('SENTRY_ENVIRONMENT', 'development'),
            integrations=[logging_integration],
            # Set traces_sample_rate to 1.0 to capture 100% of transactions for performance monitoring
            # We recommend adjusting this value in production
            traces_sample_rate=0.1,  # 10% sampling for performance
            # Enable automatic error capture
            attach_stacktrace=True,
            # Capture local variables in stack traces
            with_locals=True,
            # Release tracking (you can set this to your app version)
            release=config.get('APP_VERSION', 'development'),
        )
        
        print(f"Sentry initialized successfully for environment: {config.get('SENTRY_ENVIRONMENT')}")
        return True
        
    except Exception as e:
        print(f"Failed to initialize Sentry: {e}")
        return False

def capture_exception(error, extra_context=None):
    """
    Capture an exception with optional extra context
    """
    try:
        if extra_context:
            with sentry_sdk.configure_scope() as scope:
                for key, value in extra_context.items():
                    scope.set_context(key, value)
        
        sentry_sdk.capture_exception(error)
    except Exception as e:
        print(f"Failed to capture exception in Sentry: {e}")

def capture_message(message, level='info', extra_context=None):
    """
    Capture a message with optional extra context
    """
    try:
        if extra_context:
            with sentry_sdk.configure_scope() as scope:
                for key, value in extra_context.items():
                    scope.set_context(key, value)
        
        sentry_sdk.capture_message(message, level=level)
    except Exception as e:
        print(f"Failed to capture message in Sentry: {e}")

def add_breadcrumb(message, category='custom', level='info', data=None):
    """
    Add a breadcrumb for debugging context
    """
    try:
        sentry_sdk.add_breadcrumb(
            message=message,
            category=category,
            level=level,
            data=data or {}
        )
    except Exception as e:
        print(f"Failed to add breadcrumb in Sentry: {e}")
