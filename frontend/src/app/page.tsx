'use client';

import { Box, Button, Container, Typography, Stack, Paper, Grid } from '@mui/material';
import { useRouter } from 'next/navigation';
import DirectionsBikeIcon from '@mui/icons-material/DirectionsBike';
import TerrainIcon from '@mui/icons-material/Terrain';
import ChatIcon from '@mui/icons-material/Chat';
import MapIcon from '@mui/icons-material/Map';

export default function LandingPage() {
  const router = useRouter();

  return (
    <Box
      sx={{
        minHeight: '100vh',
        background: 'linear-gradient(135deg, #2B1F1A 0%, #4B1B2E 55%, #7A2C3D 100%)',
        color: '#FFF4DF',
      }}
    >
      {/* Hero Section */}
      <Container maxWidth="lg" sx={{ pt: 8, pb: 6 }}>
        <Stack spacing={4} alignItems="center" textAlign="center">
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <DirectionsBikeIcon sx={{ fontSize: 48, color: 'primary.main' }} />
            <Typography
              variant="h2"
              component="h1"
            sx={{ fontWeight: 700, color: '#FFD86B' }}
            >
              John Router
            </Typography>
          </Box>

          <Typography
            variant="h5"
          sx={{ maxWidth: 600, color: 'rgba(255, 244, 223, 0.88)' }}
          >
            AI-powered cycling route builder for road, gravel, and mountain bike adventures
          </Typography>

          <Typography
            variant="body1"
          sx={{ maxWidth: 500, color: 'rgba(255, 244, 223, 0.78)' }}
          >
            Chat with AI to plan your perfect ride, then fine-tune on the map.
            Get detailed trail analysis, difficulty ratings, and real-time condition updates.
          </Typography>

          <Stack direction="row" spacing={2} sx={{ mt: 4, flexWrap: 'wrap', justifyContent: 'center' }}>
            <Button
              variant="contained"
              size="large"
              onClick={() => router.push('/planner')}
              sx={{ px: 4, py: 1.5 }}
            >
              Start Planning
            </Button>
            <Button
              variant="outlined"
              size="large"
              onClick={() => router.push('/login')}
              sx={{ px: 4, py: 1.5 }}
            >
              Sign In
            </Button>
            <Button
              variant="text"
              size="large"
              onClick={() => router.push('/register')}
              sx={{ px: 4, py: 1.5, color: '#FFF4DF' }}
            >
              Create Account
            </Button>
          </Stack>
        </Stack>
      </Container>

      {/* Features Section */}
      <Container maxWidth="lg" sx={{ py: 8 }}>
        <Grid container spacing={4}>
          <Grid item xs={12} md={4}>
            <Paper
              sx={{
                p: 4,
                height: '100%',
                background: 'rgba(255, 216, 107, 0.08)',
                backdropFilter: 'blur(10px)',
              }}
            >
              <ChatIcon sx={{ fontSize: 40, color: 'primary.main', mb: 2 }} />
              <Typography variant="h6" sx={{ mb: 1, fontWeight: 600 }}>
                Chat-First Planning
              </Typography>
              <Typography sx={{ color: 'rgba(255, 244, 223, 0.78)' }}>
                Describe your ideal ride in natural language. &quot;Plan a 2-hour MTB loop with
                flow trails and minimal climbing&quot; - the AI handles the rest.
              </Typography>
            </Paper>
          </Grid>

          <Grid item xs={12} md={4}>
            <Paper
              sx={{
                p: 4,
                height: '100%',
                background: 'rgba(225, 61, 126, 0.12)',
                backdropFilter: 'blur(10px)',
              }}
            >
              <TerrainIcon sx={{ fontSize: 40, color: 'secondary.main', mb: 2 }} />
              <Typography variant="h6" sx={{ mb: 1, fontWeight: 600 }}>
                MTB-First Design
              </Typography>
              <Typography sx={{ color: 'rgba(255, 244, 223, 0.78)' }}>
                Trail difficulty ratings, surface analysis, hazard warnings, and
                technical feature detection. Built by riders, for riders.
              </Typography>
            </Paper>
          </Grid>

          <Grid item xs={12} md={4}>
            <Paper
              sx={{
                p: 4,
                height: '100%',
                background: 'rgba(247, 183, 51, 0.1)',
                backdropFilter: 'blur(10px)',
              }}
            >
              <MapIcon sx={{ fontSize: 40, color: 'warning.main', mb: 2 }} />
              <Typography variant="h6" sx={{ mb: 1, fontWeight: 600 }}>
                Professional Editing
              </Typography>
              <Typography sx={{ color: 'rgba(255, 244, 223, 0.78)' }}>
                Drag routes, lock segments, avoid areas. Full manual control when you
                need it, with snapping and validation built in.
              </Typography>
            </Paper>
          </Grid>
        </Grid>
      </Container>

      {/* Sport Types Section */}
      <Container maxWidth="lg" sx={{ py: 6 }}>
        <Typography
          variant="h4"
          textAlign="center"
          sx={{ mb: 4, fontWeight: 600, color: '#FFF4DF' }}
        >
          Built for Every Ride
        </Typography>

        <Grid container spacing={3}>
          {[
            {
              name: 'Road',
              desc: 'Optimized for pavement, bike lanes, and low-traffic routes',
              color: '#F7B733',
            },
            {
              name: 'Gravel',
              desc: 'Mix of surfaces, scenic backroads, and adventure routes',
              color: '#FFD86B',
            },
            {
              name: 'MTB',
              desc: 'Singletrack, trail systems, difficulty ratings, and features',
              color: '#E13D7E',
            },
            {
              name: 'eMTB',
              desc: 'Extended range planning with e-bike specific considerations',
              color: '#C97C1B',
            },
          ].map((sport) => (
            <Grid item xs={6} md={3} key={sport.name}>
              <Paper
                sx={{
                  p: 3,
                  textAlign: 'center',
                  background: 'rgba(43, 31, 26, 0.35)',
                }}
              >
                <Typography variant="h6" sx={{ fontWeight: 600, mb: 1 }}>
                  {sport.name}
                </Typography>
                <Typography variant="body2" sx={{ color: 'rgba(255, 244, 223, 0.78)' }}>
                  {sport.desc}
                </Typography>
              </Paper>
            </Grid>
          ))}
        </Grid>
      </Container>

      {/* CTA Section */}
      <Container maxWidth="sm" sx={{ py: 8, textAlign: 'center' }}>
        <Typography variant="h5" sx={{ mb: 2, fontWeight: 600, color: '#FFF4DF' }}>
          Ready to plan your next adventure?
        </Typography>
        <Button
          variant="contained"
          size="large"
          onClick={() => router.push('/planner')}
          sx={{ px: 6, py: 2 }}
        >
          Open Route Planner
        </Button>
      </Container>

      {/* Footer */}
      <Box
        sx={{
          py: 3,
          textAlign: 'center',
        }}
      >
        <Typography variant="body2" sx={{ color: 'rgba(255, 244, 223, 0.7)' }}>
          John Router - Built with quality and accuracy in mind
        </Typography>
      </Box>
    </Box>
  );
}
