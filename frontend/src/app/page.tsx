'use client';

import React, { useState } from 'react';
import { AuthProvider, useAuth } from '@/context/AuthContext';
import { Navbar } from '@/components/Navbar';
import { AuthCard } from '@/components/AuthCard';
import { EventList } from '@/components/EventList';
import { EventDetail } from '@/components/EventDetail';
import { HeroSplitPreview } from '@/components/landing/HeroSplitPreview';
import { EventRecord } from '@/types';
import {
  Sparkles,
  Bot,
  DollarSign,
  FileDown,
  ShieldCheck,
} from 'lucide-react';

function DashboardView() {
  const { user, loading } = useAuth();
  const [selectedEvent, setSelectedEvent] = useState<EventRecord | null>(null);

  // 1. Session Loading State
  if (loading) {
    return (
      <div className="min-h-screen bg-[#F8F9FA] flex flex-col text-[#202124]">
        <Navbar />
        <div className="flex-1 flex flex-col items-center justify-center p-6 space-y-4">
          <div className="relative">
            <div className="w-12 h-12 rounded-full border-2 border-[#E8EAED] border-t-[#1A73E8] animate-spin motion-reduce:animate-none" />
            <Bot className="w-6 h-6 text-[#1A73E8] absolute inset-0 m-auto animate-pulse motion-reduce:animate-none" />
          </div>
          <div className="text-center">
            <p className="text-sm font-semibold text-[#202124]">Verifying Supabase Session...</p>
            <p className="text-xs text-[#5F6368]">Connecting to authentication service</p>
          </div>
        </div>
      </div>
    );
  }

  // 2. Unauthenticated State (Landing + Adaptive Split Preview + Auth Card)
  if (!user) {
    return (
      <div className="min-h-screen bg-[#F8F9FA] flex flex-col text-[#202124]">
        <Navbar />
        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-10 flex flex-col items-center justify-center">
          <div className="w-full max-w-6xl space-y-12">
            {/* Hero Header */}
            <div className="text-center space-y-4 max-w-3xl mx-auto pt-4">
              <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full text-xs font-semibold bg-[#F5EBE1] text-[#8C6D3F] border border-[#E5D3BF] shadow-sm">
                <Sparkles className="w-3.5 h-3.5 text-[#8C6D3F]" /> Autonomous Event Management Platform
              </div>
              <h1 className="text-4xl sm:text-5xl md:text-6xl font-extrabold tracking-tight text-[#202124]">
                Intelligent Event Planning, <br />
                <span className="text-[#1A73E8]">Powered by AI</span>
              </h1>
              <p className="text-[#5F6368] text-base md:text-lg leading-relaxed max-w-2xl mx-auto font-normal">
                Orchestrate conferences, hackathons, and corporate summits with autonomous AI planning, real-time budget optimization, venue selection, and multi-format deliverable exports.
              </p>
            </div>

            {/* Adaptive Split Preview (AI Conversational Planner & Event Plan Cockpit) */}
            <HeroSplitPreview />

            {/* Auth Section */}
            <div className="space-y-4 pt-4">
              <div className="text-center">
                <h2 className="text-sm font-bold uppercase tracking-wider text-[#5F6368]">
                  Get Started with EventPilot AI
                </h2>
                <p className="text-xs text-[#5F6368] mt-1">
                  Create a workspace or sign in to enter your live event cockpit.
                </p>
              </div>
              <div className="flex justify-center">
                <AuthCard />
              </div>
            </div>

            {/* Feature Highlights Grid */}
            <div className="space-y-4">
              <div className="text-center">
                <h2 className="text-xs font-bold uppercase tracking-wider text-[#5F6368]">
                  Comprehensive Event Lifecycle Capabilities
                </h2>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                <div className="card-google p-6 space-y-3">
                  <div className="p-2.5 w-fit rounded-xl bg-[#E8F0FE] text-[#1A73E8] border border-[#D2E3FC]">
                    <Bot className="w-5 h-5" />
                  </div>
                  <h3 className="font-bold text-[#202124] text-base">Gemini AI Planning</h3>
                  <p className="text-xs text-[#5F6368] leading-relaxed font-normal">
                    Generate comprehensive themes, run-of-show schedules, venue specifications, and allocation guidelines tailored to your event type.
                  </p>
                </div>

                <div className="card-google p-6 space-y-3">
                  <div className="p-2.5 w-fit rounded-xl bg-[#E6F4EA] text-[#137333] border border-[#CEEAD6]">
                    <DollarSign className="w-5 h-5" />
                  </div>
                  <h3 className="font-bold text-[#202124] text-base">AI Budget Optimization</h3>
                  <p className="text-xs text-[#5F6368] leading-relaxed font-normal">
                    Track actual vs. estimated expenditure and leverage AI to identify cost-saving negotiation levers across catering, AV, and rentals.
                  </p>
                </div>

                <div className="card-google p-6 space-y-3">
                  <div className="p-2.5 w-fit rounded-xl bg-[#F5EBE1] text-[#8C6D3F] border border-[#E5D3BF]">
                    <FileDown className="w-5 h-5" />
                  </div>
                  <h3 className="font-bold text-[#202124] text-base">Multi-Format Deliverables</h3>
                  <p className="text-xs text-[#5F6368] leading-relaxed font-normal">
                    Instantly generate and download executive summary PDFs, calendar ICS schedules, budget CSV spreadsheets, and JSON system backups.
                  </p>
                </div>
              </div>
            </div>

            {/* Architecture Compliance Footer */}
            <div className="p-4 rounded-2xl bg-white border border-[#E8EAED] text-xs text-[#5F6368] flex flex-col sm:flex-row items-center justify-between gap-3 shadow-sm">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-[#137333] shrink-0" />
                <span>Supabase Row-Level Security (RLS) & JWKS ECC P-256 Token Verification</span>
              </div>
              <div className="flex items-center gap-3 font-mono text-[11px] text-[#5F6368]">
                <span>Next.js 16 + React 19</span>
                <span>•</span>
                <span>Flask 3.1 Backend</span>
              </div>
            </div>
          </div>
        </main>
      </div>
    );
  }

  // 3. Authenticated State: Either Event Cockpit (EventDetail) or Event Registry (EventList)
  return (
    <div className="min-h-screen bg-[#F8F9FA] flex flex-col text-[#202124]">
      <Navbar />
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {selectedEvent ? (
          <EventDetail
            event={selectedEvent}
            onBack={() => setSelectedEvent(null)}
            onUpdateEvent={(updated) => setSelectedEvent(updated)}
          />
        ) : (
          <EventList onSelectEvent={(event) => setSelectedEvent(event)} />
        )}
      </main>
    </div>
  );
}

export default function Home() {
  return (
    <AuthProvider>
      <DashboardView />
    </AuthProvider>
  );
}
