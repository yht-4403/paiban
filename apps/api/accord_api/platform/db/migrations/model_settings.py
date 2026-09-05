from accord_api.platform.db import database as store


def initialize():
    store.execute("""CREATE TABLE IF NOT EXISTS accord_model_preferences (
        unit_id TEXT PRIMARY KEY, reasoning_effort TEXT NOT NULL)""")
