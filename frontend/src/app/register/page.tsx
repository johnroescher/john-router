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

export default function RegisterPage() {
  const router = useRouter();
  const setAuthenticated = usePreferencesStore((state) => state.setAuthenticated);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorMessage(null);

    if (password !== confirmPassword) {
      setErrorMessage('Passwords do not match.');
      return;
    }

    setIsLoading(true);

    try {
      await api.register(email.trim(), password, name.trim() || undefined);
      const tokenResponse = await api.login(email.trim(), password);
      api.setAuthToken(tokenResponse.access_token);

      const user = await api.getCurrentUser();
      setAuthenticated({ userId: user.id, token: tokenResponse.access_token });
      router.push('/planner');
    } catch (error: any) {
      const message = error?.response?.data?.detail || 'Unable to create account. Please try again.';
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
              <Typography variant="h4" sx={{ fontWeight: 700 }}>
                Create your account
              </Typography>
              <Typography color="text.secondary">
                Get started with personalized route planning.
              </Typography>
            </Box>

            {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}

            <Box component="form" onSubmit={handleSubmit}>
              <Stack spacing={2}>
                <TextField
                  label="Name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  autoComplete="name"
                  fullWidth
                />
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
                  autoComplete="new-password"
                  fullWidth
                  helperText="Minimum 8 characters."
                />
                <TextField
                  label="Confirm Password"
                  type="password"
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  required
                  autoComplete="new-password"
                  fullWidth
                />
                <Button
                  type="submit"
                  variant="contained"
                  size="large"
                  disabled={isLoading}
                  sx={{ py: 1.5 }}
                >
                  {isLoading ? 'Creating account...' : 'Create Account'}
                </Button>
              </Stack>
            </Box>

            <Typography variant="body2" color="text.secondary">
              Already have an account?{' '}
              <MuiLink component={Link} href="/login" underline="hover">
                Sign in
              </MuiLink>
            </Typography>
          </Stack>
        </Paper>
      </Container>
    </Box>
  );
}
