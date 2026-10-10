-- Runs once, on the first boot of an empty Postgres volume.
-- The app database ("healththread") is created by POSTGRES_DB.

-- HAPI FHIR persistence
CREATE ROLE hapi WITH LOGIN PASSWORD 'hapi';
CREATE DATABASE hapi OWNER hapi;

-- Isolated database for pytest
CREATE DATABASE healththread_test OWNER healththread;
