import os
import sys
from dotenv import load_dotenv,find_dotenv
load_dotenv()


# APP_BASE_DIR = (
#     getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
#     if getattr(sys, "frozen", False)
#     else os.path.dirname(__file__)
# )

if getattr(sys, 'frozen', False):
    # For packaged/frozen app
    APP_BASE_DIR = os.path.dirname(sys.executable)
else:
    # For development
    APP_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def get_path(path: str):
    return os.path.join(APP_BASE_DIR, path)

def get_cache_path():
    return os.path.join(APP_BASE_DIR, "cache")

def get_models_path():
    return os.path.join(APP_BASE_DIR, "cache", "models")



def get_data_path():
    return os.path.join(APP_BASE_DIR, "cache", "data")

def get_translation_provider():
    return os.getenv(
        "TRANSLATION_PROVIDER",
        "OPENAI"
    )

