import type { NextConfig } from 'next';
const config: NextConfig = process.env.DIDBAN_STATIC_BUILD === '1' ? {
  output: 'export',
} : {
  async rewrites() { return [{ source: '/api/:path*', destination: 'http://127.0.0.1:8000/api/:path*' }]; },
};
export default config;
