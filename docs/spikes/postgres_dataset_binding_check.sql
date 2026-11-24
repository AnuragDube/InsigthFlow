-- 2026-11-24: dataset-binding checks for the schema in docs/DATA_ARCHITECTURE.md §7 (PostgreSQL 16).
-- Org A has two data sources (S1, S2). Expected outcome noted per statement; observed output in the .output.txt file.
\set ON_ERROR_STOP 0
insert into organizations(id,slug,name) values ('00000000-0000-0000-0000-00000000000a','org-a','A');
insert into data_sources(id,org_id,name,domain,kind,contract_version) values
 ('00000000-0000-0000-0000-000000000051','00000000-0000-0000-0000-00000000000a','s1','ecommerce','sample','1');
insert into data_sources(id,org_id,name,domain,kind,contract_version) values
 ('00000000-0000-0000-0000-000000000052','00000000-0000-0000-0000-00000000000a','s2','ecommerce','sample','1');
insert into ingestions(id,org_id,data_source_id,original_name,sha256,size_bytes,storage_path,status) values
 ('00000000-0000-0000-0000-0000000000e2','00000000-0000-0000-0000-00000000000a','00000000-0000-0000-0000-000000000052','b.csv',repeat('a',64),1,'x','stored');
insert into pipeline_runs(id,org_id,data_source_id,trigger,status,code_version) values
 ('00000000-0000-0000-0000-0000000000f1','00000000-0000-0000-0000-00000000000a','00000000-0000-0000-0000-000000000051','manual','succeeded','x');
\echo EXPECT OK: publish S1 run on S1
update data_sources set published_run_id='00000000-0000-0000-0000-0000000000f1' where id='00000000-0000-0000-0000-000000000051';
\echo EXPECT FK ERROR: publish S1 run on S2
update data_sources set published_run_id='00000000-0000-0000-0000-0000000000f1' where id='00000000-0000-0000-0000-000000000052';
\echo EXPECT FK ERROR: S1 run consuming an S2 batch
insert into pipeline_run_inputs(org_id,data_source_id,run_id,ingestion_id) values
 ('00000000-0000-0000-0000-00000000000a','00000000-0000-0000-0000-000000000051','00000000-0000-0000-0000-0000000000f1','00000000-0000-0000-0000-0000000000e2');
\echo EXPECT FK ERROR: same, but lying about the data source
insert into pipeline_run_inputs(org_id,data_source_id,run_id,ingestion_id) values
 ('00000000-0000-0000-0000-00000000000a','00000000-0000-0000-0000-000000000052','00000000-0000-0000-0000-0000000000f1','00000000-0000-0000-0000-0000000000e2');
