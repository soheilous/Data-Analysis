import {useState} from 'react';
import {Box, Button, ButtonBase, Card, CircularProgress, Stack, ToggleButton, ToggleButtonGroup, Typography} from '@mui/material';
import {Add, ForumOutlined, Instagram, LayersOutlined, PlayArrow} from '@mui/icons-material';
import {StatusChip} from './run-status';

type OverviewProject = {
  id: string;
  config: string;
  posts_count?: number;
  comments_count?: number;
};
type OverviewRun = {
  project_id?: string | null;
  started_at?: string | null;
  status: string;
  posts_count: number;
  comments_count: number;
};
type Metric = 'runs' | 'posts' | 'comments';

const metrics: Record<Metric, string> = {
  runs: 'اجرا',
  posts: 'پست تازه',
  comments: 'کامنت تازه',
};
const numbers = (value: number) => value.toLocaleString('fa-IR');
const dayKey = new Intl.DateTimeFormat('sv-SE', {timeZone: 'Asia/Tehran'});
const dayLabel = new Intl.DateTimeFormat('fa-IR', {timeZone: 'Asia/Tehran', month: 'short', day: 'numeric'});
const activeStatuses = new Set(['running', 'awaiting_code', 'awaiting_security']);

export function ProjectOverview({projects, runs, loading, onOpen, onCreate}: {
  projects: OverviewProject[];
  runs: OverviewRun[];
  loading: boolean;
  onOpen: (id: string) => void;
  onCreate: () => void;
}) {
  const [metric, setMetric] = useState<Metric>('runs');
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const history = new Map<string, OverviewRun[]>();
  for (const run of runs) {
    if (!run.project_id) continue;
    const items = history.get(run.project_id) ?? [];
    items.push(run);
    history.set(run.project_id, items);
  }
  const projectRuns = projects.flatMap(project => history.get(project.id) ?? []);
  const today = Date.now();
  const days = Array.from({length: 14}, (_, index) => {
    const date = new Date(today - (13 - index) * 86_400_000);
    return {key: dayKey.format(date), label: dayLabel.format(date), runs: 0, posts: 0, comments: 0};
  });
  const dates = new Map(days.map(day => [day.key, day]));
  for (const run of projectRuns) {
    if (!run.started_at) continue;
    const date = new Date(run.started_at);
    if (Number.isNaN(date.getTime())) continue;
    const day = dates.get(dayKey.format(date));
    if (!day) continue;
    day.runs++;
    day.posts += run.posts_count;
    day.comments += run.comments_count;
  }
  const max = Math.max(1, ...days.map(day => day[metric]));
  const selected = days.find(day => day.key === selectedDay);
  const totals = [
    {label: 'پروژه‌ها', count: projects.length, icon: <LayersOutlined />},
    {label: 'پست‌های ثبت‌شده', count: projects.reduce((sum, p) => sum + (p.posts_count ?? 0), 0), icon: <Instagram />},
    {label: 'کامنت‌های ثبت‌شده', count: projects.reduce((sum, p) => sum + (p.comments_count ?? 0), 0), icon: <ForumOutlined />},
    {label: 'اجراهای فعال', count: projectRuns.filter(run => activeStatuses.has(run.status)).length, icon: <PlayArrow />},
  ];

  if (loading) return <Box sx={{py: 6, textAlign: 'center'}}><CircularProgress size={28} aria-label="در حال بارگیری نمای کلی" /></Box>;

  return (
    <Stack spacing={3}>
      <Box sx={{display: 'grid', gridTemplateColumns: {xs: 'repeat(2, minmax(0, 1fr))', lg: 'repeat(4, minmax(0, 1fr))'}, gap: 2}}>
        {totals.map(item => (
          <Card key={item.label} sx={{p: {xs: 2, sm: 2.5}}}>
            <Box sx={{display: 'inline-flex', p: 1, mb: 1, borderRadius: 2, bgcolor: '#edf5ef', color: 'primary.main'}}>{item.icon}</Box>
            <Typography variant="body2" color="text.secondary">{item.label}</Typography>
            <Typography variant="h4" sx={{mt: 0.5}}>{numbers(item.count)}</Typography>
          </Card>
        ))}
      </Box>
      <Card sx={{p: {xs: 2, sm: 3}}}>
        <Stack direction={{xs: 'column', sm: 'row'}} spacing={2} sx={{justifyContent: 'space-between', alignItems: {sm: 'center'}}}>
          <Typography variant="h6">فعالیت ۱۴ روز گذشته</Typography>
          <ToggleButtonGroup
            exclusive size="small" color="primary" value={metric} aria-label="معیار نمودار"
            onChange={(_, value: Metric | null) => {if (value) setMetric(value);}}
          >
            <ToggleButton value="runs">اجراها</ToggleButton>
            <ToggleButton value="posts">پست‌ها</ToggleButton>
            <ToggleButton value="comments">کامنت‌ها</ToggleButton>
          </ToggleButtonGroup>
        </Stack>
        {days.every(day => day.runs === 0) ? (
          <Typography color="text.secondary" sx={{py: 4}}>در این بازه اجرایی با زمان شروع ثبت نشده است.</Typography>
        ) : (
          <>
            <Box dir="ltr" sx={{display: 'grid', gridTemplateColumns: 'repeat(14, minmax(0, 1fr))', gap: {xs: 0.4, sm: 1}, height: 150, mt: 2, borderBottom: '1px solid', borderColor: 'divider'}}>
              {days.map(day => (
                <ButtonBase
                  key={day.key}
                  aria-label={day.label + '، ' + numbers(day[metric]) + ' ' + metrics[metric]}
                  aria-pressed={day.key === selectedDay}
                  onClick={() => setSelectedDay(day.key === selectedDay ? null : day.key)}
                  sx={{alignItems: 'flex-end', px: {xs: 0.2, sm: 0.7}, borderRadius: '8px 8px 0 0', '&.Mui-focusVisible': {outline: '2px solid', outlineColor: 'primary.main'}}}
                >
                  <Box sx={{width: '100%', height: day[metric] ? Math.max(4, day[metric] / max * 100) + '%' : '2px', bgcolor: day.key === selectedDay ? '#102e26' : day[metric] ? 'primary.main' : 'divider', borderRadius: '5px 5px 0 0'}} />
                </ButtonBase>
              ))}
            </Box>
            <Stack direction="row" sx={{justifyContent: 'space-between', mt: 1}} dir="ltr">
              <Typography variant="caption" color="text.secondary" dir="rtl">{days[0].label}</Typography>
              <Typography variant="caption" color="text.secondary">امروز</Typography>
            </Stack>
            <Typography variant="body2" color="text.secondary" sx={{mt: 2}} aria-live="polite">
              {selected
                ? selected.label + ' · ' + numbers(selected.runs) + ' اجرا، ' + numbers(selected.posts) + ' پست تازه و ' + numbers(selected.comments) + ' کامنت تازه'
                : numbers(days.reduce((sum, day) => sum + day[metric], 0)) + ' ' + metrics[metric] + ' در این بازه'}
            </Typography>
          </>
        )}
      </Card>
      <Box>
        <Typography variant="h6" sx={{mb: 2}}>خلاصهٔ پروژه‌ها</Typography>
        {projects.length === 0 ? (
          <Card sx={{p: 3}}>
            <Stack spacing={1.5} sx={{alignItems: 'flex-start'}}>
              <Typography color="text.secondary">هنوز پروژه‌ای ندارید. با ساخت پروژه، پیج‌ها و تگ‌ها را تعریف کنید تا آمار اینجا نمایش داده شود.</Typography>
              <Button variant="contained" startIcon={<Add />} onClick={onCreate}>ساخت اولین پروژه</Button>
            </Stack>
          </Card>
        ) : (
          <Box sx={{display: 'grid', gridTemplateColumns: {xs: '1fr', md: 'repeat(2, minmax(0, 1fr))', xl: 'repeat(3, minmax(0, 1fr))'}, gap: 2}}>
            {projects.map(project => {
              const config = JSON.parse(project.config) as {title?: string; profiles?: string[]; hashtags?: string[]};
              const latest = history.get(project.id)?.[0];
              return (
                <Card key={project.id} sx={{p: 2.5}}>
                  <Stack spacing={1.5}>
                    <Stack direction="row" sx={{gap: 1, justifyContent: 'space-between', alignItems: 'flex-start'}}>
                      <Typography sx={{fontWeight: 700, overflowWrap: 'anywhere'}}>{config.title || 'پروژه'}</Typography>
                      <StatusChip status={latest?.status} />
                    </Stack>
                    <Typography variant="body2" color="text.secondary">
                      {numbers(config.profiles?.length ?? 0)} پیج · {numbers(config.hashtags?.length ?? 0)} تگ
                    </Typography>
                    <Typography variant="body2">
                      {numbers(project.posts_count ?? 0)} پست · {numbers(project.comments_count ?? 0)} کامنت
                    </Typography>
                    <Button variant="outlined" sx={{alignSelf: 'flex-start'}} onClick={() => onOpen(project.id)}>باز کردن پروژه</Button>
                  </Stack>
                </Card>
              );
            })}
          </Box>
        )}
      </Box>
    </Stack>
  );
}
