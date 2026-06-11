import asyncio
import asyncpg
import ssl

async def main():
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    conn = await asyncpg.connect(
        host="db.greptxqtpepmzubnddog.supabase.co",
        port=5432,
        user="postgres",
        password="4413DemiXDP",
        database="postgres",
        ssl=ssl_ctx,
    )

    with open("setup.sql", encoding="utf-8") as f:
        sql = f.read()

    # Split by semicolons to execute statements one by one
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    for stmt in statements:
        if stmt:
            try:
                await conn.execute(stmt + ";")
                print(f"  OK: {stmt[:60]}...")
            except Exception as e:
                print(f"  WARN: {e} (ignorado)")

    await conn.close()
    print("\nSQL ejecutado correctamente.")

asyncio.run(main())
