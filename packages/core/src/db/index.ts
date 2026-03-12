import { drizzle } from 'drizzle-orm/node-postgres';
import { migrate } from 'drizzle-orm/node-postgres/migrator';
import pg from 'pg';
import * as schema from './schema.js';

export interface DbConnection {
  db: ReturnType<typeof drizzle<typeof schema>>;
  pool: pg.Pool;
  /** Pool을 안전하게 닫는다. Graceful shutdown 시 호출. */
  close(): Promise<void>;
}

export function createDb(connectionString: string): DbConnection {
  const pool = new pg.Pool({ connectionString });
  const db = drizzle(pool, { schema });
  return {
    db,
    pool,
    close: () => pool.end(),
  };
}

export type Database = DbConnection['db'];

/**
 * drizzle/migrations 폴더의 SQL을 실행하여 DB 스키마를 최신 상태로 만든다.
 * 부트스트랩 시 호출된다.
 */
export async function runMigrations(db: Database, migrationsFolder: string): Promise<void> {
  await migrate(db, { migrationsFolder });
}
