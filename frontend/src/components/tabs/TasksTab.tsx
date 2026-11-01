'use client';

import React, { useEffect, useState } from 'react';
import { CheckSquare, Plus, Trash2, AlertCircle, Loader2 } from 'lucide-react';
import { tasksApi } from '@/lib/api';
import { EventRecord, TaskRecord, TaskStatus, TaskPriority } from '@/types';

interface TasksTabProps {
  event: EventRecord;
}

const TASK_STATUSES: TaskStatus[] = ['todo', 'in_progress', 'review', 'completed', 'blocked'];
const TASK_PRIORITIES: TaskPriority[] = ['low', 'medium', 'high', 'urgent'];

export function TasksTab({ event }: TasksTabProps) {
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filter State
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [priorityFilter, setPriorityFilter] = useState<string>('all');

  // Add Task State
  const [showAddModal, setShowAddModal] = useState(false);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState<TaskPriority>('medium');
  const [category, setCategory] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [savingTask, setSavingTask] = useState(false);

  const loadTasks = async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = {};
      if (statusFilter !== 'all') params.status = statusFilter;
      if (priorityFilter !== 'all') params.priority = priorityFilter;

      const res = await tasksApi.list(event.id, params);
      setError(null);
      if (res.success && res.data) {
        setTasks(res.data);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load event tasks.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let ignore = false;

    async function fetchTasks() {
      try {
        const params: Record<string, unknown> = {};
        if (statusFilter !== 'all') params.status = statusFilter;
        if (priorityFilter !== 'all') params.priority = priorityFilter;

        const res = await tasksApi.list(event.id, params);
        if (!ignore) {
          setError(null);
          if (res.success && res.data) {
            setTasks(res.data);
          }
        }
      } catch (err: unknown) {
        if (!ignore) {
          setError(err instanceof Error ? err.message : 'Failed to load event tasks.');
        }
      } finally {
        if (!ignore) {
          setLoading(false);
        }
      }
    }

    fetchTasks();
    return () => {
      ignore = true;
    };
  }, [event.id, statusFilter, priorityFilter]);

  const handleStatusChange = async (taskId: string, newStatus: TaskStatus) => {
    try {
      const res = await tasksApi.update(event.id, taskId, { status: newStatus });
      if (res.success) {
        loadTasks();
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to update task status.');
    }
  };

  const handleAddTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;

    setSavingTask(true);
    try {
      const res = await tasksApi.create(event.id, {
        title: title.trim(),
        description: description.trim() || null,
        priority,
        category: category.trim() || null,
        due_date: dueDate ? new Date(dueDate).toISOString() : null,
      });

      if (res.success) {
        setShowAddModal(false);
        setTitle('');
        setDescription('');
        setCategory('');
        setDueDate('');
        setPriority('medium');
        loadTasks();
      } else {
        setError(res.error?.message || 'Failed to create task.');
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error creating task.');
    } finally {
      setSavingTask(false);
    }
  };

  const handleDeleteTask = async (taskId: string) => {
    if (!confirm('Are you sure you want to delete this task?')) return;
    try {
      const res = await tasksApi.delete(event.id, taskId);
      if (res.success) {
        loadTasks();
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to delete task.');
    }
  };

  const getPriorityBadge = (pr: TaskPriority) => {
    switch (pr) {
      case 'urgent':
        return <span className="badge-rose uppercase text-[10px] font-mono">{pr}</span>;
      case 'high':
        return <span className="badge-champagne uppercase text-[10px] font-mono">{pr}</span>;
      case 'medium':
        return <span className="badge-blue uppercase text-[10px] font-mono">{pr}</span>;
      case 'low':
        return <span className="badge-neutral uppercase text-[10px] font-mono">{pr}</span>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Action Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h3 className="text-lg font-bold text-[#202124] flex items-center gap-2">
            <CheckSquare className="w-5 h-5 text-[#1A73E8]" /> Action Items & Deliverable Checklists
          </h3>
          <p className="text-xs text-[#5F6368] mt-0.5">Assign responsibilities, track critical path deadlines, and log operational milestones.</p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="btn-primary self-start sm:self-auto"
        >
          <Plus className="w-3.5 h-3.5" /> Add Task
        </button>
      </div>

      {/* Filters Bar */}
      <div className="card-google p-3.5 flex flex-wrap items-center gap-3 text-xs">
        <span className="font-semibold text-[#5F6368]">Filters:</span>
        <div className="flex items-center gap-1.5">
          <span className="text-[#5F6368] text-[11px]">Status:</span>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="input-google py-1 px-2.5 text-xs rounded-lg w-auto capitalize"
          >
            <option value="all">All Statuses</option>
            {TASK_STATUSES.map((st) => (
              <option key={st} value={st}>{st.replace('_', ' ')}</option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-[#5F6368] text-[11px]">Priority:</span>
          <select
            value={priorityFilter}
            onChange={(e) => setPriorityFilter(e.target.value)}
            className="input-google py-1 px-2.5 text-xs rounded-lg w-auto capitalize"
          >
            <option value="all">All Priorities</option>
            {TASK_PRIORITIES.map((pr) => (
              <option key={pr} value={pr}>{pr}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Error Callout */}
      {error && (
        <div className="p-4 rounded-xl bg-[#FCE8E6] border border-[#FAD2CF] text-[#C5221F] text-xs flex items-start gap-2.5">
          <AlertCircle className="w-4 h-4 text-[#C5221F] shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {/* Tasks List */}
      {loading ? (
        <div className="p-12 text-center text-xs text-[#5F6368] flex items-center justify-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin text-[#1A73E8] motion-reduce:animate-none" /> Loading tasks...
        </div>
      ) : tasks.length === 0 ? (
        <div className="card-google p-12 text-center space-y-2">
          <CheckSquare className="w-8 h-8 text-[#5F6368] mx-auto" />
          <h4 className="font-bold text-[#202124] text-sm">No Tasks Found</h4>
          <p className="text-xs text-[#5F6368]">Click &quot;Add Task&quot; above to create checklist milestones.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {tasks.map((task) => (
            <div
              key={task.id}
              className={`p-4 rounded-2xl border transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                task.status === 'completed'
                  ? 'card-google opacity-70 bg-[#F8F9FA]'
                  : 'card-google hover:border-[#1A73E8]/30'
              }`}
            >
              <div className="space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span
                    className={`font-semibold text-xs ${
                      task.status === 'completed' ? 'line-through text-[#5F6368]' : 'text-[#202124]'
                    }`}
                  >
                    {task.title}
                  </span>
                  {getPriorityBadge(task.priority)}
                  {task.category && (
                    <span className="badge-champagne text-[10px]">
                      {task.category}
                    </span>
                  )}
                </div>
                {task.description && <p className="text-xs text-[#5F6368] leading-relaxed">{task.description}</p>}
                {task.due_date && (
                  <p className="text-[11px] text-[#5F6368]">
                    Due: {new Date(task.due_date).toLocaleDateString()}
                  </p>
                )}
              </div>

              <div className="flex items-center gap-2.5 shrink-0 self-end sm:self-center">
                <select
                  value={task.status}
                  onChange={(e) => handleStatusChange(task.id, e.target.value as TaskStatus)}
                  className="input-google py-1 px-2.5 text-xs w-auto font-medium capitalize"
                >
                  {TASK_STATUSES.map((st) => (
                    <option key={st} value={st}>{st.replace('_', ' ')}</option>
                  ))}
                </select>
                <button
                  onClick={() => handleDeleteTask(task.id)}
                  className="text-[#5F6368] hover:text-[#C5221F] p-1.5 transition-colors"
                  title="Delete task"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add Task Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 bg-[#202124]/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-md rounded-2xl bg-white border border-[#E8EAED] p-6 space-y-4 shadow-2xl">
            <div className="flex justify-between items-center pb-3 border-b border-[#E8EAED]">
              <h4 className="font-bold text-[#202124] text-sm">Add New Task</h4>
              <button
                onClick={() => setShowAddModal(false)}
                className="text-[#5F6368] hover:text-[#202124] text-sm p-1"
                aria-label="Close dialog"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleAddTask} className="space-y-3.5">
              <div>
                <label className="block text-xs font-semibold text-[#202124] mb-1">Task Title</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Finalize catering contract and dietary menu"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="input-google"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-[#202124] mb-1">Priority</label>
                  <select
                    value={priority}
                    onChange={(e) => setPriority(e.target.value as TaskPriority)}
                    className="input-google capitalize"
                  >
                    {TASK_PRIORITIES.map((pr) => (
                      <option key={pr} value={pr}>{pr}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[#202124] mb-1">Category</label>
                  <input
                    type="text"
                    placeholder="Logistics"
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    className="input-google"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#202124] mb-1">Due Date</label>
                <input
                  type="datetime-local"
                  value={dueDate}
                  onChange={(e) => setDueDate(e.target.value)}
                  className="input-google"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#202124] mb-1">Description (Optional)</label>
                <textarea
                  rows={2}
                  placeholder="Details, vendor contact names, or acceptance criteria..."
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
                  disabled={savingTask}
                  className="btn-primary"
                >
                  {savingTask && <Loader2 className="w-3.5 h-3.5 animate-spin motion-reduce:animate-none" />} Save Task
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
