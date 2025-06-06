import enum
import logging
import os
from dotenv import set_key
from buzz.assets import APP_BASE_DIR
import os.path
from dotenv import load_dotenv,find_dotenv
load_dotenv()
#from buzz.settings.settings import APP_NAME


class Key(enum.Enum):
    OPENAI_API_KEY = "OpenAI API key"


def get_password(key: Key) -> str | None:
    try:
        # Get value from .env file using dotenv (already loaded at the top of this module)
        env_var_name = f"{key.name}"
        password = os.getenv(env_var_name, "")
        return password
    except Exception as exc:
        logging.warning("Unable to read from environment: %s", exc)
        return ""




def set_password(username: Key, password: str) -> None:
    # Save the password to the .env file
    env_var_name = f"{username.name}"
    
    try:
        # Path to .env file
        env_path = find_dotenv()
        
        # Use dotenv's built-in function to update the .env file
        set_key(env_path, env_var_name, password)
        
        # Also update the current environment
        #os.environ[env_var_name] = password
        logging.info(f"Updated {env_var_name} in {env_path} file")
    except Exception as exc:
        logging.error(f"Failed to update {env_path} file: {exc}")
        # Still update the current process environment
        #os.environ[env_var_name] = password
