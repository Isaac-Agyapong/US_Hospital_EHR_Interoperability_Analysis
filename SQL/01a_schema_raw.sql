-- =====================================================================
-- Raw layer: source files as text, one load per CMS snapshot. Nothing is cleaned here.
-- Street addresses and phone numbers are not loaded (not needed, and not personal data worth keeping).
-- =====================================================================

DROP SCHEMA IF EXISTS raw CASCADE;
CREATE SCHEMA raw;

-- Hospital General Information, one row per hospital per snapshot (2019-2024 hold the interoperability flag)
CREATE UNLOGGED TABLE raw.general_info (
    snapshot_date      text,
    facility_id        text,
    facility_name      text,
    city               text,
    state              text,
    zip_code           text,
    county             text,
    hospital_type      text,
    hospital_ownership text,
    emergency_services text,
    interop_flag       text,    -- "Meets criteria for promoting interoperability" ("meaningful use" before 2020)
    overall_rating     text
);

-- Promoting Interoperability - Hospital (latest snapshot): reporting period and CEHRT ID
CREATE UNLOGGED TABLE raw.pi_hospital (
    snapshot_date  text,
    facility_id    text,
    facility_name  text,
    state          text,
    cehrt_id       text,
    meets_criteria text,
    start_date     text,
    end_date       text
);

-- ONC CHPL: products behind each CEHRT ID (one row per CEHRT ID x certified product)
CREATE UNLOGGED TABLE raw.chpl_product (
    cehrt_id            text,
    found               text,    -- 'false' when CHPL does not know the ID
    chpl_product_number text,
    vendor              text,
    product             text,
    version             text,
    acb                 text,    -- certification body
    cures_update        text
);

-- Hospital finance (companion project, database hospital_finance): latest year per hospital
CREATE UNLOGGED TABLE raw.finance (
    ccn               text,
    fiscal_year       text,
    hospital_type     text,
    ownership         text,
    rural_urban       text,
    medicaid_status   text,
    beds              text,
    fte_employees     text,
    total_revenue     text,
    total_margin      text,
    operating_margin  text,
    medicaid_day_share text,
    medicare_day_share text,
    days_cash_on_hand text,
    lost_money_two_years text   -- net loss in both of the hospital's two latest reports
);
