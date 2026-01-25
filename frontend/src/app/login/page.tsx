'use client';

import { useState } from 'react';
import {
  Box,
  Button,
  Container,
  Paper,
  Stack,
  TextField,
  Typography,
  Alert,
  Link as MuiLink,
} from '@mui/material';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { usePreferencesStore } from '@/stores/preferencesStore';

export default function LoginPage() {
  const router = useRouter();
  const setAuthenticated = usePreferencesStore((state) => state.setAuthenticated);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorMessage(null);
    setIsLoading(true);

    try {
      const tokenResponse = await api.login(email.trim(), password);
      api.setAuthToken(tokenResponse.access_token);

      const user = await api.getCurrentUser();
      setAuthenticated({ userId: user.id, token: tokenResponse.access_token });
      router.push('/planner');
    } catch (error: any) {
      const message = error?.response?.data?.detail || 'Unable to sign in. Please try again.';
      setErrorMessage(message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        background: 'linear-gradient(135deg, #2B1F1A 0%, #4B1B2E 55%, #7A2C3D 100%)',
      }}
    >
      <Container maxWidth="sm">
        <Paper
          sx={{
            p: 4,
            borderRadius: 2,
            backgroundColor: '#FFF8F1',
            boxShadow: '0 12px 32px rgba(43, 31, 26, 0.2)',
          }}
        >
          <Stack spacing={3}>
            <Box>
              <Typography sx={{ fontSize: '1.75rem', fontWeight: 700 }}>
                Welcome back
              </Typography>
              <Typography sx={{ fontSize: '0.875rem', color: 'text.secondary', mt: 0.5 }}>
                Sign in to access your routes and preferences.
              </Typography>
            </Box>

            {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}

            <Box component="form" onSubmit={handleSubmit}>
              <Stack spacing={2}>
                <TextField
                  label="Email"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                  autoComplete="email"
                  fullWidth
                />
                <TextField
                  label="Password"
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  autoComplete="current-password"
                  fullWidth
                />
                <Button
                  type="submit"
                  variant="contained"
                  size="large"
                  disabled={isLoading}
                  sx={{ py: 1.5 }}
                >
                  {isLoading ? 'Signing in...' : 'Sign In'}
                </Button>
              </Stack>
            </Box>

            <Typography variant="body2" color="text.secondary">
              Don&apos;t have an account?{' '}
              <MuiLink component={Link} href="/register" underline="hover">
                Create one
              </MuiLink>
            </Typography>
          </Stack>
        </Paper>
      </Container>
    </Box>
  );
}
