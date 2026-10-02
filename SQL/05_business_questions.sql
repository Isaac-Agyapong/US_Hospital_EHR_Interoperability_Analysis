-- =====================================================================
-- Business questions. Run by Python/03_run_sql_queries.py.
-- Study population: general acute care and critical access hospitals, 50 states + DC + territories in CMS data.
-- "Not met" = did not meet Medicare's Promoting Interoperability criteria (uses certified EHR technology to
-- share records electronically, e-prescribe, give patients access and report to public health).
-- =====================================================================

-- Q1: How many hospitals fall short each year, by hospital type?
SELECT snapshot_year, hospital_type, hospitals, not_met, round(100 * share_not_met, 1) AS pct_not_met
FROM analytics.v_trend ORDER BY hospital_type, snapshot_year;

-- Q2: Latest year: who falls short? (type, rural/urban, owner)
SELECT dimension, grp, hospitals, round(100 * share_not_met, 1) AS pct_not_met
FROM analytics.v_by_group WHERE dimension <> 'EHR' ORDER BY dimension, share_not_met DESC;

-- Q3: Does the EHR system matter? Share not met by main EHR developer
SELECT grp AS ehr, hospitals, round(100.0 * hospitals / sum(hospitals) OVER (), 1) AS pct_of_hospitals,
       round(100 * share_not_met, 1) AS pct_not_met
FROM analytics.v_by_group WHERE dimension = 'EHR' ORDER BY hospitals DESC;

-- Q4: Is it the vendor or the kind of hospital? EHR developer within each hospital type (groups of 40+)
SELECT hospital_type, ehr_group, count(*) AS hospitals, round(100 * avg(not_met::int), 1) AS pct_not_met
FROM analytics.mv_hospital_latest GROUP BY 1, 2 HAVING count(*) >= 40 ORDER BY 1, 4 DESC;

-- Q5: Among hospitals that fell short, how many reported no certified EHR at all?
SELECT hospital_type, count(*) FILTER (WHERE not_met) AS not_met,
       count(*) FILTER (WHERE not_met AND NOT reported_ehr_id) AS not_met_no_ehr_id,
       round(100.0 * count(*) FILTER (WHERE not_met AND NOT reported_ehr_id)
             / nullif(count(*) FILTER (WHERE not_met), 0), 1) AS pct_of_not_met_with_no_ehr_id
FROM analytics.mv_hospital_latest GROUP BY 1;

-- Q6: Does money matter? Share not met by financial health (companion finance project)
SELECT CASE WHEN lost_money_two_years THEN 'Lost money two years in a row' ELSE 'Did not' END AS finances,
       hospital_type, count(*) AS hospitals, round(100 * avg(not_met::int), 1) AS pct_not_met
FROM analytics.mv_hospital_latest WHERE lost_money_two_years IS NOT NULL GROUP BY 1, 2 ORDER BY 2, 1;

-- Q7: Profit margin fifths (NTILE): do the least profitable hospitals fall short more often?
SELECT fifth, count(*) AS hospitals, round(100 * min(total_margin), 1) AS margin_from_pct,
       round(100 * max(total_margin), 1) AS margin_to_pct, round(100 * avg(not_met::int), 1) AS pct_not_met
FROM (SELECT *, ntile(5) OVER (ORDER BY total_margin) AS fifth FROM analytics.mv_hospital_latest
      WHERE total_margin IS NOT NULL) x
GROUP BY fifth ORDER BY fifth;

-- Q8: Size: share not met by number of beds
SELECT CASE WHEN beds < 25 THEN '1-24 beds' WHEN beds < 50 THEN '25-49' WHEN beds < 100 THEN '50-99'
            WHEN beds < 250 THEN '100-249' ELSE '250+' END AS size, min(beds) AS from_beds,
       count(*) AS hospitals, round(100 * avg(not_met::int), 1) AS pct_not_met
FROM analytics.mv_hospital_latest WHERE beds IS NOT NULL GROUP BY 1 ORDER BY from_beds;

-- Q9: States with the highest share of hospitals falling short (10+ program hospitals)
SELECT rank_most_not_met AS rank, state, hospitals, not_met, round(100 * share_not_met, 1) AS pct_not_met
FROM analytics.v_state ORDER BY rank_most_not_met LIMIT 10;

-- Q10: Stuck behind: how many of the six yearly snapshots (2019-2024) each hospital fell short in
SELECT years_not_met, count(*) AS hospitals,
       count(*) FILTER (WHERE hospital_type = 'Critical access') AS critical_access
FROM analytics.mv_hospital_latest WHERE years_reported = 6 GROUP BY 1 ORDER BY 1;

-- Q11: Churn: hospitals that fell behind or caught up from one snapshot to the next
SELECT snapshot_year, sum(fell_behind)::int AS fell_behind, sum(caught_up)::int AS caught_up,
       sum(hospitals_both_years)::int AS hospitals
FROM analytics.v_transitions WHERE snapshot_year > 2019 GROUP BY 1 ORDER BY 1;

-- Q12: Market concentration: share of program hospitals on the top 3 EHR developers, and the HHI
--      (Herfindahl-Hirschman index: sum of squared market shares; above 2,500 = highly concentrated)
WITH s AS (SELECT main_developer, count(*)::numeric / sum(count(*)) OVER () AS share
           FROM analytics.mv_hospital_latest WHERE main_developer IS NOT NULL GROUP BY 1)
SELECT round(100 * sum(share) FILTER (WHERE rk <= 3), 1) AS top3_share_pct, round(sum((100 * share) ^ 2)) AS hhi
FROM (SELECT *, rank() OVER (ORDER BY share DESC) AS rk FROM s) x;
