'use client';
import {useCallback,useEffect,useMemo,useState} from 'react';
import {Alert,Avatar,Box,Button,Card,Chip,CircularProgress,Container,Dialog,DialogActions,DialogContent,DialogTitle,Divider,FormControlLabel,IconButton,InputAdornment,LinearProgress,MenuItem,Paper,Stack,Step,StepLabel,Stepper,Switch,Tab,Tabs,Table,TableBody,TableCell,TableContainer,TableHead,TablePagination,TableRow,TextField,Tooltip,Typography} from '@mui/material';
import {Add,Close,DashboardOutlined,DeleteOutlined,DownloadOutlined,ForumOutlined,Instagram,LayersOutlined,PlayArrow,Refresh,Search,Tag,TravelExplore} from '@mui/icons-material';
import {ChipInput} from './chip-input';
type CollectionMethod = 'direct' | 'browser' | 'instagrapi_probe' | 'instagrapi';
type Config = {
  companies?: string[];
  title?: string;
  target?: string;
  profiles?: string[];
  hashtags?: string[];
  probe_hashtag?: string | null;
  post_url?: string | null;
  max_posts?: number;
  max_comments?: number;
  max_likers?: number;
  likers?: boolean;
  sync?: boolean;
  refresh_posts?: boolean;
  background?: boolean;
  method?: CollectionMethod;
};
type Project = {id: string; config: string; created_at: string; updated_at: string};
type Run={id:string,project_id?:string|null,started_at?:string|null,config:string,status:string,logs:string,posts_count:number,comments_count:number};
type Comment={username:string,text:string,time?:string,likes?:number};
type Post={post_url:string,shortcode?:string,published_at?:string|null,scraped_at?:string|null,caption?:string,owner?:string,source?:string,source_type?:string,total_likes?:string|number,comments:Comment[],likers:string[]};
const labels:Record<string,string>={running:'در حال جمع‌آوری',awaiting_code:'منتظر کد تأیید',awaiting_security:'منتظر تأیید امنیتی',completed:'تکمیل‌شده',failed:'نیاز به بررسی',interrupted:'قطع‌شده'};
const numbers=(n:number)=>n.toLocaleString('fa-IR');
const configOf=(r:Run | Project):Config=>JSON.parse(r.config);
function dateLabel(value?: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('fa-IR', {timeZone: 'Asia/Tehran'});
}
async function api<T>(url:string,options?:RequestInit):Promise<T>{const response=await fetch(url,{cache:'no-store',...options});if(!response.ok){let message='ارتباط با سرور برقرار نشد';try{const error=await response.json();message=typeof error.detail==='string'?error.detail:'اطلاعات فرم معتبر نیست'}catch{}throw new Error(message)}return response.json()}
function VerificationPrompt({runId, onAccepted}: {runId: string; onAccepted: () => Promise<void>}) {
  const [code, setCode] = useState('');
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');

  async function submit() {
    setSending(true);
    setError('');
    try {
      await api('/api/runs/' + runId + '/verification-code', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({code}),
      });
      setCode('');
      setSent(true);
      await onAccepted();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setSending(false);
    }
  }

  return (
    <Stack
      component="form"
      spacing={1.5}
      sx={{mb: 2, p: 2, border: '1px solid', borderColor: 'divider', borderRadius: 2}}
      onSubmit={event => {
        event.preventDefault();
        if (!sending && !sent && code.trim()) void submit();
      }}
    >
      <Alert severity="info">
        {sent ? 'کد ارسال شد و اینستاگرام در حال بررسی آن است.' : 'اینستاگرام کد تأیید خواست. کد را وارد کنید تا همین اجرا ادامه پیدا کند.'}
      </Alert>
      {error && <Alert severity="error">{error}</Alert>}
      {!sent && (
        <Stack direction={{xs: 'column', sm: 'row'}} spacing={1}>
          <TextField
            autoFocus
            label="کد تأیید"
            type="password"
            value={code}
            disabled={sending}
            onChange={event => setCode(event.target.value)}
            slotProps={{htmlInput: {dir: 'ltr', inputMode: 'numeric', autoComplete: 'one-time-code', maxLength: 8}}}
          />
          <Button type="submit" variant="contained" disabled={sending || !code.trim()} sx={{whiteSpace: 'nowrap'}}>
            ارسال کد و ادامه
          </Button>
        </Stack>
      )}
    </Stack>
  );
}

function BrowserLoginPrompt({runId, onAccepted}: {runId: string; onAccepted: () => Promise<void>}) {
  const [opening, setOpening] = useState(false);
  const [error, setError] = useState('');

  async function openBrowser() {
    setOpening(true);
    setError('');
    try {
      await api('/api/runs/' + runId + '/browser-login', {method: 'POST'});
      await onAccepted();
    } catch (error) {
      setError((error as Error).message);
      setOpening(false);
    }
  }

  return (
    <Stack spacing={1.5} sx={{mb: 2, alignItems: 'flex-start'}}>
      <Alert severity="warning">
        تأیید ورود را در پنجرهٔ اینستاگرام کامل کنید. بعد از تأیید، دریافت مستقیم ادامه پیدا می‌کند.
      </Alert>
      {error && <Alert severity="error">{error}</Alert>}
      <Button variant="contained" disabled={opening} onClick={() => void openBrowser()}>
        {opening ? 'در حال باز کردن مرورگر…' : 'تأیید ورود در مرورگر'}
      </Button>
    </Stack>
  );
}

export default function Home(){
 const [runs,setRuns]=useState<Run[]>([]),[loading,setLoading]=useState(true),[error,setError]=useState(''),[notice,setNotice]=useState(''),[nav,setNav]=useState(0);
 const [projects, setProjects] = useState<Project[]>([]);
 const [projectId, setProjectId] = useState<string | null>(null);
 const [editingProject, setEditingProject] = useState<string | null>(null);
 const [projectToDelete, setProjectToDelete] = useState<Project | null>(null);
 const [showProjectData, setShowProjectData] = useState(false);
 const currentProject = projects.find(project => project.id === projectId);
 const [testingPost, setTestingPost] = useState(false);
 const [testPostUrl, setTestPostUrl] = useState('');
 const [testCommentLimit, setTestCommentLimit] = useState(20);
 const [creating,setCreating]=useState(false),[step,setStep]=useState(0),[busy,setBusy]=useState(false),[formError,setFormError]=useState('');
 const [title,setTitle]=useState('');
 const [companies,setCompanies]=useState<string[]>([]),[hashtags,setHashtags]=useState<string[]>([]);
 const [tagDraft, setTagDraft] = useState('');
 const [background, setBackground] = useState(false);
 const [savedProfiles, setSavedProfiles] = useState<string[]>([]);
 const [profileDraft, setProfileDraft] = useState('');
 const [refreshPosts, setRefreshPosts] = useState(false);
 const [likerLimit, setLikerLimit] = useState(100);
 const [postLimit,setPostLimit]=useState(8),[commentLimit,setCommentLimit]=useState(100),[likers,setLikers]=useState(false),[sync,setSync]=useState(false);
 const [selected,setSelected]=useState<string|null>(null),[posts,setPosts]=useState<Post[]>([]),[resultBusy,setResultBusy]=useState(false),[tab,setTab]=useState(0),[query,setQuery]=useState(''),[page,setPage]=useState(0),[deleting,setDeleting]=useState<Run|null>(null);
 const refresh=useCallback(async()=>{try{const [history, saved] = await Promise.all([api<Run[]>('/api/runs'), api<Project[]>('/api/projects')]);setRuns(history);setProjects(saved);setError('')}catch(e){setError((e as Error).message)}finally{setLoading(false)}},[]);
 useEffect(()=>{void refresh();const timer=setInterval(()=>{if(!document.hidden)void refresh()},4000);return()=>clearInterval(timer)},[refresh]);
 const selectedRun=runs.find(r=>r.id===selected);
 const resultUrl = showProjectData && projectId
   ? '/api/projects/' + projectId + '/results'
   : selected ? '/api/runs/' + selected : null;
 const exportUrl = showProjectData
   ? '/api/projects/' + projectId + '/export/'
   : '/api/runs/' + selected + '/export/';
 const visibleRuns = projectId ? runs.filter(run => run.project_id === projectId) : runs.filter(run => !run.project_id);
 useEffect(()=>{if(!resultUrl)return;let alive=true;async function load(){try{const data=await api<Post[]>(resultUrl!);if(alive)setPosts(data)}catch(e){if(alive)setError((e as Error).message)}finally{if(alive)setResultBusy(false)}}setResultBusy(true);setPosts([]);void load();const timer=setInterval(()=>{if(!document.hidden)void load()},4000);return()=>{alive=false;clearInterval(timer)}},[resultUrl]);
 const totalPosts=runs.reduce((n,r)=>n+r.posts_count,0),totalComments=runs.reduce((n,r)=>n+r.comments_count,0),active=runs.some(r => ['running', 'awaiting_code', 'awaiting_security'].includes(r.status));
 function readChips(items: string[], draft: string, kind: 'tag' | 'profile') {
   const isTag = kind === 'tag';
   const additions = draft.split(/[,،\n]+/).map(item => item.trim()).filter(Boolean);
   const normalized = additions.map(item => {
     if (isTag) return item.replace(/^#+/, '');
     if (kind === 'profile') return item.replace(/^@/, '').toLowerCase();
     return item;
   });
   if (kind === 'profile' && normalized.some(item => !/^[A-Za-z0-9_.]{1,30}$/.test(item) || item === '.' || item === '..')) {
     throw new Error('نام کاربری پیج را بدون لینک وارد کنید.');
   }
   if (isTag && normalized.some(item => !/^[\p{L}\p{N}_\u200c]{1,100}$/u.test(item))) {
     throw new Error('تگ باید از حرف، عدد یا زیرخط تشکیل شود. مثلاً مراقبت_پوست');
   }
   const result = [...new Set([...items, ...normalized])];
   if (result.length > 20) throw new Error('برای هر فهرست حداکثر ۲۰ مورد وارد کنید.');
   return result;
 }
 function addChip(kind: 'tag' | 'profile') {
   setFormError('');
   try {
     if (kind === 'profile') {
       setSavedProfiles(readChips(savedProfiles, profileDraft, kind));
       setProfileDraft('');
     } else {
       setHashtags(readChips(hashtags, tagDraft, kind));
       setTagDraft('');
     }
   } catch (error) {
     setFormError((error as Error).message);
   }
 }
 function openProject(run?: Run | Project, methodOverride?: Config['method']) {
   const config = run ? configOf(run) : {};
   if (config.post_url) {
     openPostTest(config);
     return;
   }
   setEditingProject(run && 'updated_at' in run ? run.id : null);
   setTitle(config.title ?? config.target ?? '');
   setCompanies(config.companies ?? []);
   setHashtags(config.hashtags ?? []);
   setSavedProfiles(config.profiles?.length ? config.profiles : config.target ? [config.target] : []);
   setPostLimit(config.max_posts ?? 8);
   setCommentLimit(config.max_comments ?? 100);
   setLikerLimit(config.max_likers ?? 100);
   setLikers(config.likers ?? false);
   setSync(config.sync ?? false);
   setRefreshPosts(config.refresh_posts ?? false);
   setBackground(config.background ?? false);
   setProfileDraft('');
   setTagDraft('');
   setFormError('');
   setStep(methodOverride ? 2 : 0);
   setCreating(true);
 }
 function closeCreate(){if(busy)return;setCreating(false);setFormError('')}
 function nextStep() {
   setFormError('');
   if (step === 1) {
     try {
       const nextTags = readChips(hashtags, tagDraft, 'tag');
       const nextProfiles = readChips(savedProfiles, profileDraft, 'profile');
       if (!title.trim() || (!nextTags.length && !nextProfiles.length)) {
         throw new Error('عنوان پروژه و دست‌کم یک پیج یا تگ وارد کنید.');
       }
       setSavedProfiles(nextProfiles);
       setProfileDraft('');
       setHashtags(nextTags);
           setTagDraft('');
     } catch (error) {
       setFormError((error as Error).message);
       return;
     }
   }
   setStep(step + 1);
 }
 async function start() {
   setBusy(true);
   setFormError('');
   try {
     const endpoint = editingProject ? '/api/projects/' + editingProject : '/api/projects';
     const project = await api<Project>(endpoint, {
       method: editingProject ? 'PUT' : 'POST',
       headers: {'Content-Type': 'application/json'},
       body: JSON.stringify({
         title, companies, hashtags, profiles: savedProfiles, method: 'browser',
         max_posts: postLimit, max_comments: commentLimit, max_likers: likerLimit,
         likers, sync, refresh_posts: refreshPosts, background,
       }),
     });
     setCreating(false);
     setProjectId(project.id);
     setNav(1);
     setNotice('تنظیمات پروژه ذخیره شد.');
     await refresh();
   } catch (error) {
     setFormError((error as Error).message);
   } finally {
     setBusy(false);
   }
 }

 async function runProject(project: Project) {
   setBusy(true);
   try {
     const run = await api<{id: string}>('/api/projects/' + project.id + '/runs', {method: 'POST'});
     setShowProjectData(false);
     setSelected(run.id);
     setTab(2);
     await refresh();
   } catch (error) {
     setError((error as Error).message);
   } finally {
     setBusy(false);
   }
 }

 async function deleteProject() {
   if (!projectToDelete) return;
   setBusy(true);
   try {
     await api('/api/projects/' + projectToDelete.id, {method: 'DELETE'});
     setProjectId(null);
     setProjectToDelete(null);
     setNotice('پروژه و داده‌های محلی آن حذف شدند.');
     await refresh();
   } catch (error) {
     setError((error as Error).message);
     setProjectToDelete(null);
   } finally {
     setBusy(false);
   }
 }

 function openPostTest(config?: Config) {
   setTestPostUrl(config?.post_url ?? '');
   setTestCommentLimit(config?.max_comments ?? 20);
   setBackground(config?.background ?? false);
   setFormError('');
   setTestingPost(true);
 }

 async function startPostTest() {
   setBusy(true);
   setFormError('');
   try {
     const run = await api<{id: string}>('/api/runs', {
       method: 'POST',
       headers: {'Content-Type': 'application/json'},
       body: JSON.stringify({
         title: 'آزمون لینک پست',
         method: 'browser',
         post_url: testPostUrl.trim(),
         max_comments: testCommentLimit,
         background,
       }),
     });
     setTestingPost(false);
     setNotice('آزمون لینک پست آغاز شد.');
     await refresh();
     setShowProjectData(false);
     setSelected(run.id);
     setQuery('');
     setPage(0);
     setTab(0);
   } catch (error) {
     setFormError((error as Error).message);
   } finally {
     setBusy(false);
   }
 }

 async function remove(){if(!deleting)return;setBusy(true);try{await api('/api/runs/'+deleting.id+'/results',{method:'DELETE'});if(selected===deleting.id)setSelected(null);setRuns(old=>old.filter(x=>x.id!==deleting.id));setDeleting(null);setNotice('اجرا و نتایج محلی آن پاک شدند');await refresh()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 const comments=useMemo(()=>posts.flatMap(p=>(p.comments||[]).map(c=>({...c,post_url:p.post_url}))),[posts]);
 const filteredPosts=posts.filter(p=>[p.caption,p.owner,p.source,p.post_url].some(x=>x?.toLowerCase().includes(query.toLowerCase())));
 const filteredComments=comments.filter(c=>(c.text+' '+c.username).toLowerCase().includes(query.toLowerCase()));
 return <Box sx={{display:'flex',minHeight:'100vh'}}>
  <Box component="aside" style={{right:0}} sx={{width:240,position:'fixed',top:0,bottom:0,bgcolor:'#102e26',color:'#fff',p:3,display:{xs:'none',md:'flex'},flexDirection:'column'}}>
   <Stack direction="row" spacing={1.5} sx={{alignItems:"center",mb:6}}><Avatar variant="rounded" sx={{bgcolor:'#cbdf91',color:'#183c2d'}}><TravelExplore/></Avatar><Box><Typography variant="h5">دیدبان</Typography><Typography variant="caption" sx={{color:'#9bb4a8'}}>فضای کار پایش بازار</Typography></Box></Stack>
   <Typography variant="caption" sx={{color:'#819c90',mb:2}}>فضای کار شما</Typography>
   {['نمای کلی','پروژه‌ها و اجراها'].map((text,i)=><Button key={text} onClick={()=>{setNav(i);setProjectId(null)}} startIcon={i===0?<DashboardOutlined/>:<LayersOutlined/>} sx={{justifyContent:'flex-start',mb:1,color:nav===i?'#e3f6b0':'#a9c0b4',bgcolor:nav===i?'#24483a':'transparent'}}>{text}</Button>)}
   <Box sx={{mt:'auto',p:2,border:'1px solid #365346',borderRadius:3}}><Typography variant="body2">داده‌های شما، روی سیستم شما</Typography><Typography variant="caption" sx={{color:'#9bb4a8',display:'block',mt:1}}>رمز ورود در پروژه و نسخه‌های پشتیبان ذخیره نمی‌شود.</Typography></Box>
  </Box>
  <Box component="main" sx={{marginInlineStart:{md:'240px'},width:{xs:'100%',md:'calc(100% - 240px)'}}}>
   <Box component="header" sx={{bgcolor:'white',borderBottom:'1px solid #e5eae6',px:{xs:2,md:5},py:2,display:'flex',alignItems:'center',justifyContent:'space-between'}}><Stack direction="row" spacing={1} sx={{alignItems:"center"}}><Typography sx={{fontWeight:700}}>پایش اینستاگرام</Typography><Chip size="small" label="محلی" variant="outlined"/></Stack><Stack direction="row" spacing={1} sx={{alignItems:"center"}}><Box sx={{width:7,height:7,borderRadius:'50%',bgcolor:error?'error.main':'success.main'}}/><Typography variant="caption">{error?'ارتباط نیاز به بررسی دارد':'فضای کار شخصی'}</Typography><Tooltip title="تازه‌سازی"><IconButton aria-label="تازه‌سازی" onClick={()=>void refresh()}><Refresh/></IconButton></Tooltip></Stack></Box>
   <Container maxWidth="xl" sx={{py:{xs:3,md:5},px:{md:5}}}>
    {error&&<Alert severity="error" sx={{mb:2}}>{error}</Alert>}{notice&&<Alert severity="success" onClose={()=>setNotice('')} sx={{mb:2}}>{notice}</Alert>}
    <Stack direction={{xs:'column',sm:'row'}} spacing={2} sx={{alignItems:{sm:'center'},justifyContent:"space-between",mb:4}}><Box><Typography variant="overline" color="primary">MARKET INTELLIGENCE</Typography><Typography variant="h4" sx={{mt:.5,mb:1}}>{nav===0?'بازار را از نزدیک ببینید.':'پروژه‌ها و اجراها'}</Typography><Typography color="text.secondary">پست‌ها و گفتگوها را از پیج‌ها و تگ‌ها جمع‌آوری کنید.</Typography></Box><Stack direction={{xs: 'column', sm: 'row'}} spacing={1}>
      <Button variant="outlined" disabled={active} onClick={() => openPostTest()}>آزمون لینک پست</Button>
      <Button variant="contained" startIcon={<Add/>} disabled={active} onClick={() => openProject()}>پروژه جدید</Button>
    </Stack></Stack>
    {currentProject ? (
      <Card sx={{p: 3, mb: 3}}>
        <Stack spacing={2}>
          <Button sx={{alignSelf: 'flex-start'}} onClick={() => setProjectId(null)}>بازگشت به پروژه‌ها</Button>
          <Typography variant="h5">{configOf(currentProject).title}</Typography>
          <Typography color="text.secondary">
            {[...(configOf(currentProject).profiles ?? []), ...(configOf(currentProject).hashtags ?? []).map(tag => '#' + tag)].join('، ')}
          </Typography>
          <Stack direction="row" sx={{gap: 1, flexWrap: 'wrap'}}>
            <Button variant="contained" disabled={active || busy} onClick={() => void runProject(currentProject)}>شروع جمع‌آوری</Button>
            <Button onClick={() => {setSelected(null);setShowProjectData(true);setTab(0);setPage(0);setQuery('');}}>داده‌های پروژه</Button>
            <Button component="a" href={'/api/projects/' + currentProject.id + '/export/csv'}>CSV</Button>
            <Button component="a" href={'/api/projects/' + currentProject.id + '/export/xlsx'}>Excel</Button>
            <Button onClick={() => openProject(currentProject)}>ویرایش پروژه</Button>
            <Button color="error" disabled={active || busy} onClick={() => setProjectToDelete(currentProject)}>حذف پروژه</Button>
          </Stack>
        </Stack>
      </Card>
    ) : (
      <Card sx={{p: 3, mb: 3}}>
        <Typography variant="h6" sx={{mb: 2}}>پروژه‌ها</Typography>
        {loading ? <CircularProgress size={24}/> : projects.length === 0 ? (
          <Typography color="text.secondary">برای شروع، یک پروژه تعریف کنید.</Typography>
        ) : (
          <Stack spacing={1}>
            {projects.map(project => (
              <Button key={project.id} variant="outlined" sx={{justifyContent: 'flex-start'}}
                onClick={() => {setProjectId(project.id);setNav(1);}}>
                {configOf(project).title}
              </Button>
            ))}
          </Stack>
        )}
      </Card>
    )}
    <Card>
      <Typography variant="h6" sx={{p: 3}}>{currentProject ? 'تاریخچهٔ پروژه' : 'آزمون‌ها و اجراهای مستقل'}</Typography>
      <Divider />
      {visibleRuns.length === 0 ? <Typography sx={{p: 3}} color="text.secondary">هنوز اجرایی ثبت نشده است.</Typography> : (
        <TableContainer>
          <Table>
            <TableHead><TableRow>
              {['اجرا', 'زمان شروع', 'وضعیت', 'پست جدید', 'کامنت جدید', 'نتیجه'].map(label => <TableCell key={label}>{label}</TableCell>)}
            </TableRow></TableHead>
            <TableBody>{visibleRuns.map(run => (
              <TableRow key={run.id} hover>
                <TableCell>{configOf(run).title ?? configOf(run).target ?? 'اجرای قبلی'}</TableCell>
                <TableCell>{dateLabel(run.started_at)}</TableCell>
                <TableCell><Chip size="small" label={labels[run.status] ?? run.status}/></TableCell>
                <TableCell>{numbers(run.posts_count)}</TableCell>
                <TableCell>{numbers(run.comments_count)}</TableCell>
                <TableCell>
                  <Button onClick={() => {
                    setShowProjectData(false);setSelected(run.id);setTab(2);setQuery('');setPage(0);
                  }}>مشاهده</Button>
                  {!currentProject && <>
                    <Button disabled={active} onClick={() => openProject(run)}>اجرای دوباره</Button>
                    <IconButton aria-label="پاک کردن اجرا و نتایج" color="error" disabled={active} onClick={() => setDeleting(run)}><DeleteOutlined /></IconButton>
                  </>}
                </TableCell>
              </TableRow>
            ))}</TableBody>
          </Table>
        </TableContainer>
      )}
    </Card>
    <Typography variant="caption" color="text.secondary" sx={{display:'block',mt:3}}>داده‌های قابل دسترسی ممکن است کامل نباشند. جمع‌آوری باید با مجوز و رعایت شرایط استفاده اینستاگرام انجام شود.</Typography>
   </Container>
  </Box>
  <Dialog open={testingPost} onClose={() => { if (!busy) setTestingPost(false); }} fullWidth maxWidth="sm" dir="rtl">
    <Box component="form" onSubmit={event => {
      event.preventDefault();
      if (!active && !busy) void startPostTest();
    }}>
      <DialogTitle>آزمون لینک پست</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{pt: 1}}>
          {formError && <Alert severity="error">{formError}</Alert>}
          <TextField
            autoFocus
            required
            type="url"
            label="لینک پست یا ریل"
            placeholder="https://www.instagram.com/p/..."
            value={testPostUrl}
            onChange={event => setTestPostUrl(event.target.value)}
            slotProps={{htmlInput: {dir: 'ltr', maxLength: 2048}}}
          />
          <TextField
            required
            type="number"
            label="حداکثر کامنت"
            value={testCommentLimit || ''}
            onChange={event => setTestCommentLimit(Number(event.target.value))}
            slotProps={{htmlInput: {min: 1, max: 5000}}}
          />
          <FormControlLabel
            control={<Switch checked={background} onChange={event => setBackground(event.target.checked)} />}
            label="اجرا در پس‌زمینه"
          />
        </Stack>
      </DialogContent>
      <DialogActions sx={{p: 3}}>
        <Button disabled={busy} onClick={() => setTestingPost(false)}>انصراف</Button>
        <Button type="submit" variant="contained" disabled={busy || active}>شروع آزمون</Button>
      </DialogActions>
    </Box>
  </Dialog>
  <Dialog open={creating} onClose={closeCreate} fullWidth maxWidth="sm" dir="rtl"><DialogTitle><Stack direction="row" sx={{alignItems:"center",justifyContent:"space-between"}}><Typography component="span" variant="h6" sx={{fontWeight:700}}>{editingProject ? 'ویرایش پروژه' : 'پروژه جدید'}</Typography><IconButton aria-label="بستن" disabled={busy} onClick={closeCreate}><Close/></IconButton></Stack></DialogTitle><DialogContent><Stepper activeStep={step} alternativeLabel sx={{my:3}}>{['روش جمع‌آوری','پیج‌ها و تگ‌ها','تنظیمات اجرا'].map(x=><Step key={x}><StepLabel>{x}</StepLabel></Step>)}</Stepper>{formError&&<Alert severity="error" sx={{mb:2}}>{formError}</Alert>}
   <Stack spacing={2.5} sx={{pt:1}}>{step===0?<>
     <TextField select label="روش جمع‌آوری" value="browser">
       <MenuItem value="browser">جمع‌آوری با مرورگر</MenuItem>
       <MenuItem value="direct" disabled>دریافت مستقیم</MenuItem>
       <MenuItem value="instagrapi" disabled>دریافت همهٔ هشتگ‌ها با instagrapi</MenuItem>
       <MenuItem value="instagrapi_probe" disabled>آزمون مستقیم با instagrapi</MenuItem>
     </TextField>
     <FormControlLabel
       control={<Switch checked={background} onChange={event => setBackground(event.target.checked)} />}
       label="اجرا در پس‌زمینه"
     />
     <Typography variant="body2" color="text.secondary">در صورت نیاز به ورود، پنجرهٔ اینستاگرام باز می‌شود.</Typography>
   </>:step===1?<><TextField label="عنوان پروژه" placeholder="مثلاً پایش برندهای مراقبت پوست" value={title} onChange={e=>setTitle(e.target.value)}/>
     <ChipInput
       label="تگ‌های جست‌وجو"
       hint="مثلاً مراقبت_پوست. برای افزودن هر تگ Enter بزنید."
       value={tagDraft}
       items={hashtags}
       prefix="#"
       onChange={setTagDraft}
       onAdd={() => addChip('tag')}
       onRemove={item => setHashtags(hashtags.filter(tag => tag !== item))}
     />
       <ChipInput
         label="پیج‌های اینستاگرام"
         hint="نام کاربری پیج شرکت را وارد کنید و Enter بزنید."
         value={profileDraft}
         items={savedProfiles}
         prefix="@"
         onChange={setProfileDraft}
         onAdd={() => addChip('profile')}
         onRemove={item => setSavedProfiles(savedProfiles.filter(profile => profile !== item))}
       />
   </>:<><TextField label="سقف پست برای هر منبع" type="number" value={postLimit} onChange={e=>setPostLimit(Number(e.target.value))} slotProps={{htmlInput:{min:1,max:100}}}/><TextField label="سقف کامنت برای هر پست" type="number" value={commentLimit} onChange={e=>setCommentLimit(Number(e.target.value))} slotProps={{htmlInput:{min:1,max:5000}}}/>
     <Box>
       <FormControlLabel
         control={<Switch checked={likers} onChange={event => setLikers(event.target.checked)} slotProps={{input: {'aria-describedby': 'likers-hint'}}} />}
         label={`دریافت لایک‌کننده‌ها (حداکثر ${numbers(likerLimit)} نفر)`}
       />
       <Typography id="likers-hint" variant="body2" color="text.secondary" sx={{paddingInlineStart: '58px'}}>
         نام حساب‌هایی را که هر پست را لایک کرده‌اند ثبت می‌کند.
       </Typography>
     </Box>
     <Box>
       <FormControlLabel
         control={<Switch checked={refreshPosts} onChange={event => setRefreshPosts(event.target.checked)} slotProps={{input: {'aria-describedby': 'refresh-posts-hint'}}} />}
         label="به‌روزرسانی پست‌های قبلاً ثبت‌شده"
       />
       <Typography id="refresh-posts-hint" variant="body2" color="text.secondary" sx={{paddingInlineStart: '58px'}}>
         پست‌های قبلی را دوباره بررسی می‌کند تا تعداد لایک‌ها به‌روز شود و کامنت‌های تازه اضافه شوند.
       </Typography>
     </Box>
     <Box>
       <FormControlLabel
         control={<Switch checked={sync} onChange={event => setSync(event.target.checked)} slotProps={{input: {'aria-describedby': 'drive-sync-hint'}}} />}
         label="کپی خروجی و بکاپ در پوشه Google Drive"
       />
       <Typography id="drive-sync-hint" variant="body2" color="text.secondary" sx={{paddingInlineStart: '58px'}}>
         پس از اجرای موفق، خروجی‌ها و بکاپ را در پوشهٔ محلیِ تنظیم‌شده برای Google Drive کپی می‌کند.
       </Typography>
     </Box>
     <Alert severity="info">{background ? 'اجرا در پس‌زمینه. ' : 'اجرا با پنجرهٔ مرورگر. '}{numbers(savedProfiles.length)} پیج و {numbers(hashtags.length)} تگ.</Alert></>}</Stack>
  </DialogContent><DialogActions sx={{p:3}}><Button disabled={busy} onClick={()=>step?setStep(step-1):closeCreate()}>{step?'مرحله قبل':'انصراف'}</Button><Button variant="contained" disabled={busy||active} startIcon={busy?<CircularProgress size={16}/>:step===2?<PlayArrow/>:undefined} onClick={()=>step===2?void start():nextStep()}>{step === 2 ? 'ذخیرهٔ پروژه' : 'ادامه'}</Button></DialogActions></Dialog>
  <Dialog open={!!selected || showProjectData} onClose={()=>{setSelected(null);setShowProjectData(false)}} fullWidth maxWidth="lg" dir="rtl"><DialogTitle><Stack direction="row" sx={{alignItems:"center",justifyContent:"space-between"}}><Typography component="span" variant="h6">{showProjectData ? 'داده‌های پروژه' : selectedRun?(configOf(selectedRun).title||configOf(selectedRun).target||'نتایج اجرا'):'نتایج اجرا'}</Typography><IconButton aria-label="بستن نتایج" onClick={()=>{setSelected(null);setShowProjectData(false)}}><Close/></IconButton></Stack></DialogTitle><DialogContent>{selectedRun?.status==='running'&&<LinearProgress sx={{mb:2}}/>}{selectedRun?.status === 'awaiting_code' && (
    <VerificationPrompt key={selectedRun.id} runId={selectedRun.id} onAccepted={refresh} />
   )}{selectedRun?.status === 'awaiting_security' && (
    <BrowserLoginPrompt key={selectedRun.id} runId={selectedRun.id} onAccepted={refresh} />
   )}{selectedRun?.status === 'failed' && (configOf(selectedRun).method ?? 'direct') === 'direct' && (
    <Alert severity="info" sx={{mb: 2}}
      action={
        <Button
          color="inherit"
          disabled={active}
          onClick={() => {
            setSelected(null);
            openProject(selectedRun, 'browser');
          }}
        >
          اجرای مجدد با مرورگر
        </Button>
      }
    >
      روش این اجرا دریافت مستقیم بود.
    </Alert>
   )}<Stack direction="row" sx={{alignItems:"center",justifyContent:"space-between",flexWrap:"wrap"}}><Tabs value={tab} onChange={(_,value)=>{setTab(value);setPage(0)}}><Tab label={`پست‌ها (${numbers(posts.length)})`}/><Tab label={`کامنت‌ها (${numbers(comments.length)})`}/>{!showProjectData && <Tab label="گزارش اجرا"/>}</Tabs><Stack direction="row" spacing={1}>{['csv','xlsx'].map(ext=><Button key={ext} component="a" href={exportUrl + ext} startIcon={<DownloadOutlined/>} size="small">{ext.toUpperCase()}</Button>)}</Stack></Stack><Divider sx={{mb:2}}/>
   {tab<2&&<TextField label="جستجو در نتایج همین اجرا" value={query} onChange={e=>{setQuery(e.target.value);setPage(0)}} sx={{mb:2}} slotProps={{input:{startAdornment:<InputAdornment position="start"><Search/></InputAdornment>}}}/>}
   {resultBusy?<Box sx={{p:5,textAlign:'center'}}><CircularProgress/></Box>:tab===2?<Box className="logs">{selectedRun?.logs||'هنوز پیامی ثبت نشده است.'}</Box>:tab===0?<Stack spacing={2}>{filteredPosts.slice(page*10,page*10+10).map(p=><Paper variant="outlined" key={p.post_url} sx={{p:2.5}}><Stack direction="row" sx={{alignItems:"center",justifyContent:"space-between"}}><Typography dir="ltr" sx={{fontWeight:700}}>{p.owner?'@'+p.owner:'پست اینستاگرام'}</Typography><Button component="a" href={p.post_url} target="_blank" rel="noopener noreferrer" size="small">باز کردن پست</Button></Stack><Typography sx={{my:2,whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{p.caption||'کپشن ثبت نشده است.'}</Typography><Typography variant="caption" color="text.secondary" sx={{display:'block', mb: 1}}>
    شناسهٔ پست {p.shortcode ?? '—'} · انتشار {dateLabel(p.published_at)} · جمع‌آوری {dateLabel(p.scraped_at)}
   </Typography><Stack direction="row" spacing={1} sx={{flexWrap:"wrap"}}><Chip size="small" label={`${numbers(p.comments?.length||0)} کامنت دریافتی`}/><Chip size="small" variant="outlined" label={`${p.total_likes??'—'} لایک`}/>{p.source&&<Chip size="small" variant="outlined" label={(p.source_type==='hashtag'?'#':'@')+p.source}/>}</Stack></Paper>)}{!filteredPosts.length&&<Alert severity="info">پستی برای نمایش وجود ندارد.</Alert>}</Stack>:<TableContainer><Table size="small"><TableHead><TableRow><TableCell>کاربر</TableCell><TableCell>متن کامنت</TableCell><TableCell>زمان انتشار</TableCell><TableCell>پست</TableCell></TableRow></TableHead><TableBody>{filteredComments.slice(page*10,page*10+10).map((c,i)=><TableRow key={i}><TableCell dir="ltr">{c.username}</TableCell><TableCell sx={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{c.text}</TableCell><TableCell>{dateLabel(c.time)}</TableCell><TableCell><Button component="a" href={c.post_url} target="_blank" rel="noopener noreferrer" size="small">مشاهده</Button></TableCell></TableRow>)}</TableBody></Table>{!filteredComments.length&&<Alert severity="info">کامنتی برای نمایش وجود ندارد.</Alert>}</TableContainer>}
   {tab<2&&<TablePagination component="div" count={tab===0?filteredPosts.length:filteredComments.length} rowsPerPage={10} rowsPerPageOptions={[10]} page={page} onPageChange={(_,value)=>setPage(value)} labelDisplayedRows={({from,to,count})=>`${numbers(from)} تا ${numbers(to)} از ${numbers(count)}`} getItemAriaLabel={type=>type==='next'?'صفحه بعد':'صفحه قبل'}/>}
  </DialogContent></Dialog>
  <Dialog open={!!projectToDelete} onClose={() => !busy && setProjectToDelete(null)} dir="rtl">
    <DialogTitle>حذف پروژه</DialogTitle>
    <DialogContent>پروژهٔ «{projectToDelete && configOf(projectToDelete).title}» همراه با تاریخچه و داده‌های محلی حذف می‌شود.</DialogContent>
    <DialogActions>
      <Button disabled={busy} onClick={() => setProjectToDelete(null)}>انصراف</Button>
      <Button disabled={busy} color="error" variant="contained" onClick={() => void deleteProject()}>حذف پروژه</Button>
    </DialogActions>
  </Dialog>
  <Dialog open={!!deleting} onClose={()=>!busy&&setDeleting(null)} dir="rtl"><DialogTitle>پاک کردن اجرا و نتایج؟</DialogTitle><DialogContent><Typography>این اجرا، تنظیمات، گزارش، نتایج و خروجی‌های محلی CSV و Excel آن حذف می‌شوند. نسخه‌های Drive و بکاپ‌ها باقی می‌مانند.</Typography></DialogContent><DialogActions><Button disabled={busy} onClick={()=>setDeleting(null)}>انصراف</Button><Button color="error" variant="contained" disabled={busy} onClick={()=>void remove()}>پاک کردن</Button></DialogActions></Dialog>
 </Box>
}

