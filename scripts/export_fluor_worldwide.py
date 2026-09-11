"""Resilient official-source Fluor worldwide job exporter."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE='https://careers.fluor.com'; LISTING=f'{BASE}/careers'; ROBOTS=f'{BASE}/robots.txt'; SITEMAP_INDEX=f'{LISTING}/sitemap_index.xml?domain=fluor.com'; SITEMAP=f'{LISTING}/sitemap.xml?domain=fluor.com'; UA='Piping-E3D-Job-Intelligence/0.7 (+official public-source audit)'
LISTING_VARIANTS=[LISTING,f'{LISTING}?query=piping',f'{LISTING}?query=e3d',f'{LISTING}?query=pdms',f'{LISTING}?query=layout',f'{LISTING}?query=3d']
KEYWORDS={
'piping':r'\bpiping\b|\bpipe\s*(?:layout|design|support|stress|material|route|rack|fitter)\b','e3d':r'\b(?:aveva\s*)?e3d\b','pdms':r'\bpdms\b','sp3d_s3d':r'\b(?:sp3d|s3d|smartplant\s*3d|smart\s*3d)\b','plant_layout':r'\bplant\s*layout\b|\blayout(?:ing)?\b|\bequipment\s*layout\b','navisworks':r'\bnavisworks\b','microstation':r'\bmicrostation\b','autocad':r'\bautocad(?:\s*plant\s*3d)?\b','model_coordination':r'\b3d\s*model(?:ling|ing)?\b|\bmodel\s*coordinat(?:or|ion)\b','site_piping':r'\bsite\s*piping\b|\bconstruction\s*coordinat(?:or|ion)\b','oil_gas_epc':r'\boil\s*(?:&|and)\s*gas\b|\blng\b|\brefiner(?:y|ies)\b|\bpetrochemical\b|\boffshore\b|\bnuclear\b|\bepc(?:m)?\b'}
FIELDS=['company','position_id','ats_job_id','display_job_id','title','posting_name','city_state_country','all_locations','country','department','business_unit','seniority','workplace_type','hot','posted_utc','updated_utc','official_url','detail_http_status','active_status','description','experience','education','work_authorisation','urgency_evidence',*[f'kw_{k}' for k in KEYWORDS],'matched_keywords','match_count','source','discovery_method','collected_utc','content_sha256','extraction_notes']

def walk(v:Any)->Iterable[Any]:
 yield v
 if isinstance(v,dict):
  for c in v.values(): yield from walk(c)
 elif isinstance(v,list):
  for c in v: yield from walk(c)

def balanced_json_arrays(html:str,marker='"positions":')->Iterable[list[Any]]:
 start=0
 while True:
  hit=html.find(marker,start)
  if hit<0:return
  arr=html.find('[',hit)
  if arr<0:return
  depth=0;quoted=False;escaped=False
  for end in range(arr,len(html)):
   ch=html[end]
   if quoted:
    if escaped:escaped=False
    elif ch=='\\':escaped=True
    elif ch=='"':quoted=False
   elif ch=='"':quoted=True
   elif ch=='[':depth+=1
   elif ch==']':
    depth-=1
    if depth==0:
     try:yield json.loads(html[arr:end+1])
     except json.JSONDecodeError:pass
     start=end+1;break
  else:return

def extract_catalogue(html:str)->tuple[list[dict[str,Any]],dict[str,Any]]:
 soup=BeautifulSoup(html,'html.parser'); roots=[]
 for s in soup.find_all('script'):
  t=(s.string or s.get_text() or '').strip()
  if t[:1] in '[{':
   try:roots.append(json.loads(t))
   except json.JSONDecodeError:pass
 positions={};facets={}
 for root in roots:
  for n in walk(root):
   if isinstance(n,dict) and isinstance(n.get('positions'),list):
    for item in n['positions']:
     if isinstance(item,dict) and item.get('id'):positions[str(item['id'])]=item
    if isinstance(n.get('facets'),dict):facets=n['facets']
 for arr in balanced_json_arrays(html):
  for item in arr:
   if isinstance(item,dict) and item.get('id'):positions[str(item['id'])]=item
 return list(positions.values()),facets

def extract_job_links(html:str)->list[str]:
 soup=BeautifulSoup(html,'html.parser'); out=[]
 for a in soup.select('a[href]'):
  u=urljoin(BASE,a.get('href',''))
  if urlparse(u).hostname=='careers.fluor.com' and '/careers/job/' in u:out.append(u.split('#')[0])
 return sorted(set(out))

def session()->requests.Session:
 s=requests.Session(); retry=Retry(total=5,connect=5,read=5,status=5,backoff_factor=.8,status_forcelist=(408,425,429,500,502,503,504),allowed_methods=frozenset({'GET'}),respect_retry_after_header=True)
 s.mount('https://',HTTPAdapter(max_retries=retry,pool_connections=8,pool_maxsize=8));s.headers.update({'User-Agent':UA,'Accept':'text/html,application/xhtml+xml','Accept-Language':'en-US,en;q=0.8'});return s

def get(s:requests.Session,url:str,timeout:int)->requests.Response:
 r=s.get(url,timeout=timeout,allow_redirects=True);r.raise_for_status();return r

def robots_can_fetch(text:str,user_agent:str,url:str)->bool:
 """Apply RFC 9309 longest-match precedence to the applicable robots group."""
 groups=[];agents=[];rules=[]
 for raw in [*text.splitlines(),'User-agent: __end__']:
  line=raw.split('#',1)[0].strip()
  if not line or ':' not in line:continue
  field,value=(part.strip() for part in line.split(':',1));field=field.lower()
  if field=='user-agent':
   if rules:groups.append((agents,rules));agents=[];rules=[]
   agents.append(value.lower())
  elif field in {'allow','disallow'} and agents:
   if value or field=='allow':rules.append((value,field=='allow'))
 ua=user_agent.lower();applicable=[]
 for group_agents,group_rules in groups:
  specificity=max((0 if agent=='*' else len(agent) for agent in group_agents if agent=='*' or agent in ua),default=-1)
  if specificity>=0:applicable.append((specificity,group_rules))
 if not applicable:return True
 best_agent=max(item[0] for item in applicable);path=urlparse(url).path or '/';matches=[]
 for specificity,group_rules in applicable:
  if specificity!=best_agent:continue
  for pattern,allowed in group_rules:
   end=pattern.endswith('$');core=pattern[:-1] if end else pattern
   expression='^'+re.escape(core).replace(r'\*','.*')+('$' if end else '')
   if re.search(expression,path):matches.append((len(core.replace('*','')),allowed))
 if not matches:return True
 longest=max(item[0] for item in matches)
 return any(allowed for length,allowed in matches if length==longest)

def epoch(v:Any)->str:
 try:return datetime.fromtimestamp(int(v), UTC).isoformat()
 except (TypeError,ValueError,OSError):return ''

def find_text(ps:list[str],text:str)->str:
 for p in ps:
  m=re.search(p,text,re.IGNORECASE | re.DOTALL)
  if m:return re.sub(r'\s+',' ',m.group(0)).strip()[:700]
 return ''

def parse_detail(html:str)->tuple[str,dict[str,str]]:
 soup=BeautifulSoup(html,'html.parser')
 for t in soup(['script','style','noscript']):t.decompose()
 text=re.sub(r'\s+',' ',soup.get_text(' ',strip=True)).strip()
 return text[:30000],{'experience':find_text([r'(?:minimum|at least|requires?).{0,80}?\b\d{1,2}\+?\s+years?.{0,180}',r'\b\d{1,2}\+?\s+years? of.{0,220}'],text),'education':find_text([r'(?:bachelor|master|degree|diploma|associate).{0,260}'],text),'work_authorisation':find_text([r'(?:authorized|authorised|work authorization|work permit|visa|sponsor|citizenship|clearance).{0,260}'],text),'urgency_evidence':find_text([r'\b(?:urgent|immediate(?:ly)?|asap|walk[- ]?in|mobilisation|mobilization)\b.{0,180}'],text)}

def country(loc:str)->str:return loc.rsplit(',',1)[-1].strip() if ',' in loc else ''
def write_csv(path:Path,data:list[dict[str,Any]],fields=FIELDS):
 with path.open('w',encoding='utf-8-sig',newline='') as h:
  w=csv.DictWriter(h,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(data)

def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--output',default='output/fluor');p.add_argument('--delay',type=float,default=.45);p.add_argument('--timeout',type=int,default=30);p.add_argument('--max-details',type=int,default=2000);p.add_argument('--minimum-catalogue',type=int,default=100);a=p.parse_args()
 out=Path(a.output);out.mkdir(parents=True,exist_ok=True);collected=datetime.now(UTC).isoformat();s=session();evidence=[]
 try:
  robot_response=get(s,ROBOTS,a.timeout);robots_text=robot_response.text;evidence.append({'url':ROBOTS,'status':robot_response.status_code,'bytes':len(robot_response.content),'sha256':hashlib.sha256(robot_response.content).hexdigest()})
 except requests.RequestException as exc:raise SystemExit(f'robots.txt unavailable; fail closed: {type(exc).__name__}')
 if not robots_can_fetch(robots_text,UA,LISTING):raise SystemExit('robots.txt does not permit catalogue retrieval')
 jobs={};facets={};links=set()
 for url in LISTING_VARIANTS:
  if not robots_can_fetch(robots_text,UA,url):continue
  try:
   r=get(s,url,a.timeout);cat,f=extract_catalogue(r.text);links.update(extract_job_links(r.text));
   for j in cat:
    if j.get('id'):jobs[str(j['id'])]=j
   if f:facets=f
   evidence.append({'url':url,'status':r.status_code,'bytes':len(r.content),'positions':len(cat),'links':len(extract_job_links(r.text)),'sha256':hashlib.sha256(r.content).hexdigest()})
  except requests.RequestException as exc:evidence.append({'url':url,'error':type(exc).__name__})
 for sm in (SITEMAP_INDEX,SITEMAP):
  if not robots_can_fetch(robots_text,UA,sm):continue
  try:
   r=get(s,sm,a.timeout)
   if urlparse(sm).path.endswith('sitemap.xml'):links.update(re.findall(r'https://careers\.fluor\.com/careers/job/[^<\s]+',r.text))
   evidence.append({'url':sm,'status':r.status_code,'bytes':len(r.content),'sha256':hashlib.sha256(r.content).hexdigest()})
  except requests.RequestException as exc:evidence.append({'url':sm,'error':type(exc).__name__})
 for u in links:
  m=re.search(r'/careers/job/(\d+)',u)
  if m and m.group(1) not in jobs:jobs[m.group(1)]={'id':m.group(1),'canonicalPositionUrl':u}
 if len(jobs)<a.minimum_catalogue:
  (out/'Fluor_Source_Evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
  raise SystemExit(f'Coverage unexpectedly low before detail fetch: {len(jobs)}')
 rows=[];failures=[]
 for i,job in enumerate(jobs.values()):
  url=urljoin(BASE,str(job.get('canonicalPositionUrl') or f"{BASE}/careers/job/{job.get('id')}"));status='';desc='';facts={'experience':'','education':'','work_authorisation':'','urgency_evidence':''};notes='';method='embedded_catalogue' if any(job.get(k) for k in ('name','posting_name','location')) else 'official_job_link_fallback'
  if i<a.max_details and urlparse(url).hostname=='careers.fluor.com' and robots_can_fetch(robots_text,UA,url):
   try:
    d=get(s,url,a.timeout);status=str(d.status_code);desc,facts=parse_detail(d.text)
    if not desc:notes='detail page returned no readable text'
   except requests.RequestException as exc:notes=f'detail request failed after retries: {type(exc).__name__}';failures.append({'position_id':job.get('id',''),'official_url':url,'error':notes})
   time.sleep(max(a.delay,0))
  else:notes='detail not fetched because of configured limit/domain/robots policy'
  title=str(job.get('name') or job.get('posting_name') or '');posting=str(job.get('posting_name') or '');locs=job.get('locations') or [];loc=str(job.get('location') or (locs[0] if locs else ''));hay=' '.join((title,posting,desc));flags={k:bool(re.search(v, hay, re.IGNORECASE)) for k,v in KEYWORDS.items()};matched=[k for k,v in flags.items() if v]
  row={'company':'Fluor','position_id':job.get('id',''),'ats_job_id':job.get('ats_job_id',''),'display_job_id':job.get('display_job_id',''),'title':title,'posting_name':posting,'city_state_country':loc,'all_locations':' | '.join(map(str,locs)),'country':country(loc),'department':' | '.join(map(str,job.get('department') or [])),'business_unit':job.get('business_unit',''),'seniority':job.get('seniority',''),'workplace_type':job.get('work_location_option',''),'hot':job.get('hot',''),'posted_utc':epoch(job.get('t_create')),'updated_utc':epoch(job.get('t_update')),'official_url':url,'detail_http_status':status,'active_status':'confirmed_active' if status=='200' else 'potentially_active','description':desc,**facts,**{f'kw_{k}':int(v) for k,v in flags.items()},'matched_keywords':' | '.join(matched),'match_count':len(matched),'source':LISTING,'discovery_method':method,'collected_utc':collected,'content_sha256':hashlib.sha256(desc.encode()).hexdigest() if desc else '','extraction_notes':notes};rows.append(row)
 relevant=[r for r in rows if int(r['match_count'])>0];direct=[r for r in relevant if any(int(r[f'kw_{k}']) for k in ('piping','e3d','pdms','sp3d_s3d','plant_layout'))]
 write_csv(out/'Fluor_All_Worldwide_Jobs.csv',rows);write_csv(out/'Fluor_Piping_E3D_All_Matches.csv',relevant);write_csv(out/'Fluor_Direct_Piping_E3D_Matches.csv',direct);write_csv(out/'Fluor_Detail_Failures.csv',failures,['position_id','official_url','error'])
 summary={'collected_utc':collected,'catalogue_count':len(rows),'keyword_matches':len(relevant),'direct_matches':len(direct),'confirmed_active':sum(r['active_status']=='confirmed_active' for r in rows),'detail_failures':len(failures),'countries':sorted({r['country'] for r in rows if r['country']}),'facets':facets,'listing_variants_attempted':len(LISTING_VARIANTS),'source_evidence':'Fluor_Source_Evidence.json'}
 (out/'Fluor_Source_Evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8');(out/'Fluor_Worldwide_Summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
