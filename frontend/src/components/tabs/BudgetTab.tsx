'use client';

import React, { useEffect, useState } from 'react';
import { DollarSign, Plus, Trash2, TrendingDown, Sparkles, AlertCircle, Loader2 } from 'lucide-react';
import { budgetApi, aiApi } from '@/lib/api';
import {
  EventRecord,
  BudgetItemRecord,
  BudgetSummary,
  BudgetCategory,
  PaymentStatus,
  AIBudgetOptimization,
} from '@/types';

interface BudgetTabProps {
  event: EventRecord;
}

const CATEGORIES: BudgetCategory[] = [
  'venue',
  'catering',
  'av_production',
  'entertainment',
  'marketing',
  'staffing',
  'transportation',
  'decor',
  'permits',
  'contingency',
  'other',
];

const PAYMENT_STATUSES: PaymentStatus[] = ['unpaid', 'partially_paid', 'paid', 'cancelled'];

export function BudgetTab({ event }: BudgetTabProps) {
  const [summary, setSummary] = useState<BudgetSummary | null>(null);
  const [items, setItems] = useState<BudgetItemRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Add Item State
  const [showAddModal, setShowAddModal] = useState(false);
  const [itemName, setItemName] = useState('');
  const [category, setCategory] = useState<BudgetCategory>('venue');
  const [estimatedAmount, setEstimatedAmount] = useState('');
  const [actualAmount, setActualAmount] = useState('');
  const [paymentStatus, setPaymentStatus] = useState<PaymentStatus>('unpaid');
  const [savingItem, setSavingItem] = useState(false);

  // AI Optimization State
  const [showOptimizeModal, setShowOptimizeModal] = useState(false);
  const [optimizationGoal, setOptimizationGoal] = useState('');
  const [optimizing, setOptimizing] = useState(false);
  const [optimizationResult, setOptimizationResult] = useState<AIBudgetOptimization | null>(null);

  const loadBudgetData = async () => {
    setLoading(true);
    try {
      const [sumRes, itemsRes] = await Promise.all([
        budgetApi.getSummary(event.id),
        budgetApi.listItems(event.id),
      ]);

      setError(null);
      if (sumRes.success && sumRes.data) {
        setSummary(sumRes.data);
      }
      if (itemsRes.success && itemsRes.data) {
        setItems(itemsRes.data);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load budget data.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let ignore = false;

    async function fetchBudgetData() {
      try {
        const [sumRes, itemsRes] = await Promise.all([
          budgetApi.getSummary(event.id),
          budgetApi.listItems(event.id),
        ]);

        if (!ignore) {
          setError(null);
          if (sumRes.success && sumRes.data) {
            setSummary(sumRes.data);
          }
          if (itemsRes.success && itemsRes.data) {
            setItems(itemsRes.data);
          }
        }
      } catch (err: unknown) {
        if (!ignore) {
          setError(err instanceof Error ? err.message : 'Failed to load budget data.');
        }
      } finally {
        if (!ignore) {
          setLoading(false);
        }
      }
    }

    fetchBudgetData();
    return () => {
      ignore = true;
    };
  }, [event.id]);

  const handleAddItem = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!itemName.trim() || !estimatedAmount) return;

    setSavingItem(true);
    try {
      const res = await budgetApi.createItem(event.id, {
        name: itemName.trim(),
        category,
        estimated_amount: parseFloat(estimatedAmount) || 0,
        actual_amount: actualAmount ? parseFloat(actualAmount) || 0 : 0,
        payment_status: paymentStatus,
      });

      if (res.success) {
        setShowAddModal(false);
        setItemName('');
        setEstimatedAmount('');
        setActualAmount('');
        loadBudgetData();
      } else {
        setError(res.error?.message || 'Failed to create budget item.');
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error creating budget item.');
    } finally {
      setSavingItem(false);
    }
  };

  const handleDeleteItem = async (itemId: string) => {
    if (!confirm('Are you sure you want to remove this budget line item?')) return;
    try {
      const res = await budgetApi.deleteItem(event.id, itemId);
      if (res.success) {
        loadBudgetData();
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to delete budget item.');
    }
  };

  const handleAIOptimize = async () => {
    setOptimizing(true);
    setError(null);
    try {
      const res = await aiApi.optimizeBudget({
        event_id: event.id,
        optimization_goal: optimizationGoal.trim() || null,
      });

      if (res.success && res.data) {
        setOptimizationResult(res.data);
      } else {
        setError(res.error?.message || 'Failed to optimize budget with AI.');
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error running AI budget optimization.');
    } finally {
      setOptimizing(false);
    }
  };

  const getPaymentBadge = (st: PaymentStatus) => {
    switch (st) {
      case 'paid':
        return <span className="badge-mint uppercase font-mono text-[10px]">{st}</span>;
      case 'partially_paid':
        return <span className="badge-champagne uppercase font-mono text-[10px]">{st.replace('_', ' ')}</span>;
      case 'cancelled':
        return <span className="badge-rose uppercase font-mono text-[10px]">{st}</span>;
      default:
        return <span className="badge-neutral uppercase font-mono text-[10px]">{st}</span>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Action Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h3 className="text-lg font-bold text-[#202124] flex items-center gap-2">
            <DollarSign className="w-5 h-5 text-[#1A73E8]" /> Budget Ledger & Financial Analytics
          </h3>
          <p className="text-xs text-[#5F6368] mt-0.5">Track planned expenditures, committed invoices, and automated AI cost reductions.</p>
        </div>
        <div className="flex items-center gap-2.5">
          <button
            onClick={() => setShowOptimizeModal(true)}
            className="btn-secondary"
          >
            <Sparkles className="w-3.5 h-3.5 text-[#8C6D3F]" /> AI Budget Optimize
          </button>
          <button
            onClick={() => setShowAddModal(true)}
            className="btn-primary"
          >
            <Plus className="w-3.5 h-3.5" /> Add Budget Item
          </button>
        </div>
      </div>

      {/* Error Callout */}
      {error && (
        <div className="p-4 rounded-xl bg-[#FCE8E6] border border-[#FAD2CF] text-[#C5221F] text-xs flex items-start gap-2.5">
          <AlertCircle className="w-4 h-4 text-[#C5221F] shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {/* Summary KPI Cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="card-google p-4 space-y-1">
            <span className="text-[11px] font-semibold text-[#5F6368]">Target Budget</span>
            <p className="text-base font-bold text-[#202124]">
              {summary.currency} {summary.target_budget?.toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </p>
          </div>
          <div className="card-google p-4 space-y-1">
            <span className="text-[11px] font-semibold text-[#5F6368]">Total Estimated</span>
            <p className="text-base font-bold text-[#1A73E8]">
              {summary.currency} {summary.total_estimated?.toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </p>
          </div>
          <div className="card-google p-4 space-y-1">
            <span className="text-[11px] font-semibold text-[#5F6368]">Total Actual Committed</span>
            <p className="text-base font-bold text-[#8C6D3F]">
              {summary.currency} {summary.total_actual?.toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </p>
          </div>
          <div className="card-google p-4 space-y-1">
            <span className="text-[11px] font-semibold text-[#5F6368]">Remaining Contingency</span>
            <p className={`text-base font-bold ${summary.is_over_budget ? 'text-[#C5221F]' : 'text-[#137333]'}`}>
              {summary.currency} {summary.remaining_budget?.toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </p>
          </div>
        </div>
      )}

      {/* AI Optimization Results Modal/Card */}
      {optimizationResult && (
        <div className="card-google p-6 space-y-4 border-[#E5D3BF] bg-[#FBF7EE]">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-bold text-[#202124] flex items-center gap-2">
              <TrendingDown className="w-4 h-4 text-[#8C6D3F]" /> AI Budget Optimization Projections
            </h4>
            <button
              onClick={() => setOptimizationResult(null)}
              className="text-xs text-[#5F6368] hover:text-[#202124] font-medium"
            >
              Dismiss
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
            {optimizationResult.allocations.map((alloc, idx) => (
              <div key={idx} className="p-3.5 rounded-xl bg-white border border-[#E8EAED] space-y-1.5 shadow-sm">
                <div className="flex justify-between items-center text-xs">
                  <span className="font-bold text-[#202124] capitalize">{alloc.category.replace('_', ' ')}</span>
                  <span className={alloc.variance < 0 ? 'text-[#137333] font-semibold' : 'text-[#202124] font-semibold'}>
                    Recommended: {event.currency} {alloc.recommended_amount.toLocaleString()}
                  </span>
                </div>
                <div className="flex justify-between text-[11px] text-[#5F6368]">
                  <span>Current: {event.currency} {alloc.current_estimated.toLocaleString()}</span>
                  <span>Variance: {alloc.variance < 0 ? `${alloc.variance}` : `+${alloc.variance}`}</span>
                </div>
                <p className="text-[11px] text-[#8C6D3F] pt-1.5 border-t border-[#E8EAED] leading-relaxed">
                  {alloc.savings_strategy}
                </p>
              </div>
            ))}
          </div>

          {optimizationResult.optimization_tips.length > 0 && (
            <div className="pt-3 border-t border-[#E5D3BF] space-y-1.5">
              <span className="text-[11px] font-bold text-[#8C6D3F]">Tactical Negotiation Tips:</span>
              <ul className="list-disc list-inside text-xs text-[#5F6368] space-y-0.5">
                {optimizationResult.optimization_tips.map((tip, i) => (
                  <li key={i}>{tip}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Budget Items Table */}
      <div className="card-google overflow-hidden">
        <div className="px-5 py-4 border-b border-[#E8EAED] flex justify-between items-center bg-[#F8F9FA]">
          <span className="font-bold text-[#202124] text-xs">Allocated Line Items ({items.length})</span>
        </div>

        {loading ? (
          <div className="p-8 text-center text-xs text-[#5F6368] flex items-center justify-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin text-[#1A73E8] motion-reduce:animate-none" /> Loading budget ledger...
          </div>
        ) : items.length === 0 ? (
          <div className="p-8 text-center text-xs text-[#5F6368]">
            No budget items recorded yet. Click &quot;Add Budget Item&quot; to begin tracking expenses.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-[#F8F9FA] text-[#5F6368] font-bold border-b border-[#E8EAED]">
                <tr>
                  <th className="py-3 px-4">Item Name</th>
                  <th className="py-3 px-4">Category</th>
                  <th className="py-3 px-4 text-right">Estimated</th>
                  <th className="py-3 px-4 text-right">Actual</th>
                  <th className="py-3 px-4 text-center">Status</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E8EAED] text-[#202124]">
                {items.map((item) => (
                  <tr key={item.id} className="hover:bg-[#F8F9FA] transition-colors">
                    <td className="py-3 px-4 font-semibold text-[#202124]">{item.name}</td>
                    <td className="py-3 px-4 capitalize text-[#5F6368]">{item.category.replace('_', ' ')}</td>
                    <td className="py-3 px-4 text-right font-mono text-[#5F6368]">
                      {event.currency} {item.estimated_amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </td>
                    <td className="py-3 px-4 text-right font-mono font-medium text-[#202124]">
                      {event.currency} {item.actual_amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </td>
                    <td className="py-3 px-4 text-center">
                      {getPaymentBadge(item.payment_status)}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <button
                        onClick={() => handleDeleteItem(item.id)}
                        className="text-[#5F6368] hover:text-[#C5221F] p-1 transition-colors"
                        title="Delete item"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add Item Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 bg-[#202124]/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-md rounded-2xl bg-white border border-[#E8EAED] p-6 space-y-4 shadow-2xl">
            <div className="flex justify-between items-center pb-3 border-b border-[#E8EAED]">
              <h4 className="font-bold text-[#202124] text-sm">Add Budget Line Item</h4>
              <button
                onClick={() => setShowAddModal(false)}
                className="text-[#5F6368] hover:text-[#202124] text-sm p-1"
                aria-label="Close dialog"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleAddItem} className="space-y-3.5">
              <div>
                <label className="block text-xs font-semibold text-[#202124] mb-1">Item Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Main Hall AV Production Package"
                  value={itemName}
                  onChange={(e) => setItemName(e.target.value)}
                  className="input-google"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-[#202124] mb-1">Category</label>
                  <select
                    value={category}
                    onChange={(e) => setCategory(e.target.value as BudgetCategory)}
                    className="input-google capitalize"
                  >
                    {CATEGORIES.map((cat) => (
                      <option key={cat} value={cat}>
                        {cat.replace('_', ' ')}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[#202124] mb-1">Payment Status</label>
                  <select
                    value={paymentStatus}
                    onChange={(e) => setPaymentStatus(e.target.value as PaymentStatus)}
                    className="input-google capitalize"
                  >
                    {PAYMENT_STATUSES.map((st) => (
                      <option key={st} value={st}>
                        {st.replace('_', ' ')}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-[#202124] mb-1">Estimated ({event.currency})</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    required
                    placeholder="2500.00"
                    value={estimatedAmount}
                    onChange={(e) => setEstimatedAmount(e.target.value)}
                    className="input-google"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[#202124] mb-1">Actual ({event.currency})</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    placeholder="0.00"
                    value={actualAmount}
                    onChange={(e) => setActualAmount(e.target.value)}
                    className="input-google"
                  />
                </div>
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
                  disabled={savingItem}
                  className="btn-primary"
                >
                  {savingItem && <Loader2 className="w-3.5 h-3.5 animate-spin motion-reduce:animate-none" />} Save Item
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* AI Optimize Input Modal */}
      {showOptimizeModal && (
        <div className="fixed inset-0 z-50 bg-[#202124]/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-md rounded-2xl bg-white border border-[#E8EAED] p-6 space-y-4 shadow-2xl">
            <div className="flex justify-between items-center pb-3 border-b border-[#E8EAED]">
              <h4 className="font-bold text-[#202124] text-sm flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-[#8C6D3F]" /> AI Budget Optimization
              </h4>
              <button
                onClick={() => setShowOptimizeModal(false)}
                className="text-[#5F6368] hover:text-[#202124] text-sm p-1"
                aria-label="Close dialog"
              >
                ✕
              </button>
            </div>

            <p className="text-xs text-[#5F6368] leading-relaxed">
              Provide an optional financial target or focus area for Gemini AI to analyze your line items and compute recommendations.
            </p>

            <div>
              <label className="block text-xs font-semibold text-[#202124] mb-1">Optimization Goal (Optional)</label>
              <input
                type="text"
                placeholder="e.g. Cut venue costs by 15% and increase marketing"
                value={optimizationGoal}
                onChange={(e) => setOptimizationGoal(e.target.value)}
                className="input-google"
              />
            </div>

            <div className="pt-2 flex justify-end gap-2.5">
              <button
                type="button"
                onClick={() => setShowOptimizeModal(false)}
                className="btn-outline"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowOptimizeModal(false);
                  handleAIOptimize();
                }}
                disabled={optimizing}
                className="btn-primary"
              >
                {optimizing ? <Loader2 className="w-3.5 h-3.5 animate-spin motion-reduce:animate-none" /> : <Sparkles className="w-3.5 h-3.5" />}
                Run Optimization
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
