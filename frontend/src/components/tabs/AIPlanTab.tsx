'use client';

import React, { useState } from 'react';
import { Sparkles, Calendar, DollarSign, MapPin, AlertCircle, Loader2, Info } from 'lucide-react';
import { aiApi } from '@/lib/api';
import { EventRecord, AIPlanGeneratedContent, PlanRevisionRecord } from '@/types';

interface AIPlanTabProps {
  event: EventRecord;
}

export function AIPlanTab({ event }: AIPlanTabProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [userNotes, setUserNotes] = useState('');
  const [planRevision, setPlanRevision] = useState<PlanRevisionRecord | null>(null);
  const [generatedContent, setGeneratedContent] = useState<AIPlanGeneratedContent | null>(null);

  const handleGeneratePlan = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await aiApi.planEvent({
        event_id: event.id,
        prompt_context: userNotes.trim() ? { user_notes: userNotes.trim() } : null,
        change_summary: planRevision ? 'User re-plan iteration' : 'Initial AI master plan generation',
      });

      if (res.success && res.data) {
        setPlanRevision(res.data.plan);
        setGeneratedContent(res.data.generated_content);
      } else {
        setError(res.error?.message || 'Failed to generate AI plan.');
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'An error occurred while generating event plan.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Action / Trigger Banner */}
      <div className="card-google p-6 space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1.5">
            <div className="badge-champagne">
              <Sparkles className="w-3.5 h-3.5 text-[#8C6D3F]" /> Powered by Google Gemini AI
            </div>
            <h3 className="text-lg font-bold text-[#202124]">Autonomous Master Plan Architect</h3>
            <p className="text-xs text-[#5F6368] max-w-2xl leading-relaxed">
              EventPilot analyzes your event constraints, budget ceiling, dates, and preferences to architect a complete timeline, venue recommendations, and optimal budget distribution.
            </p>
          </div>
          <button
            onClick={handleGeneratePlan}
            disabled={loading}
            className="btn-primary self-start md:self-center shrink-0"
          >
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin motion-reduce:animate-none" />
            ) : (
              <Sparkles className="w-4 h-4" />
            )}
            {planRevision ? 'Re-Generate Master Plan' : 'Generate Master Plan'}
          </button>
        </div>

        {/* Optional Custom Notes */}
        <div className="pt-3 border-t border-[#E8EAED]">
          <label className="block text-xs font-semibold text-[#202124] mb-1.5">
            Planner Guidance & Custom Directives (Optional)
          </label>
          <input
            type="text"
            value={userNotes}
            onChange={(e) => setUserNotes(e.target.value)}
            disabled={loading}
            placeholder="e.g. Focus on networking breakout sessions; favor venues with outdoor terrace space."
            className="input-google"
          />
        </div>
      </div>

      {/* Error Callout */}
      {error && (
        <div className="p-4 rounded-xl bg-[#FCE8E6] border border-[#FAD2CF] text-[#C5221F] text-xs flex items-start gap-3">
          <AlertCircle className="w-4 h-4 shrink-0 text-[#C5221F] mt-0.5" />
          <div>
            <p className="font-semibold text-[#C5221F]">AI Plan Generation Failed</p>
            <p className="text-[#C5221F]/90 mt-0.5">{error}</p>
          </div>
        </div>
      )}

      {/* Loading State Skeleton */}
      {loading && (
        <div className="card-google p-8 text-center space-y-3">
          <Loader2 className="w-8 h-8 text-[#1A73E8] animate-spin motion-reduce:animate-none mx-auto" />
          <p className="text-sm font-bold text-[#202124]">Gemini is synthesizing your event master plan...</p>
          <p className="text-xs text-[#5F6368] max-w-md mx-auto">
            Structuring chronological agenda blocks, filtering venue requirements, and balancing category allocations against your target budget.
          </p>
        </div>
      )}

      {/* Plan Display */}
      {generatedContent && !loading && (
        <div className="space-y-6">
          {/* Header & Summary */}
          <div className="card-google p-6 space-y-3">
            <div className="flex items-center justify-between">
              <span className="badge-champagne uppercase font-bold tracking-wider">
                Active Plan Theme
              </span>
              {planRevision && (
                <span className="badge-neutral font-mono">
                  Revision #{planRevision.revision_number}
                </span>
              )}
            </div>
            <h4 className="text-xl font-bold text-[#202124]">{generatedContent.theme}</h4>
            <p className="text-sm text-[#5F6368] leading-relaxed">{generatedContent.summary}</p>
          </div>

          {/* Timeline Blocks */}
          <div className="card-google p-6 space-y-4">
            <h5 className="font-bold text-[#202124] text-sm flex items-center gap-2">
              <Calendar className="w-4 h-4 text-[#1A73E8]" /> Event Execution Timeline
            </h5>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {generatedContent.timeline.map((item, idx) => (
                <div key={idx} className="p-3.5 rounded-xl bg-[#F8F9FA] border border-[#E8EAED] space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-[#202124] text-xs">{item.activity}</span>
                    <span className="badge-blue text-[11px] font-mono">
                      {item.time_range}
                    </span>
                  </div>
                  <p className="text-xs text-[#5F6368]">{item.description}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Suggested Venues & Recommended Budget Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Suggested Venues */}
            <div className="card-google p-6 space-y-4">
              <h5 className="font-bold text-[#202124] text-sm flex items-center gap-2">
                <MapPin className="w-4 h-4 text-[#137333]" /> Suggested Venue Profiles
              </h5>
              <div className="space-y-3">
                {generatedContent.suggested_venues.map((venue, idx) => (
                  <div key={idx} className="p-3.5 rounded-xl bg-[#F8F9FA] border border-[#E8EAED] space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-[#202124] text-xs">{venue.name}</span>
                      <span className="text-xs font-mono font-semibold text-[#137333]">
                        {event.currency} {venue.estimated_cost?.toLocaleString()}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-xs text-[#5F6368]">
                      <span>{venue.location}</span>
                      <span>Capacity: {venue.capacity} guests</span>
                    </div>
                    {venue.notes && <p className="text-[11px] text-[#5F6368] italic mt-1">{venue.notes}</p>}
                  </div>
                ))}
              </div>
            </div>

            {/* Recommended Budget Allocation */}
            <div className="card-google p-6 space-y-4">
              <h5 className="font-bold text-[#202124] text-sm flex items-center gap-2">
                <DollarSign className="w-4 h-4 text-[#1A73E8]" /> Recommended Allocations
              </h5>
              <div className="space-y-3">
                {generatedContent.recommended_budget_allocation.map((alloc, idx) => (
                  <div key={idx} className="p-3.5 rounded-xl bg-[#F8F9FA] border border-[#E8EAED] space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-[#202124] text-xs capitalize">{alloc.category.replace('_', ' ')}</span>
                      <span className="text-xs font-mono font-semibold text-[#1A73E8]">
                        {event.currency} {alloc.allocated_amount?.toLocaleString()}
                      </span>
                    </div>
                    <p className="text-xs text-[#5F6368]">{alloc.rationale}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* AI Disclaimer */}
          {generatedContent.disclaimer && (
            <div className="p-3.5 rounded-xl bg-[#F8F9FA] border border-[#E8EAED] text-[11px] text-[#5F6368] flex items-center gap-2.5">
              <Info className="w-4 h-4 text-[#1A73E8] shrink-0" />
              <span>{generatedContent.disclaimer}</span>
            </div>
          )}
        </div>
      )}

      {/* Initial Empty State */}
      {!generatedContent && !loading && (
        <div className="card-google p-12 text-center space-y-3">
          <div className="inline-flex p-3 rounded-2xl bg-[#E8F0FE] text-[#1A73E8] border border-[#D2E3FC]">
            <Sparkles className="w-6 h-6" />
          </div>
          <h4 className="font-bold text-[#202124] text-base">No Master Plan Generated Yet</h4>
          <p className="text-xs text-[#5F6368] max-w-sm mx-auto">
            Click &quot;Generate Master Plan&quot; above to have Gemini AI analyze your dates, budget, and constraints to create your master plan.
          </p>
        </div>
      )}
    </div>
  );
}
