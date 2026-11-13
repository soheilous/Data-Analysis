import type { Metadata } from 'next';
import Providers from './providers';
import '@fontsource/vazirmatn/400.css';
import '@fontsource/vazirmatn/700.css';
import '@fontsource/vazirmatn/800.css';
import './globals.css';
export const metadata: Metadata = { title: 'دیدبان | پایش بازار', description: 'فضای کار جمع‌آوری و بررسی محتوای اینستاگرام' };
export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
 return <html lang="fa" dir="rtl"><body><Providers>{children}</Providers></body></html>;
}
