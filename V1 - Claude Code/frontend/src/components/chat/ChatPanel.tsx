'use client';

import { useState, useRef, useEffect, type RefObject } from 'react';
import {
  Box,
  Typography,
  TextField,
  IconButton,
  Chip,
  CircularProgress,
} from '@mui/material';
import SendIcon from '@mui/icons-material/Send';
import { useChatStore } from '@/stores/chatStore';
import { useRouteStore } from '@/stores/routeStore';
import { usePlanningStore } from '@/stores/planningStore';
import { useUIStore } from '@/stores/uiStore';
import { useSurfaceStore } from '@/stores/surfaceStore';
import { api } from '@/lib/api';
import { normalizeSurfaceBreakdown } from '@/lib/surfaceMix';
import StatusMessage from './StatusMessage';
import type { ChatMessage, ActionChip, Route, StatusUpdate, RouteAnalysis, ElevationPoint } from '@/types';

const renderChipLabel = (label: string) => {
  const match = label.match(/^(\p{Extended_Pictographic}|\p{Emoji_Presentation})(?:\uFE0F|\uFE0E)?\s+(.*)$/u);
  if (!match) return label;
  const [, emoji, text] = match;
  return (
    <Box
      component="span"
      sx={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 1,
        flexWrap: 'wrap',
        width: '100%',
      }}
    >
      <Box
        component="span"
        sx={{
          fontSize: '1.2rem',
          lineHeight: 1,
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'flex-start',
          marginLeft: '-5px',
        }}
      >
        {emoji}
      </Box>
      <Box component="span" sx={{ flex: 1, minWidth: 0 }}>
        {text}
      </Box>
    </Box>
  );
};

function stripLeadingEmoji(text: string) {
  const match = text.match(/^(\p{Extended_Pictographic}|\p{Emoji_Presentation})(?:\uFE0F|\uFE0E)?\s+(.*)$/u);
  return match ? match[2] : text;
}

function MessageBubble({ message, onAction }: { message: ChatMessage; onAction: (chip: ActionChip) => void }) {
  const isUser = message.role === 'user';
  
  // Don't render status messages here - they're handled separately
  if (message.isStatus && message.statusUpdate) {
    return <StatusMessage status={message.statusUpdate} />;
  }

  return (
    <Box
      sx={{
        display: 'flex',
        justifyContent: isUser ? 'flex-end' : 'flex-start',
        mb: 1.5,
      }}
      data-testid={
        message.isStatus
          ? 'chat-message-status'
          : isUser
            ? 'chat-message-user'
            : 'chat-message-assistant'
      }
    >
      <Box
        sx={{
          py: 1.5,
          px: 2,
          maxWidth: '85%',
          bgcolor: isUser ? '#310909' : 'rgba(0, 0, 0, 0.04)',
          color: isUser ? '#FFFFFF' : 'text.primary',
          borderRadius: 2,
        }}
      >
        <Typography 
          sx={{ 
            fontSize: '0.8125rem', 
            whiteSpace: 'pre-wrap',
            lineHeight: 1.5,
          }}
        >
          {stripLeadingEmoji(message.content)}
        </Typography>

        {/* Action chips */}
        {message.actionChips && message.actionChips.length > 0 && (
          <Box sx={{ mt: 1.5, display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
            {message.actionChips.map((chip) => (
              <ActionChipButton key={chip.id} chip={chip} onAction={onAction} />
            ))}
          </Box>
        )}

      </Box>
    </Box>
  );
}

function ActionChipButton({ chip, onAction }: { chip: ActionChip; onAction: (chip: ActionChip) => void }) {
  const handleClick = () => {
    onAction(chip);
  };

  return (
    <Chip
      label={renderChipLabel(chip.label)}
      size="small"
      onClick={handleClick}
      sx={{ 
        cursor: 'pointer',
        fontSize: '0.75rem',
        height: 26,
        bgcolor: 'rgba(255,255,255,0.9)',
        color: 'primary.main',
        '&:hover': {
          bgcolor: 'primary.light',
          color: 'white',
        },
      }}
    />
  );
}

function SuggestedPrompts({
  onSend,
  scrollRootRef,
  mapCenter,
}: {
  onSend: (prompt: string) => void;
  scrollRootRef: RefObject<HTMLDivElement>;
  mapCenter: { lat: number; lng: number } | null;
}) {
  const { suggestedPrompts, appendSuggestedPrompts } = useChatStore();
  const loadMoreRef = useRef<HTMLDivElement>(null);
  const isLoadingMoreRef = useRef(false);

  useEffect(() => {
    isLoadingMoreRef.current = false;
  }, [suggestedPrompts.length]);

  useEffect(() => {
    const sentinel = loadMoreRef.current;
    if (!sentinel) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries[0]?.isIntersecting || isLoadingMoreRef.current) return;
        isLoadingMoreRef.current = true;
        appendSuggestedPrompts(mapCenter);
      },
      {
        root: scrollRootRef.current,
        rootMargin: '140px 0px',
        threshold: 0.1,
      }
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [appendSuggestedPrompts, mapCenter, scrollRootRef]);

  return (
    <Box
      sx={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: '10px',
        p: 0,
        pt: '34px',
      }}
      data-testid="suggested-prompts"
    >
      {suggestedPrompts.map((prompt, idx) => (
        <Chip
          key={idx}
          label={renderChipLabel(prompt)}
          size="small"
          data-testid="suggested-prompt"
          onClick={() => onSend(prompt)}
          sx={{ 
            cursor: 'pointer',
            fontSize: '0.75rem',
            height: 'auto',
            minHeight: 'unset',
            maxWidth: '100%',
            bgcolor: 'transparent',
            border: 'none',
            borderLeft: '3px solid #310909',
            borderRadius: 0,
            '& .MuiChip-label': {
              whiteSpace: 'normal',
              display: 'block',
              textAlign: 'left',
              lineHeight: 1.25,
              paddingTop: '8px',
              paddingBottom: '8px',
              paddingLeft: 2,
              paddingRight: 2,
            },
            '&:hover': {
              bgcolor: 'transparent',
            },
          }}
        />
      ))}
      <Box ref={loadMoreRef} sx={{ width: '100%', height: 1 }} />
    </Box>
  );
}

export default function ChatPanel() {
  const [inputValue, setInputValue] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const hasGeneratedPromptsRef = useRef(false);

  const {
    messages,
    isLoading,
    addMessage,
    setIsLoading,
    handleChatResponse,
    conversationId,
    updateStatusMessage,
    clearStatusMessage,
    setStatusMessageId,
    regenerateSuggestedPrompts,
  } = useChatStore();

  const { constraints, routeGeometry, currentRoute, setCandidates, setManualAnalysis } = useRouteStore();
  const { setPlanning } = usePlanningStore();
  const mapCenter = useUIStore((state) => state.mapCenter);
  const setSegmentedSurface = useSurfaceStore((state) => state.setSegmentedSurface);

  const sendChatMessage = async (message: string) => {
    if (!message.trim() || isLoading) return;

    addMessage({
      role: 'user',
      content: message,
      timestamp: new Date().toISOString(),
    });

    const statusMessageId = String(messages.length);
    const initialStatus: StatusUpdate = {
      stage: 'starting',
      message: 'Starting...',
      timestamp: new Date().toISOString(),
    };
    addMessage({
      role: 'assistant',
      content: initialStatus.message,
      timestamp: new Date().toISOString(),
      isStatus: true,
      statusUpdate: initialStatus,
    });
    setStatusMessageId(statusMessageId);

    setIsLoading(true);

    try {
      const response = await api.sendMessageStream(
        {
          message,
          conversationId: conversationId || undefined,
          routeId: currentRoute?.id,
          currentConstraints: constraints,
          currentRouteGeometry: routeGeometry || undefined,
          mapCenter: mapCenter ? { lat: mapCenter.lat, lng: mapCenter.lng } : undefined,
          qualityMode: true,
          explainMode: true,
        },
        (status: StatusUpdate) => {
          updateStatusMessage(statusMessageId, status);
        }
      );

      clearStatusMessage(statusMessageId);
      handleChatResponse(response);

      if (response.planning) {
        setPlanning(response.planning);
      }
      if (response.routeCandidates && response.routeCandidates.length > 0) {
        setCandidates(response.routeCandidates);
      }

      if (response.routeUpdated && response.routeData) {
        const surfaceData = normalizeSurfaceBreakdown(response.routeData.surface_breakdown);
        const routeFromChat: Route = {
          id: response.routeId || 'generated',
          name: 'Generated Route',
          sportType: response.routeData.sport_type as 'road' | 'gravel' | 'mtb' | 'emtb',
          geometry: response.routeData.geometry,
          distanceMeters: response.routeData.distance_meters,
          elevationGainMeters: response.routeData.elevation_gain,
          estimatedTimeSeconds: response.routeData.duration_seconds,
          surfaceBreakdown: surfaceData,
          mtbDifficultyBreakdown: { green: 0, blue: 0, black: 0, double_black: 0, unknown: 1 },
          tags: [],
          isPublic: false,
          confidenceScore: 0.8,
          validationStatus: 'pending',
          validationResults: { status: 'valid' as const, errors: [], warnings: [], info: [], confidenceScore: 0.8 },
          waypoints: [],
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        };
        useRouteStore.getState().setCurrentRoute(routeFromChat);

        if (response.routeData.segmented_surface) {
          setSegmentedSurface(response.routeData.segmented_surface);
        } else {
          setSegmentedSurface(null);
        }

        if (response.routeData.elevation_profile && response.routeData.elevation_profile.length > 0) {
          const profile = response.routeData.elevation_profile as ElevationPoint[];
          const elevations = profile.map((p) => p.elevationMeters);
          const grades = profile.map((p) => Math.abs(p.gradePercent || 0));
          const maxElevation = Math.max(...elevations);
          const minElevation = Math.min(...elevations);
          const avgGradePercent = grades.length ? grades.reduce((a, b) => a + b, 0) / grades.length : 0;
          const maxGradePercent = grades.length ? Math.max(...grades) : 0;

          const elevationLossMeters = profile.reduce((sum, point, idx) => {
            if (idx === 0) return 0;
            const prev = profile[idx - 1];
            const diff = (prev.elevationMeters || 0) - (point.elevationMeters || 0);
            return sum + (diff > 0 ? diff : 0);
          }, 0);

          const analysis: RouteAnalysis = {
            distanceMeters: response.routeData.distance_meters,
            elevationGainMeters: response.routeData.elevation_gain,
            elevationLossMeters,
            estimatedTimeSeconds: response.routeData.duration_seconds,
            maxElevationMeters: maxElevation,
            minElevationMeters: minElevation,
            avgGradePercent,
            maxGradePercent,
            longestClimbMeters: 0,
            steepest100mPercent: maxGradePercent,
            steepest1kmPercent: maxGradePercent,
            climbingAbove8PercentMeters: 0,
            surfaceBreakdown: surfaceData,
            mtbDifficultyBreakdown: { green: 0, blue: 0, black: 0, double_black: 0, unknown: 100 },
            maxTechnicalRating: undefined,
            hikeABikeSections: 0,
            hikeABikeDistanceMeters: 0,
            physicalDifficulty: 0,
            technicalDifficulty: 0,
            riskRating: 0,
            overallDifficulty: 0,
            elevationProfile: profile,
            confidenceScore: 0.5,
            dataCompleteness: 0.5,
          };
          setManualAnalysis(analysis);
        } else {
          setManualAnalysis(null);
        }

        const coords = response.routeData.geometry?.coordinates;
        if (coords && coords.length > 0) {
          let minLng = Infinity, maxLng = -Infinity;
          let minLat = Infinity, maxLat = -Infinity;
          for (const coord of coords) {
            const [lng, lat] = coord;
            if (lng < minLng) minLng = lng;
            if (lng > maxLng) maxLng = lng;
            if (lat < minLat) minLat = lat;
            if (lat > maxLat) maxLat = lat;
          }
          useUIStore.getState().fitMapToBounds({ minLng, minLat, maxLng, maxLat, reason: 'chat_route' });
        }
      }
    } catch (error) {
      console.error('Failed to send message:', error);
      clearStatusMessage(statusMessageId);
      addMessage({
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please try again.',
        timestamp: new Date().toISOString(),
      });
    } finally {
      setIsLoading(false);
    }
  };

  // Generate prompts only once per page load/session.
  useEffect(() => {
    if (hasGeneratedPromptsRef.current) return;
    if (messages.length === 0) {
      regenerateSuggestedPrompts(mapCenter);
      hasGeneratedPromptsRef.current = true;
    }
  }, [messages.length, mapCenter, regenerateSuggestedPrompts]);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    if (!inputValue.trim() || isLoading) return;

    const message = inputValue.trim();
    setInputValue('');
    await sendChatMessage(message);
  };

  const handleActionChip = async (chip: ActionChip) => {
    if (chip.action === 'send_message' && typeof chip.data?.message === 'string') {
      await sendChatMessage(chip.data.message);
      return;
    }
    await sendChatMessage(chip.label);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Messages area */}
      <Box
        ref={messagesContainerRef}
        sx={{
          flex: 1,
          overflow: 'auto',
          px: 3,
          py: 2,
          maskImage:
            'linear-gradient(to bottom, rgba(0,0,0,1) 0%, rgba(0,0,0,1) calc(100% - 70px), rgba(0,0,0,0) 100%)',
          WebkitMaskImage:
            'linear-gradient(to bottom, rgba(0,0,0,1) 0%, rgba(0,0,0,1) calc(100% - 70px), rgba(0,0,0,0) 100%)',
        }}
      >
        {messages.length === 0 ? (
          <Box
            sx={{
              textAlign: 'left',
              py: 1,
              px: 0,
            }}
          >
            <SuggestedPrompts onSend={sendChatMessage} scrollRootRef={messagesContainerRef} mapCenter={mapCenter} />
          </Box>
        ) : (
          <>
            {messages.map((msg, idx) => (
              <MessageBubble key={idx} message={msg} onAction={handleActionChip} />
            ))}
            <div ref={messagesEndRef} />
          </>
        )}
      </Box>

      {/* Input area */}
      <Box
        sx={{
          px: 3,
          pt: '18px',
          pb: 3,
        }}
      >
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-end' }}>
          <TextField
            fullWidth
            multiline
            maxRows={4}
            placeholder="Describe your ideal ride..."
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={handleKeyPress}
            disabled={isLoading}
            size="small"
            sx={{
              '& .MuiOutlinedInput-root': {
                bgcolor: 'transparent',
                borderLeft: '3px solid #310909',
                borderRadius: 0,
                color: 'text.primary',
                fontSize: '0.75rem',
                lineHeight: 1.25,
                fontWeight: 500,
                '& .MuiInputBase-input': {
                  color: 'inherit',
                  fontWeight: 'inherit',
                  '&::placeholder': {
                    color: 'inherit',
                    opacity: 0.8,
                  },
                },
                '& textarea': {
                  color: 'inherit',
                  fontWeight: 'inherit',
                },
                '&:hover': {
                  bgcolor: 'rgba(0, 0, 0, 0.04)',
                  color: 'text.primary',
                  '& .MuiInputBase-input': {
                    color: 'inherit',
                  },
                  '& textarea': {
                    color: 'inherit',
                  },
                  '& .MuiInputBase-input::placeholder': {
                    color: 'inherit',
                  },
                },
                '& fieldset': {
                  border: 'none',
                  borderRadius: 0,
                },
                '&:hover fieldset': {
                  border: 'none',
                  borderRadius: 0,
                },
                '&.Mui-focused fieldset': {
                  border: 'none',
                  borderRadius: 0,
                },
              },
            }}
          />

          <IconButton
            onClick={handleSend}
            disabled={!inputValue.trim() || isLoading}
            sx={{
              bgcolor: '#FF38AB',
              color: '#000000',
              width: 36,
              height: 36,
              '&:hover': { bgcolor: '#FF38AB' },
              '& .MuiSvgIcon-root': {
                color: '#000000',
              },
              '&.Mui-disabled': { 
                bgcolor: '#FF38AB',
                color: '#000000',
              },
            }}
          >
            <SendIcon sx={{ fontSize: 18, color: '#000000' }} />
          </IconButton>
        </Box>
      </Box>
    </Box>
  );
}
