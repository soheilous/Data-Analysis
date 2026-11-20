'use client';
import {useCallback,useEffect,useMemo,useState} from 'react';
import type {StepIconProps} from '@mui/material';
import {Alert,Avatar,Box,Button,Card,Chip,CircularProgress,Container,Dialog,DialogActions,DialogContent,DialogTitle,Divider,FormControlLabel,IconButton,InputAdornment,MenuItem,Paper,Stack,Step,StepLabel,Stepper,Switch,Tab,Tabs,Table,TableBody,TableCell,TableContainer,TableHead,TablePagination,TableRow,TextField,Tooltip,Typography,useMediaQuery} from '@mui/material';
import {Add,ArrowForward,Check,Close,DashboardOutlined,DeleteOutlined,DownloadOutlined,LayersOutlined,PlayArrow,Refresh,Search,Tag,TravelExplore} from '@mui/icons-material';
import {ChipInput} from './chip-input';
import {ProjectOverview} from './project-overview';
import {ProjectAnalytics} from './project-analytics';
import {AccountStatusCard,ActiveRunBanner,RunProgress,StatusChip,activeStatuses,blockedReason,useAccountStatus,useNow} from './run-status';
type CollectionMethod = 'direct' | 'browser' | 'instagrapi_probe' | 'instagrapi';
type CollectionScope = 'profile_tags' | 'discover';
type Config = {
  companies?: string[];
  title?: string;
  target?: string;
  profiles?: string[];
  hashtags?: string[];
  collection_scope?: CollectionScope | null;
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
// Keeps @usernames and other Latin text in the right order inside Persian sentences.
const ltr=(text:string)=>'\u2066'+text+'\u2069';
const likesLabel=(value?:string|number)=>{if(value===undefined||value===null||value==='')return '—';const n=Number(String(value).replace(/,/g,''));return Number.isFinite(n)?numbers(n):String(value)};
function PersianStepIcon({active,completed,icon}:StepIconProps){return <Box sx={{width:28,height:28,borderRadius:'50%',display:'grid',placeItems:'center',fontSize:14,fontWeight:700,color:'#fff',bgcolor:active||completed?'primary.main':'#b9c2bd'}}>{completed?<Check sx={{fontSize:18}}/>:numbers(Number(icon))}</Box>}
const numbers=(n:number)=>n.toLocaleString('fa-IR');
const configOf=(r:Run | Project):Config=>JSON.parse(r.config);
function dateLabel(value?: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('fa-IR', {timeZone: 'Asia/Tehran', dateStyle: 'medium', timeStyle: 'short'});
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

type DriveFile = {path: string; name: string; modified: string; size: number};
function DriveFiles({open, onClose}: {open: boolean; onClose: () => void}) {
  const [files, setFiles] = useState<DriveFile[]>([]);
  const [error, setError] = useState('');
  const [target, setTarget] = useState<DriveFile | null>(null);
  const [action, setAction] = useState<'rename' | 'delete'>('rename');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try { setFiles(await api<DriveFile[]>('/api/drive/files')); setError(''); }
    catch (e) { setError((e as Error).message); }
  }, []);
  useEffect(() => { if (open) void load(); }, [open, load]);
  async function save() {
    if (!target) return;
    setBusy(true); setError('');
    try {
      await api('/api/drive/files', {method: action === 'rename' ? 'PATCH' : 'DELETE', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({path: target.path, name})});
      setTarget(null); await load();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  return <Dialog open={open} onClose={onClose} fullWidth maxWidth="md" dir="rtl">
    <DialogTitle>فایل‌های دیدبان در Google Drive</DialogTitle>
    <DialogContent>
      <Typography color="text.secondary" sx={{mb: 2}}>فایل‌های پوشهٔ خروجی دیدبان، شامل نسخه‌های قبلی، در این فهرست نمایش داده می‌شوند.</Typography>
      {error && <Alert severity="error" sx={{mb: 2}}>{error}</Alert>}
      <Button onClick={() => void load()}>تازه‌سازی</Button>
      {files.length === 0 ? <Typography>فایلی در این پوشه پیدا نشد.</Typography> : <TableContainer><Table><TableHead><TableRow><TableCell>نام و پوشه</TableCell><TableCell>آخرین تغییر</TableCell><TableCell>عملیات</TableCell></TableRow></TableHead><TableBody>
        {files.map(file => <TableRow key={file.path}><TableCell><Typography>{file.name}</Typography><Typography variant="caption" sx={{overflowWrap: 'anywhere'}}>{file.path}</Typography></TableCell><TableCell>{dateLabel(file.modified)}</TableCell><TableCell><Button onClick={() => {setTarget(file); setName(file.name); setAction('rename');}}>تغییر نام</Button><Button color="error" onClick={() => {setTarget(file); setAction('delete');}}>حذف</Button></TableCell></TableRow>)}
      </TableBody></Table></TableContainer>}
    </DialogContent><DialogActions><Button onClick={onClose}>بستن</Button></DialogActions>
    <Dialog open={!!target} onClose={() => !busy && setTarget(null)} dir="rtl"><DialogTitle>{action === 'rename' ? 'تغییر نام فایل' : 'حذف فایل از Drive؟'}</DialogTitle><DialogContent>
      {action === 'rename' ? <TextField autoFocus fullWidth label="نام فایل همراه با پسوند" value={name} onChange={e => setName(e.target.value)} sx={{mt: 1}}/> : <Typography>{target?.path}</Typography>}
      {error && <Alert severity="error" sx={{mt: 2}}>{error}</Alert>}
    </DialogContent><DialogActions><Button disabled={busy} onClick={() => setTarget(null)}>انصراف</Button><Button disabled={busy} color={action === 'delete' ? 'error' : 'primary'} onClick={() => void save()}>{action === 'delete' ? 'حذف' : 'ذخیره'}</Button></DialogActions></Dialog>
  </Dialog>;
}

export default function Home(){
 const [runs,setRuns]=useState<Run[]>([]),[loading,setLoading]=useState(true),[error,setError]=useState(''),[notice,setNotice]=useState(''),[nav,setNav]=useState(0);
 const [projects, setProjects] = useState<Project[]>([]);
 const [driveOpen, setDriveOpen] = useState(false);
 const [projectId, setProjectId] = useState<string | null>(null);
 const [editingProject, setEditingProject] = useState<string | null>(null);
 const [projectToDelete, setProjectToDelete] = useState<Project | null>(null);
 const [showProjectData, setShowProjectData] = useState(false);
 const [showAnalytics, setShowAnalytics] = useState(false);
 const currentProject = projects.find(project => project.id === projectId);
 const account = useAccountStatus();
 const clock = useNow();
 const blocked = blockedReason(account, clock);
 const compact = useMediaQuery('(max-width:599.95px)');
 const [testingPost, setTestingPost] = useState(false);
 const [testPostUrl, setTestPostUrl] = useState('');
 const [testCommentLimit, setTestCommentLimit] = useState(20);
 const [creating,setCreating]=useState(false),[step,setStep]=useState(0),[busy,setBusy]=useState(false),[formError,setFormError]=useState('');
 const [title,setTitle]=useState('');
 const [collectionScope, setCollectionScope] = useState<CollectionScope>('profile_tags');
 const [companies,setCompanies]=useState<string[]>([]),[hashtags,setHashtags]=useState<string[]>([]);
 const [tagDraft, setTagDraft] = useState('');
 const [background, setBackground] = useState(false);
 const [savedProfiles, setSavedProfiles] = useState<string[]>([]);
 const [profileDraft, setProfileDraft] = useState('');
 const [refreshPosts, setRefreshPosts] = useState(false);
 const [likerLimit, setLikerLimit] = useState(50);
 const [postLimit,setPostLimit]=useState(8),[commentLimit,setCommentLimit]=useState(100),[likers,setLikers]=useState(false),[sync,setSync]=useState(false);
 const [expandedPost, setExpandedPost] = useState<string | null>(null);
 const [selected,setSelected]=useState<string|null>(null),[posts,setPosts]=useState<Post[]>([]),[resultBusy,setResultBusy]=useState(false),[tab,setTab]=useState(0),[query,setQuery]=useState(''),[page,setPage]=useState(0),[deleting,setDeleting]=useState<Run|null>(null);
 const applyAddress = useCallback(() => {
   const params = new URLSearchParams(window.location.search);
   const project = params.get('project');
   const run = params.get('run');
   setNav(params.get('page') === 'projects' || project || run ? 1 : 0);
   setProjectId(project);
   setSelected(run);
   setShowProjectData(!!project && params.get('view') === 'results' && !run);
   setShowAnalytics(!!project && params.get('view') === 'analytics' && !run);
   setDriveOpen(params.get('view') === 'drive');
   setTab(0);
   setExpandedPost(null);
   setQuery('');
   setPage(0);
 }, []);
 const navigate = useCallback((params: Record<string, string | null>) => {
   const search = new URLSearchParams();
   Object.entries(params).forEach(([key, value]) => { if (value) search.set(key, value); });
   const address = window.location.pathname + (search.size ? '?' + search.toString() : '');
   if (address !== window.location.pathname + window.location.search) window.history.pushState(null, '', address);
   applyAddress();
 }, [applyAddress]);
 useEffect(() => {
   applyAddress();
   window.addEventListener('popstate', applyAddress);
   return () => window.removeEventListener('popstate', applyAddress);
 }, [applyAddress]);
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
 const activeRun=runs.find(r => activeStatuses.has(r.status));
 const active=!!activeRun;
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
   setCollectionScope(config.collection_scope ?? (run && !config.profiles?.length && !config.target ? 'discover' : 'profile_tags'));
   setCompanies(config.companies ?? []);
   setHashtags(config.hashtags ?? []);
   setSavedProfiles(config.profiles?.length ? config.profiles : config.target ? [config.target] : []);
   setPostLimit(config.max_posts ?? 8);
   setCommentLimit(config.max_comments ?? 100);
   setLikerLimit(config.max_likers ?? 50);
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
       if (!title.trim()) throw new Error('عنوان پروژه را وارد کنید.');
       if (!nextTags.length) throw new Error('دست‌کم یک تگ وارد کنید.');
       if (collectionScope === 'profile_tags') {
         const nextProfiles = readChips(savedProfiles, profileDraft, 'profile');
         if (!nextProfiles.length) throw new Error('دست‌کم یک پیج وارد کنید.');
         setSavedProfiles(nextProfiles);
         setProfileDraft('');
       }
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
         title, companies, hashtags, method: 'browser', collection_scope: collectionScope,
         profiles: collectionScope === 'profile_tags' ? savedProfiles : [],
         max_posts: postLimit, max_comments: commentLimit, max_likers: likerLimit,
         likers, sync, refresh_posts: refreshPosts, background,
       }),
     });
     setCreating(false);
     navigate({page: 'projects', project: project.id});
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
     navigate({page: 'projects', project: project.id, run: run.id});
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
     navigate({page: 'projects'});
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
     navigate({page: 'projects', run: run.id});
     setTab(0);
   } catch (error) {
     setFormError((error as Error).message);
   } finally {
     setBusy(false);
   }
 }

 async function remove(){if(!deleting)return;setBusy(true);try{await api('/api/runs/'+deleting.id+'/results',{method:'DELETE'});if(selected===deleting.id)navigate({page:'projects',project:projectId});setRuns(old=>old.filter(x=>x.id!==deleting.id));setDeleting(null);setNotice('اجرا و نتایج محلی آن پاک شدند');await refresh()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 const postOwners = [...new Set(posts.map(post => post.owner || (post.source_type === 'profile' ? post.source : '')).filter(Boolean))];
 const resultTitle = postOwners.length ? postOwners.map(owner => ltr('@' + owner)).join('، ') : (selectedRun ? configOf(selectedRun).profiles?.map(name => ltr('@' + name)).join('، ') : '') || (showProjectData ? 'داده‌های پروژه' : 'نتایج اجرا');
 const comments=useMemo(()=>posts.flatMap(p=>(p.comments||[]).map(c=>({...c,post_url:p.post_url}))),[posts]);
 const filteredPosts=posts.filter(p=>[p.caption,p.owner,p.source,p.post_url].some(x=>x?.toLowerCase().includes(query.toLowerCase())));
 const filteredComments=comments.filter(c=>(c.text+' '+c.username).toLowerCase().includes(query.toLowerCase()));
 return <Box sx={{display:'flex',minHeight:'100vh'}}>
  <DriveFiles open={driveOpen} onClose={() => navigate({page: nav === 1 ? 'projects' : null, project: projectId})}/>
  <Box component="aside" style={{right:0}} sx={{width:240,position:'fixed',top:0,bottom:0,bgcolor:'#102e26',color:'#fff',p:3,display:{xs:'none',md:'flex'},flexDirection:'column'}}>
   <Stack direction="row" spacing={1.5} sx={{alignItems:"center",mb:6}}><Avatar variant="rounded" sx={{bgcolor:'#cbdf91',color:'#183c2d'}}><TravelExplore/></Avatar><Box><Typography variant="h5">دیدبان</Typography><Typography variant="caption" sx={{color:'#9bb4a8'}}>فضای کار پایش بازار</Typography></Box></Stack>
   <Typography variant="caption" sx={{color:'#819c90',mb:2}}>فضای کار شما</Typography>
   {['نمای کلی','پروژه‌ها و اجراها'].map((text,i)=><Button key={text} onClick={()=>navigate({page:i === 1 ? 'projects' : null})} startIcon={i===0?<DashboardOutlined/>:<LayersOutlined/>} sx={{justifyContent:'flex-start',mb:1,color:nav===i?'#e3f6b0':'#a9c0b4',bgcolor:nav===i?'#24483a':'transparent'}}>{text}</Button>)}
   <Box sx={{mt:'auto',p:2,border:'1px solid #365346',borderRadius:3}}><Typography variant="body2">داده‌های شما، روی سیستم شما</Typography><Typography variant="caption" sx={{color:'#9bb4a8',display:'block',mt:1}}>رمز ورود در پروژه و نسخه‌های پشتیبان ذخیره نمی‌شود.</Typography></Box>
  </Box>
  <Box component="main" sx={{marginInlineStart:{md:'240px'},width:{xs:'100%',md:'calc(100% - 240px)'}}}>
   <Box component="header" sx={{bgcolor:'white',borderBottom:'1px solid #e5eae6',px:{xs:2,md:5},py:2,display:'flex',alignItems:'center',justifyContent:'space-between'}}><Stack direction="row" spacing={1} sx={{alignItems:"center"}}><Typography sx={{fontWeight:700}}>پایش اینستاگرام</Typography><Chip size="small" label="محلی" variant="outlined"/></Stack><Stack direction="row" spacing={1} sx={{alignItems:"center"}}><Box sx={{width:7,height:7,borderRadius:'50%',bgcolor:error?'error.main':'success.main'}}/><Typography variant="caption">{error?'ارتباط نیاز به بررسی دارد':'فضای کار شخصی'}</Typography><Tooltip title="تازه‌سازی"><IconButton aria-label="تازه‌سازی" onClick={()=>void refresh()}><Refresh/></IconButton></Tooltip></Stack></Box>
   <Container maxWidth="xl" sx={{py:{xs:3,md:5},px:{md:5}}}>
    {error&&<Alert severity="error" sx={{mb:2}}>{error}</Alert>}{notice&&<Alert severity="success" onClose={()=>setNotice('')} sx={{mb:2}}>{notice}</Alert>}
    {activeRun&&<ActiveRunBanner run={activeRun} title={configOf(activeRun).title ?? 'اجرا'} onOpen={()=>navigate({page:'projects',project:activeRun.project_id ?? null,run:activeRun.id})}/>}
    <Stack direction={{xs:'column',sm:'row'}} spacing={2} sx={{alignItems:{sm:'center'},justifyContent:"space-between",mb:{xs:2,md:4}}}><Box sx={{minWidth:0}}>{currentProject&&<Button size="small" startIcon={<ArrowForward/>} onClick={() => navigate({page: 'projects'})} sx={{px:1,mb:.5}}>پروژه‌ها</Button>}<Typography variant="h4" sx={{mt:.5,mb:1,fontSize:{xs:'1.6rem',md:'2.125rem'},overflowWrap:'anywhere'}}>{nav===0?'نمای کلی':currentProject?configOf(currentProject).title:'پروژه‌ها و اجراها'}</Typography></Box><Stack direction="row" sx={{flexWrap:'wrap',gap:1,flexShrink:0}}>
      <Button variant="outlined" size={compact?'small':'medium'} onClick={() => navigate({page: nav === 1 ? 'projects' : null, project: projectId, view: 'drive'})}>فایل‌های Google Drive</Button>
      <Button variant="outlined" size={compact?'small':'medium'} disabled={active} onClick={() => openPostTest()}>آزمون لینک پست</Button>
      <Button variant="contained" size={compact?'small':'medium'} startIcon={<Add/>} onClick={() => openProject()}>پروژه جدید</Button>
    </Stack></Stack>
    <Tabs value={nav} onChange={(_, value) => navigate({page: value === 1 ? 'projects' : null})} sx={{display: {md: 'none'}, mb: 2}}>
      <Tab label="نمای کلی" />
      <Tab label="پروژه‌ها و اجراها" />
    </Tabs>
    {nav === 0 ? (<Stack spacing={3}>
      <AccountStatusCard status={account} />
      <ProjectOverview
        projects={projects}
        runs={runs}
        loading={loading}
        onOpen={id => navigate({page: 'projects', project: id})}
        onCreate={() => openProject()}
      />
    </Stack>) : <>
    {currentProject ? (
      <Stack spacing={3} sx={{mb: 3}}>
      <Card sx={{p: {xs: 2, sm: 3}}}>
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            {configOf(currentProject).collection_scope === 'discover' ? 'تگ‌ها در دیسکاور جست‌وجو می‌شوند.' : 'پست‌های این پیج‌ها با تگ‌های زیر بررسی می‌شوند.'}
          </Typography>
          <Stack direction="row" sx={{gap: 0.75, flexWrap: 'wrap'}}>
            {(configOf(currentProject).profiles ?? []).map(name => <Chip key={'p' + name} size="small" label={ltr('@' + name)} />)}
            {(configOf(currentProject).hashtags ?? []).map(tag => <Chip key={'t' + tag} size="small" variant="outlined" label={'#' + tag} />)}
          </Stack>
          <Stack direction="row" sx={{gap: 1, flexWrap: 'wrap'}}>
            <Button variant="contained" startIcon={<PlayArrow/>} disabled={active || busy || !!blocked} onClick={() => void runProject(currentProject)}>شروع جمع‌آوری</Button>
            <Button onClick={() => navigate({page: 'projects', project: currentProject.id, view: 'results'})}>داده‌های پروژه</Button>
            <Button variant={showAnalytics ? 'outlined' : 'text'} aria-pressed={showAnalytics}
              onClick={() => navigate({page: 'projects', project: currentProject.id, view: showAnalytics ? null : 'analytics'})}>تحلیل پروژه</Button>
            <Button component="a" href={'/api/projects/' + currentProject.id + '/export/csv'}>CSV</Button>
            <Button component="a" href={'/api/projects/' + currentProject.id + '/export/xlsx'}>Excel</Button>
            <Button onClick={() => openProject(currentProject)}>ویرایش پروژه</Button>
            <Button color="error" disabled={active || busy} onClick={() => setProjectToDelete(currentProject)}>حذف پروژه</Button>
          </Stack>
          {(blocked || active) && <Typography variant="body2" color="text.secondary">{blocked ?? 'تا پایان اجرای فعلی، جمع‌آوری تازه و حذف پروژه ممکن نیست.'}</Typography>}
        </Stack>
      </Card>
      <AccountStatusCard status={account} />
      </Stack>
    ) : (
      <Card sx={{p: 3, mb: 3}}>
        <Typography variant="h6" sx={{mb: 2}}>پروژه‌ها</Typography>
        {loading ? <CircularProgress size={24} aria-label="در حال بارگیری پروژه‌ها"/> : projects.length === 0 ? (
          <Stack spacing={1.5} sx={{alignItems: 'flex-start'}}>
            <Typography color="text.secondary">هنوز پروژه‌ای ندارید. در پروژه، پیج‌ها و تگ‌هایی را که می‌خواهید پایش کنید تعریف می‌کنید.</Typography>
            <Button variant="contained" startIcon={<Add/>} onClick={() => openProject()}>ساخت اولین پروژه</Button>
          </Stack>
        ) : (
          <Stack divider={<Divider/>} sx={{border: '1px solid', borderColor: 'divider', borderRadius: 2}}>
            {projects.map(project => {
              const config = configOf(project) as Config & {};
              const stats = project as Project & {posts_count?: number; comments_count?: number};
              const latest = runs.find(run => run.project_id === project.id);
              return (
                <Box key={project.id} component="button" type="button" onClick={() => navigate({page: 'projects', project: project.id})}
                  sx={{display: 'flex', alignItems: 'center', gap: 2, p: 2, border: 0, bgcolor: 'transparent', color: 'inherit', textAlign: 'start', cursor: 'pointer', font: 'inherit', borderRadius: 2, '&:hover': {bgcolor: 'action.hover'}, '&:focus-visible': {outline: '2px solid', outlineColor: 'primary.main'}}}>
                  <Box sx={{flex: 1, minWidth: 0}}>
                    <Typography sx={{fontWeight: 700, overflowWrap: 'anywhere'}}>{config.title}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      {numbers(config.profiles?.length ?? 0)} پیج · {numbers(config.hashtags?.length ?? 0)} تگ · {numbers(stats.posts_count ?? 0)} پست · {numbers(stats.comments_count ?? 0)} کامنت
                    </Typography>
                  </Box>
                  <StatusChip status={latest?.status} />
                </Box>
              );
            })}
          </Stack>
        )}
      </Card>
    )}
    {currentProject && showAnalytics && <Box sx={{mb: 3}}><ProjectAnalytics projectId={currentProject.id} /></Box>}
    <Card>
      <Typography variant="h6" sx={{p: 3}}>{currentProject ? 'تاریخچهٔ پروژه' : 'آزمون‌ها و اجراهای مستقل'}</Typography>
      <Divider />
      {visibleRuns.length === 0 ? <Typography sx={{p: 3}} color="text.secondary">{currentProject ? 'این پروژه هنوز اجرا نشده است. با «شروع جمع‌آوری» اولین اجرا را آغاز کنید.' : 'هنوز آزمون یا اجرای مستقلی ثبت نشده است.'}</Typography> : compact ? (
        <Stack divider={<Divider/>}>
          {visibleRuns.map(run => (
            <Stack key={run.id} spacing={1} sx={{p: 2}}>
              <Stack direction="row" sx={{justifyContent: 'space-between', alignItems: 'center', gap: 1}}>
                <Typography variant="body2" sx={{fontWeight: 700}}>{dateLabel(run.started_at)}</Typography>
                <StatusChip status={run.status}/>
              </Stack>
              {!currentProject && <Typography variant="body2" color="text.secondary">{configOf(run).title ?? configOf(run).target ?? 'اجرای قبلی'}</Typography>}
              <Typography variant="body2">{numbers(run.posts_count)} پست جدید · {numbers(run.comments_count)} کامنت جدید</Typography>
              <Stack direction="row" sx={{gap: 1}}>
                <Button size="small" variant="outlined" onClick={() => navigate({page: 'projects', project: projectId, run: run.id})}>مشاهده</Button>
                {!currentProject && <>
                  <Button size="small" disabled={active} onClick={() => openProject(run)}>اجرای دوباره</Button>
                  <IconButton size="small" aria-label="پاک کردن اجرا و نتایج" color="error" disabled={active} onClick={() => setDeleting(run)}><DeleteOutlined /></IconButton>
                </>}
              </Stack>
            </Stack>
          ))}
        </Stack>
      ) : (
        <TableContainer>
          <Table>
            <TableHead><TableRow>
              {[...(currentProject ? [] : ['اجرا']), 'زمان شروع', 'وضعیت', 'پست جدید', 'کامنت جدید', 'نتیجه'].map(label => <TableCell key={label}>{label}</TableCell>)}
            </TableRow></TableHead>
            <TableBody>{visibleRuns.map(run => (
              <TableRow key={run.id} hover>
                {!currentProject && <TableCell>{configOf(run).title ?? configOf(run).target ?? 'اجرای قبلی'}</TableCell>}
                <TableCell>{dateLabel(run.started_at)}</TableCell>
                <TableCell><StatusChip status={run.status}/></TableCell>
                <TableCell>{numbers(run.posts_count)}</TableCell>
                <TableCell>{numbers(run.comments_count)}</TableCell>
                <TableCell>
                  <Button onClick={() => {
                    navigate({page: 'projects', project: projectId, run: run.id});
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
    </>}
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
            slotProps={{htmlInput: {min: 1, max: 500}}}
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
  <Dialog open={creating} onClose={closeCreate} fullWidth maxWidth="sm" fullScreen={compact} dir="rtl"><DialogTitle><Stack direction="row" sx={{alignItems:"center",justifyContent:"space-between"}}><Typography component="span" variant="h6" sx={{fontWeight:700}}>{editingProject ? 'ویرایش پروژه' : 'پروژه جدید'}</Typography><IconButton aria-label="بستن" disabled={busy} onClick={closeCreate}><Close/></IconButton></Stack></DialogTitle><DialogContent><Stepper activeStep={step} alternativeLabel sx={{my:3}}>{['روش جمع‌آوری',collectionScope === 'discover' ? 'تگ‌ها' : 'پیج‌ها و تگ‌ها','تنظیمات اجرا'].map(x=><Step key={x}><StepLabel slots={{stepIcon: PersianStepIcon}}>{x}</StepLabel></Step>)}</Stepper>{formError&&<Alert severity="error" sx={{mb:2}}>{formError}</Alert>}
   <Stack spacing={2.5} sx={{pt:1}}>{step===0?<>
     <TextField select label="روش جمع‌آوری" value={collectionScope}
       onChange={event => setCollectionScope(event.target.value as CollectionScope)}
       helperText={collectionScope === 'profile_tags'
         ? 'در پیج‌های مشخص، پست‌هایی را ثبت می‌کند که کپشنشان دست‌کم یکی از تگ‌ها را دارد.'
         : 'هر تگ را در جست‌وجوی اینستاگرام بررسی می‌کند.'}>
       <MenuItem value="profile_tags">آیدی پیج + تگ</MenuItem>
       <MenuItem value="discover">فقط تگ از دیسکاور</MenuItem>
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
       {collectionScope === 'profile_tags' && <ChipInput
         label="پیج‌های اینستاگرام"
         hint="نام کاربری پیج شرکت را وارد کنید و Enter بزنید."
         value={profileDraft}
         items={savedProfiles}
         prefix="@"
         onChange={setProfileDraft}
         onAdd={() => addChip('profile')}
         onRemove={item => setSavedProfiles(savedProfiles.filter(profile => profile !== item))}
       />}
   </>:<><TextField label={collectionScope === 'discover' ? 'سقف پست برای هر تگ' : 'سقف بررسی پست برای هر پیج'} type="number" value={postLimit || ''} onChange={e=>setPostLimit(Number(e.target.value))} error={postLimit<1||postLimit>50} helperText="بین ۱ تا ۵۰. عدد کمتر یعنی اجرای کوتاه‌تر و کم‌خطرتر." slotProps={{htmlInput:{min:1,max:50}}}/><TextField label="سقف کامنت برای هر پست" type="number" value={commentLimit || ''} onChange={e=>setCommentLimit(Number(e.target.value))} error={commentLimit<1||commentLimit>500} helperText="بین ۱ تا ۵۰۰." slotProps={{htmlInput:{min:1,max:500}}}/>
     <Box>
       <FormControlLabel
         control={<Switch checked={likers} onChange={event => setLikers(event.target.checked)} slotProps={{input: {'aria-describedby': 'likers-hint'}}} />}
         label={`دریافت لایک‌کننده‌ها (حداکثر ${numbers(likerLimit)} نفر)`}
       />
       <Typography id="likers-hint" variant="body2" color="text.secondary" sx={{paddingInlineStart: '58px'}}>
         نام حساب‌هایی را که هر پست را لایک کرده‌اند ثبت می‌کند. این بخش پرریسک‌ترین درخواست برای حساب است؛ فقط در صورت نیاز روشن کنید.
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
     <Alert severity="info">{background ? 'اجرا در پس‌زمینه. ' : 'اجرا با پنجرهٔ مرورگر. '}{collectionScope === 'profile_tags' ? `${numbers(savedProfiles.length)} پیج و ` : 'دیسکاور، '}{numbers(hashtags.length)} تگ. حداکثر {numbers((collectionScope === 'discover' ? hashtags.length : savedProfiles.length) * postLimit)} پست در هر اجرا بررسی می‌شود.{account ? ` امروز ${numbers(Math.max(0, account.posts_limit - account.posts_used))} پست از سقف روزانهٔ حساب باقی مانده است.` : ''}</Alert></>}</Stack>
  </DialogContent><DialogActions sx={{p:3}}><Button disabled={busy} onClick={()=>step?setStep(step-1):closeCreate()}>{step?'مرحله قبل':'انصراف'}</Button><Button variant="contained" disabled={busy||(step===2&&(postLimit<1||postLimit>50||commentLimit<1||commentLimit>500))} startIcon={busy?<CircularProgress size={16}/>:undefined} onClick={()=>step===2?void start():nextStep()}>{step === 2 ? 'ذخیرهٔ پروژه' : 'ادامه'}</Button></DialogActions></Dialog>
  <Dialog open={!!selected || showProjectData} onClose={()=>navigate({page:'projects',project:projectId})} fullWidth maxWidth="lg" fullScreen={compact} dir="rtl"><DialogTitle><Stack direction="row" sx={{alignItems:"center",justifyContent:"space-between"}}><Typography component="span" variant="h6">{resultTitle}</Typography><IconButton aria-label="بستن نتایج" onClick={()=>navigate({page:'projects',project:projectId})}><Close/></IconButton></Stack></DialogTitle><DialogContent>{selectedRun&&activeStatuses.has(selectedRun.status)&&<RunProgress run={selectedRun}/>}{selectedRun?.status === 'awaiting_code' && (
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
            navigate({page: 'projects', project: projectId});
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
   {resultBusy?<Box sx={{p:5,textAlign:'center'}}><CircularProgress/></Box>:tab===2?<Box className="logs" ref={(el:HTMLDivElement|null)=>{if(el&&selectedRun&&activeStatuses.has(selectedRun.status))el.scrollTop=el.scrollHeight}}>{selectedRun?.logs||'هنوز پیامی ثبت نشده است.'}</Box> :tab===0?<Stack spacing={2}>{filteredPosts.slice(page*10,page*10+10).map(post => {
     const expanded = expandedPost === post.post_url;
     const owner = post.owner || (post.source_type === 'profile' ? post.source : '');
     return <Paper variant="outlined" key={post.post_url} sx={{p: 2.5}}>
       <Stack direction="row" sx={{alignItems: 'center', justifyContent: 'space-between', gap: 1}}>
         <Typography dir="ltr" sx={{fontWeight: 700}}>{owner ? '@' + owner : 'پست اینستاگرام'}</Typography>
         <Button component="a" href={post.post_url} target="_blank" rel="noopener noreferrer" size="small">باز کردن پست</Button>
       </Stack>
       <Box component="button" type="button" aria-expanded={expanded} onClick={() => setExpandedPost(expanded ? null : post.post_url)} sx={{display: 'block', width: '100%', textAlign: 'start', border: 0, p: 0, bgcolor: 'transparent', color: 'inherit', cursor: 'pointer'}}>
         <Typography sx={{my: 2, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>{post.caption || 'متن پست ثبت نشده است.'}</Typography>
         <Typography variant="caption" color="text.secondary" sx={{display: 'block', mb: 1}}>شناسهٔ پست <bdi>{post.shortcode ?? '—'}</bdi> · انتشار {dateLabel(post.published_at)} · جمع‌آوری {dateLabel(post.scraped_at)}</Typography>
         <Stack direction="row" spacing={1} sx={{flexWrap: 'wrap', gap: 1}}>
           <Chip size="small" label={`${numbers(post.comments?.length || 0)} کامنت دریافتی · ${expanded ? 'بستن' : 'نمایش کامنت‌ها'}`}/>
           <Chip size="small" variant="outlined" label={`${likesLabel(post.total_likes)} لایک`}/>
           {post.source && <Chip size="small" variant="outlined" label={post.source_type === 'hashtag' ? '#' + post.source : ltr('@' + post.source)}/>}
         </Stack>
       </Box>
       {expanded && <Box sx={{mt: 2}}><Divider sx={{mb: 2}}/>
         {!post.comments?.length ? <Typography color="text.secondary">کامنتی برای این پست ثبت نشده است.</Typography> : <Stack spacing={1.5}>{post.comments.map((comment, index) => <Box key={index} sx={{p: 1.5, bgcolor: 'action.hover', borderRadius: 1}}>
           <Typography sx={{fontWeight: 700}} dir="ltr">@{comment.username}</Typography>
           <Typography sx={{whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>{comment.text}</Typography>
           {comment.time && <Typography variant="caption" color="text.secondary">{dateLabel(comment.time)}</Typography>}
         </Box>)}</Stack>}
       </Box>}
     </Paper>;
   })}{!filteredPosts.length&&<Alert severity="info">{query ? 'پستی با این عبارت پیدا نشد.' : selectedRun && activeStatuses.has(selectedRun.status) ? 'هنوز پستی ذخیره نشده است. پست‌ها همزمان با جمع‌آوری اینجا اضافه می‌شوند.' : 'پستی برای نمایش وجود ندارد.'}</Alert>}</Stack>:<TableContainer><Table size="small"><TableHead><TableRow><TableCell>کاربر</TableCell><TableCell>متن کامنت</TableCell><TableCell>زمان انتشار</TableCell><TableCell>پست</TableCell></TableRow></TableHead><TableBody>{filteredComments.slice(page*10,page*10+10).map((c,i)=><TableRow key={i}><TableCell dir="ltr">{c.username}</TableCell><TableCell sx={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{c.text}</TableCell><TableCell>{dateLabel(c.time)}</TableCell><TableCell><Button component="a" href={c.post_url} target="_blank" rel="noopener noreferrer" size="small">مشاهده</Button></TableCell></TableRow>)}</TableBody></Table>{!filteredComments.length&&<Alert severity="info">کامنتی برای نمایش وجود ندارد.</Alert>}</TableContainer>}
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

