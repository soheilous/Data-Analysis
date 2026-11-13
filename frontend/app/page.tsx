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
  method?: CollectionMethod;
};
type Run={id:string,config:string,status:string,logs:string,posts_count:number,comments_count:number};
type Comment={username:string,text:string,time?:string,likes?:number};
type Post={post_url:string,caption?:string,owner?:string,source?:string,source_type?:string,total_likes?:string|number,comments:Comment[],likers:string[]};
const labels:Record<string,string>={running:'در حال جمع‌آوری',awaiting_code:'منتظر کد تأیید',awaiting_security:'منتظر تأیید امنیتی',completed:'تکمیل‌شده',failed:'نیاز به بررسی',interrupted:'قطع‌شده'};
const numbers=(n:number)=>n.toLocaleString('fa-IR');
const configOf=(r:Run):Config=>JSON.parse(r.config);
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
 const [testingPost, setTestingPost] = useState(false);
 const [testPostUrl, setTestPostUrl] = useState('');
 const [testCommentLimit, setTestCommentLimit] = useState(20);
 const [creating,setCreating]=useState(false),[step,setStep]=useState(0),[busy,setBusy]=useState(false),[formError,setFormError]=useState('');
 const [title,setTitle]=useState(''),[username,setUsername]=useState(''),[password,setPassword]=useState('');
 const [companies,setCompanies]=useState<string[]>([]),[hashtags,setHashtags]=useState<string[]>([]);
 const [companyDraft,setCompanyDraft]=useState(''),[tagDraft,setTagDraft]=useState('');
 const [method, setMethod] = useState<CollectionMethod>('direct');
 const hashtagOnly = method === 'instagrapi' || method === 'instagrapi_probe';
 const [probeTag, setProbeTag] = useState('');
 const selectedProbeTag = hashtags.length === 1 ? hashtags[0] : hashtags.includes(probeTag) ? probeTag : '';
 const [editing, setEditing] = useState(false);
 const [savedProfiles, setSavedProfiles] = useState<string[]>([]);
 const [profileDraft, setProfileDraft] = useState('');
 const [refreshPosts, setRefreshPosts] = useState(false);
 const [likerLimit, setLikerLimit] = useState(100);
 const [postLimit,setPostLimit]=useState(8),[commentLimit,setCommentLimit]=useState(100),[likers,setLikers]=useState(false),[sync,setSync]=useState(false);
 const [selected,setSelected]=useState<string|null>(null),[posts,setPosts]=useState<Post[]>([]),[resultBusy,setResultBusy]=useState(false),[tab,setTab]=useState(0),[query,setQuery]=useState(''),[page,setPage]=useState(0),[deleting,setDeleting]=useState<Run|null>(null);
 const refresh=useCallback(async()=>{try{setRuns(await api<Run[]>('/api/runs'));setError('')}catch(e){setError((e as Error).message)}finally{setLoading(false)}},[]);
 useEffect(()=>{void refresh();const timer=setInterval(()=>{if(!document.hidden)void refresh()},4000);return()=>clearInterval(timer)},[refresh]);
 const selectedRun=runs.find(r=>r.id===selected);
 useEffect(()=>{if(!selected)return;let alive=true;async function load(){try{const data=await api<Post[]>('/api/runs/'+selected);if(alive)setPosts(data)}catch(e){if(alive)setError((e as Error).message)}finally{if(alive)setResultBusy(false)}}setResultBusy(true);setPosts([]);void load();const timer=setInterval(()=>{if(!document.hidden)void load()},4000);return()=>{alive=false;clearInterval(timer)}},[selected]);
 const totalPosts=runs.reduce((n,r)=>n+r.posts_count,0),totalComments=runs.reduce((n,r)=>n+r.comments_count,0),active=runs.some(r => ['running', 'awaiting_code', 'awaiting_security'].includes(r.status));
 function readChips(items: string[], draft: string, kind: 'company' | 'tag' | 'profile') {
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
   if (!isTag && normalized.some(item => Array.from(item).length > 100)) {
     throw new Error('نام هر شرکت می‌تواند حداکثر ۱۰۰ نویسه باشد');
   }
   const result = [...new Set([...items, ...normalized])];
   if (result.length > 20) throw new Error('برای هر فهرست حداکثر ۲۰ مورد وارد کنید.');
   return result;
 }
 function addChip(kind: 'company' | 'tag' | 'profile') {
   setFormError('');
   try {
     if (kind === 'company') {
       setCompanies(readChips(companies, companyDraft, kind));
       setCompanyDraft('');
     } else if (kind === 'profile') {
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
 function openProject(run?: Run, methodOverride?: Config['method']) {
   const config = run ? configOf(run) : {};
   if (config.post_url) {
     openPostTest(config);
     return;
   }
   setEditing(Boolean(run));
   setMethod(methodOverride ?? config.method ?? 'browser');
   setTitle(config.title ?? config.target ?? '');
   setCompanies(config.companies ?? []);
   setHashtags(config.hashtags ?? []);
   setProbeTag(config.probe_hashtag ?? '');
   setSavedProfiles(config.profiles?.length ? config.profiles : config.target ? [config.target] : []);
   setPostLimit(config.max_posts ?? 8);
   setCommentLimit(config.max_comments ?? 100);
   setLikerLimit(config.max_likers ?? 100);
   setLikers(config.likers ?? false);
   setSync(config.sync ?? false);
   setRefreshPosts(config.refresh_posts ?? false);
   setProfileDraft('');
   setCompanyDraft('');
   setTagDraft('');
   setPassword('');
   setFormError('');
   setStep(methodOverride ? 2 : 0);
   setCreating(true);
 }
 function closeCreate(){if(busy)return;setCreating(false);setPassword('');setFormError('')}
 function nextStep() {
   setFormError('');
   if (step === 0 && method !== 'browser' && (!username.trim() || !password)) {
     setFormError('نام کاربری و رمز حساب ورود را وارد کنید');
     return;
   }
   if (step === 1) {
     try {
       const nextCompanies = readChips(companies, companyDraft, 'company');
       const nextTags = readChips(hashtags, tagDraft, 'tag');
       const nextProfiles = hashtagOnly ? savedProfiles : readChips(savedProfiles, profileDraft, 'profile');
       if (!title.trim() || (!nextTags.length && (hashtagOnly || !nextProfiles.length))) {
         throw new Error('عنوان پروژه و دست‌کم یک پیج یا تگ وارد کنید.');
       }
       setSavedProfiles(nextProfiles);
       setProfileDraft('');
       setCompanies(nextCompanies);
       setHashtags(nextTags);
       setCompanyDraft('');
       setTagDraft('');
       if (method === 'instagrapi_probe' && nextTags.length !== 1 && !nextTags.includes(probeTag)) {
         throw new Error('از فهرست «هشتگ آزمون» یک مورد انتخاب کنید.');
       }
     } catch (error) {
       setFormError((error as Error).message);
       return;
     }
   }
   setStep(step + 1);
 }
 async function start(){setBusy(true);setFormError('');try{const run=await api<{id:string}>('/api/runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,companies,hashtags,probe_hashtag:method === 'instagrapi_probe' ? selectedProbeTag : undefined,profiles:hashtagOnly ? [] : savedProfiles,method,login_username:method !== 'browser' ? username : '',login_password:method !== 'browser' ? password : '',max_posts:postLimit,max_comments:commentLimit,max_likers:likerLimit,likers:hashtagOnly ? false : likers,sync,refresh_posts:method === 'browser' && refreshPosts})});setPassword('');setCreating(false);setNotice('جمع‌آوری آغاز شد؛ وضعیت ورود در گزارش اجرا نمایش داده می‌شود.');await refresh();setSelected(run.id);setTab(2)}catch(e){setFormError((e as Error).message)}finally{setBusy(false)}}
 function openPostTest(config?: Config) {
   setTestPostUrl(config?.post_url ?? '');
   setTestCommentLimit(config?.max_comments ?? 20);
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
       }),
     });
     setTestingPost(false);
     setNotice('آزمون لینک پست آغاز شد.');
     await refresh();
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
   {['نمای کلی','پروژه‌ها و اجراها'].map((text,i)=><Button key={text} onClick={()=>setNav(i)} startIcon={i===0?<DashboardOutlined/>:<LayersOutlined/>} sx={{justifyContent:'flex-start',mb:1,color:nav===i?'#e3f6b0':'#a9c0b4',bgcolor:nav===i?'#24483a':'transparent'}}>{text}</Button>)}
   <Box sx={{mt:'auto',p:2,border:'1px solid #365346',borderRadius:3}}><Typography variant="body2">داده‌های شما، روی سیستم شما</Typography><Typography variant="caption" sx={{color:'#9bb4a8',display:'block',mt:1}}>رمز ورود در پروژه و نسخه‌های پشتیبان ذخیره نمی‌شود.</Typography></Box>
  </Box>
  <Box component="main" sx={{marginInlineStart:{md:'240px'},width:{xs:'100%',md:'calc(100% - 240px)'}}}>
   <Box component="header" sx={{bgcolor:'white',borderBottom:'1px solid #e5eae6',px:{xs:2,md:5},py:2,display:'flex',alignItems:'center',justifyContent:'space-between'}}><Stack direction="row" spacing={1} sx={{alignItems:"center"}}><Typography sx={{fontWeight:700}}>پایش اینستاگرام</Typography><Chip size="small" label="محلی" variant="outlined"/></Stack><Stack direction="row" spacing={1} sx={{alignItems:"center"}}><Box sx={{width:7,height:7,borderRadius:'50%',bgcolor:error?'error.main':'success.main'}}/><Typography variant="caption">{error?'ارتباط نیاز به بررسی دارد':'فضای کار شخصی'}</Typography><Tooltip title="تازه‌سازی"><IconButton aria-label="تازه‌سازی" onClick={()=>void refresh()}><Refresh/></IconButton></Tooltip></Stack></Box>
   <Container maxWidth="xl" sx={{py:{xs:3,md:5},px:{md:5}}}>
    {error&&<Alert severity="error" sx={{mb:2}}>{error}</Alert>}{notice&&<Alert severity="success" onClose={()=>setNotice('')} sx={{mb:2}}>{notice}</Alert>}
    <Stack direction={{xs:'column',sm:'row'}} spacing={2} sx={{alignItems:{sm:'center'},justifyContent:"space-between",mb:4}}><Box><Typography variant="overline" color="primary">MARKET INTELLIGENCE</Typography><Typography variant="h4" sx={{mt:.5,mb:1}}>{nav===0?'بازار را از نزدیک ببینید.':'پروژه‌ها و اجراها'}</Typography><Typography color="text.secondary">شرکت‌ها را ثبت کنید و پست‌ها و گفتگوها را با تگ‌ها پیدا کنید.</Typography></Box><Stack direction={{xs: 'column', sm: 'row'}} spacing={1}>
      <Button variant="outlined" disabled={active} onClick={() => openPostTest()}>آزمون لینک پست</Button>
      <Button variant="contained" startIcon={<Add/>} disabled={active} onClick={() => openProject()}>پروژه جدید</Button>
    </Stack></Stack>
    {nav===0&&<Box sx={{display:'grid',gridTemplateColumns:{xs:'1fr',sm:'repeat(3,1fr)'},gap:2,mb:4}}>{[{label:'پست‌های جمع‌آوری‌شده',value:totalPosts,icon:<Instagram/>},{label:'کامنت‌های دریافت‌شده',value:totalComments,icon:<ForumOutlined/>},{label:'تعداد اجراها',value:runs.length,icon:<LayersOutlined/>}].map(item=><Card key={item.label} sx={{p:3}}><Stack direction="row" sx={{justifyContent:"space-between"}}><Typography color="text.secondary" variant="body2">{item.label}</Typography><Box sx={{color:'primary.main'}}>{item.icon}</Box></Stack><Typography variant="h4" sx={{mt:2}}>{numbers(item.value)}</Typography><Typography variant="caption" color="text.secondary">از داده‌های ذخیره‌شده در این سیستم</Typography></Card>)}</Box>}
    <Card><Box sx={{p:3,display:'flex',justifyContent:'space-between',alignItems:'center'}}><Box><Typography variant="h6" sx={{fontWeight:700}}>تاریخچه جمع‌آوری</Typography><Typography variant="body2" color="text.secondary">نتایج و گزارش هر اجرا در دسترس شماست.</Typography></Box><Chip label={`${numbers(runs.length)} اجرا`} size="small"/></Box><Divider/>
    {loading?<Box sx={{p:8,textAlign:'center'}}><CircularProgress/></Box>:runs.length===0?<Box sx={{py:9,textAlign:'center',px:2}}><TravelExplore sx={{fontSize:60,color:'#9db7a6',mb:2}}/><Typography variant="h6">اولین پروژه‌تان را شروع کنید</Typography><Typography color="text.secondary" sx={{mt:1,mb:3}}>یک پیج اینستاگرام یا تگ جست‌وجو اضافه کنید.</Typography><Button variant="outlined" startIcon={<Add/>} onClick={() => openProject()}>تعریف پروژه</Button></Box>:<TableContainer><Table><TableHead><TableRow>{['پروژه / منابع','وضعیت','پست','کامنت','عملیات'].map(x=><TableCell key={x}>{x}</TableCell>)}</TableRow></TableHead><TableBody>{runs.map(r=>{const cfg=configOf(r);return <TableRow key={r.id} hover><TableCell><Typography sx={{fontWeight:700}}>{cfg.title||cfg.target||'اجرای قبلی'}</Typography><Typography variant="caption" color="text.secondary">{[cfg.post_url, ...(cfg.companies||[]),...(cfg.profiles||[cfg.target||'']),...(cfg.hashtags||[]).map(x=>'#'+x)].filter(Boolean).join('، ')}</Typography></TableCell><TableCell><Chip size="small" label={labels[r.status]||r.status} color={r.status==='completed'?'success':r.status==='running'?'primary':r.status==='failed'?'error':'default'} variant="outlined"/></TableCell><TableCell>{numbers(r.posts_count)}</TableCell><TableCell>{numbers(r.comments_count)}</TableCell><TableCell><Stack direction="row" spacing={.5}><Button size="small" onClick={()=>{setSelected(r.id);setTab(r.status.startsWith('awaiting_') ? 2 : 0);setQuery('');setPage(0)}}>{r.status === 'awaiting_code' ? 'وارد کردن کد' : r.status === 'awaiting_security' ? 'تأیید امنیتی' : 'مشاهده'}</Button><Button size="small" disabled={active} onClick={() => openProject(r)}>ویرایش و اجرای مجدد</Button><Tooltip title="پاک کردن اجرا و نتایج"><span><IconButton aria-label="پاک کردن اجرا و نتایج" size="small" color="error" disabled={active} onClick={()=>setDeleting(r)}><DeleteOutlined/></IconButton></span></Tooltip></Stack></TableCell></TableRow>})}</TableBody></Table></TableContainer>}</Card>
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
        </Stack>
      </DialogContent>
      <DialogActions sx={{p: 3}}>
        <Button disabled={busy} onClick={() => setTestingPost(false)}>انصراف</Button>
        <Button type="submit" variant="contained" disabled={busy || active}>شروع آزمون</Button>
      </DialogActions>
    </Box>
  </Dialog>
  <Dialog open={creating} onClose={closeCreate} fullWidth maxWidth="sm" dir="rtl"><DialogTitle><Stack direction="row" sx={{alignItems:"center",justifyContent:"space-between"}}><Typography component="span" variant="h6" sx={{fontWeight:700}}>{editing ? 'ویرایش و اجرای مجدد' : 'پروژه جدید'}</Typography><IconButton aria-label="بستن" disabled={busy} onClick={closeCreate}><Close/></IconButton></Stack></DialogTitle><DialogContent><Stepper activeStep={step} alternativeLabel sx={{my:3}}>{['روش جمع‌آوری','شرکت‌ها و تگ‌ها','تنظیمات اجرا'].map(x=><Step key={x}><StepLabel>{x}</StepLabel></Step>)}</Stepper>{formError&&<Alert severity="error" sx={{mb:2}}>{formError}</Alert>}
   <Stack spacing={2.5} sx={{pt:1}}>{step===0?<>
     <TextField
       select
       label="روش جمع‌آوری"
       value={method}
       onChange={event => {
         setMethod(event.target.value as CollectionMethod);
         setPassword('');
         setFormError('');
       }}
     >
       <MenuItem value="direct">دریافت مستقیم</MenuItem>
       <MenuItem value="instagrapi">دریافت همهٔ هشتگ‌ها با instagrapi</MenuItem>
       <MenuItem value="instagrapi_probe">آزمون مستقیم با instagrapi</MenuItem>
       <MenuItem value="browser">جمع‌آوری با مرورگر</MenuItem>
     </TextField>
     {method === 'browser' ? (
       <Alert severity="info">بار اول در پنجرهٔ اینستاگرام وارد شوید. دیدبان نشست محلی را برای اجراهای بعد استفاده می‌کند و پست‌ها را از همان مرورگر می‌خواند.</Alert>
     ) : (
       <>
         {method === 'instagrapi_probe' && <Alert severity="info">یک هشتگ را آزمایش کنید. در صورت وجود نتیجه، حداکثر یک پست و یک کامنت ثبت می‌شود.</Alert>}
         <TextField label="نام کاربری حساب ورود" value={username} onChange={e=>setUsername(e.target.value)} slotProps={{htmlInput:{dir:'ltr',autoComplete:'off'}}}/>
         <TextField label="رمز ورود" type="password" value={password} onChange={e=>setPassword(e.target.value)} slotProps={{htmlInput:{dir:'ltr',autoComplete:'new-password'}}}/>
       </>
     )}
   </>:step===1?<><TextField label="عنوان پروژه" placeholder="مثلاً پایش برندهای مراقبت پوست" value={title} onChange={e=>setTitle(e.target.value)}/>
     <ChipInput
       label="نام شرکت‌ها"
       hint="نام کامل شرکت را بنویسید و Enter بزنید."
       value={companyDraft}
       items={companies}
       onChange={setCompanyDraft}
       onAdd={() => addChip('company')}
       onRemove={item => setCompanies(companies.filter(company => company !== item))}
     />
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
     {method === 'instagrapi_probe' && hashtags.length > 1 && (
       <TextField
         select
         label="هشتگ آزمون"
         value={selectedProbeTag}
         onChange={event => {
           setProbeTag(event.target.value);
           setFormError('');
         }}
         helperText="یکی از تگ‌های پروژه را برای این آزمون انتخاب کنید."
       >
         {hashtags.map(tag => <MenuItem key={tag} value={tag}>#{tag}</MenuItem>)}
       </TextField>
     )}
     {!hashtagOnly && (
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
     )}
   </>:method === 'instagrapi_probe' ? (
     <Alert severity="info">آزمون مستقیم برای #{selectedProbeTag} انجام می‌شود. نتیجهٔ آزمون را در گزارش اجرا ببینید.</Alert>
   ) : <><TextField label="سقف پست برای هر منبع" type="number" value={postLimit} onChange={e=>setPostLimit(Number(e.target.value))} slotProps={{htmlInput:{min:1,max:100}}}/><TextField label="سقف کامنت برای هر پست" type="number" value={commentLimit} onChange={e=>setCommentLimit(Number(e.target.value))} slotProps={{htmlInput:{min:1,max:5000}}}/>{!hashtagOnly && <FormControlLabel control={<Switch checked={likers} onChange={e=>setLikers(e.target.checked)}/>} label={`دریافت لایک‌کننده‌ها (حداکثر ${numbers(likerLimit)} نفر)`}/>}{method === 'browser' && (
     <FormControlLabel
       control={<Switch checked={refreshPosts} onChange={event => setRefreshPosts(event.target.checked)} />}
       label="به‌روزرسانی پست‌های قبلاً ثبت‌شده"
     />
   )}<FormControlLabel control={<Switch checked={sync} onChange={e=>setSync(e.target.checked)}/>} label="کپی خروجی و بکاپ در پوشه Google Drive"/><Alert severity="info">{method === 'browser' ? 'روش اجرا: جمع‌آوری با مرورگر. ' : method === 'instagrapi' ? 'همهٔ هشتگ‌ها به‌ترتیب بررسی می‌شوند. ' : ''}{numbers(companies.length)} شرکت و {numbers(hashtags.length)} تگ جست‌وجو؛ پست‌های تکراری در همین اجرا یک‌بار ذخیره می‌شوند. پوشه Drive باید روی سرور تنظیم شده باشد.</Alert></>}</Stack>
  </DialogContent><DialogActions sx={{p:3}}><Button disabled={busy} onClick={()=>step?setStep(step-1):closeCreate()}>{step?'مرحله قبل':'انصراف'}</Button><Button variant="contained" disabled={busy||active} startIcon={busy?<CircularProgress size={16}/>:step===2?<PlayArrow/>:undefined} onClick={()=>step===2?void start():nextStep()}>{step === 2 ? (method === 'instagrapi_probe' ? 'شروع آزمون' : editing ? 'اجرای مجدد' : 'شروع جمع‌آوری') : 'ادامه'}</Button></DialogActions></Dialog>
  <Dialog open={!!selected} onClose={()=>setSelected(null)} fullWidth maxWidth="lg" dir="rtl"><DialogTitle><Stack direction="row" sx={{alignItems:"center",justifyContent:"space-between"}}><Typography component="span" variant="h6">{selectedRun?(configOf(selectedRun).title||configOf(selectedRun).target||'نتایج اجرا'):'نتایج اجرا'}</Typography><IconButton aria-label="بستن نتایج" onClick={()=>setSelected(null)}><Close/></IconButton></Stack></DialogTitle><DialogContent>{selectedRun?.status==='running'&&<LinearProgress sx={{mb:2}}/>}{selectedRun?.status === 'awaiting_code' && (
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
   )}<Stack direction="row" sx={{alignItems:"center",justifyContent:"space-between",flexWrap:"wrap"}}><Tabs value={tab} onChange={(_,value)=>{setTab(value);setPage(0)}}><Tab label={`پست‌ها (${numbers(posts.length)})`}/><Tab label={`کامنت‌ها (${numbers(comments.length)})`}/><Tab label="گزارش اجرا"/></Tabs><Stack direction="row" spacing={1}>{['csv','xlsx'].map(ext=><Button key={ext} component="a" href={'/api/runs/'+selected+'/export/'+ext} startIcon={<DownloadOutlined/>} size="small">{ext.toUpperCase()}</Button>)}</Stack></Stack><Divider sx={{mb:2}}/>
   {tab<2&&<TextField label="جستجو در نتایج همین اجرا" value={query} onChange={e=>{setQuery(e.target.value);setPage(0)}} sx={{mb:2}} slotProps={{input:{startAdornment:<InputAdornment position="start"><Search/></InputAdornment>}}}/>}
   {resultBusy?<Box sx={{p:5,textAlign:'center'}}><CircularProgress/></Box>:tab===2?<Box className="logs">{selectedRun?.logs||'هنوز پیامی ثبت نشده است.'}</Box>:tab===0?<Stack spacing={2}>{filteredPosts.slice(page*10,page*10+10).map(p=><Paper variant="outlined" key={p.post_url} sx={{p:2.5}}><Stack direction="row" sx={{alignItems:"center",justifyContent:"space-between"}}><Typography dir="ltr" sx={{fontWeight:700}}>{p.owner?'@'+p.owner:'پست اینستاگرام'}</Typography><Button component="a" href={p.post_url} target="_blank" rel="noopener noreferrer" size="small">باز کردن پست</Button></Stack><Typography sx={{my:2,whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{p.caption||'کپشن در این اجرا ثبت نشده است.'}</Typography><Stack direction="row" spacing={1} sx={{flexWrap:"wrap"}}><Chip size="small" label={`${numbers(p.comments?.length||0)} کامنت دریافتی`}/><Chip size="small" variant="outlined" label={`${p.total_likes??'—'} لایک`}/>{p.source&&<Chip size="small" variant="outlined" label={(p.source_type==='hashtag'?'#':'@')+p.source}/>}</Stack></Paper>)}{!filteredPosts.length&&<Alert severity="info">پستی برای نمایش وجود ندارد.</Alert>}</Stack>:<TableContainer><Table size="small"><TableHead><TableRow><TableCell>کاربر</TableCell><TableCell>متن کامنت</TableCell><TableCell>پست</TableCell></TableRow></TableHead><TableBody>{filteredComments.slice(page*10,page*10+10).map((c,i)=><TableRow key={i}><TableCell dir="ltr">{c.username}</TableCell><TableCell sx={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{c.text}</TableCell><TableCell><Button component="a" href={c.post_url} target="_blank" rel="noopener noreferrer" size="small">مشاهده</Button></TableCell></TableRow>)}</TableBody></Table>{!filteredComments.length&&<Alert severity="info">کامنتی برای نمایش وجود ندارد.</Alert>}</TableContainer>}
   {tab<2&&<TablePagination component="div" count={tab===0?filteredPosts.length:filteredComments.length} rowsPerPage={10} rowsPerPageOptions={[10]} page={page} onPageChange={(_,value)=>setPage(value)} labelDisplayedRows={({from,to,count})=>`${numbers(from)} تا ${numbers(to)} از ${numbers(count)}`} getItemAriaLabel={type=>type==='next'?'صفحه بعد':'صفحه قبل'}/>}
  </DialogContent></Dialog>
  <Dialog open={!!deleting} onClose={()=>!busy&&setDeleting(null)} dir="rtl"><DialogTitle>پاک کردن اجرا و نتایج؟</DialogTitle><DialogContent><Typography>این اجرا، تنظیمات، گزارش، نتایج و خروجی‌های محلی CSV و Excel آن حذف می‌شوند. نسخه‌های Drive و بکاپ‌ها باقی می‌مانند.</Typography></DialogContent><DialogActions><Button disabled={busy} onClick={()=>setDeleting(null)}>انصراف</Button><Button color="error" variant="contained" disabled={busy} onClick={()=>void remove()}>پاک کردن</Button></DialogActions></Dialog>
 </Box>
}

