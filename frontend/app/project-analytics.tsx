'use client';
import {useEffect, useState} from 'react';
import {Alert, Box, Button, ButtonBase, Card, Chip, CircularProgress, Stack, ToggleButton, ToggleButtonGroup, Typography} from '@mui/material';

type Summary = {
  posts: number;
  posts_with_likes: number;
  total_likes: number;
  total_comments: number;
  collected_comments: number;
  unique_commenters: number;
  avg_likes: number;
  avg_comments: number;
  avg_engagement: number;
  posts_per_week: number | null;
  first_post_at: string | null;
  last_post_at: string | null;
};
type TopPost = {
  post_url: string;
  shortcode?: string;
  owner?: string | null;
  caption: string;
  published_at?: string | null;
  likes: number | null;
  comments: number;
  engagement: number;
};
type Bucket = {posts: number; avg_engagement: number};
export type Analytics = {
  summary: Summary;
  top_posts: TopPost[];
  posting: {
    timeline: {date: string; posts: number; likes: number; comments: number; engagement: number}[];
    weekly: {week: string; posts: number}[];
    weekdays: (Bucket & {day: string})[];
    hours: (Bucket & {hour: number})[];
  };
  hashtags: {
    top: {tag: string; posts: number; avg_engagement: number}[];
    trends: {tag: string; weeks: {week: string; posts: number}[]}[];
  };
  comments: {
    timeline: {date: string; comments: number}[];
    top_commenters: {username: string; comments: number}[];
    top_terms: {term: string; count: number}[];
  };
  accounts: {owner: string; posts: number; likes: number; comments: number; engagement: number; avg_engagement: number}[];
};
type Rhythm = 'weekly' | 'weekdays' | 'hours';

const numbers = (value: number) => value.toLocaleString('fa-IR', {maximumFractionDigits: 1});
const shortDate = new Intl.DateTimeFormat('fa-IR', {month: 'short', day: 'numeric'});
const fullDate = new Intl.DateTimeFormat('fa-IR', {timeZone: 'Asia/Tehran', dateStyle: 'medium'});
// Day keys from the API are Tehran calendar dates; parse at noon UTC so they never shift a day.
const dayLabel = (key: string) => shortDate.format(new Date(key + 'T12:00:00Z'));
const dateLabel = (value?: string | null) => {
  const date = value ? new Date(value) : null;
  return date && !Number.isNaN(date.getTime()) ? fullDate.format(date) : '—';
};

function Section({title, hint, action, children}: {title: string; hint?: string; action?: React.ReactNode; children: React.ReactNode}) {
  return (
    <Card sx={{p: {xs: 2, sm: 3}, minWidth: 0}}>
      <Stack direction={{xs: 'column', sm: 'row'}} spacing={1.5} sx={{justifyContent: 'space-between', alignItems: {sm: 'center'}, mb: 2}}>
        <Box>
          <Typography variant="h6">{title}</Typography>
          {hint && <Typography variant="body2" color="text.secondary">{hint}</Typography>}
        </Box>
        {action}
      </Stack>
      {children}
    </Card>
  );
}

function Empty({children}: {children: React.ReactNode}) {
  return <Typography color="text.secondary" sx={{py: 3}}>{children}</Typography>;
}

/** Vertical bars, oldest on the left like the overview chart. */
function Columns({items, label}: {items: {key: string; label: string; value: number; detail: string}[]; label: string}) {
  const [selected, setSelected] = useState<string | null>(null);
  const max = Math.max(1, ...items.map(item => item.value));
  const current = items.find(item => item.key === selected);
  return (
    <>
      <Box dir="ltr" sx={{display: 'grid', gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))`, gap: items.length > 20 ? 0.25 : {xs: 0.4, sm: 1}, height: 150, borderBottom: '1px solid', borderColor: 'divider'}}>
        {items.map(item => (
          <ButtonBase
            key={item.key}
            aria-label={item.label + '، ' + item.detail}
            aria-pressed={item.key === selected}
            onClick={() => setSelected(item.key === selected ? null : item.key)}
            sx={{alignItems: 'flex-end', px: items.length > 20 ? 0 : {xs: 0.2, sm: 0.6}, borderRadius: '6px 6px 0 0', '&.Mui-focusVisible': {outline: '2px solid', outlineColor: 'primary.main'}}}
          >
            <Box sx={{width: '100%', height: item.value ? Math.max(4, item.value / max * 100) + '%' : '2px', bgcolor: item.key === selected ? '#102e26' : item.value ? 'primary.main' : 'divider', borderRadius: '4px 4px 0 0'}} />
          </ButtonBase>
        ))}
      </Box>
      {items.length > 0 && (
        <Stack direction="row" dir="ltr" sx={{justifyContent: 'space-between', mt: 1}}>
          <Typography variant="caption" color="text.secondary">{items[0].label}</Typography>
          <Typography variant="caption" color="text.secondary">{items[items.length - 1].label}</Typography>
        </Stack>
      )}
      <Typography variant="body2" color="text.secondary" sx={{mt: 1.5}} aria-live="polite">
        {current ? current.label + ' · ' + current.detail : label}
      </Typography>
    </>
  );
}

/** Horizontal bars for ranked lists. */
function Ranking({items}: {items: {key: string; label: React.ReactNode; value: number; detail: string}[]}) {
  const max = Math.max(1, ...items.map(item => item.value));
  return (
    <Stack spacing={1.25}>
      {items.map(item => (
        <Box key={item.key}>
          <Stack direction="row" spacing={1} sx={{justifyContent: 'space-between', mb: 0.5}}>
            <Typography variant="body2" sx={{fontWeight: 700, overflowWrap: 'anywhere'}}>{item.label}</Typography>
            <Typography variant="body2" color="text.secondary" sx={{whiteSpace: 'nowrap'}}>{item.detail}</Typography>
          </Stack>
          <Box sx={{height: 8, borderRadius: 4, bgcolor: '#edf5ef'}}>
            <Box sx={{height: '100%', width: Math.max(2, item.value / max * 100) + '%', borderRadius: 4, bgcolor: 'primary.main'}} />
          </Box>
        </Box>
      ))}
    </Stack>
  );
}

export function ProjectAnalytics({projectId}: {projectId: string}) {
  const [data, setData] = useState<Analytics | null>(null);
  const [error, setError] = useState('');
  const [rhythm, setRhythm] = useState<Rhythm>('weekly');

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const response = await fetch('/api/projects/' + projectId + '/analytics', {cache: 'no-store'});
        if (!response.ok) throw new Error('تحلیل پروژه دریافت نشد.');
        const body = await response.json() as Analytics;
        if (alive) {setData(body); setError('');}
      } catch (e) {
        if (alive) setError((e as Error).message === 'Failed to fetch' ? 'ارتباط با سرور برقرار نشد' : (e as Error).message);
      }
    }
    setData(null);
    void load();
    const timer = setInterval(() => {if (!document.hidden) void load();}, 15000);
    return () => {alive = false; clearInterval(timer);};
  }, [projectId]);

  if (error && !data) return <Alert severity="error">{error}</Alert>;
  if (!data) return <Box sx={{p: 5, textAlign: 'center'}}><CircularProgress aria-label="در حال محاسبهٔ تحلیل" /></Box>;
  const {summary} = data;
  if (!summary.posts) return <Card sx={{p: 3}}><Typography color="text.secondary">هنوز پستی برای تحلیل ثبت نشده است. پس از اولین جمع‌آوری، آمار این‌جا نمایش داده می‌شود.</Typography></Card>;

  const kpis = [
    {label: 'پست‌های ثبت‌شده', value: numbers(summary.posts)},
    {label: 'میانگین تعامل هر پست', value: numbers(summary.avg_engagement), hint: 'لایک + کامنت'},
    {label: 'میانگین لایک', value: numbers(summary.avg_likes), hint: summary.posts_with_likes < summary.posts ? `از ${numbers(summary.posts_with_likes)} پست دارای لایک` : undefined},
    {label: 'میانگین کامنت', value: numbers(summary.avg_comments)},
    {label: 'پست در هفته', value: summary.posts_per_week === null ? '—' : numbers(summary.posts_per_week)},
    {label: 'کامنت‌گذاران یکتا', value: numbers(summary.unique_commenters), hint: `${numbers(summary.collected_comments)} کامنت دریافتی`},
  ];
  const rhythmItems = rhythm === 'weekly'
    ? data.posting.weekly.map(item => ({key: item.week, label: 'هفتهٔ ' + dayLabel(item.week), value: item.posts, detail: numbers(item.posts) + ' پست'}))
    : rhythm === 'weekdays'
      ? data.posting.weekdays.map(item => ({key: item.day, label: item.day, value: item.posts, detail: numbers(item.posts) + ' پست · میانگین تعامل ' + numbers(item.avg_engagement)}))
      : data.posting.hours.map(item => ({key: String(item.hour), label: 'ساعت ' + numbers(item.hour), value: item.posts, detail: numbers(item.posts) + ' پست · میانگین تعامل ' + numbers(item.avg_engagement)}));
  const undated = summary.posts - data.posting.timeline.reduce((sum, day) => sum + day.posts, 0);

  return (
    <Stack spacing={3}>
      {error && <Alert severity="warning">{error}</Alert>}
      <Box sx={{display: 'grid', gridTemplateColumns: {xs: 'repeat(2, minmax(0, 1fr))', md: 'repeat(3, minmax(0, 1fr))', xl: 'repeat(6, minmax(0, 1fr))'}, gap: 2}}>
        {kpis.map(item => (
          <Card key={item.label} sx={{p: 2}}>
            <Typography variant="body2" color="text.secondary">{item.label}</Typography>
            <Typography variant="h5" sx={{mt: 0.5}}>{item.value}</Typography>
            {item.hint && <Typography variant="caption" color="text.secondary">{item.hint}</Typography>}
          </Card>
        ))}
      </Box>
      <Typography variant="body2" color="text.secondary">
        بازهٔ انتشار: {dateLabel(summary.first_post_at)} تا {dateLabel(summary.last_post_at)}. تعداد دنبال‌کننده جمع‌آوری نمی‌شود، پس تعامل به‌صورت عدد مطلق (لایک + کامنت) محاسبه شده است.
      </Typography>

      <Section
        title="ریتم انتشار"
        hint={undated > 0 ? `${numbers(undated)} پست بدون زمان انتشار در این نمودار نیستند.` : 'بر اساس زمان انتشار به وقت تهران'}
        action={
          <ToggleButtonGroup exclusive size="small" color="primary" value={rhythm} aria-label="نوع نمودار انتشار"
            onChange={(_, value: Rhythm | null) => {if (value) setRhythm(value);}}>
            <ToggleButton value="weekly">هفتگی</ToggleButton>
            <ToggleButton value="weekdays">روز هفته</ToggleButton>
            <ToggleButton value="hours">ساعت</ToggleButton>
          </ToggleButtonGroup>
        }
      >
        {rhythmItems.every(item => !item.value) ? <Empty>زمان انتشار پست‌ها ثبت نشده است.</Empty> : (
          <Columns key={rhythm} items={rhythmItems} label={rhythm === 'weekly' ? 'تعداد پست در هر هفته (شروع از شنبه)' : 'برای جزئیات روی هر ستون بزنید.'} />
        )}
      </Section>

      <Section title="پست‌های برتر" hint="مرتب‌شده بر اساس مجموع لایک و کامنت">
        <Stack spacing={1.5}>
          {data.top_posts.map((post, index) => (
            <Stack key={post.post_url ?? index} direction={{xs: 'column', sm: 'row'}} spacing={2} sx={{p: 1.5, borderRadius: 2, bgcolor: index === 0 ? '#edf5ef' : 'action.hover', alignItems: {sm: 'center'}}}>
              <Typography variant="h6" color="primary" sx={{minWidth: 28}}>{numbers(index + 1)}</Typography>
              <Box sx={{flex: 1, minWidth: 0}}>
                <Typography variant="body2" sx={{fontWeight: 700}} dir="ltr" component="span">{post.owner ? '@' + post.owner : 'پست'}</Typography>
                <Typography variant="body2" color="text.secondary" component="span"> · {dateLabel(post.published_at)}</Typography>
                <Typography variant="body2" sx={{mt: 0.5, overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflowWrap: 'anywhere'}}>
                  {post.caption || 'متن پست ثبت نشده است.'}
                </Typography>
              </Box>
              <Stack direction="row" spacing={1} sx={{flexWrap: 'wrap', gap: 1, alignItems: 'center'}}>
                <Chip size="small" color="primary" label={numbers(post.engagement) + ' تعامل'} />
                <Chip size="small" variant="outlined" label={(post.likes === null ? '—' : numbers(post.likes)) + ' لایک'} />
                <Chip size="small" variant="outlined" label={numbers(post.comments) + ' کامنت'} />
                {post.post_url && <Button size="small" component="a" href={post.post_url} target="_blank" rel="noopener noreferrer">باز کردن</Button>}
              </Stack>
            </Stack>
          ))}
        </Stack>
      </Section>

      <Box sx={{display: 'grid', gridTemplateColumns: {xs: '1fr', lg: 'repeat(2, minmax(0, 1fr))'}, gap: 3}}>
        <Section title="هشتگ‌ها" hint="پرتکرارترین هشتگ‌های کپشن و میانگین تعامل پست‌هایشان">
          {!data.hashtags.top.length ? <Empty>در کپشن‌ها هشتگی پیدا نشد.</Empty> : (
            <Ranking items={data.hashtags.top.slice(0, 10).map(item => ({
              key: item.tag, label: '#' + item.tag, value: item.posts,
              detail: numbers(item.posts) + ' پست · ' + numbers(item.avg_engagement) + ' تعامل',
            }))} />
          )}
          {data.hashtags.trends.length > 0 && data.posting.weekly.length > 1 && (
            <Box sx={{mt: 3}}>
              <Typography variant="subtitle2" sx={{mb: 1}}>روند هفتگی پنج هشتگ اول</Typography>
              <Stack spacing={1}>
                {data.hashtags.trends.map(trend => {
                  const max = Math.max(1, ...trend.weeks.map(week => week.posts));
                  return (
                    <Stack key={trend.tag} direction="row" spacing={1} sx={{alignItems: 'center'}}>
                      <Typography variant="caption" sx={{width: 110, flexShrink: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}}>#{trend.tag}</Typography>
                      <Box dir="ltr" sx={{display: 'flex', gap: '2px', flex: 1, minWidth: 0}}>
                        {trend.weeks.map(week => (
                          <Box key={week.week} title={'هفتهٔ ' + dayLabel(week.week) + ': ' + numbers(week.posts) + ' پست'}
                            sx={{flex: 1, height: 16, borderRadius: '3px', bgcolor: 'primary.main', opacity: week.posts ? 0.25 + 0.75 * week.posts / max : 0.06}} />
                        ))}
                      </Box>
                    </Stack>
                  );
                })}
              </Stack>
            </Box>
          )}
        </Section>

        <Section title="کامنت‌ها" hint="بر اساس کامنت‌های دریافت‌شده">
          {!data.comments.timeline.length && !data.comments.top_commenters.length ? <Empty>هنوز کامنتی دریافت نشده است.</Empty> : (
            <Stack spacing={3}>
              {data.comments.timeline.length > 1 && (
                <Columns
                  items={data.comments.timeline.slice(-30).map(item => ({key: item.date, label: dayLabel(item.date), value: item.comments, detail: numbers(item.comments) + ' کامنت'}))}
                  label="تعداد کامنت در روز (۳۰ روز آخرِ دارای کامنت)"
                />
              )}
              {data.comments.top_commenters.length > 0 && (
                <Box>
                  <Typography variant="subtitle2" sx={{mb: 1}}>فعال‌ترین کامنت‌گذاران</Typography>
                  <Ranking items={data.comments.top_commenters.slice(0, 8).map(item => ({
                    key: item.username, label: <span dir="ltr">@{item.username}</span>, value: item.comments, detail: numbers(item.comments) + ' کامنت',
                  }))} />
                </Box>
              )}
              {data.comments.top_terms.length > 0 && (
                <Box>
                  <Typography variant="subtitle2" sx={{mb: 1}}>واژه‌های پرتکرار</Typography>
                  <Stack direction="row" sx={{flexWrap: 'wrap', gap: 1}}>
                    {data.comments.top_terms.map(item => <Chip key={item.term} size="small" variant="outlined" label={item.term + ' · ' + numbers(item.count)} />)}
                  </Stack>
                </Box>
              )}
            </Stack>
          )}
        </Section>
      </Box>

      {data.accounts.length > 1 && (
        <Section title="مقایسهٔ پیج‌ها" hint="مجموع تعامل پست‌های هر صاحب پست">
          <Ranking items={data.accounts.map(item => ({
            key: item.owner, label: <span dir="ltr">{item.owner === '—' ? 'نامشخص' : '@' + item.owner}</span>, value: item.engagement,
            detail: numbers(item.posts) + ' پست · میانگین ' + numbers(item.avg_engagement),
          }))} />
        </Section>
      )}
    </Stack>
  );
}
