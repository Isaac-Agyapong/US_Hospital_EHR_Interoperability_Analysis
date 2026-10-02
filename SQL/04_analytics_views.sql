-- =====================================================================
-- Analytics layer: one view per question. The notebook, Power BI and the companion ML project read these.
-- Study population: general acute care and critical access hospitals (the hospital types Medicare's
-- Promoting Interoperability program applies to). "Did not meet" = blank flag for these hospitals.
-- =====================================================================

-- every program hospital per snapshot year
CREATE VIEW analytics.v_hospital_year AS
SELECT y.ccn, y.snapshot_year, y.hospital_type, y.meets_criteria, NOT y.meets_criteria AS not_met,
       h.hospital_name, h.state, h.ownership
FROM core.fact_interop_year y JOIN core.dim_hospital h USING (ccn)
WHERE y.hospital_type IN ('General acute care', 'Critical access');

-- latest reporting year (2024), one row per program hospital with EHR, finance and history
CREATE MATERIALIZED VIEW analytics.mv_hospital_latest AS
WITH hist AS (
    SELECT ccn, count(*) AS years_reported, count(*) FILTER (WHERE not_met) AS years_not_met,
           bool_or(not_met) FILTER (WHERE snapshot_year <= 2023) AS not_met_before_2024
    FROM analytics.v_hospital_year GROUP BY ccn
)
SELECT e.ccn, h.hospital_name, h.city, h.state, h.hospital_type, h.ownership, h.emergency_services,
       NOT e.meets_criteria                                        AS not_met,
       e.cehrt_id IS NOT NULL                                      AS reported_ehr_id,
       coalesce(d.developer_group, CASE WHEN e.cehrt_id IS NULL THEN 'No EHR ID reported' END) AS ehr_group,
       d.main_developer, d.n_products, d.n_developers, d.all_cures_update, d.found_in_chpl,
       f.rural_urban, f.medicaid_status, f.beds, f.fte_employees, f.total_revenue, f.total_margin, f.operating_margin,
       f.medicaid_day_share, f.medicare_day_share, f.days_cash_on_hand, f.lost_money_two_years,
       hist.years_reported, hist.years_not_met, hist.not_met_before_2024,
       count(*) OVER (PARTITION BY e.cehrt_id)                     AS hospitals_sharing_ehr_id
FROM core.fact_hospital_ehr e
JOIN core.dim_hospital h USING (ccn)
LEFT JOIN core.dim_ehr d USING (cehrt_id)
LEFT JOIN core.fact_finance f USING (ccn)
LEFT JOIN hist USING (ccn)
WHERE h.in_program;
CREATE UNIQUE INDEX ON analytics.mv_hospital_latest (ccn);

-- Q1. National trend by hospital type
CREATE VIEW analytics.v_trend AS
SELECT snapshot_year, hospital_type, count(*) AS hospitals, count(*) FILTER (WHERE not_met) AS not_met,
       avg(not_met::int) AS share_not_met
FROM analytics.v_hospital_year GROUP BY 1, 2;

-- Q2. Latest year by group (type, rural/urban, ownership, EHR)
CREATE VIEW analytics.v_by_group AS
SELECT 'Hospital type' AS dimension, hospital_type AS grp, count(*) AS hospitals, avg(not_met::int) AS share_not_met
FROM analytics.mv_hospital_latest GROUP BY 2
UNION ALL
SELECT 'Area', coalesce(rural_urban, 'Unknown'), count(*), avg(not_met::int) FROM analytics.mv_hospital_latest GROUP BY 2
UNION ALL
SELECT 'Owner', ownership, count(*), avg(not_met::int) FROM analytics.mv_hospital_latest GROUP BY 2
UNION ALL
SELECT 'EHR', ehr_group, count(*), avg(not_met::int) FROM analytics.mv_hospital_latest GROUP BY 2;

-- Q3. States: share not met, ranked against all states (states with 10+ program hospitals)
CREATE VIEW analytics.v_state AS
SELECT state, count(*) AS hospitals, count(*) FILTER (WHERE not_met) AS not_met, avg(not_met::int) AS share_not_met,
       rank() OVER (ORDER BY avg(not_met::int) DESC) AS rank_most_not_met
FROM analytics.mv_hospital_latest GROUP BY state HAVING count(*) >= 10;

-- Q4. Status changes between consecutive snapshots (LAG)
CREATE VIEW analytics.v_transitions AS
SELECT snapshot_year, hospital_type,
       count(*) FILTER (WHERE prev_not_met = false AND not_met)  AS fell_behind,
       count(*) FILTER (WHERE prev_not_met AND NOT not_met)      AS caught_up,
       count(*) FILTER (WHERE prev_not_met IS NOT NULL)          AS hospitals_both_years
FROM (SELECT *, lag(not_met) OVER (PARTITION BY ccn ORDER BY snapshot_year) AS prev_not_met
      FROM analytics.v_hospital_year) x
GROUP BY 1, 2;
