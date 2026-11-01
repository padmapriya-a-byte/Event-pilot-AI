'use client';

import React, { useEffect, useState } from 'react';
import { Calendar, Plus, Trash2, Clock, User, AlertCircle, Loader2 } from 'lucide-react';
import { agendaApi } from '@/lib/api';
import { EventRecord, AgendaSessionRecord, SessionType } from '@/types';

interface AgendaTabProps {
  event: EventRecord;
}

const SESSION_TYPES: SessionType[] = [
  'keynote',
  'panel',
  'workshop',
  'presentation',
  'break',
  'networking',
  'ceremony',
  'other',
];

export function AgendaTab({ event }: AgendaTabProps) {
  const [sessions, setSessions] = useState<AgendaSessionRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Add Session State
  const [showAddModal, setShowAddModal] = useState(false);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');
  const [sessionType, setSessionType] = useState<SessionType>('presentation');
  const [speaker, setSpeaker] = useState('');
  const [room, setRoom] = useState('');
  const [savingSession, setSavingSession] = useState(false);

  const loadSessions = async () => {
    setLoading(true);
    try {
      const res = await agendaApi.list(event.id);
      setError(null);
      if (res.success && res.data) {
        setSessions(res.data);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load agenda sessions.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let ignore = false;

    async function fetchAgenda() {
      try {
        const res = await agendaApi.list(event.id);
        if (!ignore) {
          setError(null);
          if (res.success && res.data) {
            setSessions(res.data);
          }
        }
      } catch (err: unknown) {
        if (!ignore) {
          setError(err instanceof Error ? err.message : 'Failed to load agenda sessions.');
        }
      } finally {
        if (!ignore) {
          setLoading(false);
        }
      }
    }

    fetchAgenda();
    return () => {
      ignore = true;
    };
  }, [event.id]);

  const handleAddSession = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !startTime || !endTime) return;

    if (new Date(endTime) <= new Date(startTime)) {
      setError('End time must be strictly after start time.');
      return;
    }

    setSavingSession(true);
    try {
      const res = await agendaApi.create(event.id, {
        title: title.trim(),
        description: description.trim() || null,
        start_time: new Date(startTime).toISOString(),
        end_time: new Date(endTime).toISOString(),
        session_type: sessionType,
        speaker_facilitator: speaker.trim() || null,
        room_location: room.trim() || null,
      });

      if (res.success) {
        setShowAddModal(false);
        setTitle('');
        setDescription('');
        setStartTime('');
        setEndTime('');
        setSpeaker('');
        setRoom('');
        loadSessions();
      } else {
        setError(res.error?.message || 'Failed to create session.');
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error creating session.');
    } finally {
      setSavingSession(false);
    }
  };

  const handleDeleteSession = async (sessionId: string) => {
    if (!confirm('Are you sure you want to delete this session?')) return;
    try {
      const res = await agendaApi.delete(event.id, sessionId);
      if (res.success) {
        loadSessions();
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to delete session.');
    }
  };

  const formatTime = (isoString: string) => {
    try {
      const d = new Date(isoString);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return isoString;
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Action Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h3 className="text-lg font-bold text-[#202124] flex items-center gap-2">
            <Clock className="w-5 h-5 text-[#1A73E8]" /> Chronological Agenda & Schedule
          </h3>
          <p className="text-xs text-[#5F6368] mt-0.5">Order keynotes, breakout tracks, panels, and catering breaks across event days.</p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="btn-primary self-start sm:self-auto"
        >
          <Plus className="w-3.5 h-3.5" /> Add Agenda Session
        </button>
      </div>

      {/* Error Callout */}
      {error && (
        <div className="p-4 rounded-xl bg-[#FCE8E6] border border-[#FAD2CF] text-[#C5221F] text-xs flex items-start gap-2.5">
          <AlertCircle className="w-4 h-4 text-[#C5221F] shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {/* Sessions List */}
      {loading ? (
        <div className="p-12 text-center text-xs text-[#5F6368] flex items-center justify-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin text-[#1A73E8] motion-reduce:animate-none" /> Loading agenda sessions...
        </div>
      ) : sessions.length === 0 ? (
        <div className="card-google p-12 text-center space-y-2">
          <Calendar className="w-8 h-8 text-[#5F6368] mx-auto" />
          <h4 className="font-bold text-[#202124] text-sm">No Sessions Scheduled</h4>
          <p className="text-xs text-[#5F6368]">Click &quot;Add Agenda Session&quot; to build your event schedule.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {sessions.map((sess) => (
            <div
              key={sess.id}
              className="card-google p-5 flex flex-col md:flex-row md:items-center justify-between gap-4 hover:border-[#1A73E8]/30"
            >
              <div className="flex items-start gap-4">
                <div className="text-center p-3 rounded-xl bg-[#F8F9FA] border border-[#E8EAED] min-w-[95px]">
                  <span className="text-xs font-mono font-bold text-[#1A73E8]">{formatTime(sess.start_time)}</span>
                  <span className="text-[10px] text-[#5F6368] block mt-0.5">to {formatTime(sess.end_time)}</span>
                </div>
                <div className="space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h4 className="font-bold text-[#202124] text-base">{sess.title}</h4>
                    <span className="badge-blue text-[10px] capitalize">
                      {sess.session_type}
                    </span>
                    {sess.room_location && (
                      <span className="badge-champagne text-[10px]">
                        {sess.room_location}
                      </span>
                    )}
                  </div>
                  {sess.description && <p className="text-xs text-[#5F6368] leading-relaxed">{sess.description}</p>}
                  {sess.speaker_facilitator && (
                    <p className="text-xs text-[#202124] flex items-center gap-1.5 pt-1">
                      <User className="w-3.5 h-3.5 text-[#5F6368]" /> {sess.speaker_facilitator}
                    </p>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-2 self-end md:self-center">
                <button
                  onClick={() => handleDeleteSession(sess.id)}
                  className="text-[#5F6368] hover:text-[#C5221F] p-1.5 transition-colors"
                  title="Delete session"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add Session Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 bg-[#202124]/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-md rounded-2xl bg-white border border-[#E8EAED] p-6 space-y-4 shadow-2xl">
            <div className="flex justify-between items-center pb-3 border-b border-[#E8EAED]">
              <h4 className="font-bold text-[#202124] text-sm">Add Agenda Session</h4>
              <button
                onClick={() => setShowAddModal(false)}
                className="text-[#5F6368] hover:text-[#202124] text-sm p-1"
                aria-label="Close dialog"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleAddSession} className="space-y-3.5">
              <div>
                <label className="block text-xs font-semibold text-[#202124] mb-1">Session Title</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Opening Keynote: The Future of Autonomous AI"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="input-google"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-[#202124] mb-1">Start Time</label>
                  <input
                    type="datetime-local"
                    required
                    value={startTime}
                    onChange={(e) => setStartTime(e.target.value)}
                    className="input-google"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[#202124] mb-1">End Time</label>
                  <input
                    type="datetime-local"
                    required
                    value={endTime}
                    onChange={(e) => setEndTime(e.target.value)}
                    className="input-google"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-[#202124] mb-1">Session Type</label>
                  <select
                    value={sessionType}
                    onChange={(e) => setSessionType(e.target.value as SessionType)}
                    className="input-google capitalize"
                  >
                    {SESSION_TYPES.map((st) => (
                      <option key={st} value={st}>
                        {st.replace('_', ' ')}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[#202124] mb-1">Room / Stage</label>
                  <input
                    type="text"
                    placeholder="Grand Ballroom A"
                    value={room}
                    onChange={(e) => setRoom(e.target.value)}
                    className="input-google"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#202124] mb-1">Speaker / Facilitator</label>
                <input
                  type="text"
                  placeholder="Dr. Jane Doe, VP of Engineering"
                  value={speaker}
                  onChange={(e) => setSpeaker(e.target.value)}
                  className="input-google"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#202124] mb-1">Description (Optional)</label>
                <textarea
                  rows={2}
                  placeholder="Brief overview of topic and target takeaways..."
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="input-google"
                />
              </div>

              <div className="pt-2 flex justify-end gap-2.5">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="btn-outline"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={savingSession}
                  className="btn-primary"
                >
                  {savingSession && <Loader2 className="w-3.5 h-3.5 animate-spin motion-reduce:animate-none" />} Save Session
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
