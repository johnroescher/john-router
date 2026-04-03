'use client';

import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState, useEffect } from 'react';
import { useUIStore } from '@/stores/uiStore';
import AuthProvider from '@/components/AuthProvider';
import 'maplibre-gl/dist/maplibre-gl.css';

const lightTheme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#F7B733',
      light: '#FFD86B',
      dark: '#C97C1B',
      contrastText: '#2B1F1A',
    },
    secondary: {
      main: '#E13D7E',
      light: '#F06BA0',
      dark: '#B42E63',
      contrastText: '#FFFFFF',
    },
    success: {
      main: '#22C55E',
    },
    error: {
      main: '#EF4444',
    },
    info: {
      main: '#3B82F6',
    },
    warning: {
      main: '#F59E0B',
    },
    background: {
      default: '#FFF8F1',
      paper: '#FFFFFF',
    },
    text: {
      primary: '#2B1F1A',
      secondary: '#6B4F4A',
    },
    divider: 'rgba(43, 31, 26, 0.08)',
  },
  typography: {
    fontFamily: '"Rubik", "Roboto", "Helvetica", "Arial", sans-serif',
    h5: {
      fontWeight: 600,
    },
    h6: {
      fontWeight: 600,
    },
    subtitle1: {
      fontWeight: 500,
    },
    subtitle2: {
      fontWeight: 600,
      fontSize: '0.875rem',
    },
    body1: {
      fontSize: '0.875rem',
    },
    body2: {
      fontSize: '0.8125rem',
    },
    caption: {
      fontSize: '0.75rem',
      color: '#6B4F4A',
    },
  },
  shape: {
    borderRadius: 8,
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          borderRadius: 8,
          fontWeight: 500,
          boxShadow: 'none',
          '&:hover': {
            boxShadow: 'none',
          },
        },
        outlined: {
          borderColor: 'transparent',
          '&:hover': {
            borderColor: 'transparent',
            backgroundColor: 'rgba(247, 183, 51, 0.08)',
          },
        },
        contained: {
          '&:hover': {
            boxShadow: 'none',
          },
        },
      },
    },
    MuiTab: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          minWidth: 'auto',
          fontWeight: 500,
          fontSize: '0.8125rem',
        },
      },
    },
    MuiTabs: {
      styleOverrides: {
        indicator: {
          display: 'none',
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          boxShadow: 'none',
        },
        elevation1: {
          boxShadow: '0 1px 2px rgba(0, 0, 0, 0.04)',
        },
        elevation2: {
          boxShadow: '0 1px 3px rgba(0, 0, 0, 0.06)',
        },
      },
    },
    MuiAccordion: {
      styleOverrides: {
        root: {
          boxShadow: 'none',
          '&:before': {
            display: 'none',
          },
          '&.Mui-expanded': {
            margin: 0,
          },
        },
      },
    },
    MuiAccordionSummary: {
      styleOverrides: {
        root: {
          minHeight: 48,
          '&.Mui-expanded': {
            minHeight: 48,
          },
        },
        content: {
          '&.Mui-expanded': {
            margin: '12px 0',
          },
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          fontWeight: 500,
        },
        outlined: {
          borderColor: 'transparent',
        },
      },
    },
    MuiTextField: {
      styleOverrides: {
        root: {
          '& .MuiOutlinedInput-root': {
            borderRadius: 8,
            '& fieldset': {
              borderColor: 'transparent',
            },
            '&:hover fieldset': {
              borderColor: 'transparent',
            },
            '&.Mui-focused fieldset': {
              borderColor: 'transparent',
            },
          },
        },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          '& fieldset': {
            borderColor: 'transparent',
          },
          '&:hover fieldset': {
            borderColor: 'transparent',
          },
          '&.Mui-focused fieldset': {
            borderColor: 'transparent',
          },
        },
      },
    },
    MuiIconButton: {
      styleOverrides: {
        root: {
          borderRadius: 8,
        },
      },
    },
    MuiToggleButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          fontWeight: 500,
          borderColor: 'transparent',
          '&.Mui-selected': {
            backgroundColor: '#F7B733',
            color: '#2B1F1A',
            '&:hover': {
              backgroundColor: '#C97C1B',
            },
          },
        },
      },
    },
    MuiSlider: {
      styleOverrides: {
        root: {
          color: '#F7B733',
        },
      },
    },
    MuiSwitch: {
      styleOverrides: {
        switchBase: {
          '&.Mui-checked': {
            color: '#F7B733',
            '& + .MuiSwitch-track': {
              backgroundColor: '#FFD86B',
            },
          },
        },
      },
    },
    MuiLinearProgress: {
      styleOverrides: {
        root: {
          borderRadius: 4,
          backgroundColor: 'rgba(43, 31, 26, 0.08)',
        },
        bar: {
          borderRadius: 4,
        },
      },
    },
    MuiDivider: {
      styleOverrides: {
        root: {
          borderColor: 'transparent',
        },
      },
    },
    MuiMenu: {
      styleOverrides: {
        paper: {
          boxShadow: '0 4px 12px rgba(0, 0, 0, 0.1)',
          borderRadius: 8,
        },
      },
    },
    MuiMenuItem: {
      styleOverrides: {
        root: {
          fontSize: '0.875rem',
        },
      },
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          backgroundColor: '#2B1F1A',
          fontSize: '0.75rem',
          borderRadius: 6,
        },
      },
    },
  },
});

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 minutes
      retry: 1,
    },
  },
});

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const setIsMobile = useUIStore((state) => state.setIsMobile);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);

    // Check for mobile
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768);
    };

    checkMobile();
    window.addEventListener('resize', checkMobile);

    return () => window.removeEventListener('resize', checkMobile);
  }, [setIsMobile]);

  // Prevent hydration mismatch
  if (!mounted) {
    return (
      <html
        lang="en"
        style={{
          height: '100%',
          width: '100%',
          margin: 0,
          padding: 0,
          border: '5px solid #FF38AB',
          boxSizing: 'border-box',
          overflow: 'hidden',
        }}
      >
        <head>
          <title>John Router - AI Cycling Route Planner</title>
          <meta name="description" content="Plan road, gravel, and MTB routes with AI assistance" />
          <meta name="viewport" content="width=device-width, initial-scale=1" />
          <link rel="preconnect" href="https://fonts.googleapis.com" />
          <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
          <link
            href="https://fonts.googleapis.com/css2?family=Rubik:wght@400;500;600;700&display=swap"
            rel="stylesheet"
          />
          <link href="https://fonts.googleapis.com/css2?family=Honk&display=swap" rel="stylesheet" />
        </head>
        <body
          style={{
            margin: 0,
            padding: 0,
            boxSizing: 'border-box',
            height: '100%',
            overflow: 'hidden',
          }}
        >
          <div style={{ minHeight: '100%', backgroundColor: '#FFF8F1' }} />
        </body>
      </html>
    );
  }

  return (
    <html
      lang="en"
      style={{
        height: '100%',
        width: '100%',
        margin: 0,
        padding: 0,
        border: '5px solid #FF38AB',
        boxSizing: 'border-box',
        overflow: 'hidden',
      }}
    >
      <head>
        <title>John Router - AI Cycling Route Planner</title>
        <meta name="description" content="Plan road, gravel, and MTB routes with AI assistance" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Rubik:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
        <link href="https://fonts.googleapis.com/css2?family=Honk&display=swap" rel="stylesheet" />
      </head>
      <body
        style={{
          margin: 0,
          padding: 0,
          boxSizing: 'border-box',
          height: '100%',
          overflow: 'hidden',
        }}
      >
        <QueryClientProvider client={queryClient}>
          <ThemeProvider theme={lightTheme}>
            <CssBaseline />
            <AuthProvider>{children}</AuthProvider>
          </ThemeProvider>
        </QueryClientProvider>
      </body>
    </html>
  );
}
