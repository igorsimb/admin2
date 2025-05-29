-- Create additional databases if needed
-- CREATE DATABASE your_extra_db;

-- Create additional users and grant privileges
-- CREATE USER readonly_user WITH PASSWORD 'readonly_password';
-- GRANTUSAGE ON SCHEMA public TO readonly_user;
-- GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;
-- ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly_user;

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Set default search path
ALTER DATABASE admin2 SET search_path = public, extensions;

-- Set timezone
ALTER DATABASE admin2 SET timezone TO 'Europe/Moscow';

-- Performance tuning (adjust based on your server resources)
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET work_mem = '16MB';
ALTER SYSTEM SET maintenance_work_mem = '64MB';
ALTER SYSTEM SET effective_cache_size = '768MB';
ALTER SYSTEM SET random_page_cost = 1.1;
ALTER SYSTEM SET effective_io_concurrency = 200;

-- Logging
ALTER SYSTEM SET log_min_duration_statement = '200ms';
ALTER SYSTEM SET log_checkpoints = on;
ALTER SYSTEM SET log_connections = on;
ALTER SYSTEM SET log_disconnections = on;
ALTER SYSTEM SET log_lock_waits = on;
ALTER SYSTEM SET log_temp_files = 0;

-- WAL and Checkpoints
ALTER SYSTEM SET wal_level = 'replica';
ALTER SYSTEM SET max_wal_size = '1GB';
ALTER SYSTEM SET min_wal_size = '80MB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;

-- Connections
ALTER SYSTEM SET max_connections = '100';
ALTER SYSTEM SET max_parallel_workers_per_gather = 2;

-- Reload configuration
SELECT pg_reload_conf();
