-- NL FM dashboard + MH-in pendency split + NP ageing (rolling 3M create cohort, IST)
-- Hub names: join facility dim at shipment grain (not only after GROUP BY).

WITH params AS (
  SELECT
    DATE_SUB(CURRENT_DATE('Asia/Kolkata'), INTERVAL 3 MONTH) AS start_date,
    CURRENT_DATE('Asia/Kolkata') AS end_date,
    CAST(FORMAT_DATE('%Y%m%d', DATE_SUB(CURRENT_DATE('Asia/Kolkata'), INTERVAL 3 MONTH)) AS INT64) AS start_key,
    CAST(FORMAT_DATE('%Y%m%d', CURRENT_DATE('Asia/Kolkata')) AS INT64) AS end_key
),
hub_dim AS (
  SELECT
    fac.ekl_facility_dim_key AS mp_pickup_hub_key,
    fac.name AS pickup_hub_name,
    fac.city AS pickup_hub_city,
    fac.zone AS pickup_hub_zone
  FROM bigfoot_external_neo.scp_ekl__ekl_facility_dim fac
),
mh_in AS (
  SELECT
    mv.vendor_tracking_id,
    MIN(DATE(mv.consignment_received_at)) AS mh_in_date
  FROM bigfoot_external_neo.scp_fsgde_ns__mh_shipment_movement_bag_consignment_base_fact mv
  CROSS JOIN params p
  WHERE UPPER(mv.consignment_dest_hub_type) = 'MOTHER_HUB'
    AND mv.consignment_received_at IS NOT NULL
    AND DATE(mv.consignment_created_at) >= p.start_date
  GROUP BY 1
),
ext_enriched AS (
  SELECT
    ext.vendor_tracking_id,
    SAFE_CAST(ext.mp_pickup_hub_key AS INT64) AS mp_pickup_hub_key,
    ext.seller_type,
    IF(LOWER(ext.payment_type) = 'prepaid', 'prepaid', 'cod') AS payment_type,
    PARSE_DATE('%Y%m%d', CAST(ext.shipment_created_at_date_key AS STRING)) AS created_date,
    CASE
      WHEN ext.shipment_received_at_origin_date_key IS NOT NULL
      THEN PARSE_DATE('%Y%m%d', CAST(ext.shipment_received_at_origin_date_key AS STRING))
    END AS phin_date,
    mh.mh_in_date,
    (
      ext.rto_create_date_key IS NOT NULL
      OR LOWER(COALESCE(ext.status, '')) LIKE '%cancel%'
      OR LOWER(COALESCE(ext.status, '')) LIKE '%rto%'
    ) AS is_rto_cxl,
    hd.pickup_hub_name,
    hd.pickup_hub_city,
    hd.pickup_hub_zone
  FROM bigfoot_external_neo.scp_fsgde_ns__externalisation_l1_scala_fact ext
  CROSS JOIN params p
  LEFT JOIN mh_in mh
    ON mh.vendor_tracking_id = ext.vendor_tracking_id
  LEFT JOIN hub_dim hd
    ON hd.mp_pickup_hub_key = SAFE_CAST(ext.mp_pickup_hub_key AS INT64)
  WHERE ext.shipment_created_at_date_key BETWEEN p.start_key AND p.end_key
    AND ext.seller_type NOT IN (
      'Non-FA','FA','WSR','MYN','MYS','FKW','FKH','MYE',
      'MP_FBF_SELLER','MP_NON_FBF_SELLER','SF2','SF3','SF4'
    )
    AND LOWER(ext.ekl_shipment_type) != 'rvp'
    AND NOT STARTS_WITH(ext.vendor_tracking_id, 'FMP')
),
created_cal_day AS (
  SELECT
    created_date AS reporting_date,
    mp_pickup_hub_key,
    seller_type,
    payment_type,
    ANY_VALUE(pickup_hub_name) AS pickup_hub_name,
    ANY_VALUE(pickup_hub_city) AS pickup_hub_city,
    ANY_VALUE(pickup_hub_zone) AS pickup_hub_zone,
    COUNT(DISTINCT vendor_tracking_id) AS cal_created_volume,
    COUNT(DISTINCT IF(DATE_DIFF(phin_date, created_date, DAY) <= 0 AND phin_date IS NOT NULL, vendor_tracking_id, NULL)) AS cal_d0_picked,
    COUNT(DISTINCT IF(DATE_DIFF(phin_date, created_date, DAY) = 1, vendor_tracking_id, NULL)) AS cal_d1_picked,
    COUNT(DISTINCT IF(DATE_DIFF(phin_date, created_date, DAY) >= 2, vendor_tracking_id, NULL)) AS cal_d2_plus_picked,
    COUNT(DISTINCT IF(phin_date IS NULL AND mh_in_date IS NOT NULL, vendor_tracking_id, NULL)) AS cal_mhin_no_phin,
    COUNT(DISTINCT IF(phin_date IS NULL AND mh_in_date IS NULL AND is_rto_cxl, vendor_tracking_id, NULL)) AS cal_rto_cxl_no_phin,
    COUNT(DISTINCT IF(phin_date IS NULL AND mh_in_date IS NULL AND NOT is_rto_cxl, vendor_tracking_id, NULL)) AS cal_no_phin,
    COUNT(DISTINCT IF(phin_date IS NULL AND mh_in_date IS NULL AND NOT is_rto_cxl AND DATE_DIFF(CURRENT_DATE('Asia/Kolkata'), created_date, DAY) <= 1, vendor_tracking_id, NULL)) AS np_age_1,
    COUNT(DISTINCT IF(phin_date IS NULL AND mh_in_date IS NULL AND NOT is_rto_cxl AND DATE_DIFF(CURRENT_DATE('Asia/Kolkata'), created_date, DAY) = 2, vendor_tracking_id, NULL)) AS np_age_2,
    COUNT(DISTINCT IF(phin_date IS NULL AND mh_in_date IS NULL AND NOT is_rto_cxl AND DATE_DIFF(CURRENT_DATE('Asia/Kolkata'), created_date, DAY) = 3, vendor_tracking_id, NULL)) AS np_age_3,
    COUNT(DISTINCT IF(phin_date IS NULL AND mh_in_date IS NULL AND NOT is_rto_cxl AND DATE_DIFF(CURRENT_DATE('Asia/Kolkata'), created_date, DAY) = 4, vendor_tracking_id, NULL)) AS np_age_4,
    COUNT(DISTINCT IF(phin_date IS NULL AND mh_in_date IS NULL AND NOT is_rto_cxl AND DATE_DIFF(CURRENT_DATE('Asia/Kolkata'), created_date, DAY) >= 5, vendor_tracking_id, NULL)) AS np_age_5_plus
  FROM ext_enriched
  GROUP BY 1, 2, 3, 4
)
SELECT
  cc.reporting_date,
  cc.seller_type,
  COALESCE(cc.pickup_hub_name, IF(cc.mp_pickup_hub_key IS NULL, 'No pickup hub key', CONCAT('Hub_', CAST(cc.mp_pickup_hub_key AS STRING)))) AS pickup_hub_name,
  COALESCE(cc.pickup_hub_city, 'Unknown') AS pickup_hub_city,
  COALESCE(cc.pickup_hub_zone, 'Unknown') AS pickup_hub_zone,
  cc.payment_type,
  cc.cal_created_volume,
  cc.cal_d0_picked,
  cc.cal_d1_picked,
  cc.cal_d2_plus_picked,
  cc.cal_mhin_no_phin,
  cc.cal_rto_cxl_no_phin,
  cc.cal_no_phin,
  cc.np_age_1,
  cc.np_age_2,
  cc.np_age_3,
  cc.np_age_4,
  cc.np_age_5_plus
FROM created_cal_day cc
ORDER BY reporting_date, seller_type, pickup_hub_name, payment_type;

-- Sanity (expect unknown hub names only when mp_pickup_hub_key IS NULL or missing from hub_dim):
-- SELECT
--   COUNT(*) AS n,
--   COUNTIF(pickup_hub_name LIKE 'Hub_%' OR pickup_hub_name = 'No pickup hub key') AS unresolved_hub
-- FROM (<query above>) q;
