'use client';
import {useCallback, useEffect, useState} from 'react';
import {Alert, Box, Button, Card, Chip, LinearProgress, Stack, Typography} from '@mui/material';
import type {ChipProps} from '@mui/material';
import {HourglassTopOutlined, ShieldOutlined} from '@mui/icons-material';

export type AccountStatus = {
  requests_used: number;
  requests_limit: number;
  posts_used: number;
  posts_limit: number;
  cooldown_until: string | null;
  cooldown_reason: string | null;
};

type RunLike = {
  id: string;
  config: string;
  status: string;
  logs: string;
  started_at?: string | null;
  posts_count: number;
  comments_count: number;
};

export const statusLabels: Record<string, string> = {
  running: 'در حال جمع‌آوری',
  awaiting_code: 'منتظر کد تأیید',
  awaiting_security: 'منتظر تأیید امنیتی',
  completed: 'تکمیل‌شده',
  failed: 'نیاز به بررسی',
  interrupted: 'قطع‌شده',
};
export const activeStatuses = new Set(['running', 'awaiting_code', 'awaiting_security']);
const statusColors: Record<string, ChipProps['color']> = {
  running: 'info',
  awaiting_code: 'warning',
  awaiting_security: 'warning',
  completed: 'success',
  failed: 'error',
  interrupted: 'default',
};
export const fa = (value: number) => value.toLocaleString('fa-IR');

export function StatusChip({status}: {status?: string}) {
  if (!status) return <Chip size="small" variant="outlined" label="بدون اجرا" />;
  return <Chip size="small" variant="outlined" color={statusColors[status] ?? 'default'} label={statusLabels[status] ?? status} />;
}

/** Re-renders every `ms` so elapsed and remaining times stay current. */
export function useNow(ms = 30_000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(timer);
  }, [ms]);
  return now;
}

export function duration(milliseconds: number) {
  const minutes = Math.max(0, Math.round(milliseconds / 60_000));
  if (minutes < 1) return 'کمتر از یک دقیقه';
  if (minutes < 60) return fa(minutes) + ' دقیقه';
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return fa(hours) + ' ساعت' + (rest ? ' و ' + fa(rest) + ' دقیقه' : '');
}

export function useAccountStatus() {
  const [status, setStatus] = useState<AccountStatus | null>(null);
  const load = useCallback(async () => {
    try {
      const response = await fetch('/api/account-status', {cache: 'no-store'});
      if (response.ok) setStatus(await response.json());
    } catch {
      // The connection error is already shown by the main page.
    }
  }, []);
  useEffect(() => {
    void load();
    const timer = setInterval(() => { if (!document.hidden) void load(); }, 15_000);
    return () => clearInterval(timer);
  }, [load]);
  return status;
}

/** Why a new collection run cannot start now, or null when it can. */
export function blockedReason(status: AccountStatus | null, now: number) {
  if (!status) return null;
  if (status.cooldown_until && new Date(status.cooldown_until).getTime() > now) {
    return 'حساب در دورهٔ استراحت است؛ ' + duration(new Date(status.cooldown_until).getTime() - now) + ' دیگر می‌توانید جمع‌آوری را شروع کنید.';
  }
  if (status.posts_used >= status.posts_limit) return 'سقف روزانهٔ پست برای حساب پر شده است. فردا ادامه دهید.';
  if (status.requests_used >= status.requests_limit) return 'سقف روزانهٔ درخواست برای حساب پر شده است. فردا ادامه دهید.';
  return null;
}

function Meter({label, used, limit}: {label: string; used: number; limit: number}) {
  const ratio = limit ? Math.min(1, used / limit) : 1;
  const color = ratio >= 1 ? 'error' : ratio >= 0.8 ? 'warning' : 'primary';
  return (
    <Box sx={{flex: 1, minWidth: 0}}>
      <Stack direction="row" sx={{justifyContent: 'space-between', mb: 0.75}}>
        <Typography variant="body2" color="text.secondary">{label}</Typography>
        <Typography variant="body2" sx={{fontWeight: 700}}>{fa(used)} از {fa(limit)}</Typography>
      </Stack>
      <LinearProgress variant="determinate" value={ratio * 100} color={color} aria-label={label}
        sx={{height: 8, borderRadius: 4, bgcolor: '#e8eeea'}} />
    </Box>
  );
}

/** Today's budget and any cooldown for the collecting account. */
export function AccountStatusCard({status}: {status: AccountStatus | null}) {
  const now = useNow();
  if (!status) return null;
  const cooling = status.cooldown_until && new Date(status.cooldown_until).getTime() > now;
  return (
    <Card sx={{p: {xs: 2, sm: 3}}}>
      <Stack direction="row" spacing={1} sx={{alignItems: 'center', mb: 2}}>
        <ShieldOutlined color={cooling ? 'warning' : 'primary'} />
        <Typography variant="h6" sx={{flex: 1}}>وضعیت حساب جمع‌آوری</Typography>
        <Chip size="small" color={cooling ? 'warning' : 'success'} variant="outlined" label={cooling ? 'در استراحت' : 'آماده'} />
      </Stack>
      {cooling && (
        <Alert severity="warning" sx={{mb: 2}}>
          {status.cooldown_reason}. برای کم کردن خطر مسدود شدن، جمع‌آوری تا{' '}
          {new Date(status.cooldown_until!).toLocaleString('fa-IR', {timeZone: 'Asia/Tehran', dateStyle: 'medium', timeStyle: 'short'})}
          {' '}({duration(new Date(status.cooldown_until!).getTime() - now)} دیگر) متوقف است.
        </Alert>
      )}
      <Stack direction={{xs: 'column', sm: 'row'}} spacing={{xs: 2, sm: 4}}>
        <Meter label="پست‌های بررسی‌شدهٔ امروز" used={status.posts_used} limit={status.posts_limit} />
        <Meter label="درخواست‌های امروز" used={status.requests_used} limit={status.requests_limit} />
      </Stack>
      <Typography variant="caption" color="text.secondary" sx={{display: 'block', mt: 1.5}}>
        سقف‌ها هر روز صفر می‌شوند. سرعت جمع‌آوری عمداً شبیه یک کاربر عادی است.
      </Typography>
    </Card>
  );
}

function runSources(config: {profiles?: string[]; hashtags?: string[]; collection_scope?: string | null; post_url?: string | null}) {
  if (config.post_url) return 1;
  if (config.collection_scope === 'discover') return config.hashtags?.length || 1;
  return config.profiles?.length || 1;
}

/** Progress details for a slow, deliberately paced run. */
export function RunProgress({run}: {run: RunLike}) {
  const now = useNow(10_000);
  const config = JSON.parse(run.config) as {profiles?: string[]; hashtags?: string[]; collection_scope?: string | null; post_url?: string | null; max_posts?: number};
  const started = run.started_at ? new Date(run.started_at).getTime() : NaN;
  const cap = config.post_url ? 1 : runSources(config) * (config.max_posts ?? 8);
  const lastLine = run.logs.trim().split('\n').filter(Boolean).pop();
  // Rough range from the pacing in safety.py: about 20 to 70 seconds per post, plus breaks between sources.
  const low = Math.max(1, Math.round(cap * 20 / 60));
  const high = Math.max(2, Math.round(cap * 70 / 60 + runSources(config)));
  return (
    <Box sx={{mb: 2, p: 2, borderRadius: 2, bgcolor: '#f1f7f3', border: '1px solid #d7e7dd'}} aria-live="polite">
      <Stack direction="row" spacing={1} sx={{alignItems: 'center', mb: 1.5}}>
        <HourglassTopOutlined color="primary" fontSize="small" />
        <Typography sx={{fontWeight: 700, flex: 1}}>{statusLabels[run.status] ?? run.status}</Typography>
        {!Number.isNaN(started) && <Typography variant="body2" color="text.secondary">{duration(now - started)} گذشته</Typography>}
      </Stack>
      <LinearProgress sx={{mb: 1.5, borderRadius: 4}} />
      <Stack direction="row" sx={{flexWrap: 'wrap', gap: 1, mb: 1}}>
        <Chip size="small" label={fa(run.posts_count) + ' پست جدید'} />
        <Chip size="small" label={fa(run.comments_count) + ' کامنت جدید'} />
        <Chip size="small" variant="outlined" label={'حداکثر ' + fa(cap) + ' پست بررسی می‌شود'} />
      </Stack>
      {lastLine && <Typography variant="body2" sx={{overflowWrap: 'anywhere'}}>آخرین مرحله: {lastLine}</Typography>}
      <Typography variant="caption" color="text.secondary" sx={{display: 'block', mt: 1}}>
        برای کم کردن خطر محدودیت، بین پست‌ها مکث می‌شود. زمان تقریبی این اجرا {fa(low)} تا {fa(high)} دقیقه است. می‌توانید این پنجره را ببندید؛ جمع‌آوری ادامه پیدا می‌کند.
      </Typography>
    </Box>
  );
}

/** Shown on every page while a run is active, so disabled buttons have a visible reason. */
export function ActiveRunBanner({run, title, onOpen}: {run: RunLike; title: string; onOpen: () => void}) {
  const now = useNow();
  const started = run.started_at ? new Date(run.started_at).getTime() : NaN;
  const waiting = run.status !== 'running';
  return (
    <Alert
      severity={waiting ? 'warning' : 'info'}
      icon={<HourglassTopOutlined />}
      sx={{mb: 2, alignItems: 'center', flexWrap: {xs: 'wrap', sm: 'nowrap'}, '& .MuiAlert-message': {flex: 1, minWidth: 0}, '& .MuiAlert-action': {xs: {width: '100%', p: 0, m: 0, justifyContent: 'flex-end'}, sm: {width: 'auto', marginInlineStart: 'auto'}}}}
      action={<Button color="inherit" size="small" onClick={onOpen} sx={{whiteSpace: 'nowrap'}}>{waiting ? 'ادامه دادن' : 'مشاهدهٔ پیشرفت'}</Button>}
    >
      <Typography variant="body2" sx={{fontWeight: 700}}>
        «{title}» {waiting ? '— ' + (statusLabels[run.status] ?? run.status) : 'در حال جمع‌آوری است'}
      </Typography>
      <Typography variant="body2">
        {!Number.isNaN(started) && duration(now - started) + ' گذشته · '}
        {fa(run.posts_count)} پست و {fa(run.comments_count)} کامنت جدید. تا پایان این اجرا، اجرای دیگری شروع نمی‌شود.
      </Typography>
    </Alert>
  );
}
