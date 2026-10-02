-- =====================================================================
-- Data quality checks. Run by Python/03_run_sql_queries.py; results in SQL/query_results.md.
-- Framed on the dimensions used in EHR data-quality research: completeness, conformance, plausibility,
-- consistency over time, and linkage.
-- =====================================================================

-- Q1: Row counts by layer
SELECT 'raw.general_info (6 yearly snapshots)' AS layer, count(*) AS rows FROM raw.general_info
UNION ALL SELECT 'raw.pi_hospital (latest file, reporting year 2024)', count(*) FROM raw.pi_hospital
UNION ALL SELECT 'raw.chpl_product (products behind each CEHRT ID)', count(*) FROM raw.chpl_product
UNION ALL SELECT 'core.dim_hospital', count(*) FROM core.dim_hospital
UNION ALL SELECT 'core.dim_hospital (in the Medicare program)', count(*) FROM core.dim_hospital WHERE in_program
UNION ALL SELECT 'core.fact_interop_year', count(*) FROM core.fact_interop_year
UNION ALL SELECT 'core.dim_ehr (CEHRT IDs)', count(*) FROM core.dim_ehr;

-- Q2: (plausibility) hospital types outside the program never meet the criteria. Pass: met = 0 for those types
SELECT hospital_type, count(*) AS hospital_years, count(*) FILTER (WHERE meets_criteria) AS met
FROM core.fact_interop_year GROUP BY hospital_type ORDER BY hospital_years DESC;

-- Q3: (uniqueness) duplicate hospital IDs within a snapshot. Pass: 0 rows
SELECT snapshot_date, facility_id, count(*) FROM raw.general_info GROUP BY 1, 2 HAVING count(*) > 1;

-- Q4: (completeness and conformance) the CEHRT ID field in the latest file
SELECT CASE WHEN cehrt_id IS NULL OR cehrt_id = ''            THEN 'Empty'
            WHEN cehrt_id = 'Not Available'                    THEN 'Text "Not Available" instead of an ID'
            WHEN cehrt_id !~ '^0015[A-Z0-9]{11}$'              THEN 'Wrong format (lowercase or wrong length)'
            ELSE 'Valid format' END                            AS cehrt_id_quality,
       count(*) AS hospitals,
       count(*) FILTER (WHERE meets_criteria = 'Y')            AS met_criteria
FROM raw.pi_hospital GROUP BY 1 ORDER BY 2 DESC;

-- Q5: (linkage) CEHRT IDs that the ONC Certified Health IT Product List does not recognise
SELECT count(*) FILTER (WHERE found_in_chpl)     AS ids_found,
       count(*) FILTER (WHERE NOT found_in_chpl) AS ids_not_found,
       (SELECT count(*) FROM core.fact_hospital_ehr f JOIN core.dim_ehr d USING (cehrt_id) WHERE NOT d.found_in_chpl)
                                                 AS hospitals_with_unrecognised_id
FROM core.dim_ehr;

-- Q6: (consistency) hospitals that changed type between snapshots (e.g. general -> critical access)
SELECT a.hospital_type AS from_type, b.hospital_type AS to_type, count(DISTINCT a.ccn) AS hospitals
FROM core.fact_interop_year a
JOIN core.fact_interop_year b ON b.ccn = a.ccn AND b.snapshot_year > a.snapshot_year AND b.hospital_type <> a.hospital_type
GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 10;

-- Q7: (completeness over time) program hospitals present in every yearly snapshot vs only some
SELECT n_snapshots, count(*) AS hospitals
FROM (SELECT ccn, count(*) AS n_snapshots FROM core.fact_interop_year
      WHERE hospital_type IN ('General acute care', 'Critical access') GROUP BY ccn) x
GROUP BY n_snapshots ORDER BY n_snapshots DESC;

-- Q8: (consistency between files) status in the 2024 general snapshot vs the latest Promoting Interoperability file
SELECT y.meets_criteria AS met_in_2024_snapshot, e.meets_criteria AS met_in_latest_file, count(*) AS hospitals
FROM core.fact_interop_year y JOIN core.fact_hospital_ehr e USING (ccn)
WHERE y.snapshot_year = 2024 AND y.hospital_type IN ('General acute care', 'Critical access')
GROUP BY 1, 2 ORDER BY 1, 2;

-- Q9: (conformance) reporting period in the latest file. Pass: one calendar year for every hospital
SELECT period_start, period_end, count(*) AS hospitals FROM core.fact_hospital_ehr GROUP BY 1, 2;

-- Q10: (linkage) program hospitals matched to the hospital finance data (companion project)
SELECT h.hospital_type, count(*) AS hospitals, count(f.ccn) AS with_finance,
       round(100.0 * count(f.ccn) / count(*), 1) AS match_pct
FROM core.fact_hospital_ehr e JOIN core.dim_hospital h USING (ccn) LEFT JOIN core.fact_finance f USING (ccn)
WHERE h.in_program GROUP BY 1;

-- Q11: (plausibility) one CEHRT ID shared by many hospitals is expected for health systems; very large shares are checked
SELECT e.cehrt_id, d.main_developer, count(*) AS hospitals, count(DISTINCT h.state) AS states
FROM core.fact_hospital_ehr e JOIN core.dim_ehr d USING (cehrt_id) JOIN core.dim_hospital h USING (ccn)
GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 8;
