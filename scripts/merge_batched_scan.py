from __future__ import annotations
import argparse, json, re, shutil, sqlite3
from datetime import UTC, datetime
from pathlib import Path
from job_intelligence.database import init_database
from job_intelligence.excel_export import export_excel, verify_excel
from job_intelligence.proof import init_proof_tables
from job_intelligence.run_cloud_daily import _build_summary

TABLES = ('jobs','job_identity_aliases','source_health','runs','source_evidence')
SHARD = re.compile(r'shard-\d{3}')

def exists(db, table):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None

def cols(db, table):
    return [r[1] for r in db.execute(f'PRAGMA table_info("{table}")')]

def shard_id(path):
    for part in reversed(path.parts):
        m=SHARD.search(part)
        if m: return m.group(0)
    return None

def copy_table(src, dst, table, raw_dest=None):
    if not exists(src, table) or not exists(dst, table): return 0
    names=[x for x in cols(src, table) if x in cols(dst, table)]
    q=', '.join(f'"{x}"' for x in names); marks=', '.join('?' for _ in names)
    sql=f'INSERT OR REPLACE INTO "{table}" ({q}) VALUES ({marks})'
    path_i=names.index('file_path') if table=='source_evidence' and 'file_path' in names else -1
    n=0
    for row in src.execute(f'SELECT {q} FROM "{table}"'):
        values=list(row)
        if path_i >= 0 and raw_dest:
            parts=list(Path(str(values[path_i])).parts)
            rel=Path(*parts[parts.index('raw')+1:]) if 'raw' in parts else Path(Path(str(values[path_i])).name)
            values[path_i]=str(raw_dest/rel)
        dst.execute(sql, values); n+=1
    return n

def bundle(out):
    zip_path=out/'Piping_E3D_Daily_Bundle.zip'; zip_path.unlink(missing_ok=True)
    base=Path(shutil.make_archive(str(out.parent/'Piping_E3D_Daily_Bundle_batched'),'zip',root_dir=out.parent,base_dir=out.name))
    base.replace(zip_path)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--plan',type=Path,required=True); ap.add_argument('--shards-root',type=Path,required=True); ap.add_argument('--output',type=Path,required=True); a=ap.parse_args()
    plan=json.loads(a.plan.read_text()); expected={x['id'] for x in plan['shards']}
    found={}; dirs={}
    for sp in a.shards_root.rglob('status.json'):
        sid=shard_id(sp.parent)
        if sid: found[sid]=json.loads(sp.read_text()); dirs[sid]=sp.parent
    errors=[]
    for sid in sorted(expected):
        st=found.get(sid)
        if not st: errors.append(f'{sid}: missing status')
        elif st.get('exit_code') != 0 or st.get('verified') is not True: errors.append(f"{sid}: {st.get('error') or st.get('collection_status') or 'unverified'}")
    shutil.rmtree(a.output, ignore_errors=True); a.output.mkdir(parents=True)
    db_path=a.output/'jobs.db'; init_database(db_path); init_proof_tables(db_path)
    raw=a.output/'raw'; raw.mkdir()
    with sqlite3.connect(db_path) as dst:
        for sid, folder in sorted(dirs.items()):
            src_path=folder/'jobs.db'
            if not src_path.exists(): errors.append(f'{sid}: missing jobs.db'); continue
            src_raw=folder/'raw'; raw_dest=raw/sid
            if src_raw.exists(): shutil.copytree(src_raw,raw_dest,dirs_exist_ok=True)
            with sqlite3.connect(src_path) as src:
                for table in TABLES: copy_table(src,dst,table,raw_dest if src_raw.exists() else None)
        dst.commit()
    sums=lambda key: sum(int(x.get(key,0)) for x in found.values())
    ok=not errors and expected==set(found)
    status={'generated_at':datetime.now(UTC).replace(microsecond=0).isoformat(),'run_id':'batched-'+datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ'),'exit_code':0 if ok else 1,'collection_status':'pass' if ok else ('partial' if sums('sources_passed') else 'fail'),'verified':False,'coverage_verified':False,'error':' | '.join(errors),'sources_attempted':sums('sources_attempted'),'sources_passed':sums('sources_passed'),'sources_failed':sums('sources_failed'),'jobs_collected':sums('jobs_collected'),'new_jobs':sums('new_jobs'),'updated_jobs':sums('updated_jobs'),'shards_expected':len(expected),'shards_completed':len(found),'shards_failed':len(errors)}
    try:
        workbook=a.output/'Piping_E3D_Jobs.xlsx'; export_excel(db_path,workbook); export_errors=verify_excel(workbook)
        if export_errors: raise RuntimeError(' | '.join(export_errors))
        status['verified']=ok
    except Exception as exc:
        status['exit_code']=1; status['verified']=False; status['error']=' | '.join(filter(None,[status['error'],f'{type(exc).__name__}: {exc}']))
    (a.output/'shard_statuses.json').write_text(json.dumps({'plan':plan,'statuses':found,'errors':errors},indent=2)+'\n')
    (a.output/'status.json').write_text(json.dumps(status,indent=2,sort_keys=True)+'\n')
    (a.output/'run.log').write_text(f"merged {len(found)}/{len(expected)} shards; sources={status['sources_passed']}/{status['sources_attempted']}; errors={status['error']}\n")
    (a.output/'SUMMARY.md').write_text(_build_summary(db_path,status)); bundle(a.output)
    print(json.dumps(status,sort_keys=True)); return status['exit_code']

if __name__=='__main__': raise SystemExit(main())
