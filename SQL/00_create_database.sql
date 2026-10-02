-- =====================================================================
-- One-time setup (run as a superuser, connected to the "postgres" database).
-- The loader (Python/02_load_postgres.py) runs this automatically on first use.
--
-- The database gets its own tablespace on the D: drive. Change LOCATION to any
-- empty folder the PostgreSQL service account can write to
-- (on Windows: NT AUTHORITY\NetworkService).
-- =====================================================================

CREATE TABLESPACE hospital_interop_ts LOCATION 'D:/PostgresData/hospital_interop';

CREATE DATABASE hospital_interop
    WITH TABLESPACE = hospital_interop_ts
         ENCODING = 'UTF8'
         TEMPLATE = template0;

COMMENT ON DATABASE hospital_interop IS
    'EHR interoperability of US hospitals: CMS Promoting Interoperability 2019-2024 + ONC CHPL (portfolio project)';
