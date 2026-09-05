"""Ordered, repeatable startup migrations. Existing table IDs and versions are retained."""

from accord_api.platform.db import database
from accord_api.platform.db.migrations import (
    activity,
    auth,
    base,
    collaboration,
    coordination,
    knowledge_index,
    model_settings,
    runtime,
    schema,
)


def initialize():
    base.init()
    collaboration.initialize()
    auth.initialize()
    runtime.initialize()
    model_settings.initialize()
    schema.initialize()
    activity.initialize()
    coordination.initialize()
    knowledge_index.initialize()
    if database.query_one("SELECT 1 FROM project_state WHERE key='accord_seed_v1'"):
        raise RuntimeError('请为真实工作空间设置独立的 ACCORD_DATA_DIR，旧参考数据保留原位。')
