from pathlib import Path

from sqlalchemy import URL, Engine, create_engine, event


# 以源码位置定位数据库，避免因终端工作目录不同而创建多个数据库。
DATABASE_PATH = Path(__file__).resolve().parents[2] / "data" / "ai_secure.db"


def create_db_engine(database_path: Path = DATABASE_PATH) -> Engine:
    """创建数据库连接入口；导入本模块本身不会建表或写入账户。"""
    database_path = database_path.resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        URL.create("sqlite", database=str(database_path)),
        hide_parameters=True,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _connection_record):
        # SQLite 默认不启用外键检查；启用后会话不能指向不存在的用户。
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine
