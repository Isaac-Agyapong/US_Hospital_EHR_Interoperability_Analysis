-- =====================================================================
-- Core layer: typed star schema.
--   dim_hospital          one row per hospital (CCN), latest attributes
--   fact_interop_year     interoperability status per hospital per snapshot year
--   dim_ehr               one row per CEHRT ID: main EHR developer and products (ONC CHPL)
--   fact_hospital_ehr     latest reporting year: each hospital's CEHRT ID and status
--   fact_finance          hospital finance (companion project), latest year
-- =====================================================================

DROP SCHEMA IF EXISTS analytics CASCADE;
DROP SCHEMA IF EXISTS core CASCADE;
CREATE SCHEMA core;
CREATE SCHEMA analytics;

CREATE TABLE core.dim_hospital (
    ccn               char(6) PRIMARY KEY,
    hospital_name     text NOT NULL,
    city              text,
    state             char(2),
    county            text,
    hospital_type     text NOT NULL,   -- 'General acute care' / 'Critical access' / other types
    ownership         text,            -- 'Nonprofit' / 'For-profit' / 'Government' / 'Physician' / 'Tribal'
    emergency_services boolean,
    in_program        boolean NOT NULL, -- general acute care or critical access: required to report to Medicare PI
    first_snapshot    smallint,
    last_snapshot     smallint
);

CREATE TABLE core.fact_interop_year (
    ccn            char(6)  NOT NULL REFERENCES core.dim_hospital,
    snapshot_year  smallint NOT NULL,        -- year of the CMS snapshot the status comes from
    hospital_type  text     NOT NULL,        -- type in that snapshot
    meets_criteria boolean  NOT NULL,        -- 'Y' = met; blank = did not meet (for program hospitals)
    PRIMARY KEY (ccn, snapshot_year)
);

CREATE TABLE core.dim_ehr (
    cehrt_id          text PRIMARY KEY,
    found_in_chpl     boolean NOT NULL,
    main_developer    text,                  -- developer with the most certified products in the ID
    developer_group   text,                  -- main developer, small vendors grouped as 'Other'
    n_products        smallint,
    n_developers      smallint,              -- >1 = hospital combines products from several vendors
    all_cures_update  boolean                -- every product updated to the 21st Century Cures Act criteria
);

CREATE TABLE core.fact_hospital_ehr (
    ccn            char(6) PRIMARY KEY REFERENCES core.dim_hospital,
    cehrt_id       text REFERENCES core.dim_ehr,
    meets_criteria boolean NOT NULL,
    period_start   date,
    period_end     date
);

CREATE TABLE core.fact_finance (
    ccn                char(6) PRIMARY KEY,
    fiscal_year        smallint,
    rural_urban        text,
    medicaid_status    text,
    beds               integer,
    fte_employees      numeric,
    total_revenue      numeric,
    total_margin       numeric,
    operating_margin   numeric,
    medicaid_day_share numeric,
    medicare_day_share numeric,
    days_cash_on_hand  numeric,
    lost_money_two_years boolean
);
