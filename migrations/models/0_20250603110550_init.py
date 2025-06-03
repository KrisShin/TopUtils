from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "tb_system_parameter" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "create_time" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "update_time" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "name" VARCHAR(128) NOT NULL UNIQUE,
    "description" VARCHAR(1024),
    "data_type" VARCHAR(8) NOT NULL DEFAULT 'str',
    "data" TEXT
);
COMMENT ON COLUMN "tb_system_parameter"."data_type" IS 'STRING: str\nFLOAT: float\nINTEGER: int\nJSON: json\nDATE: date\nDATETIME: datetime';
COMMENT ON TABLE "tb_system_parameter" IS '保存一些独立变量和选项';
CREATE TABLE IF NOT EXISTS "tb_tag" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "create_time" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "update_time" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "name" VARCHAR(128) NOT NULL UNIQUE,
    "description" VARCHAR(512),
    "color" VARCHAR(32),
    "category" VARCHAR(5) NOT NULL DEFAULT 'util'
);
CREATE INDEX IF NOT EXISTS "idx_tb_tag_categor_dd64eb" ON "tb_tag" ("category");
COMMENT ON COLUMN "tb_tag"."category" IS 'UTIL: util\nORDER: order';
COMMENT ON TABLE "tb_tag" IS '标签模型';
CREATE TABLE IF NOT EXISTS "tb_user" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "create_time" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "update_time" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "nickname" VARCHAR(64) NOT NULL,
    "username" VARCHAR(256) NOT NULL UNIQUE,
    "phone" VARCHAR(15),
    "email" VARCHAR(128),
    "password" VARCHAR(256) NOT NULL,
    "avatar" VARCHAR(256),
    "last_login_ip" VARCHAR(32),
    "last_login_time" TIMESTAMPTZ,
    "disabled" BOOL NOT NULL DEFAULT False
);
CREATE INDEX IF NOT EXISTS "idx_tb_user_disable_48f3a4" ON "tb_user" ("disabled");
CREATE TABLE IF NOT EXISTS "tb_tool" (
    "code" VARCHAR(32) NOT NULL PRIMARY KEY,
    "name" VARCHAR(128) NOT NULL UNIQUE,
    "description" VARCHAR(512),
    "context" TEXT,
    "pics" JSONB NOT NULL,
    "link" VARCHAR(256),
    "passwd" VARCHAR(64),
    "create_time" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "update_time" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "price" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "is_public" BOOL NOT NULL DEFAULT True
);
COMMENT ON TABLE "tb_tool" IS '工具模型';
CREATE TABLE IF NOT EXISTS "tb_order" (
    "id" VARCHAR(32) NOT NULL PRIMARY KEY,
    "create_time" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "update_time" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "email" VARCHAR(255) NOT NULL UNIQUE,
    "expire_time" TIMESTAMPTZ,
    "paid_status" SMALLINT NOT NULL DEFAULT 0,
    "totp_secret" VARCHAR(32),
    "is_totp_enabled" BOOL NOT NULL DEFAULT False,
    "device_info_hashed" VARCHAR(512),
    "last_rebind_time" TIMESTAMPTZ,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "tool_id" VARCHAR(32) NOT NULL REFERENCES "tb_tool" ("code") ON DELETE CASCADE,
    CONSTRAINT "uid_tb_order_tool_id_3ec9fe" UNIQUE ("tool_id", "device_info_hashed")
);
CREATE INDEX IF NOT EXISTS "idx_tb_order_email_01c3ed" ON "tb_order" ("email");
COMMENT ON COLUMN "tb_order"."paid_status" IS 'TRY: 0\nSUBSCRIBE: 1';
COMMENT ON TABLE "tb_order" IS '订单模型（优化后）';
CREATE TABLE IF NOT EXISTS "aerich" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "version" VARCHAR(255) NOT NULL,
    "app" VARCHAR(100) NOT NULL,
    "content" JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS "rs_tool_tag" (
    "tb_tool_id" VARCHAR(32) NOT NULL REFERENCES "tb_tool" ("code") ON DELETE CASCADE,
    "tag_id" BIGINT NOT NULL REFERENCES "tb_tag" ("id") ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS "uidx_rs_tool_tag_tb_tool_a9d088" ON "rs_tool_tag" ("tb_tool_id", "tag_id");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """
