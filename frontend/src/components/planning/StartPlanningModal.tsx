'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  Bot,
  Sliders,
  Sparkles,
  Calendar,
  DollarSign,
  MapPin,
  Clock,
  ArrowRight,
  ArrowLeft,
  CheckCircle2,
  AlertCircle,
  Loader2,
  HelpCircle,
} from 'lucide-react';
import { eventsApi, aiApi } from '@/lib/api';
import { EventRecord, EventType } from '@/types';

interface StartPlanningModalProps {
  isOpen: boolean;
  onClose: () => void;
  onEventCreated: (event: EventRecord) => void;
}

type PlanningMode = 'select' | 'ai' | 'wizard';

const EVENT_TYPES: EventType[] = [
  'conference',
  'hackathon',
  'meetup',
  'corporate',
  'concert',
  'exhibition',
  'wedding',
  'other',
];

interface InspirationPreset {
  chip: string;
  label: string;
  title: string;
  eventType: EventType;
  prompt: string;
  budget: string;
  attendees: string;
}

const INSPIRATION_PRESETS: InspirationPreset[] = [
  {
    chip: '🚀 Tech Conference',
    label: 'Tech Conference',
    title: 'DevCon AI Global Summit 2026',
    eventType: 'conference',
    prompt:
      'A 2-day developer conference in San Francisco for 400 attendees with a $65,000 budget. Need keynote slots, hands-on workshop breakout tracks, and an evening rooftop networking mixer.',
    budget: '65000',
    attendees: '400',
  },
  {
    chip: '💻 Hackathon',
    label: 'Hackathon',
    title: 'Autonomous AI Hackathon 2026',
    eventType: 'hackathon',
    prompt:
      'A 48-hour autonomous AI hackathon for 250 engineers with a $30,000 budget. Requires 24/7 venue access, gigabit internet, catered meals, and mentor breakout stages.',
    budget: '30000',
    attendees: '250',
  },
  {
    chip: '🌟 Charity Gala',
    label: 'Charity Gala',
    title: 'Horizon Foundation Charity Gala 2026',
    eventType: 'corporate',
    prompt:
      'An annual black-tie charity fundraising gala for 300 guests with an $80,000 target budget. Features a silent auction, keynote addresses, 3-course plated dinner, and champagne reception.',
    budget: '80000',
    attendees: '300',
  },
];

// Helper to calculate sensible default ISO datetimes
function getDefaultDates() {
  const start = new Date();
  start.setDate(start.getDate() + 30);
  start.setHours(9, 0, 0, 0);

  const end = new Date(start);
  end.setDate(end.getDate() + 2);
  end.setHours(18, 0, 0, 0);

  // Format to YYYY-MM-DDTHH:mm for datetime-local
  const formatLocal = (d: Date) => {
    const pad = (n: number) => n.toString().padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  };

  return {
    startStr: formatLocal(start),
    endStr: formatLocal(end),
  };
}

export function StartPlanningModal({ isOpen, onClose, onEventCreated }: StartPlanningModalProps) {
  const [mode, setMode] = useState<PlanningMode>('select');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [loadingStatus, setLoadingStatus] = useState<string>('');

  // --------------------------------------------------------------------------
  // Option A (AI Conversational) Form State
  // --------------------------------------------------------------------------
  const [aiPrompt, setAiPrompt] = useState('');
  const [aiTitle, setAiTitle] = useState('');
  const [aiEventType, setAiEventType] = useState<EventType>('conference');
  const [aiBudget, setAiBudget] = useState('');
  const [aiAttendees, setAiAttendees] = useState('');
  const [aiStartDate, setAiStartDate] = useState<string>(() => getDefaultDates().startStr);
  const [aiEndDate, setAiEndDate] = useState<string>(() => getDefaultDates().endStr);

  // --------------------------------------------------------------------------
  // Option B (Guided Wizard) Form State
  // --------------------------------------------------------------------------
  const [wizardStep, setWizardStep] = useState<number>(1);
  const [wTitle, setWTitle] = useState('');
  const [wEventType, setWEventType] = useState<EventType>('conference');
  const [wTimezone, setWTimezone] = useState('UTC');
  const [wStartDate, setWStartDate] = useState<string>(() => getDefaultDates().startStr);
  const [wEndDate, setWEndDate] = useState<string>(() => getDefaultDates().endStr);

  const [wCurrency, setWCurrency] = useState('USD');
  const [wBudget, setWBudget] = useState('');
  const [wAttendees, setWAttendees] = useState('');

  const [wDescription, setWDescription] = useState('');
  const [wCity, setWCity] = useState('');
  const [wFocus, setWFocus] = useState('Keynotes & Workshops');

  const handleModalClose = useCallback(() => {
    if (submitting) return;
    setMode('select');
    setWizardStep(1);
    setError(null);
    setAiPrompt('');
    setAiTitle('');
    onClose();
  }, [submitting, onClose]);

  // Handle Escape key to close
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !submitting) {
        handleModalClose();
      }
    };
    if (isOpen) {
      window.addEventListener('keydown', handleKeyDown);
    }
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, submitting, handleModalClose]);

  if (!isOpen) return null;

  const applyInspirationPreset = (preset: InspirationPreset) => {
    setAiPrompt(preset.prompt);
    setAiTitle(preset.title);
    setAiEventType(preset.eventType);
    setAiBudget(preset.budget);
    setAiAttendees(preset.attendees);
  };

  // --------------------------------------------------------------------------
  // Submit: Option A (Describe Your Event with Gemini AI)
  // --------------------------------------------------------------------------
  const handleAiPlanningSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!aiTitle.trim()) {
      setError('Please provide an event title (or click an inspiration chip above).');
      return;
    }
    if (!aiStartDate || !aiEndDate) {
      setError('Start date and end date are required.');
      return;
    }
    if (new Date(aiEndDate) < new Date(aiStartDate)) {
      setError('End date cannot be earlier than start date.');
      return;
    }

    setSubmitting(true);
    setError(null);
    setLoadingStatus('Creating event workspace in database...');

    try {
      // 1. Create Event Record
      const eventRes = await eventsApi.create({
        title: aiTitle.trim(),
        event_type: aiEventType,
        description: aiPrompt.trim() || null,
        start_date: new Date(aiStartDate).toISOString(),
        end_date: new Date(aiEndDate).toISOString(),
        timezone: 'UTC',
        expected_attendees: aiAttendees ? parseInt(aiAttendees, 10) : null,
        target_budget: aiBudget ? parseFloat(aiBudget) : null,
        currency: 'USD',
        status: 'planning',
      });

      if (!eventRes.success || !eventRes.data) {
        throw new Error(eventRes.error?.message || 'Failed to initialize event workspace.');
      }

      const createdEvent = eventRes.data;

      // 2. Trigger Gemini AI Master Plan Synthesis
      setLoadingStatus('Gemini is architecting your master plan, schedule, and budget...');
      try {
        await aiApi.planEvent({
          event_id: createdEvent.id,
          prompt_context: {
            user_notes: aiPrompt.trim() || `Plan a ${aiEventType} titled ${createdEvent.title}`,
          },
          change_summary: 'Initial dual-path AI conversational master plan generation',
        });
      } catch (aiErr) {
        console.warn('AI initial plan generation warning:', aiErr);
        // Do not fail event creation if AI timed out; cockpit has manual re-generate button
      }

      // 3. Complete and launch cockpit
      setLoadingStatus('Finalizing cockpit launch...');
      onEventCreated(createdEvent);
      handleModalClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error launching AI event plan.');
    } finally {
      setSubmitting(false);
      setLoadingStatus('');
    }
  };

  // --------------------------------------------------------------------------
  // Submit: Option B (Guided 4-Step Wizard)
  // --------------------------------------------------------------------------
  const handleWizardNext = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (wizardStep === 1) {
      if (!wTitle.trim()) {
        setError('Event title is required.');
        return;
      }
      if (!wStartDate || !wEndDate) {
        setError('Start date and end date are required.');
        return;
      }
      if (new Date(wEndDate) < new Date(wStartDate)) {
        setError('End date cannot be earlier than start date.');
        return;
      }
      setWizardStep(2);
    } else if (wizardStep === 2) {
      if (wBudget && parseFloat(wBudget) < 0) {
        setError('Target budget cannot be negative.');
        return;
      }
      if (wAttendees && parseInt(wAttendees, 10) < 1) {
        setError('Expected attendees must be at least 1.');
        return;
      }
      setWizardStep(3);
    } else if (wizardStep === 3) {
      setWizardStep(4);
    }
  };

  const handleWizardSubmit = async () => {
    setSubmitting(true);
    setError(null);
    setLoadingStatus('Creating customized event cockpit...');

    try {
      const fullDescription = [
        wDescription.trim(),
        wCity.trim() ? `Target Location: ${wCity.trim()}` : '',
        wFocus.trim() ? `Primary Focus: ${wFocus.trim()}` : '',
      ]
        .filter(Boolean)
        .join(' • ');

      const res = await eventsApi.create({
        title: wTitle.trim(),
        event_type: wEventType,
        description: fullDescription || null,
        start_date: new Date(wStartDate).toISOString(),
        end_date: new Date(wEndDate).toISOString(),
        timezone: wTimezone.trim() || 'UTC',
        expected_attendees: wAttendees ? parseInt(wAttendees, 10) : null,
        target_budget: wBudget ? parseFloat(wBudget) : null,
        currency: wCurrency.trim().toUpperCase() || 'USD',
        status: 'draft',
      });

      if (!res.success || !res.data) {
        throw new Error(res.error?.message || 'Failed to create event.');
      }

      onEventCreated(res.data);
      handleModalClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error creating event via wizard.');
    } finally {
      setSubmitting(false);
      setLoadingStatus('');
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="planning-modal-title"
      className="fixed inset-0 z-50 bg-[#202124]/50 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto"
    >
      <div className="w-full max-w-3xl rounded-2xl bg-white border border-[#E8EAED] p-6 sm:p-8 space-y-6 shadow-2xl my-8">
        {/* ===================================================================
            MODAL HEADER
            =================================================================== */}
        <div className="flex items-start justify-between pb-4 border-b border-[#E8EAED]">
          <div>
            <div className="flex items-center gap-2">
              {mode !== 'select' && (
                <button
                  type="button"
                  onClick={() => {
                    setError(null);
                    if (mode === 'wizard' && wizardStep > 1) {
                      setWizardStep(wizardStep - 1);
                    } else {
                      setMode('select');
                      setWizardStep(1);
                    }
                  }}
                  className="p-1 rounded-lg hover:bg-[#F1F3F4] text-[#5F6368] hover:text-[#202124] transition-colors"
                  aria-label="Back"
                >
                  <ArrowLeft className="w-4 h-4" />
                </button>
              )}
              <h3 id="planning-modal-title" className="font-bold text-[#202124] text-lg sm:text-xl tracking-tight">
                {mode === 'select' && 'Start Planning Your Event'}
                {mode === 'ai' && 'Option A: Describe Your Event (AI Planner)'}
                {mode === 'wizard' && `Option B: Guided Wizard (Step ${wizardStep} of 4)`}
              </h3>
            </div>
            <p className="text-xs text-[#5F6368] mt-1">
              {mode === 'select' &&
                'Choose how you want to begin. Both options launch a full event cockpit with complete AI tooling and manual controls.'}
              {mode === 'ai' &&
                'Provide a natural language brief. Gemini AI will synthesize your timeline, venue requirements, and budget allocations.'}
              {mode === 'wizard' &&
                'Configure your event step-by-step with guided validation and parameter control.'}
            </p>
          </div>
          <button
            onClick={handleModalClose}
            disabled={submitting}
            className="text-[#5F6368] hover:text-[#202124] text-sm p-1.5 rounded-lg hover:bg-[#F1F3F4] transition-colors"
            aria-label="Close dialog"
          >
            ✕
          </button>
        </div>

        {/* Global Error Banner */}
        {error && (
          <div role="alert" className="p-3.5 rounded-xl bg-[#FCE8E6] border border-[#FAD2CF] text-[#C5221F] text-xs flex items-start gap-2.5">
            <AlertCircle className="w-4 h-4 text-[#C5221F] shrink-0 mt-0.5" />
            <span className="font-medium">{error}</span>
          </div>
        )}

        {/* ===================================================================
            SCREEN 1: DUAL-CHOICE SELECTION (EQUAL VISUAL WEIGHT)
            =================================================================== */}
        {mode === 'select' && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              {/* Choice 1: Describe your event (AI Conversational) */}
              <div
                onClick={() => setMode('ai')}
                className="card-google p-6 flex flex-col justify-between cursor-pointer border-[#E8EAED] hover:border-[#1A73E8] hover:shadow-md transition-all group"
              >
                <div className="space-y-4">
                  <div className="flex items-start justify-between">
                    <div className="p-3 rounded-2xl bg-[#E8F0FE] text-[#1A73E8] border border-[#D2E3FC] shadow-sm">
                      <Bot className="w-6 h-6" />
                    </div>
                    <span className="badge-champagne text-[11px] font-bold">
                      Conversational AI
                    </span>
                  </div>

                  <div className="space-y-1.5">
                    <h4 className="font-bold text-base text-[#202124] group-hover:text-[#1A73E8] transition-colors">
                      Describe your event
                    </h4>
                    <p className="text-xs text-[#5F6368] leading-relaxed">
                      Write your vision in plain English. Gemini AI will analyze your goals, auto-generate themes, run-of-show schedules, and budget allocations.
                    </p>
                  </div>

                  <ul className="space-y-2 text-xs text-[#5F6368] pt-2 border-t border-[#E8EAED]">
                    <li className="flex items-center gap-2">
                      <Sparkles className="w-3.5 h-3.5 text-[#8C6D3F] shrink-0" />
                      <span>Inspiration chips for instant scaffolding</span>
                    </li>
                    <li className="flex items-center gap-2">
                      <Clock className="w-3.5 h-3.5 text-[#1A73E8] shrink-0" />
                      <span>Synthesized chronological schedule</span>
                    </li>
                    <li className="flex items-center gap-2">
                      <DollarSign className="w-3.5 h-3.5 text-[#137333] shrink-0" />
                      <span>Automated budget contingency allocation</span>
                    </li>
                  </ul>
                </div>

                <div className="pt-6">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setMode('ai');
                    }}
                    className="btn-primary w-full py-2.5 justify-center"
                  >
                    Start with AI Architect <ArrowRight className="w-4 h-4 ml-1" />
                  </button>
                </div>
              </div>

              {/* Choice 2: Build my plan step by step (Guided Wizard) */}
              <div
                onClick={() => setMode('wizard')}
                className="card-google p-6 flex flex-col justify-between cursor-pointer border-[#E8EAED] hover:border-[#1A73E8] hover:shadow-md transition-all group"
              >
                <div className="space-y-4">
                  <div className="flex items-start justify-between">
                    <div className="p-3 rounded-2xl bg-[#E6F4EA] text-[#137333] border border-[#CEEAD6] shadow-sm">
                      <Sliders className="w-6 h-6" />
                    </div>
                    <span className="badge-blue text-[11px] font-bold">
                      Guided Wizard
                    </span>
                  </div>

                  <div className="space-y-1.5">
                    <h4 className="font-bold text-base text-[#202124] group-hover:text-[#1A73E8] transition-colors">
                      Build my plan step by step
                    </h4>
                    <p className="text-xs text-[#5F6368] leading-relaxed">
                      Follow a structured 4-step wizard to configure your dates, budget targets, attendee caps, and venue requirements with granular control.
                    </p>
                  </div>

                  <ul className="space-y-2 text-xs text-[#5F6368] pt-2 border-t border-[#E8EAED]">
                    <li className="flex items-center gap-2">
                      <Calendar className="w-3.5 h-3.5 text-[#1A73E8] shrink-0" />
                      <span>Step 1: Basics, Dates & Timezone</span>
                    </li>
                    <li className="flex items-center gap-2">
                      <DollarSign className="w-3.5 h-3.5 text-[#137333] shrink-0" />
                      <span>Step 2: Budget Ceiling & Capacity</span>
                    </li>
                    <li className="flex items-center gap-2">
                      <MapPin className="w-3.5 h-3.5 text-[#8C6D3F] shrink-0" />
                      <span>Step 3: Venue & Vibe Specifications</span>
                    </li>
                    <li className="flex items-center gap-2">
                      <CheckCircle2 className="w-3.5 h-3.5 text-[#1A73E8] shrink-0" />
                      <span>Step 4: Review & Direct Launch</span>
                    </li>
                  </ul>
                </div>

                <div className="pt-6">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setMode('wizard');
                    }}
                    className="btn-outline w-full py-2.5 justify-center border-[#1A73E8] text-[#1A73E8] hover:bg-[#E8F0FE]"
                  >
                    Open Step-by-Step Wizard <ArrowRight className="w-4 h-4 ml-1" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ===================================================================
            SCREEN 2: OPTION A — "DESCRIBE YOUR EVENT" (CONVERSATIONAL AI)
            =================================================================== */}
        {mode === 'ai' && (
          <form onSubmit={handleAiPlanningSubmit} className="space-y-5">
            {/* Inspiration Chips */}
            <div className="space-y-2">
              <span className="text-xs font-semibold text-[#5F6368]">
                Select an Inspiration Preset (or type your own below):
              </span>
              <div className="flex flex-wrap gap-2">
                {INSPIRATION_PRESETS.map((preset) => (
                  <button
                    key={preset.label}
                    type="button"
                    onClick={() => applyInspirationPreset(preset)}
                    className="badge-champagne text-xs py-1.5 px-3 hover:bg-[#ECE0D2] transition-colors cursor-pointer"
                  >
                    {preset.chip}
                  </button>
                ))}
              </div>
            </div>

            {/* Prompt Textarea */}
            <div>
              <label className="block text-xs font-semibold text-[#202124] mb-1.5">
                Event Vision, Themes & Constraints *
              </label>
              <textarea
                rows={3}
                required
                value={aiPrompt}
                onChange={(e) => {
                  setAiPrompt(e.target.value);
                  if (!aiTitle && e.target.value.length > 5) {
                    setAiTitle(e.target.value.slice(0, 40) + '...');
                  }
                }}
                placeholder="e.g. Plan a 2-day developer summit in Austin for 400 attendees with a $75k budget. Emphasize developer workshops, edge computing, and rooftop networking."
                className="input-google leading-relaxed"
              />
            </div>

            {/* Event Name & Quick Defaults */}
            <div className="p-4 rounded-xl bg-[#F8F9FA] border border-[#E8EAED] space-y-3.5">
              <span className="text-xs font-bold text-[#202124] block">
                Workspace Parameters:
              </span>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-[#202124] mb-1">Event Title *</label>
                  <input
                    type="text"
                    required
                    value={aiTitle}
                    onChange={(e) => setAiTitle(e.target.value)}
                    placeholder="e.g. DevCon AI Summit 2026"
                    className="input-google"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-[#202124] mb-1">Event Type</label>
                  <select
                    value={aiEventType}
                    onChange={(e) => setAiEventType(e.target.value as EventType)}
                    className="input-google capitalize"
                  >
                    {EVENT_TYPES.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-[#202124] mb-1">Budget ($)</label>
                  <input
                    type="number"
                    min="0"
                    placeholder="75000"
                    value={aiBudget}
                    onChange={(e) => setAiBudget(e.target.value)}
                    className="input-google"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-[#202124] mb-1">Attendees</label>
                  <input
                    type="number"
                    min="1"
                    placeholder="400"
                    value={aiAttendees}
                    onChange={(e) => setAiAttendees(e.target.value)}
                    className="input-google"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-[#202124] mb-1">Start Date *</label>
                  <input
                    type="datetime-local"
                    required
                    value={aiStartDate}
                    onChange={(e) => setAiStartDate(e.target.value)}
                    className="input-google text-xs"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-[#202124] mb-1">End Date *</label>
                  <input
                    type="datetime-local"
                    required
                    value={aiEndDate}
                    onChange={(e) => setAiEndDate(e.target.value)}
                    className="input-google text-xs"
                  />
                </div>
              </div>
            </div>

            {/* Submit Action */}
            <div className="pt-2 flex flex-col sm:flex-row items-center justify-between gap-3 border-t border-[#E8EAED]">
              <button
                type="button"
                onClick={() => setMode('select')}
                disabled={submitting}
                className="btn-ghost order-2 sm:order-1"
              >
                &larr; Back to Choices
              </button>

              <div className="flex items-center gap-3 order-1 sm:order-2 w-full sm:w-auto">
                {submitting && (
                  <span className="text-xs text-[#1A73E8] flex items-center gap-1.5 font-medium animate-pulse motion-reduce:animate-none">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    {loadingStatus}
                  </span>
                )}
                <button
                  type="submit"
                  disabled={submitting}
                  className="btn-primary w-full sm:w-auto"
                >
                  <Sparkles className="w-4 h-4 text-[#FFFFFF]" />
                  Generate Plan & Launch Cockpit
                </button>
              </div>
            </div>
          </form>
        )}

        {/* ===================================================================
            SCREEN 3: OPTION B — "BUILD MY PLAN STEP BY STEP" (GUIDED WIZARD)
            =================================================================== */}
        {mode === 'wizard' && (
          <div className="space-y-6">
            {/* Step Progress Header */}
            <div className="space-y-2">
              <div className="flex justify-between text-xs text-[#5F6368] font-semibold">
                <span>Step {wizardStep} of 4: {
                  wizardStep === 1 ? 'Basics & Dates' :
                  wizardStep === 2 ? 'Budget & Capacity' :
                  wizardStep === 3 ? 'Venue & Vibe' : 'Review & Launch'
                }</span>
                <span>{wizardStep * 25}% Completed</span>
              </div>
              <div className="w-full h-1.5 rounded-full bg-[#E8EAED] overflow-hidden">
                <div
                  className="h-full bg-[#1A73E8] transition-all duration-300"
                  style={{ width: `${wizardStep * 25}%` }}
                />
              </div>
            </div>

            {/* ---------------------------------------------------------------
                Step 1: Basics & Dates
                --------------------------------------------------------------- */}
            {wizardStep === 1 && (
              <form onSubmit={handleWizardNext} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-[#202124] mb-1">Event Title *</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. NextGen Web & Cloud Summit 2026"
                    value={wTitle}
                    onChange={(e) => setWTitle(e.target.value)}
                    className="input-google"
                  />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-[#202124] mb-1">Event Type *</label>
                    <select
                      value={wEventType}
                      onChange={(e) => setWEventType(e.target.value as EventType)}
                      className="input-google capitalize"
                    >
                      {EVENT_TYPES.map((t) => (
                        <option key={t} value={t}>{t}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[#202124] mb-1">Timezone</label>
                    <input
                      type="text"
                      placeholder="UTC"
                      value={wTimezone}
                      onChange={(e) => setWTimezone(e.target.value)}
                      className="input-google"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-[#202124] mb-1">Start Date & Time *</label>
                    <input
                      type="datetime-local"
                      required
                      value={wStartDate}
                      onChange={(e) => setWStartDate(e.target.value)}
                      className="input-google"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[#202124] mb-1">End Date & Time *</label>
                    <input
                      type="datetime-local"
                      required
                      value={wEndDate}
                      onChange={(e) => setWEndDate(e.target.value)}
                      className="input-google"
                    />
                  </div>
                </div>

                <div className="pt-3 flex justify-between items-center border-t border-[#E8EAED]">
                  <button
                    type="button"
                    onClick={() => setMode('select')}
                    className="btn-ghost"
                  >
                    &larr; Back to Choices
                  </button>
                  <button type="submit" className="btn-primary">
                    Next: Budget & Capacity &rarr;
                  </button>
                </div>
              </form>
            )}

            {/* ---------------------------------------------------------------
                Step 2: Budget & Capacity
                --------------------------------------------------------------- */}
            {wizardStep === 2 && (
              <form onSubmit={handleWizardNext} className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-[#202124] mb-1">Currency</label>
                    <input
                      type="text"
                      maxLength={3}
                      placeholder="USD"
                      value={wCurrency}
                      onChange={(e) => setWCurrency(e.target.value.toUpperCase())}
                      className="input-google uppercase font-mono"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[#202124] mb-1">Target Budget</label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      placeholder="50000"
                      value={wBudget}
                      onChange={(e) => setWBudget(e.target.value)}
                      className="input-google"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[#202124] mb-1">Expected Attendees</label>
                    <input
                      type="number"
                      min="1"
                      placeholder="300"
                      value={wAttendees}
                      onChange={(e) => setWAttendees(e.target.value)}
                      className="input-google"
                    />
                  </div>
                </div>

                {/* Helpful Budget Advice Card */}
                <div className="p-3.5 rounded-xl bg-[#E8F0FE] border border-[#D2E3FC] text-xs text-[#1A73E8] flex items-start gap-2.5">
                  <HelpCircle className="w-4 h-4 shrink-0 mt-0.5" />
                  <p className="leading-relaxed text-[11px]">
                    Setting a realistic budget ceiling enables EventPilot AI to automatically enforce a 15–20% contingency buffer and alert you when venue proposals exceed target ceilings.
                  </p>
                </div>

                <div className="pt-3 flex justify-between items-center border-t border-[#E8EAED]">
                  <button
                    type="button"
                    onClick={() => setWizardStep(1)}
                    className="btn-ghost"
                  >
                    &larr; Back to Basics
                  </button>
                  <button type="submit" className="btn-primary">
                    Next: Venue & Vibe &rarr;
                  </button>
                </div>
              </form>
            )}

            {/* ---------------------------------------------------------------
                Step 3: Venue & Vibe
                --------------------------------------------------------------- */}
            {wizardStep === 3 && (
              <form onSubmit={handleWizardNext} className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-[#202124] mb-1">Preferred City / Region</label>
                    <input
                      type="text"
                      placeholder="e.g. Austin, Texas or Remote / Hybrid"
                      value={wCity}
                      onChange={(e) => setWCity(e.target.value)}
                      className="input-google"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[#202124] mb-1">Primary Program Focus</label>
                    <input
                      type="text"
                      placeholder="e.g. Keynotes, Interactive Labs, Networking"
                      value={wFocus}
                      onChange={(e) => setWFocus(e.target.value)}
                      className="input-google"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-[#202124] mb-1">
                    Event Description & Atmosphere Goals
                  </label>
                  <textarea
                    rows={3}
                    placeholder="Describe the desired attendee experience, catering style, or stage requirements..."
                    value={wDescription}
                    onChange={(e) => setWDescription(e.target.value)}
                    className="input-google"
                  />
                </div>

                <div className="pt-3 flex justify-between items-center border-t border-[#E8EAED]">
                  <button
                    type="button"
                    onClick={() => setWizardStep(2)}
                    className="btn-ghost"
                  >
                    &larr; Back to Budget
                  </button>
                  <button type="submit" className="btn-primary">
                    Next: Review & Launch &rarr;
                  </button>
                </div>
              </form>
            )}

            {/* ---------------------------------------------------------------
                Step 4: Review & Launch
                --------------------------------------------------------------- */}
            {wizardStep === 4 && (
              <div className="space-y-4">
                <div className="p-4 rounded-xl bg-[#F8F9FA] border border-[#E8EAED] space-y-4">
                  <div className="flex justify-between items-center border-b border-[#E8EAED] pb-2">
                    <span className="font-bold text-xs text-[#202124]">Event Summary Verification</span>
                    <span className="badge-champagne text-[10px] font-bold">Ready to Launch</span>
                  </div>

                  {/* Summary Rows */}
                  <div className="space-y-2.5 text-xs">
                    <div className="flex justify-between items-center">
                      <span className="text-[#5F6368]">Event Title:</span>
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-[#202124]">{wTitle}</span>
                        <button
                          type="button"
                          onClick={() => setWizardStep(1)}
                          className="text-[#1A73E8] hover:underline text-[11px]"
                        >
                          Edit
                        </button>
                      </div>
                    </div>

                    <div className="flex justify-between items-center">
                      <span className="text-[#5F6368]">Type & Timezone:</span>
                      <span className="font-semibold text-[#202124] capitalize">{wEventType} ({wTimezone})</span>
                    </div>

                    <div className="flex justify-between items-center">
                      <span className="text-[#5F6368]">Dates:</span>
                      <span className="text-[#202124]">
                        {new Date(wStartDate).toLocaleDateString()} &ndash; {new Date(wEndDate).toLocaleDateString()}
                      </span>
                    </div>

                    <div className="flex justify-between items-center">
                      <span className="text-[#5F6368]">Target Budget & Attendees:</span>
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-[#137333]">
                          {wCurrency} {wBudget ? parseFloat(wBudget).toLocaleString() : 'Unset'}
                        </span>
                        <span className="text-[#5F6368]">
                          • {wAttendees ? `${wAttendees} guests` : 'TBD'}
                        </span>
                        <button
                          type="button"
                          onClick={() => setWizardStep(2)}
                          className="text-[#1A73E8] hover:underline text-[11px]"
                        >
                          Edit
                        </button>
                      </div>
                    </div>

                    {wCity && (
                      <div className="flex justify-between items-center">
                        <span className="text-[#5F6368]">Target Location:</span>
                        <span className="text-[#202124]">{wCity}</span>
                      </div>
                    )}
                  </div>
                </div>

                <div className="pt-3 flex justify-between items-center border-t border-[#E8EAED]">
                  <button
                    type="button"
                    onClick={() => setWizardStep(3)}
                    disabled={submitting}
                    className="btn-ghost"
                  >
                    &larr; Back to Edit
                  </button>
                  <button
                    type="button"
                    onClick={handleWizardSubmit}
                    disabled={submitting}
                    className="btn-primary"
                  >
                    {submitting && <Loader2 className="w-3.5 h-3.5 animate-spin motion-reduce:animate-none" />}
                    Launch Event Cockpit
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
