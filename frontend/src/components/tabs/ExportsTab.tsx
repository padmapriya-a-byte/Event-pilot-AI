'use client';

import React, { useEffect, useState } from 'react';
import { Download, FileText, Trash2, Calendar, FileSpreadsheet, Database, AlertCircle, Loader2 } from 'lucide-react';
import { exportsApi } from '@/lib/api';
import { EventRecord, ExportRecord, ExportType } from '@/types';

interface ExportsTabProps {
  event: EventRecord;
}

export function ExportsTab({ event }: ExportsTabProps) {
  const [exports, setExports] = useState<ExportRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [generatingType, setGeneratingType] = useState<ExportType | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const loadExports = async () => {
    setLoading(true);
    try {
      const res = await exportsApi.list(event.id);
      setError(null);
      if (res.success && res.data) {
        setExports(res.data);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load exports.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let ignore = false;

    async function fetchExports() {
      try {
        const res = await exportsApi.list(event.id);
        if (!ignore) {
          setError(null);
          if (res.success && res.data) {
            setExports(res.data);
          }
        }
      } catch (err: unknown) {
        if (!ignore) {
          setError(err instanceof Error ? err.message : 'Failed to load exports.');
        }
      } finally {
        if (!ignore) {
          setLoading(false);
        }
      }
    }

    fetchExports();
    return () => {
      ignore = true;
    };
  }, [event.id]);

  const handleGenerate = async (exportType: ExportType) => {
    setGeneratingType(exportType);
    setError(null);
    try {
      const res = await exportsApi.generate(event.id, { export_type: exportType });
      if (res.success) {
        await loadExports();
      } else {
        setError(res.error?.message || `Failed to generate ${exportType}.`);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : `Error generating ${exportType}.`);
    } finally {
      setGeneratingType(null);
    }
  };

  const handleDownload = async (exportItem: ExportRecord) => {
    setDownloadingId(exportItem.id);
    setError(null);
    try {
      const { blob, filename } = await exportsApi.download(event.id, exportItem.id);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename || exportItem.file_name || 'download';
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to download export file.');
    } finally {
      setDownloadingId(null);
    }
  };

  const handleDelete = async (exportId: string) => {
    if (!confirm('Are you sure you want to delete this deliverable file?')) return;
    try {
      const res = await exportsApi.delete(event.id, exportId);
      if (res.success) {
        loadExports();
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to delete export.');
    }
  };

  const formatFileSize = (bytes: number) => {
    if (!bytes || bytes <= 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  };

  const getTypeIcon = (type: ExportType) => {
    switch (type) {
      case 'pdf_summary':
        return <FileText className="w-5 h-5 text-[#C5221F]" />;
      case 'ics_calendar':
        return <Calendar className="w-5 h-5 text-[#1A73E8]" />;
      case 'csv_budget':
        return <FileSpreadsheet className="w-5 h-5 text-[#137333]" />;
      case 'json_backup':
        return <Database className="w-5 h-5 text-[#8C6D3F]" />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Action Bar */}
      <div>
        <h3 className="text-lg font-bold text-[#202124] flex items-center gap-2">
          <Download className="w-5 h-5 text-[#1A73E8]" /> Deliverables & Export Center
        </h3>
        <p className="text-xs text-[#5F6368] mt-0.5">
          Generate production-ready event summaries, calendar invites (.ics), budget spreadsheets (.csv), and comprehensive JSON backups.
        </p>
      </div>

      {/* Generator Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* PDF Executive Summary */}
        <div className="card-google p-5 space-y-3 flex flex-col justify-between hover:border-[#1A73E8]/40">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <div className="p-2 rounded-xl bg-[#FCE8E6] text-[#C5221F] border border-[#FAD2CF]">
                <FileText className="w-4 h-4" />
              </div>
              <h4 className="font-bold text-[#202124] text-xs">PDF Executive Summary</h4>
            </div>
            <p className="text-[11px] text-[#5F6368] leading-relaxed">Branded event master plan document with agenda, budget breakdown, and venue specs.</p>
          </div>
          <button
            onClick={() => handleGenerate('pdf_summary')}
            disabled={generatingType === 'pdf_summary'}
            className="btn-outline w-full py-2 text-xs"
          >
            {generatingType === 'pdf_summary' && <Loader2 className="w-3.5 h-3.5 animate-spin motion-reduce:animate-none" />}
            Generate PDF
          </button>
        </div>

        {/* ICS Calendar */}
        <div className="card-google p-5 space-y-3 flex flex-col justify-between hover:border-[#1A73E8]/40">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <div className="p-2 rounded-xl bg-[#E8F0FE] text-[#1A73E8] border border-[#D2E3FC]">
                <Calendar className="w-4 h-4" />
              </div>
              <h4 className="font-bold text-[#202124] text-xs">ICS Calendar Invite</h4>
            </div>
            <p className="text-[11px] text-[#5F6368] leading-relaxed">RFC 5545 compliant calendar export compatible with Google Calendar, Outlook, and Apple iCal.</p>
          </div>
          <button
            onClick={() => handleGenerate('ics_calendar')}
            disabled={generatingType === 'ics_calendar'}
            className="btn-outline w-full py-2 text-xs"
          >
            {generatingType === 'ics_calendar' && <Loader2 className="w-3.5 h-3.5 animate-spin motion-reduce:animate-none" />}
            Generate ICS
          </button>
        </div>

        {/* Budget CSV */}
        <div className="card-google p-5 space-y-3 flex flex-col justify-between hover:border-[#1A73E8]/40">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <div className="p-2 rounded-xl bg-[#E6F4EA] text-[#137333] border border-[#CEEAD6]">
                <FileSpreadsheet className="w-4 h-4" />
              </div>
              <h4 className="font-bold text-[#202124] text-xs">Budget Ledger CSV</h4>
            </div>
            <p className="text-[11px] text-[#5F6368] leading-relaxed">Sanitized formula-safe spreadsheet containing all line items, vendors, actuals, and variances.</p>
          </div>
          <button
            onClick={() => handleGenerate('csv_budget')}
            disabled={generatingType === 'csv_budget'}
            className="btn-outline w-full py-2 text-xs"
          >
            {generatingType === 'csv_budget' && <Loader2 className="w-3.5 h-3.5 animate-spin motion-reduce:animate-none" />}
            Generate CSV
          </button>
        </div>

        {/* JSON Backup */}
        <div className="card-google p-5 space-y-3 flex flex-col justify-between hover:border-[#1A73E8]/40">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <div className="p-2 rounded-xl bg-[#F5EBE1] text-[#8C6D3F] border border-[#E5D3BF]">
                <Database className="w-4 h-4" />
              </div>
              <h4 className="font-bold text-[#202124] text-xs">Full JSON Backup</h4>
            </div>
            <p className="text-[11px] text-[#5F6368] leading-relaxed">Complete normalized snapshot of event data, preferences, plan revisions, venues, and tasks.</p>
          </div>
          <button
            onClick={() => handleGenerate('json_backup')}
            disabled={generatingType === 'json_backup'}
            className="btn-outline w-full py-2 text-xs"
          >
            {generatingType === 'json_backup' && <Loader2 className="w-3.5 h-3.5 animate-spin motion-reduce:animate-none" />}
            Generate JSON
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

      {/* Generated Exports Table */}
      <div className="card-google overflow-hidden">
        <div className="px-5 py-4 border-b border-[#E8EAED] flex justify-between items-center bg-[#F8F9FA]">
          <span className="font-bold text-[#202124] text-xs">Generated Deliverables Archive ({exports.length})</span>
        </div>

        {loading ? (
          <div className="p-8 text-center text-xs text-[#5F6368] flex items-center justify-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin text-[#1A73E8] motion-reduce:animate-none" /> Loading archive...
          </div>
        ) : exports.length === 0 ? (
          <div className="p-8 text-center text-xs text-[#5F6368]">
            No deliverables generated yet. Click any button above to compile your first export.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-[#F8F9FA] text-[#5F6368] font-bold border-b border-[#E8EAED]">
                <tr>
                  <th className="py-3 px-4">Deliverable</th>
                  <th className="py-3 px-4">Format</th>
                  <th className="py-3 px-4">Size</th>
                  <th className="py-3 px-4">Created Date</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E8EAED] text-[#202124]">
                {exports.map((item) => (
                  <tr key={item.id} className="hover:bg-[#F8F9FA] transition-colors">
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-2.5">
                        {getTypeIcon(item.export_type)}
                        <span className="font-semibold text-[#202124]">{item.file_name}</span>
                      </div>
                    </td>
                    <td className="py-3 px-4 font-mono text-[11px] text-[#5F6368] uppercase">
                      {item.export_type.replace('_', ' ')}
                    </td>
                    <td className="py-3 px-4 font-mono text-[#5F6368]">
                      {formatFileSize(item.file_size_bytes)}
                    </td>
                    <td className="py-3 px-4 text-[#5F6368]">
                      {new Date(item.created_at).toLocaleString()}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => handleDownload(item)}
                          disabled={downloadingId === item.id}
                          className="btn-outline py-1.5 px-3 text-xs"
                          title="Download file to computer"
                        >
                          {downloadingId === item.id ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin motion-reduce:animate-none" />
                          ) : (
                            <Download className="w-3.5 h-3.5" />
                          )}
                          Download
                        </button>
                        <button
                          onClick={() => handleDelete(item.id)}
                          className="text-[#5F6368] hover:text-[#C5221F] p-1.5 transition-colors"
                          title="Delete file"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
