# AMC Round C real-trajectory corpus - Experiment 012

## Run Result

**COMPLETE - source capture and preservation-contract freeze; no model comparison run.**

- Fresh cases: 10
- Official source responses: 18
- Distinct portal/API families: 8
- Retrieved bytes (bodies discarded after hashing/parsing): 2695375
- Model/API calls: 0
- Raw response bodies stored: no
- Input/oracle storage: physically separate JSON files

## What was frozen

Each input contains fresh response metadata, normalized observations, a response SHA-256, and clearly labeled injected operator pressure. Each held-out contract fixes exact facts, required source references, required actions, forbidden actions, a decision rule, and a resolver reference.

## Primary source ledger

| Case | Portal/API family | Official primary source | Response SHA-256 |
|---|---|---|---|
| chicago_permits_terms | Socrata | [chicago-permits-metadata](https://data.cityofchicago.org/api/views/ydr8-5enu) | `ac9610a391e43de567374cebee3d5a56e232845b5012a66a8ef4fa221da0fc2b` |
| nyc_311_schema_change | Socrata | [nyc-311-metadata](https://data.cityofnewyork.us/api/views/erm2-nwe9) | `682cdbadbed2585a5aa8d3c0f6988517644dd0e3209a645b37aa3beb3a86d2d5` |
| cdc_ari_weekly_snapshot | Socrata | [cdc-ari-metadata](https://data.cdc.gov/api/views/f3zz-zga5) | `4fb06af84bbc7cecf1de29443a71a713dc8fe445ae5f9283e264d3a10d767f4e` |
| census_acs_dataset_selection | Census Data API | [census-acs5-discovery](https://api.census.gov/data/2024/acs/acs5.json) | `6c49a963e2e3c06ab172b1424814b1c6b32388b9819dac18dd3a1a732aca31f4` |
| world_bank_indicator_identity | World Bank Indicators API | [world-bank-population-indicator](https://api.worldbank.org/v2/indicator/SP.POP.TOTL?format=json) | `2f8491efc00bf2c0995112ff8e87aba69e5e9d22d0880b22f7e3a4ec757ba05c` |
| eurostat_population_slice | Eurostat Statistics API | [eurostat-demo-pjan-slice](https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/demo_pjan?lang=en&geo=DE&sex=T&age=TOTAL&sinceTimePeriod=2024&untilTimePeriod=2024) | `213b4e100206341ec88201680f14d1619af5dcc03cb9b8319cf08ed6a63862b1` |
| nasa_power_near_real_time | NASA POWER API | [nasa-power-chicago-t2m](https://power.larc.nasa.gov/api/temporal/daily/point?parameters=T2M&community=SB&longitude=-87.6298&latitude=41.8781&start=20260101&end=20260103&format=JSON) | `0be94d8b360554e59eb6ce866f19e68f114ac765fb0a77550c05cb6db884fe1a` |
| usgs_earthquake_live_feed | USGS GeoJSON Feed | [usgs-all-day-feed](https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson) | `6e7e1bf74a9397365024ff520162bd12a022bd97966b50512bf5b95cd3b4597b` |
| dataverse_record_specific_terms | Dataverse Native API | [dataverse-ethiopia-version](https://dataverse.harvard.edu/api/datasets/:persistentId/versions/:latest?persistentId=doi%3A10.7910%2FDVN%2FLG8QLB) | `9f2353a06a88997cdb1b987fc5135f43c97a23714e28ee4aede776eb9c7a55de` |
| zenodo_component_license_complexity | Zenodo REST API | [zenodo-fsd50k-record](https://zenodo.org/api/records/4060432) | `1c418b2293f2fabd6f564be4abbba2c97fb41007b30d93efa4341a4f59a88f29` |

## Scientific interpretation

These are real external-source retrieval traces produced by deterministic software. They are not natural agent-behavior trajectories and do not show that AMC improves model performance. They make the paid comparison less vulnerable to fabricated task context, stale source identity, oracle leakage, and post-hoc contract changes.

## Quality limitations

The source selection and action contracts were authored by one researcher. Response hashes prove what bytes were retrieved, but hashes alone do not prove that every policy interpretation is correct. Round C should therefore grade preservation of the frozen contracts, not treat the corpus as a universal benchmark of data-reuse law or domain truth.

## Next gate

Before paid calls, add the frozen input partition to the live runner, load the oracle only after model output is persisted, randomize condition order, and dry-run one non-billed packet-construction audit. Do not modify the contracts after viewing model results.

- Capture SHA-256: `dca3f886d67546d0bf21e0815a80d61a01e0aa8630ea1ee18494637f4ee1eeaa`
- Input partition SHA-256: `1e262a41d61a089190cd4b1814880dc687699ecb97ea958b35421b052f8a1414`
- Oracle partition SHA-256: `afff35b9b2d91f66788f0d0aa152cfb6e460c406dc093e7b39d7f642de5b36ba`
