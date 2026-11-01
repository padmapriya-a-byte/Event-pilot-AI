'use client';

import React from 'react';
import {
  Sparkles,
  Bot,
  MapPin,
  Clock,
  ShieldCheck,
  Check,
  Send,
} from 'lucide-react';

export function HeroSplitPreview() {
  return (
    <section aria-label="Interactive Product Preview" className="w-full space-y-3">
      {/* Top Simulation Marker */}
      <div className="flex items-center justify-between text-xs text-[#5F6368] px-1">
        <div className="flex items-center gap-2">
          <span className="badge-champagne text-[11px] font-bold">
            Interactive Product Preview
          </span>
          <span className="hidden sm:inline text-[#5F6368] text-xs">
            See how EventPilot AI architects an entire summit in seconds
          </span>
        </div>
        <div className="flex items-center gap-1.5 text-[11px] font-medium text-[#137333]">
          <span className="w-2 h-2 rounded-full bg-[#137333] animate-pulse motion-reduce:animate-none" />
          <span>Real-time Live Simulation</span>
        </div>
      </div>

      {/* Adaptive Split Preview Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 w-full">
        {/* ===================================================================
            LEFT PANEL: AI Conversational Planner
            =================================================================== */}
        <div className="card-google p-5 sm:p-6 space-y-4 bg-white border border-[#E8EAED] flex flex-col justify-between">
          {/* Panel Header */}
          <div className="space-y-3 pb-3 border-b border-[#E8EAED]">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-[#EA4335]/70" />
                <span className="w-2.5 h-2.5 rounded-full bg-[#FBBC05]/70" />
                <span className="w-2.5 h-2.5 rounded-full bg-[#34A853]/70" />
              </div>
              <span className="badge-blue text-[10px] font-mono">
                Gemini 3.5 Flash-Lite
              </span>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="p-1.5 rounded-lg bg-[#E8F0FE] text-[#1A73E8]">
                  <Bot className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="font-bold text-sm text-[#202124]">AI Conversational Planner</h3>
                  <p className="text-[11px] text-[#5F6368]">Natural language prompt to full architectural plan</p>
                </div>
              </div>
              <span className="badge-champagne text-[10px]">
                Autonomous Mode
              </span>
            </div>
          </div>

          {/* Chat Stream Body */}
          <div className="space-y-3.5">
            {/* User Prompt Bubble */}
            <div className="p-3.5 rounded-2xl bg-[#F8F9FA] border border-[#DADCE0] space-y-1">
              <div className="flex items-center justify-between text-[11px] text-[#5F6368] font-semibold">
                <span>Organizer Directive</span>
                <span>Prompt #1</span>
              </div>
              <p className="text-xs text-[#202124] leading-relaxed">
                &ldquo;Plan a 2-day AI summit in Austin for 400 attendees with a $75k budget. Emphasize developer workshops, edge computing, and rooftop networking.&rdquo;
              </p>
            </div>

            {/* Gemini Thinking / Synthesis Indicator */}
            <div className="flex items-center gap-2.5 p-2.5 rounded-xl bg-[#E8F0FE] border border-[#D2E3FC] text-[#1A73E8] text-xs">
              <Sparkles className="w-4 h-4 shrink-0 text-[#1A73E8] animate-pulse motion-reduce:animate-none" />
              <div className="flex-1 flex items-center justify-between">
                <span className="font-semibold text-[11px]">
                  Synthesized 4 agenda tracks, 2 venue fits & budget ledger
                </span>
                <span className="text-[10px] font-mono bg-white px-1.5 py-0.5 rounded text-[#1A73E8] border border-[#D2E3FC]">
                  1.4s latency
                </span>
              </div>
            </div>

            {/* Generated Master Plan Theme Card */}
            <div className="p-3.5 rounded-xl bg-[#FBF7EE] border border-[#E5D3BF] space-y-1.5 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="badge-champagne text-[10px] uppercase font-bold">
                  Recommended Theme
                </span>
                <span className="text-[10px] font-mono text-[#8C6D3F]">
                  Score: 98% Match
                </span>
              </div>
              <h4 className="text-xs font-bold text-[#202124]">
                Next-Gen Edge Intelligence: Silicon, Models, and Real-Time Systems
              </h4>
              <p className="text-[11px] text-[#5F6368] leading-relaxed">
                Balancing technical breakout tracks with executive networking. Budget optimized with 17.3% contingency reserve.
              </p>
            </div>

            {/* Schedule & Allocation Chips */}
            <div className="space-y-2">
              <span className="text-[11px] font-semibold text-[#5F6368] block">Generated Schedule Blocks:</span>
              <div className="flex flex-wrap gap-1.5">
                <span className="badge-blue text-[10px]">
                  <Clock className="w-3 h-3" /> Day 1: Edge Models Keynote (09:00 - 10:30)
                </span>
                <span className="badge-blue text-[10px]">
                  <Clock className="w-3 h-3" /> Day 1: Wasm Hack Lab (11:00 - 13:00)
                </span>
                <span className="badge-champagne text-[10px]">
                  <Sparkles className="w-3 h-3" /> Day 2: Rooftop Networking (17:30 - 20:00)
                </span>
              </div>
            </div>

            {/* Category Allocation Pills */}
            <div className="space-y-1.5">
              <span className="text-[11px] font-semibold text-[#5F6368] block">AI Budget Distribution:</span>
              <div className="flex flex-wrap gap-1.5 text-[10px]">
                <span className="badge-mint font-mono">
                  Venue: $26,000 (35%)
                </span>
                <span className="badge-champagne font-mono">
                  Catering: $18,000 (24%)
                </span>
                <span className="badge-champagne font-mono">
                  AV & Staging: $14,000 (19%)
                </span>
                <span className="badge-mint font-mono font-bold">
                  Contingency: $13,000 (17%)
                </span>
              </div>
            </div>
          </div>

          {/* Interactive Chat Input Bar Simulation */}
          <div className="pt-3 border-t border-[#E8EAED]">
            <div className="relative flex items-center">
              <input
                type="text"
                readOnly
                aria-label="Simulated prompt input"
                value="Refine timeline to add an extra panel on local model quantization..."
                className="input-google pr-10 text-xs text-[#5F6368] bg-[#F8F9FA] cursor-default"
              />
              <button
                type="button"
                disabled
                className="absolute right-1.5 p-1.5 rounded-lg bg-[#1A73E8] text-white opacity-80"
                aria-label="Send prompt (preview only)"
              >
                <Send className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>

        {/* ===================================================================
            RIGHT PANEL: Event Plan Cockpit Dashboard
            =================================================================== */}
        <div className="card-google p-5 sm:p-6 space-y-4 bg-white border border-[#E8EAED] flex flex-col justify-between">
          {/* Panel Header */}
          <div className="space-y-3 pb-3 border-b border-[#E8EAED]">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-[#EA4335]/70" />
                <span className="w-2.5 h-2.5 rounded-full bg-[#FBBC05]/70" />
                <span className="w-2.5 h-2.5 rounded-full bg-[#34A853]/70" />
              </div>
              <span className="badge-mint text-[10px] font-semibold">
                Status: Planning Active
              </span>
            </div>
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <h3 className="font-bold text-sm text-[#202124]">Event Plan Cockpit</h3>
                <p className="text-[11px] text-[#5F6368]">
                  Austin Convention District • Nov 14–15, 2026 • 400 Guests
                </p>
              </div>
              <span className="badge-neutral text-[10px] font-mono">
                USD ($)
              </span>
            </div>
          </div>

          {/* Body: Live Budget Tracker with Contingency */}
          <div className="space-y-4">
            {/* Financial Health Bar */}
            <div className="p-3.5 rounded-xl bg-[#F8F9FA] border border-[#E8EAED] space-y-2">
              <div className="flex justify-between items-center text-xs">
                <span className="font-semibold text-[#202124]">Financial Health & Ledger</span>
                <span className="badge-mint text-[10px]">
                  Under Target Budget
                </span>
              </div>

              {/* Progress bar */}
              <div className="w-full h-2 rounded-full bg-[#E8EAED] overflow-hidden flex">
                <div className="h-full bg-[#1A73E8]" style={{ width: '35%' }} title="Venue 35%" />
                <div className="h-full bg-[#8C6D3F]" style={{ width: '24%' }} title="Catering 24%" />
                <div className="h-full bg-[#FBBC05]" style={{ width: '19%' }} title="AV & Staging 19%" />
                <div className="h-full bg-[#137333]" style={{ width: '22%' }} title="Safe Contingency 22%" />
              </div>

              {/* Numbers Grid */}
              <div className="grid grid-cols-3 gap-2 pt-1 text-center">
                <div className="p-1.5 rounded-lg bg-white border border-[#E8EAED]">
                  <span className="text-[10px] text-[#5F6368] block">Target Budget</span>
                  <span className="font-mono text-xs font-bold text-[#202124]">$75,000.00</span>
                </div>
                <div className="p-1.5 rounded-lg bg-white border border-[#E8EAED]">
                  <span className="text-[10px] text-[#5F6368] block">Committed</span>
                  <span className="font-mono text-xs font-bold text-[#1A73E8]">$58,000.00</span>
                </div>
                <div className="p-1.5 rounded-lg bg-white border border-[#E8EAED]">
                  <span className="text-[10px] text-[#5F6368] block">Contingency</span>
                  <span className="font-mono text-xs font-bold text-[#137333]">+$17,000.00</span>
                </div>
              </div>
            </div>

            {/* Venue Candidate Comparison Card */}
            <div className="p-3.5 rounded-xl bg-[#F3FBF5] border border-[#CEEAD6] space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-xs font-bold text-[#202124]">
                  <MapPin className="w-3.5 h-3.5 text-[#137333]" /> Selected Primary Venue
                </div>
                <span className="badge-mint text-[10px]">
                  <Check className="w-3 h-3 text-[#137333]" /> Locked In
                </span>
              </div>
              <div className="flex justify-between items-center text-xs">
                <div>
                  <h5 className="font-bold text-[#202124]">Austin Innovation Hall</h5>
                  <p className="text-[11px] text-[#5F6368]">450 capacity (12.5% safety buffer for 400 attendees)</p>
                </div>
                <div className="text-right">
                  <span className="font-mono font-bold text-xs text-[#137333]">$26,000</span>
                  <span className="text-[10px] text-[#5F6368] block">Flat 2-day rental</span>
                </div>
              </div>
            </div>

            {/* Run-of-Show Agenda Preview */}
            <div className="space-y-1.5">
              <span className="text-[11px] font-semibold text-[#5F6368] flex items-center justify-between">
                <span>Run-of-Show Schedule Preview:</span>
                <span className="text-[10px] text-[#1A73E8] font-bold">4 sessions planned</span>
              </span>
              <div className="space-y-1.5">
                <div className="p-2 rounded-lg bg-[#F8F9FA] border border-[#E8EAED] flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[11px] font-bold text-[#1A73E8]">09:00</span>
                    <span className="font-semibold text-[#202124]">Autonomous Intelligence Keynote</span>
                  </div>
                  <span className="text-[10px] text-[#5F6368]">Main Hall A</span>
                </div>
                <div className="p-2 rounded-lg bg-[#F8F9FA] border border-[#E8EAED] flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[11px] font-bold text-[#1A73E8]">11:15</span>
                    <span className="font-semibold text-[#202124]">WebAssembly & Edge Deployment Lab</span>
                  </div>
                  <span className="text-[10px] text-[#5F6368]">Workshop Studio B</span>
                </div>
              </div>
            </div>
          </div>

          {/* Deliverables Action Strip */}
          <div className="pt-3 border-t border-[#E8EAED] flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-1.5 text-[11px] text-[#5F6368]">
              <ShieldCheck className="w-3.5 h-3.5 text-[#137333]" />
              <span>Multi-Format Deliverables Ready:</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="badge-neutral text-[10px] font-mono">.PDF</span>
              <span className="badge-neutral text-[10px] font-mono">.ICS</span>
              <span className="badge-neutral text-[10px] font-mono">.CSV</span>
              <span className="badge-neutral text-[10px] font-mono">.JSON</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
