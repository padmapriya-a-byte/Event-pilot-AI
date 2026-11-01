'use client';

import React, { useEffect, useState } from 'react';
import { Bot, LogOut, AlertCircle, RefreshCw } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { getBackendHealth } from '@/lib/api';
import { BackendHealthData } from '@/types';

export function Navbar() {
  const { user, signOut } = useAuth();
  const [health, setHealth] = useState<BackendHealthData | null>(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [showHealthDetails, setShowHealthDetails] = useState(false);

  const fetchHealth = async () => {
    try {
      const res = await getBackendHealth();
      if (res.success && res.data) {
        setHealth(res.data);
      }
    } catch {
      setHealth(null);
    } finally {
      setHealthLoading(false);
    }
  };

  const handleManualRefresh = async () => {
    setHealthLoading(true);
    await fetchHealth();
  };

  useEffect(() => {
    let ignore = false;

    async function loadHealth() {
      try {
        const res = await getBackendHealth();
        if (!ignore) {
          if (res.success && res.data) {
            setHealth(res.data);
          } else {
            setHealth(null);
          }
        }
      } catch {
        if (!ignore) {
          setHealth(null);
        }
      } finally {
        if (!ignore) {
          setHealthLoading(false);
        }
      }
    }

    loadHealth();
    const interval = setInterval(() => {
      loadHealth();
    }, 30000);

    return () => {
      ignore = true;
      clearInterval(interval);
    };
  }, []);

  return (
    <header className="border-b border-[#E8EAED] bg-white/95 backdrop-blur-md sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-[#E8F0FE] text-[#1A73E8] border border-[#D2E3FC] shadow-sm">
            <Bot className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-lg text-[#202124] tracking-tight">EventPilot AI</span>
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-[#F5EBE1] text-[#8C6D3F] border border-[#E5D3BF]">
                v1.0
              </span>
            </div>
            <p className="text-[11px] text-[#5F6368] hidden sm:block">Autonomous Event Planning & Operations</p>
          </div>
        </div>

        {/* Right Section: Health Pill & User Auth */}
        <div className="flex items-center gap-3">
          {/* Live Backend Health Pill */}
          <div className="relative">
            <button
              onClick={() => setShowHealthDetails(!showHealthDetails)}
              className="flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium bg-[#F8F9FA] border border-[#DADCE0] hover:bg-[#F1F3F4] transition-colors"
              title="Click to view backend health status"
            >
              {healthLoading ? (
                <RefreshCw className="w-3.5 h-3.5 text-[#5F6368] animate-spin" />
              ) : health?.status === 'healthy' ? (
                <span className="flex items-center gap-1.5 text-[#137333] font-medium">
                  <span className="w-2 h-2 rounded-full bg-[#137333] animate-pulse" />
                  API Healthy
                </span>
              ) : (
                <span className="flex items-center gap-1.5 text-[#B06000] font-medium">
                  <AlertCircle className="w-3.5 h-3.5 text-[#B06000]" />
                  API Degraded
                </span>
              )}
            </button>

            {/* Health Popover Details */}
            {showHealthDetails && (
              <div className="absolute right-0 mt-2 w-72 rounded-2xl bg-white border border-[#E8EAED] shadow-xl p-4 z-50 text-xs space-y-3">
                <div className="flex items-center justify-between pb-2 border-b border-[#E8EAED]">
                  <span className="font-semibold text-[#202124]">System Integration Status</span>
                  <button
                    onClick={() => setShowHealthDetails(false)}
                    className="text-[#5F6368] hover:text-[#202124] p-1"
                    aria-label="Close health status details"
                  >
                    ✕
                  </button>
                </div>
                {health ? (
                  <div className="space-y-2 text-[#5F6368]">
                    <div className="flex justify-between">
                      <span>Backend Service:</span>
                      <span className="font-mono text-[11px] text-[#202124]">{health.service}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Environment:</span>
                      <span className="capitalize text-[#202124]">{health.environment}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Supabase DB:</span>
                      <span className={health.integrations.supabase.configured ? 'text-[#137333] font-semibold' : 'text-[#C5221F] font-semibold'}>
                        {health.integrations.supabase.configured ? 'Connected' : 'Unconfigured'}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span>Gemini AI Model:</span>
                      <span className="font-mono text-[11px] text-[#1A73E8] font-medium">
                        {health.integrations.gemini_ai.model || 'None'}
                      </span>
                    </div>
                  </div>
                ) : (
                  <p className="text-[#C5221F]">Could not communicate with Flask backend at {process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000'}</p>
                )}
                <div className="pt-2 border-t border-[#E8EAED] text-right">
                  <button
                    onClick={handleManualRefresh}
                    disabled={healthLoading}
                    className="text-[11px] text-[#1A73E8] hover:underline font-semibold"
                  >
                    Refresh Now
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* User Email & Sign Out */}
          {user && (
            <div className="flex items-center gap-2 pl-3 border-l border-[#E8EAED]">
              <span className="text-xs text-[#5F6368] hidden md:block max-w-[160px] truncate" title={user.email}>
                {user.email}
              </span>
              <button
                onClick={() => signOut()}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold text-[#5F6368] bg-[#F8F9FA] border border-[#DADCE0] hover:bg-[#F1F3F4] hover:text-[#202124] transition-colors shadow-sm"
                title="Sign Out"
              >
                <LogOut className="w-3.5 h-3.5 text-[#5F6368]" />
                <span className="hidden sm:inline">Sign Out</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
