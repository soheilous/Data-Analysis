'use client';
import { AppRouterCacheProvider } from '@mui/material-nextjs/v16-appRouter';
import { ThemeProvider, createTheme, CssBaseline } from '@mui/material';
import rtlPlugin from '@mui/stylis-plugin-rtl';
import { prefixer } from 'stylis';
const theme = createTheme({ direction:'rtl', palette:{primary:{main:'#176b57'},secondary:{main:'#c69b54'},background:{default:'#f5f6f4',paper:'#ffffff'},text:{primary:'#1e302c',secondary:'#77827d'}}, typography:{fontFamily:'Vazirmatn, Tahoma, Arial, sans-serif',button:{textTransform:'none',fontWeight:700},h4:{fontWeight:800},h5:{fontWeight:700}},shape:{borderRadius:14},components:{MuiButton:{defaultProps:{disableElevation:true},styleOverrides:{root:{padding:'10px 20px'}}},MuiPaper:{styleOverrides:{root:{backgroundImage:'none'}}},MuiTextField:{defaultProps:{size:'small',fullWidth:true}},MuiCard:{styleOverrides:{root:{boxShadow:'none',border:'1px solid #e5eae6'}}}} });
export default function Providers({children}:{children:React.ReactNode}) {return <AppRouterCacheProvider options={{key:'muirtl',stylisPlugins:[prefixer,rtlPlugin]}}><ThemeProvider theme={theme}><CssBaseline />{children}</ThemeProvider></AppRouterCacheProvider>}
