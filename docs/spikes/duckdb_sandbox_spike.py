"""Throwaway spike (2026-11-24): verify DuckDB sandbox + sqlglot behaviour assumed by SECURITY.md §5.

Not application code. Run: uv run --with duckdb --with sqlglot python docs/spikes/duckdb_sandbox_spike.py
"""
import os
import tempfile

import duckdb
import sqlglot

SANDBOX = {
    "enable_external_access": False,
    "lock_configuration": True,
    "autoinstall_known_extensions": False,
    "autoload_known_extensions": False,
}

d = tempfile.mkdtemp()
pq, db = os.path.join(d, "fact.parquet"), os.path.join(d, "gold.duckdb")
open(os.path.join(d, "secret.csv"), "w").write("a\n1\n")
duckdb.sql(f"copy (select 1 id, 9.5 rev) to '{pq}' (format parquet)")
c = duckdb.connect(db)
c.execute("create table orders as select 1 id, 10.0 amt")
c.execute(f"create view v_parquet as select * from read_parquet('{pq}')")
c.close()

print("duckdb", duckdb.__version__, "sqlglot", sqlglot.__version__)
r = duckdb.connect(db, read_only=True, config=SANDBOX)
for q in [
    "select sum(amt) from orders",
    "select * from v_parquet",
    f"select * from read_csv('{d}/secret.csv')",
    "insert into orders values (2, 3)",
    "set enable_external_access=true",
    "attach ':memory:' as x",
    "install httpfs",
    f"copy orders to '{d}/out.csv'",
]:
    try:
        r.execute(q).fetchall()
        print("ALLOWED ", q[:60])
    except Exception as e:  # noqa: BLE001 - spike
        print("BLOCKED ", q[:60], "->", type(e).__name__)

# Second connection to the same file with a different config in the same process
try:
    duckdb.connect(db, read_only=True)
    print("ALLOWED  second connection with different config")
except Exception as e:  # noqa: BLE001
    print("BLOCKED  second connection with different config ->", type(e).__name__)

print("statements in 'select 1; drop table x':", len(sqlglot.parse("select 1; drop table x", read="duckdb")))
tree = sqlglot.parse_one("select o.id from orders o join read_parquet('x') p on 1=1", read="duckdb")
print("table names:", [t.name for t in tree.find_all(sqlglot.exp.Table)],
      "functions:", [type(f).__name__ for f in tree.find_all(sqlglot.exp.Func)])
