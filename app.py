from pathlib import Path
import sqlite3,json,threading,uuid,shutil,os,csv,io
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import FastAPI,HTTPException,Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.responses import HTMLResponse,Response,FileResponse,RedirectResponse
from pydantic import BaseModel,Field,SecretStr,field_validator,model_validator
from typing import Literal
from contextlib import contextmanager
from unicodedata import decimal
from direct_scraper import collect_direct,CollectionError
from openpyxl import Workbook
import re
from project_store import initialize_projects, now, store_post
from analytics import project_analytics
from browser_scraper import collect_in_browser, parse_post_url
ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('DIDBAN_DATA_DIR') or ROOT/'data')
DATA.mkdir(parents=True, exist_ok=True)
DB=DATA/'project.sqlite'
@contextmanager
def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row
    try:
        with c:yield c
    finally:c.close()
with db() as c:
    c.execute('BEGIN IMMEDIATE')
    c.execute('CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, config TEXT,status TEXT,logs TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS results(run TEXT,payload TEXT)')
    initialize_projects(c)
    c.execute("UPDATE runs SET status='interrupted' WHERE status IN ('running', 'awaiting_code', 'awaiting_security')")
app=FastAPI()
@app.exception_handler(RequestValidationError)
async def invalid_input(request:Request,error:RequestValidationError):
    # FastAPI's default model-level validation response can echo the whole body.
    if any(item['loc'] == ('body', 'post_url') for item in error.errors()):
        return JSONResponse(status_code=422,content={'detail':'لینک کامل یک پست یا ریل اینستاگرام را وارد کنید.'})
    return JSONResponse(status_code=422,content={'detail':'اطلاعات فرم معتبر نیست؛ عنوان، نام شرکت‌ها، تگ‌ها و سقف‌ها را بررسی کنید.'})
lock=threading.Lock()
verification_ready = threading.Condition()
pending_verification: dict[str, tuple[str, str | None]] = {}

class VerificationCode(BaseModel):
    code: SecretStr

class Config(BaseModel):
    title:str=Field(default='پروژه جدید',min_length=1,max_length=100)
    target:str=''
    companies: list[str] = Field(default_factory=list, max_length=20)
    profiles:list[str]=Field(default_factory=list,max_length=20)
    hashtags:list[str]=Field(default_factory=list,max_length=20)
    collection_scope: Literal['profile_tags', 'discover'] | None = None
    probe_hashtag: str | None = None
    post_url: str | None = Field(default=None, max_length=2048)

    @field_validator('post_url')
    @classmethod
    def normalize_post_url(cls, value):
        if value is None:
            return None
        return parse_post_url(value)[1]

    @model_validator(mode='after')
    def validate_sources(self):
        if self.collection_scope and (self.method != 'browser' or self.post_url):
            raise ValueError('حالت جست‌وجو فقط برای جمع‌آوری پروژه با مرورگر است')
        if self.post_url is not None:
            if self.method != 'browser' or self.profiles or self.hashtags or self.target:
                raise ValueError('آزمون لینک فقط با یک پست و روش مرورگر انجام می‌شود')
            self.max_posts = 1
            self.likers = self.sync = False
            return self
        self.companies = list(dict.fromkeys(name.strip() for name in self.companies if name.strip()))
        if any(len(name) > 100 for name in self.companies):
            raise ValueError('نام شرکت بیش از ۱۰۰ نویسه است')
        self.profiles=list(dict.fromkeys(x.strip().lstrip('@') for x in self.profiles if x.strip()))
        self.hashtags=list(dict.fromkeys(x.strip().lstrip('#') for x in self.hashtags if x.strip()))
        if self.target and self.target not in self.profiles:self.profiles.insert(0,self.target)
        if len(self.profiles)>20:raise ValueError('حداکثر ۲۰ پیج مجاز است')
        if self.collection_scope == 'profile_tags' and not (self.profiles and self.hashtags):
            raise ValueError('برای جست‌وجو در پیج‌ها، دست‌کم یک پیج و یک تگ وارد کنید')
        if self.collection_scope == 'discover' and (self.profiles or not self.hashtags):
            raise ValueError('برای دیسکاور، دست‌کم یک تگ وارد کنید')
        if not self.profiles and not self.hashtags:raise ValueError('حداقل یک پیج یا هشتگ وارد کنید')
        if self.method == 'instagrapi_probe':
            if self.probe_hashtag is None and len(self.hashtags) == 1:
                self.probe_hashtag = self.hashtags[0]
            if self.profiles or self.probe_hashtag not in self.hashtags:
                raise ValueError('یک هشتگ از فهرست پروژه برای آزمون مستقیم انتخاب کنید')
            self.max_posts = self.max_comments = 1
            self.likers = self.sync = False
        if self.method == 'instagrapi':
            if self.profiles or not self.hashtags:
                raise ValueError('روش instagrapi به فهرست هشتگ‌ها نیاز دارد')
            self.likers = False
        if any(not re.fullmatch(r'[A-Za-z0-9_.]{1,30}',x) for x in self.profiles):raise ValueError('نام پیج نامعتبر است')
        if any(not re.fullmatch(r'[\w\u200c]{1,100}',x) for x in self.hashtags):raise ValueError('هشتگ نامعتبر است')
        if not self.target and self.profiles:self.target=self.profiles[0]
        return self
    max_posts:int=Field(default=8,ge=1,le=100)
    scrolls:int=Field(default=3,ge=1,le=30)
    refresh_posts: bool = False
    background: bool = False
    likers:bool=False
    demo:bool=False
    sync:bool=False
    method:Literal['direct','browser','instagrapi_probe','instagrapi']='direct'
    max_comments:int=Field(default=100,ge=1,le=5000)
    max_likers:int=Field(default=100,ge=1,le=5000)
    login_username:str=Field(default='',exclude=True,repr=False)
    login_password:SecretStr=Field(default=SecretStr(''),exclude=True)
    verification_code:SecretStr=Field(default=SecretStr(''),exclude=True)
@app.middleware('http')
async def local_only(request:Request,call_next):
    if request.headers.get('host','').split(':')[0] not in ('127.0.0.1','localhost'):
        return Response(status_code=403)
    origin=request.headers.get('origin')
    if origin and origin not in ('http://127.0.0.1:8000','http://localhost:8000','http://127.0.0.1:3000','http://localhost:3000',os.environ.get('DIDBAN_LOCAL_ORIGIN')):
        return Response(status_code=403)
    return await call_next(request)
def log(r,msg):
    with db() as c: c.execute('UPDATE runs SET logs=logs||? WHERE id=?',(msg+'\n',r))

def wait_for_verification(run_id, status, prompt, timeout_message):
    with verification_ready:
        with db() as c:
            c.execute(
                'UPDATE runs SET status=?, logs=logs||? WHERE id=?',
                (status, prompt + '\n', run_id),
            )
        pending_verification[run_id] = (status, None)
        try:
            received = verification_ready.wait_for(
                lambda: pending_verification[run_id][1] is not None, timeout=300,
            )
            if not received:
                raise CollectionError(timeout_message)
            _, value = pending_verification[run_id]
        finally:
            pending_verification.pop(run_id, None)
    with db() as c:
        c.execute("UPDATE runs SET status='running' WHERE id=?", (run_id,))
    return value

def recover_instagram_login(run_id, username, loader):
    wait_for_verification(
        run_id, 'awaiting_security',
        'اینستاگرام تأیید امنیتی خواست. برای ادامهٔ همین اجرا، ورود در مرورگر را انتخاب کنید.',
        'مهلت انتخاب ورود در مرورگر تمام شد.',
    )
    from browser_login import get_instagram_session

    log(run_id, 'ورود و تأیید امنیتی را در پنجرهٔ اینستاگرام کامل کنید.')
    cookies = get_instagram_session(username)
    try:
        loader.load_session(username, cookies)
    finally:
        cookies.clear()
    log(run_id, 'حساب ورود در مرورگر تأیید شد. درخواست دریافت پست‌ها با همین نشست آغاز می‌شود.')
def save(r, row):
    with db() as c:
        project_id = c.execute('SELECT project_id FROM runs WHERE id=?', (r,)).fetchone()[0]
        if project_id:
            row = store_post(c, project_id, row)
        if row:
            c.execute('INSERT INTO results VALUES (?,?)', (r, json.dumps(row, ensure_ascii=False)))

def rows(r):
    with db() as c:
        return [json.loads(x[0]) for x in c.execute('SELECT payload FROM results WHERE run=?', (r,))]

def project_rows(project_id):
    with db() as c:
        return [json.loads(x[0]) for x in c.execute(
            'SELECT payload FROM project_posts WHERE project_id=? ORDER BY rowid DESC', (project_id,),
        )]

def previously_collected_posts(project_id):
    if not project_id:
        return set()
    return {post['shortcode'] for post in project_rows(project_id)
            if post.get('comments') or post.get('reported_comment_count') == 0}

def export(r, ext):
    return export_records(rows(r), DATA / (r + '.' + ext), ext)

def export_filename(config, records, ext):
    title = config.get('title') or config.get('target') or 'دیدبان'
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '-', title)
    title = re.sub(r'\s+', ' ', title).strip(' .-')[:80] or 'دیدبان'
    date = datetime.now(ZoneInfo('Asia/Tehran')).strftime('%Y-%m-%d')
    comments = sum(len(record.get('comments') or []) for record in records)
    return f'{title} - {date} - {len(records)} پست - {comments} کامنت.{ext}'

def export_records(records, path, ext):
    fields = ['post_url','shortcode','media_id','owner','caption','source','source_type',
              'published_at','first_collected_at','scraped_at','total_likes','comments','likers']
    table = [fields]
    for record in records:
        table.append([
            json.dumps(record.get(field, []), ensure_ascii=False)
            if field in ('comments', 'likers') else record.get(field)
            for field in fields
        ])
    table=[['post_url','owner','caption','source','source_type','published_at','total_likes','comments','likers']]+[[x['post_url'],x.get('owner',''),x.get('caption',''),x.get('source',''),x.get('source_type',''),x.get('published_at',''),x.get('total_likes'),json.dumps(x.get('comments',[]),ensure_ascii=False),json.dumps(x.get('likers',[]),ensure_ascii=False)] for x in records]
    table=[["'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for v in row] for row in table]
    if ext=='csv':
        with path.open('w',encoding='utf-8-sig',newline='') as f:csv.writer(f).writerows(table)
    else:
        w=Workbook();s=w.active;s.title='پست‌ها'
        for row in table:s.append(row)
        comments = w.create_sheet('کامنت‌ها')
        comment_fields = ['comment_id', 'username', 'text', 'time', 'likes']
        comments.append(['post_url', 'shortcode', *comment_fields])
        likers = w.create_sheet('لایک‌ها')
        likers.append(['post_url', 'data'])
        for record in records:
            for item in record.get('comments', []):
                values = [record['post_url'], record.get('shortcode'), *(item.get(field) for field in comment_fields)]
                comments.append(["'" + value if isinstance(value, str) and value.startswith(('=', '+', '-', '@')) else value for value in values])
            for item in record.get('likers', []):
                likers.append([record['post_url'], json.dumps(item, ensure_ascii=False)])
        w.save(path)
    return path
def worker(r,cfg,credentials=None,project_id=None):
    def request_code():
        return wait_for_verification(
            r, 'awaiting_code',
            'اینستاگرام کد تأیید خواست. کد را در پنجرهٔ همین اجرا وارد کنید.',
            'مهلت ورود کد تأیید تمام شد. اجرا را دوباره شروع کنید.',
        )

    try:
        if cfg['demo']:
            save(r,{'post_url':'https://www.instagram.com/p/DEMO/','total_likes':'12','comments':[{'username':'demo','text':'داده آزمایشی'}],'likers':['demo']})
            log(r,'داده نمایشی ذخیره شد')
        elif cfg['method']=='direct':
            collect_direct(
                cfg, credentials, lambda row: save(r, row), lambda msg: log(r, msg),
                request_code=request_code,
                recover_login=lambda username, loader: recover_instagram_login(r, username, loader),
            )
        elif cfg['method'] == 'instagrapi_probe':
            from check_direct_access import probe_hashtag

            result = probe_hashtag(cfg['probe_hashtag'], credentials, request_code, lambda msg: log(r, msg))
            if result:
                save(r, result)
        elif cfg['method'] == 'instagrapi':
            from check_direct_access import collect_hashtags

            collect_hashtags(
                cfg['hashtags'], credentials, request_code,
                lambda msg: log(r, msg), lambda row: save(r, row),
                max_posts=cfg['max_posts'], max_comments=cfg['max_comments'],
            )
        else:
            collect_in_browser(
                cfg, lambda row: save(r, row), lambda msg: log(r, msg),
                known_posts=previously_collected_posts(project_id) if not (cfg['refresh_posts'] or cfg['post_url']) else (),
            )
        with db() as c:c.execute("UPDATE runs SET status='completed' WHERE id=?",(r,))
        if cfg['sync']:
            try:
                dest=os.environ.get('DRIVE_OUTPUT_DIR')
                if not dest:raise ValueError()
                folder=Path(dest)/'Marketing Intelligence'/(project_id or 'اجراهای مستقل')/r;folder.mkdir(parents=True,exist_ok=True)
                for ext in ['csv','xlsx']:shutil.copy2(export(r,ext),folder)
                backup=DATA/(r+'.sqlite')
                with db() as source,sqlite3.connect(backup) as target:source.backup(target)
                shutil.copy2(backup,folder)
                log(r,'فایل‌ها به پوشه Drive کپی شدند؛ ارسال ابری با برنامه Drive انجام می‌شود.')
            except Exception:log(r,'همگام‌سازی ناموفق؛ خروجی محلی موجود است.')
    except CollectionError as error:
        log(r,str(error))
        with db() as c:c.execute("UPDATE runs SET status='failed' WHERE id=?",(r,))
    except Exception:
        log(r,'جمع‌آوری ناموفق؛ ورود، دسترسی یا ساختار صفحه را بررسی کنید. نتایج جزئی محفوظ است.')
        with db() as c:c.execute("UPDATE runs SET status='failed' WHERE id=?",(r,))
    finally:
        if credentials is not None:credentials.clear()
        lock.release()
@app.get('/',response_class=HTMLResponse)
def index():return RedirectResponse('http://127.0.0.1:3000')
class DriveFileChange(BaseModel):
    path: str
    name: str | None = None


def drive_root():
    dest = os.environ.get('DRIVE_OUTPUT_DIR')
    if not dest:
        raise HTTPException(503, 'مسیر Google Drive تنظیم نشده است.')
    root = Path(dest) / 'Marketing Intelligence'
    if not Path(dest).is_dir():
        raise HTTPException(503, 'پوشه Google Drive در دسترس نیست.')
    return root


def drive_file(relative):
    root = drive_root().resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.suffix.lower() not in ('.csv', '.xlsx', '.sqlite'):
        raise HTTPException(404, 'فایل پیدا نشد.')
    return path


@app.get('/api/drive/files')
def list_drive_files():
    root = drive_root()
    if not root.exists():
        return []
    files = []
    for path in root.rglob('*'):
        if path.is_file() and not path.is_symlink() and path.suffix.lower() in ('.csv', '.xlsx', '.sqlite') and path.resolve().is_relative_to(root.resolve()):
            stat = path.stat()
            files.append({'path': path.relative_to(root).as_posix(), 'name': path.name, 'size': stat.st_size, 'modified': datetime.fromtimestamp(stat.st_mtime, ZoneInfo('Asia/Tehran')).isoformat()})
    return sorted(files, key=lambda item: item['modified'], reverse=True)


@app.patch('/api/drive/files')
def rename_drive_file(change: DriveFileChange):
    path = drive_file(change.path)
    name = (change.name or '').strip()
    if not name or name in ('.', '..') or re.search(r'[<>:"/\\|?*\x00-\x1f]', name) or name.endswith(('.', ' ')) or Path(name).suffix.lower() != path.suffix.lower() or re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)', name, re.I):
        raise HTTPException(400, 'نام معتبر با پسوند اصلی فایل وارد کنید.')
    target = path.with_name(name)
    if target != path and target.exists():
        raise HTTPException(409, 'فایلی با این نام وجود دارد.')
    try:
        path.rename(target)
    except OSError:
        raise HTTPException(400, 'تغییر نام فایل ممکن نشد.')
    return {'ok': True}


@app.delete('/api/drive/files')
def delete_drive_file(change: DriveFileChange):
    path = drive_file(change.path)
    try:
        path.unlink()
    except OSError:
        raise HTTPException(400, 'حذف فایل ممکن نشد.')
    return {'ok': True}

@app.get('/api/runs')
def runs():
    with db() as c:
        items=[dict(x) for x in c.execute('SELECT * FROM runs ORDER BY rowid DESC')]
    for item in items:
        records=rows(item['id'])
        item['posts_count']=sum(row.get('new_post', True) for row in records)
        item['comments_count']=sum(len(x.get('comments',[])) for x in records)
    return items
@app.post('/api/runs')
def start(cfg:Config):
    return start_run(cfg)

def start_run(cfg, project_id=None):
    if not cfg.demo and cfg.method != 'browser' and (not cfg.login_username.strip() or not cfg.login_password.get_secret_value()):
        raise HTTPException(400,'برای روش بدون مرورگر، نام کاربری ورود و رمز را وارد کنید')
    if not lock.acquire(False):raise HTTPException(409,'یک اجرا فعال است')
    r=uuid.uuid4().hex
    try:
        with db() as c:
            if project_id:
                saved = c.execute('SELECT config FROM projects WHERE id=?', (project_id,)).fetchone()
                if not saved:
                    raise HTTPException(404, 'پروژه پیدا نشد.')
                cfg = Config.model_validate_json(saved['config'])
            c.execute(
                'INSERT INTO runs(id,config,status,logs,project_id,started_at) VALUES (?,?,?,?,?,?)',
                (r,cfg.model_dump_json(),'running','',project_id,now()),
            )
        credentials={'username':cfg.login_username.strip(),'password':cfg.login_password.get_secret_value(),'code':cfg.verification_code.get_secret_value()}
        threading.Thread(target=worker,args=(r,cfg.model_dump(),credentials,project_id),daemon=True).start()
    except Exception:lock.release();raise
    return {'id':r}

@app.post('/api/runs/{run_id}/verification-code')
def submit_verification(run_id: str, body: VerificationCode):
    code = body.code.get_secret_value().strip()
    if len(code) not in (6, 8) or not code.isdecimal():
        raise HTTPException(400, 'کد را با ۶ یا ۸ رقم وارد کنید.')
    accept_verification(run_id, 'awaiting_code', ''.join(str(decimal(digit)) for digit in code))
    return {'accepted': True}

def accept_verification(run_id, status, value):
    with verification_ready:
        if pending_verification.get(run_id) != (status, None):
            raise HTTPException(409, 'این اجرا دیگر منتظر این مرحلهٔ ورود نیست.')
        pending_verification[run_id] = (status, value)
        verification_ready.notify_all()

@app.post('/api/runs/{run_id}/browser-login')
def start_browser_login(run_id: str):
    accept_verification(run_id, 'awaiting_security', 'open_browser')
    return {'accepted': True}

@app.get('/api/runs/{r}')
def result(r:str):
    with db() as c:
        if not c.execute('SELECT 1 FROM runs WHERE id=?',(r,)).fetchone():
            raise HTTPException(404,'اجرا پیدا نشد')
    return rows(r)
@app.delete('/api/runs/{r}/results')
def clear_results(r:str):
    if not re.fullmatch('[a-f0-9]{32}',r):raise HTTPException(404)
    if not lock.acquire(False):raise HTTPException(409,'تا پایان اجرای فعال صبر کنید')
    try:
        with db() as c:
            if not c.execute('SELECT 1 FROM runs WHERE id=?',(r,)).fetchone():
                raise HTTPException(404,'اجرا پیدا نشد')
            c.execute('DELETE FROM results WHERE run=?',(r,))
            c.execute('DELETE FROM runs WHERE id=?',(r,))
        for ext in ('csv','xlsx'):
            (DATA/(r+'.'+ext)).unlink(missing_ok=True)
        return {'cleared':True}
    finally:lock.release()
@app.get('/api/runs/{r}/export/{ext}')
def download(r:str,ext:str):
    if ext not in ('csv','xlsx') or not re.fullmatch('[a-f0-9]{32}',r):raise HTTPException(404)
    with db() as c:
        run = c.execute('SELECT config FROM runs WHERE id=?', (r,)).fetchone()
    if not run:
        raise HTTPException(404, 'اجرا پیدا نشد')
    records = rows(r)
    path = export_records(records, DATA / f'{r}.{ext}', ext)
    return FileResponse(path, filename=export_filename(json.loads(run['config']), records, ext))

def get_project(project_id):
    with db() as c:
        row = c.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'پروژه پیدا نشد.')
    return dict(row)


@app.get('/api/projects')
def list_projects():
    with db() as c:
        return [dict(row) for row in c.execute("""
            SELECT projects.*,
                   COALESCE(stats.posts_count, 0) AS posts_count,
                   COALESCE(stats.comments_count, 0) AS comments_count
            FROM projects
            LEFT JOIN (
                SELECT project_id, COUNT(*) AS posts_count,
                       SUM(json_array_length(payload, '$.comments')) AS comments_count
                FROM project_posts GROUP BY project_id
            ) AS stats ON stats.project_id = projects.id
            ORDER BY projects.updated_at DESC
        """)]


def project_config(cfg):
    if cfg.method != 'browser' or cfg.post_url or cfg.demo:
        raise HTTPException(422, 'برای پروژه، روش مرورگر و دست‌کم یک پیج یا تگ وارد کنید.')
    return cfg.model_dump_json()


@app.post('/api/projects')
def create_project(cfg: Config):
    raw = project_config(cfg)
    project_id, stamp = uuid.uuid4().hex, now()
    with db() as c:
        c.execute('INSERT INTO projects VALUES (?,?,?,?)', (project_id, raw, stamp, stamp))
    return get_project(project_id)


@app.put('/api/projects/{project_id}')
def edit_project(project_id: str, cfg: Config):
    raw = project_config(cfg)
    with db() as c:
        updated = c.execute('UPDATE projects SET config=?,updated_at=? WHERE id=?', (raw, now(), project_id))
        if not updated.rowcount:
            raise HTTPException(404, 'پروژه پیدا نشد.')
    return get_project(project_id)


@app.post('/api/projects/{project_id}/runs')
def run_project(project_id: str):
    project = get_project(project_id)
    return start_run(Config.model_validate_json(project['config']), project_id)


@app.get('/api/projects/{project_id}/results')
def get_project_results(project_id: str):
    get_project(project_id)
    return project_rows(project_id)


@app.get('/api/projects/{project_id}/analytics')
def get_project_analytics(project_id: str):
    get_project(project_id)
    return project_analytics(project_rows(project_id))


@app.get('/api/projects/{project_id}/export/{ext}')
def download_project(project_id: str, ext: str):
    if ext not in ('csv', 'xlsx') or not re.fullmatch('[a-f0-9]{32}', project_id):
        raise HTTPException(404)
    project = get_project(project_id)
    records = project_rows(project_id)
    path = export_records(records, DATA / f'project-{project_id}.{ext}', ext)
    return FileResponse(path, filename=export_filename(json.loads(project['config']), records, ext))


@app.delete('/api/projects/{project_id}')
def delete_project(project_id: str):
    if not re.fullmatch('[a-f0-9]{32}', project_id):
        raise HTTPException(404)
    if not lock.acquire(False):
        raise HTTPException(409, 'تا پایان اجرای فعال صبر کنید.')
    try:
        get_project(project_id)
        with db() as c:
            run_ids = [row[0] for row in c.execute('SELECT id FROM runs WHERE project_id=?', (project_id,))]
            c.execute('DELETE FROM results WHERE run IN (SELECT id FROM runs WHERE project_id=?)', (project_id,))
            c.execute('DELETE FROM runs WHERE project_id=?', (project_id,))
            c.execute('DELETE FROM project_posts WHERE project_id=?', (project_id,))
            c.execute('DELETE FROM projects WHERE id=?', (project_id,))
        for name in [*run_ids, f'project-{project_id}']:
            if re.fullmatch(r'(?:project-)?[a-f0-9]{32}', name):
                for ext in ('csv', 'xlsx'):
                    (DATA / f'{name}.{ext}').unlink(missing_ok=True)
        return {'cleared': True}
    finally:
        lock.release()
