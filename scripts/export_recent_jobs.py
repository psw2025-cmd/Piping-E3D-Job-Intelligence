import argparse
import os
import sqlite3

import pandas as pd

repo_dir = r'C:\Pritam_CV_Tier1_EPC\Piping-E3D-Job-Intelligence'
db_path = os.path.join(repo_dir, 'data', 'database', 'jobs.db')

def export_recent_jobs(days=3):
    conn = sqlite3.connect(db_path)
    
    query = """
    SELECT 
        company AS [Company],
        title AS [Job Title],
        location AS [Location],
        city AS [City],
        country AS [Country],
        found_at AS [Found Date],
        published_at AS [Published Date],
        match_score AS [Match Score],
        priority AS [Priority],
        apply_url AS [Apply Link],
        source_name AS [Source]
    FROM jobs
    WHERE datetime(found_at) >= datetime('now', '-' || ? || ' days')
       OR datetime(last_seen_at) >= datetime('now', '-' || ? || ' days')
    ORDER BY found_at DESC, match_score DESC;
    """
    
    df = pd.read_sql_query(query, conn, params=(days, days))
    conn.close()
    
    out_file = os.path.join(repo_dir, 'data', 'exports', f'Jobs_Last_{days}_Days.xlsx')
    
    with pd.ExcelWriter(out_file, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name=f'Last_{days}_Days', index=False)
        
    print(f"PASS: Exported {len(df)} jobs from the last {days} days to {out_file}")
    return len(df), out_file

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Export jobs collected in the last N days")
    parser.add_argument('--days', type=int, default=3, help="Number of days to look back (default: 3)")
    args = parser.parse_args()
    export_recent_jobs(args.days)
