import os

# Unit tests mock database I/O and must also run without a developer's .env file.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test-user@127.0.0.1:1/test-db")
