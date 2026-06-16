"""Initialize the job environment definition."""
import os

from src.infra.config import get_settings, Settings
from src.infra.logging import set_transaction_id, configure_logging


def initialize_job() -> Settings:
    """Initialize the job environment."""
    current_settings = get_settings()
    transaction_id = os.getenv("TRANSACTION_ID", "")
    if transaction_id:
        set_transaction_id(transaction_id)
    configure_logging(current_settings)
    return current_settings
