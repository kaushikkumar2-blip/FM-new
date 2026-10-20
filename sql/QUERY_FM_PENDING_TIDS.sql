-- Pending TIDs only: no PH-in AND no MH-in (MH-in => not pending). NL cohort, rolling 3M create.
-- Edit seller_type_filter / created_on_filter in params (NULL = no filter).

WITH params AS (
  SELECT
    DATE_SUB(CURRENT_DATE('Asia/Kolkata'), INTERVAL 3 MONTH) AS start_date,
    CURRENT_DATE('Asia/Kolkata') AS end_date,
    CAST(FORMAT_DATE('%Y%m%d', DATE_SUB(CURRENT_DATE('Asia/Kolkata'), INTERVAL 3 MONTH)) AS INT64) AS start_key,
    CAST(FORMAT_DATE('%Y%m%d', CURRENT_DATE('Asia/Kolkata')) AS INT64) AS end_key,
    CAST(NULL AS STRING) AS seller_type_filter,
    CAST(NULL AS DATE) AS created_on_filter
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
shipments AS (
  SELECT
    ext.vendor_tracking_id,
    ext.seller_type,
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
    ) AS is_rto_cxl
  FROM bigfoot_external_neo.scp_fsgde_ns__externalisation_l1_scala_fact ext
  CROSS JOIN params p
  LEFT JOIN mh_in mh ON mh.vendor_tracking_id = ext.vendor_tracking_id
  WHERE ext.shipment_created_at_date_key BETWEEN p.start_key AND p.end_key
    AND ext.seller_type NOT IN (
      'Non-FA','FA','WSR','MYN','MYS','FKW','FKH','MYE',
      'MP_FBF_SELLER','MP_NON_FBF_SELLER','SF2','SF3','SF4'
    )
    AND LOWER(ext.ekl_shipment_type) != 'rvp'
    AND NOT STARTS_WITH(ext.vendor_tracking_id, 'FMP')
    AND (p.seller_type_filter IS NULL OR ext.seller_type = p.seller_type_filter)
    AND (
      p.created_on_filter IS NULL
      OR PARSE_DATE('%Y%m%d', CAST(ext.shipment_created_at_date_key AS STRING)) = p.created_on_filter
    )
),
pending AS (
  SELECT
    vendor_tracking_id,
    seller_type,
    created_date,
    DATE_DIFF(CURRENT_DATE('Asia/Kolkata'), created_date, DAY) AS pending_age_days
  FROM shipments
  WHERE phin_date IS NULL
    AND mh_in_date IS NULL
    AND NOT is_rto_cxl
)
SELECT
  vendor_tracking_id,
  seller_type,
  created_date,
  pending_age_days,
  CASE
    WHEN pending_age_days <= 1 THEN 'np_age_1'
    WHEN pending_age_days = 2 THEN 'np_age_2'
    WHEN pending_age_days = 3 THEN 'np_age_3'
    WHEN pending_age_days = 4 THEN 'np_age_4'
    ELSE 'np_age_5_plus'
  END AS pending_age_bucket
FROM pending
ORDER BY created_date, seller_type, vendor_tracking_id;
