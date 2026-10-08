DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'rag_ro') THEN
    CREATE ROLE rag_ro LOGIN PASSWORD 'rag_ro';
  END IF;
END
$$;
GRANT CONNECT ON DATABASE rag TO rag_ro;
GRANT USAGE ON SCHEMA public TO rag_ro;
GRANT SELECT ON documents, chunks TO rag_ro;
ALTER ROLE rag_ro SET statement_timeout = '5s';
