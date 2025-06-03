from pathlib import Path
import yaml

# Set the project base directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent

STATIC_PATH = BASE_DIR / "server" / "statics"
DEFAULT_AVATAR_PATH = STATIC_PATH / "avatar"

# Load YAML configuration
with open(BASE_DIR / "config.yaml", "r") as f:
    config = yaml.safe_load(f)

# Assign variables from YAML
DEBUG = config.get("DEBUG", False)
DEV = config.get("DEV", False)

SECRET_KEY = config.get("SECRET_KEY", "secret")

# Database settings
PG_HOST = config["database"]["host"]
PG_PORT = config["database"]["port"]
PG_USER = config["database"]["user"]
PG_PASS = config["database"]["password"]
PG_DB = config["database"]["name"]
DB_URL = f"postgres://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{PG_DB}"

if PG_DB.endswith('_test'):
    print('-' * 10, 'db', '-' * 10, f"Using \033[92m{PG_DB} \033[0m now...")
else:
    print('-' * 10, 'db', '-' * 10, f"\033[91mWarning!!!\033[0m using production DB: \033[91m{PG_DB}\033[0m now")

# Redis settings
REDIS_HOST = config["redis"]["host"]
REDIS_PORT = config["redis"]["port"]
REDIS_USER = config["redis"]["user"]
REDIS_PASS = config["redis"]["password"]
REDIS_DB = config["redis"]["db"]
REDIS_URL = f"redis://{REDIS_USER}:{REDIS_PASS}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
CACHE_HEADER = "tutil.cache."

# HTTP settings
HTTP_HOST = config["http"]["host"]
HTTP_PORT = config["http"]["port"]
HTTP_ADDR = f"http://{HTTP_HOST}:{HTTP_PORT}"


# JWT and other settings
ALGORITHM = config.get("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_DAYS = config.get("ACCESS_TOKEN_EXPIRE_DAYS", 7)

TORTOISE_ORM = {
    "connections": {
        "default": {
            "engine": "tortoise.backends.asyncpg",
            "credentials": {
                "host": PG_HOST,
                "port": PG_PORT,
                "user": PG_USER,
                "password": PG_PASS,
                "database": PG_DB,
            },
        }
    },
    "apps": {
        "models": {
            "models": [
                'server.module.common.models',
                'server.module.user.models',
                'server.module.tool.models',
                'server.module.order.models',
                'aerich.models',
            ],
            "default_connection": "default",
        },
    },
    "use_tz": True,
    "timezone": "UTC",
}
