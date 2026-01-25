'use client';

import { Box, Typography } from '@mui/material';
import { useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import type { StatusUpdate } from '@/types';

const FALLBACK_FACTS = [
  'A steady cadence can save energy on longer rides.',
  'Tire pressure affects comfort, speed, and grip.',
  'Headwinds make flat roads feel like short climbs.',
  'A clean, lubricated chain improves efficiency.',
  'Smooth pedaling improves traction on loose surfaces.',
  'Drafting behind a rider reduces effort at higher speeds.',
];

interface RouteLoadingMessageProps {
  status: StatusUpdate;
}

export default function RouteLoadingMessage({ status }: RouteLoadingMessageProps) {
  const [facts, setFacts] = useState<string[]>(FALLBACK_FACTS);
  const [factIndex, setFactIndex] = useState(0);
  const hasFetchedRef = useRef(false);

  useEffect(() => {
    if (hasFetchedRef.current) return;
    hasFetchedRef.current = true;

    let active = true;
    api.getCyclingFacts(6)
      .then((response) => {
        if (!active || !response?.facts?.length) return;
        setFacts(response.facts);
      })
      .catch(() => {
        // Keep fallback facts on error.
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (facts.length <= 1) return undefined;
    const intervalId = window.setInterval(() => {
      setFactIndex((prev) => (prev + 1) % facts.length);
    }, 5000);
    return () => window.clearInterval(intervalId);
  }, [facts]);

  const progressValue = typeof status.progress === 'number'
    ? Math.min(1, Math.max(0, status.progress))
    : undefined;
  const activeFact = facts[factIndex] || FALLBACK_FACTS[0];

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
          maxWidth: '100%',
          width: '100%',
          bgcolor: 'rgba(0, 0, 0, 0.02)',
          borderRadius: 2,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'stretch',
          gap: 1.25,
          minWidth: 240,
          '@keyframes pedal': {
            '0%': { backgroundPosition: '0 0' },
            '100%': { backgroundPosition: '-64px 0' },
          },
          '@keyframes wheelSpin': {
            '0%': { transform: 'rotate(0deg)' },
            '100%': { transform: 'rotate(360deg)' },
          },
          '@keyframes hillsScroll': {
            '0%': { backgroundPositionX: '0px' },
            '100%': { backgroundPositionX: '-120px' },
          },
          '@keyframes treesScroll': {
            '0%': { backgroundPositionX: '0px' },
            '100%': { backgroundPositionX: '-120px' },
          },
          '@keyframes obstacleMove': {
            '0%': { transform: 'translateX(240px)' },
            '100%': { transform: 'translateX(-80px)' },
          },
          '@keyframes roadDash': {
            '0%': { backgroundPositionX: '0px' },
            '100%': { backgroundPositionX: '-24px' },
          },
          '@keyframes riderMotion': {
            '0%, 18%': { transform: 'translate(0, 0) rotate(0deg)' },
            '26%, 34%': { transform: 'translate(0, -4px) rotate(0deg)' },
            '38%, 48%': { transform: 'translate(0, 0) rotate(0deg)' },
            '58%, 66%': { transform: 'translate(0, -10px) rotate(0deg)' },
            '70%, 78%': { transform: 'translate(0, 0) rotate(0deg)' },
            '82%, 88%': { transform: 'translate(0, 6px) rotate(-70deg)' },
            '92%, 96%': { transform: 'translate(0, -2px) rotate(0deg)' },
            '100%': { transform: 'translate(0, 0) rotate(0deg)' },
          },
        }}
      >
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

          <Box sx={{ mt: 0.75 }}>
            <Box
              sx={{
                height: 6,
                borderRadius: 999,
                bgcolor: 'rgba(0, 0, 0, 0.08)',
                overflow: 'hidden',
                position: 'relative',
              }}
            >
              <Box
                sx={{
                  height: '100%',
                  width: progressValue !== undefined ? `${progressValue * 100}%` : '40%',
                  bgcolor: 'rgba(0, 0, 0, 0.35)',
                  backgroundImage: 'repeating-linear-gradient(90deg, rgba(255,255,255,0.4) 0 6px, rgba(255,255,255,0) 6px 12px)',
                  transition: 'width 200ms ease',
                }}
              />
              {progressValue === undefined && (
                <Box
                  sx={{
                    position: 'absolute',
                    inset: 0,
                    backgroundImage: 'repeating-linear-gradient(90deg, rgba(255,255,255,0.5) 0 6px, rgba(255,255,255,0) 6px 12px)',
                    animation: 'roadDash 1s linear infinite',
                    opacity: 0.6,
                    '@media (prefers-reduced-motion: reduce)': {
                      animation: 'none',
                    },
                  }}
                />
              )}
            </Box>
          </Box>
        </Box>

        <Box
          sx={{
            position: 'relative',
            width: 'calc(100% + 32px)',
            mx: -2,
            height: 68,
            borderRadius: 0,
            overflow: 'hidden',
            bgcolor: 'rgba(0, 0, 0, 0.03)',
            imageRendering: 'pixelated',
            flexShrink: 0,
            alignSelf: 'flex-start',
          }}
        >
          <Box
            sx={{
              position: 'absolute',
              inset: 0,
              backgroundImage: 'url(/pixel/hills.svg)',
              backgroundRepeat: 'repeat-x',
              backgroundPosition: '0 100%',
              animation: 'hillsScroll 6s linear infinite',
              zIndex: 0,
              '@media (prefers-reduced-motion: reduce)': {
                animation: 'none',
              },
            }}
          />
          <Box
            sx={{
              position: 'absolute',
              inset: 0,
              backgroundImage: 'url(/pixel/grass.svg)',
              backgroundRepeat: 'repeat-x',
              backgroundPosition: '0 100%',
              animation: 'treesScroll 3.5s linear infinite',
              opacity: 0.95,
              zIndex: 2,
              '@media (prefers-reduced-motion: reduce)': {
                animation: 'none',
              },
            }}
          />
          <Box
            sx={{
              position: 'absolute',
              inset: 0,
              backgroundImage: 'url(/pixel/tall-trees.svg)',
              backgroundRepeat: 'repeat-x',
              backgroundPosition: '0 100%',
              animation: 'treesScroll 7.5s linear infinite',
              opacity: 0.9,
              zIndex: 4,
              '@media (prefers-reduced-motion: reduce)': {
                animation: 'none',
              },
            }}
          />
          <Box
            sx={{
              position: 'absolute',
              left: 22,
              bottom: 8,
              width: 32,
              height: 32,
              zIndex: 3,
              transformOrigin: 'bottom center',
              animation: 'riderMotion 12s linear infinite',
              '@media (prefers-reduced-motion: reduce)': {
                animation: 'none',
              },
            }}
          >
            <Box
              sx={{
                position: 'absolute',
                left: -4,
                bottom: -2,
                width: 10,
                height: 10,
                borderRadius: '50%',
                animation: 'wheelSpin 0.8s linear infinite',
                '@media (prefers-reduced-motion: reduce)': {
                  animation: 'none',
                },
              }}
            />
            <Box
              sx={{
                position: 'absolute',
                left: 18,
                bottom: -2,
                width: 10,
                height: 10,
                borderRadius: '50%',
                animation: 'wheelSpin 0.8s linear infinite',
                '@media (prefers-reduced-motion: reduce)': {
                  animation: 'none',
                },
              }}
            />
            <Box
              sx={{
                width: 32,
                height: 32,
                backgroundImage: 'url(/pixel/cyclist-sprite.svg)',
                backgroundRepeat: 'no-repeat',
                backgroundSize: '64px 32px',
                animation: 'pedal 0.6s steps(2) infinite',
                '@media (prefers-reduced-motion: reduce)': {
                  animation: 'none',
                },
              }}
            />
          </Box>
          <Box
            sx={{
              position: 'absolute',
              bottom: 6,
              left: 0,
              width: 20,
              height: 8,
              backgroundImage: 'url(/pixel/hill-bump.svg)',
              backgroundRepeat: 'no-repeat',
              zIndex: 3,
              animation: 'obstacleMove 8s linear infinite',
              animationDelay: '-3s',
              '@media (prefers-reduced-motion: reduce)': {
                animation: 'none',
              },
            }}
          />
          <Box
            sx={{
              position: 'absolute',
              bottom: 4,
              left: 0,
              width: 20,
              height: 6,
              backgroundImage: 'url(/pixel/stream.svg)',
              backgroundRepeat: 'no-repeat',
              zIndex: 3,
              opacity: 0.9,
              animation: 'obstacleMove 10s linear infinite',
              animationDelay: '-6s',
              '@media (prefers-reduced-motion: reduce)': {
                animation: 'none',
              },
            }}
          />
          <Box
            sx={{
              position: 'absolute',
              bottom: 12,
              left: 0,
              width: 20,
              height: 16,
              backgroundImage: 'url(/pixel/house.svg)',
              backgroundRepeat: 'no-repeat',
              zIndex: 1,
              opacity: 0.9,
              animation: 'obstacleMove 16s linear infinite',
              animationDelay: '-8s',
              '@media (prefers-reduced-motion: reduce)': {
                animation: 'none',
              },
            }}
          />
          <Box
            sx={{
              position: 'absolute',
              bottom: 8,
              left: 0,
              width: 16,
              height: 12,
              backgroundImage: 'url(/pixel/dog.svg)',
              backgroundRepeat: 'no-repeat',
              zIndex: 5,
              animation: 'obstacleMove 12s linear infinite',
              '@media (prefers-reduced-motion: reduce)': {
                animation: 'none',
              },
            }}
          />
          <Box
            sx={{
              position: 'absolute',
              bottom: 2,
              left: 0,
              width: 20,
              height: 36,
              backgroundImage: 'url(/pixel/yeti.svg)',
              backgroundRepeat: 'no-repeat',
              zIndex: 5,
              animation: 'obstacleMove 12s linear infinite',
              animationDelay: '2s',
              '@media (prefers-reduced-motion: reduce)': {
                animation: 'none',
              },
            }}
          />
          <Box
            sx={{
              position: 'absolute',
              inset: 0,
              backgroundImage: 'url(/pixel/grass.svg)',
              backgroundRepeat: 'repeat-x',
              backgroundPosition: '0 100%',
              animation: 'treesScroll 2.8s linear infinite',
              opacity: 0.75,
              zIndex: 6,
              '@media (prefers-reduced-motion: reduce)': {
                animation: 'none',
              },
            }}
          />
          <Box
            sx={{
              position: 'absolute',
              left: 0,
              right: 0,
              bottom: 0,
              height: 12,
              bgcolor: 'rgba(0, 0, 0, 0.12)',
              zIndex: 2,
            }}
          />
        </Box>

        <Typography
          aria-live="polite"
          sx={{
            mt: 0.25,
            fontSize: '0.75rem',
            color: 'text.secondary',
            lineHeight: 1.4,
          }}
        >
          {activeFact}
        </Typography>
      </Box>
    </Box>
  );
}
