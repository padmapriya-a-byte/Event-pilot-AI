'use client';

import React, { useEffect, useState } from 'react';
import { Plus, Calendar, DollarSign, Users, Trash2, ArrowRight, AlertCircle, Loader2 } from 'lucide-react';
import { eventsApi } from '@/lib/api';
import { EventRecord, EventStatus } from '@/types';
import { StartPlanningModal } from './planning/StartPlanningModal';

interface EventListProps {
  onSelectEvent: (event: EventRecord) => void;
}

export function EventList({ onSelectEvent }: EventListProps) {
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);

  const loadEvents = async () => {
    setLoading(true);
    try {
      const res = await eventsApi.list();
      setError(null);
      if (res.success && res.data) {
        setEvents(res.data);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load events.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let ignore = false;
    async function fetchEvents() {
      try {
        const res = await eventsApi.list();
        if (!ignore) {
          setError(null);
          if (res.success && res.data) {
            setEvents(res.data);
          }
        }
      } catch (err: unknown) {
        if (!ignore) {
          setError(err instanceof Error ? err.message : 'Failed to load events.');
        }
      } finally {
        if (!ignore) {
          setLoading(false);
        }
      }
    }
    fetchEvents();
    return () => {
      ignore = true;
    };
  }, []);

  const handleDeleteEvent = async (e: React.MouseEvent, eventId: string) => {
    e.stopPropagation();
    if (!confirm('Are you sure you want to permanently delete this event and all associated records?')) return;

    try {
      const res = await eventsApi.delete(eventId);
      if (res.success) {
        await loadEvents();
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to delete event.');
    }
  };

  const formatDate = (isoString: string | null) => {
    if (!isoString) return 'Date TBD';
    try {
      return new Date(isoString).toLocaleDateString([], {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      });
    } catch {
      return isoString;
    }
  };

  const getStatusBadge = (st: EventStatus) => {
    switch (st) {
      case 'confirmed':
        return <span className="badge-mint capitalize">{st}</span>;
      case 'planning':
        return <span className="badge-blue capitalize">{st}</span>;
      case 'completed':
        return <span className="badge-neutral capitalize">{st}</span>;
      case 'cancelled':
        return <span className="badge-rose capitalize">{st}</span>;
      default:
        return <span className="badge-neutral capitalize">{st}</span>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-[#202124] tracking-tight">Your Events Portfolio</h2>
          <p className="text-xs text-[#5F6368] mt-0.5">Select an existing event to enter the cockpit, or launch a new event master plan.</p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="btn-primary self-start sm:self-auto"
        >
          <Plus className="w-4 h-4" /> Start Planning Event
        </button>
      </div>

      {/* Error Callout */}
      {error && (
        <div className="p-4 rounded-xl bg-[#FCE8E6] border border-[#FAD2CF] text-[#C5221F] text-xs flex items-start gap-2.5">
          <AlertCircle className="w-4 h-4 text-[#C5221F] shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {/* Events Grid */}
      {loading ? (
        <div className="p-16 text-center text-xs text-[#5F6368] flex items-center justify-center gap-2">
          <Loader2 className="w-5 h-5 animate-spin text-[#1A73E8] motion-reduce:animate-none" /> Loading portfolio...
        </div>
      ) : events.length === 0 ? (
        <div className="card-google p-16 text-center space-y-4">
          <div className="w-12 h-12 rounded-2xl bg-[#E8F0FE] text-[#1A73E8] border border-[#D2E3FC] flex items-center justify-center mx-auto shadow-sm">
            <Calendar className="w-6 h-6" />
          </div>
          <div>
            <h3 className="font-bold text-[#202124] text-base">No Events Created Yet</h3>
            <p className="text-xs text-[#5F6368] max-w-sm mx-auto mt-1">
              Start by describing your vision to Gemini AI or use our guided step-by-step wizard to configure dates and budgets.
            </p>
          </div>
          <button
            onClick={() => setShowCreateModal(true)}
            className="btn-primary inline-flex"
          >
            <Plus className="w-4 h-4" /> Start Planning Event
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {events.map((ev) => (
            <div
              key={ev.id}
              onClick={() => onSelectEvent(ev)}
              className="card-google p-6 cursor-pointer group flex flex-col justify-between hover:border-[#1A73E8]/40"
            >
              <div className="space-y-3">
                <div className="flex items-start justify-between gap-2">
                  <span className="badge-champagne capitalize">
                    {ev.event_type}
                  </span>
                  <div className="flex items-center gap-2">
                    {getStatusBadge(ev.status)}
                    <button
                      onClick={(e) => handleDeleteEvent(e, ev.id)}
                      className="text-[#5F6368] hover:text-[#C5221F] p-1 opacity-0 group-hover:opacity-100 transition-opacity"
                      title="Delete event"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                <h3 className="font-bold text-[#202124] text-base group-hover:text-[#1A73E8] transition-colors">
                  {ev.title}
                </h3>
                {ev.description && (
                  <p className="text-xs text-[#5F6368] line-clamp-2 leading-relaxed">{ev.description}</p>
                )}
              </div>

              <div className="space-y-3 pt-4 border-t border-[#E8EAED] mt-4">
                <div className="space-y-2 text-xs text-[#5F6368]">
                  <div className="flex items-center justify-between">
                    <span className="flex items-center gap-1.5">
                      <Calendar className="w-3.5 h-3.5 text-[#5F6368]" />
                      {formatDate(ev.start_date)}
                    </span>
                    <span className="flex items-center gap-1.5">
                      <Users className="w-3.5 h-3.5 text-[#5F6368]" />
                      {ev.expected_attendees ? `${ev.expected_attendees} guests` : 'TBD'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="flex items-center gap-1.5 font-mono text-[#202124] font-medium">
                      <DollarSign className="w-3.5 h-3.5 text-[#5F6368]" />
                      {ev.target_budget ? `${ev.currency} ${ev.target_budget.toLocaleString()}` : 'Budget unset'}
                    </span>
                    <span className="text-[#1A73E8] group-hover:translate-x-0.5 transition-transform flex items-center gap-1 font-semibold text-xs">
                      Manage Cockpit <ArrowRight className="w-3 h-3" />
                    </span>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Start Planning Modal (Dual-Path Experience) */}
      <StartPlanningModal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onEventCreated={(newEvent) => {
          loadEvents();
          onSelectEvent(newEvent);
        }}
      />
    </div>
  );
}
