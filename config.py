import os

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_OWNER = os.getenv("GITHUB_OWNER", "")
MAX_ZIP_MB = int(os.getenv("MAX_ZIP_MB", "40"))
MAX_EXTRACTED_MB = int(os.getenv("MAX_EXTRACTED_MB", "200"))
MAX_FILES = int(os.getenv("MAX_FILES", "500"))
