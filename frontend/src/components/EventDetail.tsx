'use client';

import React, { useState } from 'react';
import {
  ArrowLeft,
  Sparkles,
  DollarSign,
  MapPin,
  Clock,
  CheckSquare,
  Download,
  Calendar,
  Users,
} from 'lucide-react';
import { EventRecord, EventStatus } from '@/types';
import { eventsApi } from '@/lib/api';
import { AIPlanTab } from './tabs/AIPlanTab';
import { BudgetTab } from './tabs/BudgetTab';
import { VenuesTab } from './tabs/VenuesTab';
import { AgendaTab } from './tabs/AgendaTab';
import { TasksTab } from './tabs/TasksTab';
import { ExportsTab } from './tabs/ExportsTab';

interface EventDetailProps {
  event: EventRecord;
  onBack: () => void;
  onUpdateEvent: (updated: EventRecord) => void;
}

type TabKey = 'ai' | 'budget' | 'venues' | 'agenda' | 'tasks' | 'exports';

export function EventDetail({ event, onBack, onUpdateEvent }: EventDetailProps) {
  const [activeTab, setActiveTab] = useState<TabKey>('ai');
  const [updatingStatus, setUpdatingStatus] = useState(false);

  const handleStatusChange = async (newStatus: EventStatus) => {
    setUpdatingStatus(true);
    try {
      const res = await eventsApi.update(event.id, { status: newStatus });
      if (res.success && res.data) {
        onUpdateEvent(res.data);
      }
    } catch (err) {
      console.error('Failed to update event status:', err);
    } finally {
      setUpdatingStatus(false);
    }
  };

  const tabs: { key: TabKey; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
    { key: 'ai', label: 'AI Master Plan', icon: Sparkles },
    { key: 'budget', label: 'Budget & Ledger', icon: DollarSign },
    { key: 'venues', label: 'Venues', icon: MapPin },
    { key: 'agenda', label: 'Agenda Schedule', icon: Clock },
    { key: 'tasks', label: 'Tasks & Milestones', icon: CheckSquare },
    { key: 'exports', label: 'Deliverables & Exports', icon: Download },
  ];

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

  return (
    <div className="space-y-6">
      {/* Top Navigation & Breadcrumb */}
      <div className="flex items-center justify-between">
        <button
          onClick={onBack}
          className="flex items-center gap-1.5 text-xs font-semibold text-[#5F6368] hover:text-[#202124] transition-colors"
        >
          <ArrowLeft className="w-4 h-4" /> Back to Events Dashboard
        </button>
      </div>

      {/* Event Header Banner */}
      <div className="card-google p-6 space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2.5 flex-wrap">
              <h2 className="text-2xl font-bold text-[#202124] tracking-tight">{event.title}</h2>
              <span className="badge-champagne capitalize">
                {event.event_type}
              </span>
            </div>
            {event.description && <p className="text-xs text-[#5F6368] max-w-2xl">{event.description}</p>}
          </div>

          <div className="flex items-center gap-2.5">
            <label className="text-xs text-[#5F6368] font-semibold">Status:</label>
            <select
              value={event.status}
              disabled={updatingStatus}
              onChange={(e) => handleStatusChange(e.target.value as EventStatus)}
              className="px-3 py-1.5 rounded-xl bg-[#F8F9FA] border border-[#DADCE0] text-[#202124] text-xs font-semibold capitalize focus:outline-none focus:ring-2 focus:ring-[#1A73E8]/20 focus:border-[#1A73E8]"
            >
              <option value="draft">Draft</option>
              <option value="planning">Planning</option>
              <option value="confirmed">Confirmed</option>
              <option value="completed">Completed</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </div>
        </div>

        {/* Quick Meta Stats */}
        <div className="flex flex-wrap gap-5 pt-4 border-t border-[#E8EAED] text-xs text-[#5F6368]">
          <div className="flex items-center gap-1.5">
            <Calendar className="w-4 h-4 text-[#5F6368]" />
            <span>
              {formatDate(event.start_date)} - {formatDate(event.end_date)} ({event.timezone})
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <Users className="w-4 h-4 text-[#5F6368]" />
            <span>{event.expected_attendees ? `${event.expected_attendees} attendees` : 'Attendees TBD'}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <DollarSign className="w-4 h-4 text-[#5F6368]" />
            <span className="font-mono text-[#202124] font-medium">
              Target: {event.currency} {event.target_budget?.toLocaleString() || 'Not set'}
            </span>
          </div>
        </div>
      </div>

      {/* Tabs Navigation */}
      <div
        role="tablist"
        aria-label="Event cockpit modules"
        className="flex border-b border-[#E8EAED] overflow-x-auto space-x-1 scrollbar-none"
      >
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              role="tab"
              aria-selected={isActive}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-2 px-4 py-3 text-xs font-semibold border-b-2 transition-all whitespace-nowrap ${
                isActive
                  ? 'border-[#1A73E8] text-[#1A73E8] bg-[#E8F0FE]/40'
                  : 'border-transparent text-[#5F6368] hover:text-[#202124] hover:bg-[#F1F3F4]'
              }`}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Tab Content Panels */}
      <div className="pt-2">
        {activeTab === 'ai' && <AIPlanTab event={event} />}
        {activeTab === 'budget' && <BudgetTab event={event} />}
        {activeTab === 'venues' && <VenuesTab event={event} />}
        {activeTab === 'agenda' && <AgendaTab event={event} />}
        {activeTab === 'tasks' && <TasksTab event={event} />}
        {activeTab === 'exports' && <ExportsTab event={event} />}
      </div>
    </div>
  );
}
