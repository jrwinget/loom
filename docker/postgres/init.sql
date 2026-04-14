-- enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- create temporal database if it doesn't exist
SELECT 'CREATE DATABASE temporal'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'temporal'
)\gexec

SELECT 'CREATE DATABASE temporal_visibility'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'temporal_visibility'
)\gexec
