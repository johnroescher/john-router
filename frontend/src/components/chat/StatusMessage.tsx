'use client';

import { Box, Typography, LinearProgress, CircularProgress } from '@mui/material';
import type { StatusUpdate } from '@/types';
import RouteLoadingMessage from './RouteLoadingMessage';

const LOADING_STAGES = new Set([
  'starting',
  'connecting',
  'extracting_intent',
  'expanding_brief',
  'refining',
  'discovering_trails',
  'geocoding',
  'generating_routes',
  'analyzing_routes',
  'validating_routes',
  'evaluating_routes',
  'critiquing_routes',
]);

interface StatusMessageProps {
  status: StatusUpdate;
}

export default function StatusMessage({ status }: StatusMessageProps) {
  if (LOADING_STAGES.has(status.stage)) {
    return <RouteLoadingMessage status={status} />;
  }

  return (
    <Box
      sx={{
        display: 'flex',
        justifyContent: 'flex-start',
        mb: 1.5,
      }}
    >
      <Box
        sx={{
          py: 1.5,
          px: 2,
          maxWidth: '85%',
          bgcolor: 'rgba(0, 0, 0, 0.02)',
          borderRadius: 2,
          display: 'flex',
          alignItems: 'center',
          gap: 1.5,
          minWidth: 200,
        }}
      >
        <CircularProgress 
          size={14} 
          sx={{ 
            color: 'primary.main',
            flexShrink: 0,
          }} 
        />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography 
            sx={{ 
              fontSize: '0.8125rem', 
              color: 'text.secondary',
              lineHeight: 1.5,
            }}
          >
            {status.message}
          </Typography>
          {status.progress !== undefined && status.progress !== null && (
            <Box sx={{ mt: 0.75 }}>
              <LinearProgress 
                variant="determinate" 
                value={status.progress * 100} 
                sx={{
                  height: 2,
                  borderRadius: 1,
                  bgcolor: 'rgba(0, 0, 0, 0.05)',
                  '& .MuiLinearProgress-bar': {
                    borderRadius: 1,
                  },
                }}
              />
            </Box>
          )}
        </Box>
      </Box>
    </Box>
  );
}
