from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "tb_order" ADD "email_verify_code" VARCHAR(6);
        ALTER TABLE "tb_order" ADD "email_verify_expire" TIMESTAMPTZ;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "tb_order" DROP COLUMN "email_verify_code";
        ALTER TABLE "tb_order" DROP COLUMN "email_verify_expire";"""
