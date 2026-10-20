# FDP SQL (BigQuery)

| File | Use |
|------|-----|
| `QUERY_FM_NL_MH_DASHBOARD.sql` | Export for Streamlit (`fm_nl_bundled_export.csv`) — rolling 3M NL create cohort |
| `QUERY_FM_PENDING_TIDS.sql` | Shipment-level true pending TIDs (no PH-in, no MH-in, not RTO/cancel) |

Run on FDP with team **core-logistics-t**. Prefix tables with `bigfoot_external_neo.` as in the files.
