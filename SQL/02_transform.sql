-- =====================================================================
-- raw -> core. Every rule fixes a problem found while profiling the raw data
-- (see SQL/03_data_quality.sql and the README "Data problems found and fixed").
-- =====================================================================

-- ---------------------------------------------------------------------
-- Snapshot rows, typed. Hospital types and ownership are grouped into a few plain categories.
-- Only general acute care and critical access hospitals report to Medicare's Promoting
-- Interoperability program; psychiatric, children's, VA and military hospitals are always blank.
-- ---------------------------------------------------------------------
CREATE TEMP TABLE gi AS
SELECT left(snapshot_date, 4)::smallint                         AS snapshot_year,
       lpad(facility_id, 6, '0')                                AS ccn,
       initcap(facility_name)                                   AS hospital_name,
       initcap(city)                                            AS city,
       state, initcap(county)                                   AS county,
       CASE hospital_type
            WHEN 'Acute Care Hospitals'      THEN 'General acute care'
            WHEN 'Critical Access Hospitals' THEN 'Critical access'
            WHEN 'Psychiatric'               THEN 'Psychiatric'
            WHEN 'Childrens'                 THEN 'Children''s'
            ELSE hospital_type END                              AS hospital_type,
       CASE WHEN hospital_ownership ILIKE 'Voluntary%'   THEN 'Nonprofit'
            WHEN hospital_ownership ILIKE 'Proprietary%' THEN 'For-profit'
            WHEN hospital_ownership ILIKE 'Physician%'   THEN 'Physician-owned'
            WHEN hospital_ownership ILIKE 'Tribal%'      THEN 'Tribal'
            WHEN hospital_ownership ILIKE '%Government%' OR hospital_ownership ILIKE '%Veterans%'
              OR hospital_ownership ILIKE '%Defense%'    THEN 'Government'
            ELSE 'Unknown' END                                  AS ownership,
       coalesce(emergency_services = 'Yes', false)              AS emergency_services,
       coalesce(interop_flag = 'Y', false)                      AS meets_criteria
FROM raw.general_info
WHERE facility_id ~ '^[0-9A-Z]{5,6}$';

-- the 2020-05 snapshot is the only one that year; 2025 has no general-file flag (moved to its own file)

-- ---------------------------------------------------------------------
-- Hospitals: attributes from the latest snapshot they appear in
-- ---------------------------------------------------------------------
INSERT INTO core.dim_hospital
SELECT DISTINCT ON (ccn)
       ccn, hospital_name, city, state, county, hospital_type, ownership, emergency_services,
       hospital_type IN ('General acute care', 'Critical access'),
       min(snapshot_year) OVER (PARTITION BY ccn), max(snapshot_year) OVER (PARTITION BY ccn)
FROM gi
ORDER BY ccn, snapshot_year DESC;

-- latest-year hospitals that are only in the Promoting Interoperability file
INSERT INTO core.dim_hospital (ccn, hospital_name, state, hospital_type, ownership, in_program, first_snapshot, last_snapshot)
SELECT lpad(p.facility_id, 6, '0'), initcap(p.facility_name), p.state,
       CASE WHEN right(lpad(p.facility_id, 6, '0'), 4)::int BETWEEN 1300 AND 1399 THEN 'Critical access'
            ELSE 'General acute care' END,
       'Unknown', true, 2026, 2026
FROM raw.pi_hospital p
WHERE NOT EXISTS (SELECT 1 FROM core.dim_hospital h WHERE h.ccn = lpad(p.facility_id, 6, '0'))
  AND p.facility_id ~ '^[0-9]{6}$';

INSERT INTO core.fact_interop_year
SELECT ccn, snapshot_year, hospital_type, meets_criteria FROM gi;

-- ---------------------------------------------------------------------
-- EHR technology (ONC CHPL). A CEHRT ID bundles every certified product a hospital uses: its core EHR
-- plus add-ons (quality reporting, secure messaging, e-prescribing). The main developer is the core EHR
-- vendor with the most products in the bundle; add-on vendors are not counted as the hospital's EHR.
-- ---------------------------------------------------------------------
CREATE TEMP TABLE chpl AS
SELECT cehrt_id, found = 'true' AS found, product, cures_update = 'True' AS cures_update,
       CASE WHEN vendor ILIKE 'Epic%'                                   THEN 'Epic'
            WHEN vendor ILIKE '%MEDITECH%' OR vendor ILIKE 'HCA Healthcare%' THEN 'MEDITECH'
            WHEN vendor ILIKE 'Oracle%' OR vendor ILIKE 'Cerner%'         THEN 'Oracle Health (Cerner)'
            WHEN vendor ILIKE 'MEDHOST%'                                 THEN 'MEDHOST'
            WHEN vendor ILIKE 'TruBridge%' OR vendor ILIKE 'Evident%' OR vendor ILIKE 'CPSI%'
              OR vendor ILIKE 'Computer Programs and Systems%'           THEN 'TruBridge (CPSI)'
            WHEN vendor ILIKE 'Altera%' OR vendor ILIKE 'Allscripts%'     THEN 'Altera (Allscripts)'
            WHEN vendor ILIKE 'Veradigm%'                                THEN 'Veradigm'
            WHEN vendor ILIKE 'NextGen%' OR vendor ILIKE 'Greenway%' OR vendor ILIKE 'eClinicalWorks%'
              OR vendor ILIKE 'athena%' OR vendor ILIKE 'Netsmart%' OR vendor ILIKE 'Infomedika%'
              OR vendor ILIKE 'Medical Transcription Billing%' OR vendor ILIKE 'Harris%'
              OR vendor ILIKE 'Healthland%' OR vendor ILIKE 'Azalea%' OR vendor ILIKE 'Prognosis%'
                                                                         THEN 'Other EHR vendor'
            ELSE NULL END                                                AS core_vendor,
       vendor
FROM raw.chpl_product
WHERE cehrt_id NOT IN ('', 'Not Available');

INSERT INTO core.dim_ehr
SELECT c.cehrt_id,
       bool_or(c.found),
       m.core_vendor,
       NULL,
       count(c.product)::smallint,
       count(DISTINCT c.core_vendor)::smallint,
       CASE WHEN count(c.product) > 0 THEN bool_and(coalesce(c.cures_update, false)) END
FROM chpl c
LEFT JOIN LATERAL (
    SELECT core_vendor FROM chpl x
    WHERE x.cehrt_id = c.cehrt_id AND x.core_vendor IS NOT NULL
    GROUP BY core_vendor ORDER BY count(*) DESC, core_vendor LIMIT 1
) m ON true
GROUP BY c.cehrt_id, m.core_vendor;

-- CEHRT IDs in the hospital file that CHPL did not return at all
INSERT INTO core.dim_ehr (cehrt_id, found_in_chpl)
SELECT DISTINCT p.cehrt_id, false FROM raw.pi_hospital p
WHERE p.cehrt_id NOT IN ('', 'Not Available') AND NOT EXISTS (SELECT 1 FROM core.dim_ehr e WHERE e.cehrt_id = p.cehrt_id);

INSERT INTO core.fact_hospital_ehr
SELECT lpad(facility_id, 6, '0'),
       -- 'Not Available' means the hospital reported no certified EHR ID (494 hospitals, none met the criteria)
       CASE WHEN cehrt_id IN ('', 'Not Available') THEN NULL ELSE cehrt_id END,
       coalesce(meets_criteria = 'Y', false),
       to_date(nullif(start_date, ''), 'MM/DD/YYYY'), to_date(nullif(end_date, ''), 'MM/DD/YYYY')
FROM raw.pi_hospital
WHERE facility_id ~ '^[0-9]{6}$';

-- Developer groups: the vendors behind at least 100 hospitals keep their name; the rest are 'Other'
UPDATE core.dim_ehr e
SET developer_group = CASE WHEN e.main_developer IS NULL THEN 'Unknown'
                           WHEN e.main_developer IN (
                               SELECT d.main_developer FROM core.fact_hospital_ehr f JOIN core.dim_ehr d USING (cehrt_id)
                               WHERE d.main_developer <> 'Other EHR vendor'
                               GROUP BY d.main_developer HAVING count(*) >= 100) THEN e.main_developer
                           ELSE 'Other' END;

-- ---------------------------------------------------------------------
-- Hospital finance (companion project)
-- ---------------------------------------------------------------------
INSERT INTO core.fact_finance
SELECT ccn, nullif(fiscal_year, '')::smallint, nullif(rural_urban, ''), nullif(medicaid_status, ''),
       nullif(beds, '')::numeric::int, nullif(fte_employees, '')::numeric, nullif(total_revenue, '')::numeric,
       nullif(total_margin, '')::numeric, nullif(operating_margin, '')::numeric,
       nullif(medicaid_day_share, '')::numeric, nullif(medicare_day_share, '')::numeric,
       nullif(days_cash_on_hand, '')::numeric, coalesce(lost_money_two_years = 'True', false)
FROM raw.finance;

ANALYZE core.fact_interop_year;
ANALYZE core.dim_hospital;
