-- Run by hand on PostgreSQL 16 on 2026-11-24 after applying the DDL in docs/DATA_ARCHITECTURE.md §7
-- (an earlier draft — the schema has since been revised per review; re-run in Phase 2 as automated tests).
-- Observed result for each statement is recorded in the comment above it.
insert into organizations(id,slug,name) values
 ('00000000-0000-0000-0000-00000000000a','org-a','A'),('00000000-0000-0000-0000-00000000000b','org-b','B');
insert into users(id,email,display_name) values ('00000000-0000-0000-0000-000000000001','x@y.z','X');
insert into roles(id,org_id,name) values ('00000000-0000-0000-0000-0000000000b1','00000000-0000-0000-0000-00000000000b','viewer');
-- OBSERVED: ERROR violates foreign key constraint "memberships_org_id_role_id_fkey"
insert into memberships(org_id,user_id,role_id) values
 ('00000000-0000-0000-0000-00000000000a','00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-0000000000b1');
insert into data_sources(id,org_id,name,domain,kind,contract_version) values
 ('00000000-0000-0000-0000-0000000000d1','00000000-0000-0000-0000-00000000000b','retail','ecommerce','sample','1');
-- OBSERVED: ERROR violates foreign key constraint "pipeline_runs_org_id_data_source_id_fkey"
insert into pipeline_runs(id,org_id,data_source_id,trigger,status,code_version,input_ingestions) values
 (gen_random_uuid(),'00000000-0000-0000-0000-00000000000a','00000000-0000-0000-0000-0000000000d1','manual','queued','x','{}');
-- OBSERVED: first insert succeeds, second fails: duplicate key violates unique constraint "uq_one_active_run"
insert into pipeline_runs(id,org_id,data_source_id,trigger,status,code_version,input_ingestions) values
 (gen_random_uuid(),'00000000-0000-0000-0000-00000000000b','00000000-0000-0000-0000-0000000000d1','manual','queued','x','{}');
insert into pipeline_runs(id,org_id,data_source_id,trigger,status,code_version,input_ingestions) values
 (gen_random_uuid(),'00000000-0000-0000-0000-00000000000b','00000000-0000-0000-0000-0000000000d1','manual','running','x','{}');
