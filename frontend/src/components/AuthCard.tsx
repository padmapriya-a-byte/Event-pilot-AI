'use client';

import React, { useState } from 'react';
import { LogIn, UserPlus, Shield, AlertCircle, CheckCircle2, Loader2 } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';

export function AuthCard() {
  const { signIn, signUp } = useAuth();
  const [mode, setMode] = useState<'signin' | 'signup'>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setMessage(null);

    if (!email.trim() || !password) {
      setError('Please provide both an email and password.');
      return;
    }

    if (password.length < 6) {
      setError('Password must be at least 6 characters.');
      return;
    }

    setLoading(true);
    try {
      if (mode === 'signin') {
        const { error: signInErr } = await signIn(email.trim(), password);
        if (signInErr) {
          setError(signInErr.message);
        }
      } else {
        const { error: signUpErr, needsEmailConfirmation } = await signUp(email.trim(), password);
        if (signUpErr) {
          setError(signUpErr.message);
        } else if (needsEmailConfirmation) {
          setMessage('Account created! Please check your email inbox to confirm your account before logging in.');
          setMode('signin');
        } else {
          setMessage('Account created successfully! You are now logged in.');
        }
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'An unexpected authentication error occurred.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-full max-w-md mx-auto p-8 rounded-2xl bg-white border border-[#E8EAED] shadow-lg">
      {/* Header */}
      <div className="text-center space-y-2 mb-6">
        <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-[#E8F0FE] text-[#1A73E8] border border-[#D2E3FC] mb-1 shadow-sm">
          <Shield className="w-6 h-6" />
        </div>
        <h2 className="text-xl font-bold text-[#202124] tracking-tight">
          {mode === 'signin' ? 'Sign in to EventPilot AI' : 'Create an Account'}
        </h2>
        <p className="text-xs text-[#5F6368]">
          {mode === 'signin'
            ? 'Access your autonomous event master plans, budgets, and deliverables.'
            : 'Get started planning, optimizing, and executing intelligent events.'}
        </p>
      </div>

      {/* Segmented Mode Control */}
      <div className="grid grid-cols-2 p-1 rounded-xl bg-[#F1F3F4] border border-[#E8EAED] mb-6">
        <button
          type="button"
          onClick={() => {
            setMode('signin');
            setError(null);
            setMessage(null);
          }}
          className={`flex items-center justify-center gap-2 py-2 text-xs font-semibold rounded-lg transition-all ${
            mode === 'signin'
              ? 'bg-white text-[#1A73E8] shadow-sm'
              : 'text-[#5F6368] hover:text-[#202124]'
          }`}
        >
          <LogIn className="w-3.5 h-3.5" />
          Sign In
        </button>
        <button
          type="button"
          onClick={() => {
            setMode('signup');
            setError(null);
            setMessage(null);
          }}
          className={`flex items-center justify-center gap-2 py-2 text-xs font-semibold rounded-lg transition-all ${
            mode === 'signup'
              ? 'bg-white text-[#1A73E8] shadow-sm'
              : 'text-[#5F6368] hover:text-[#202124]'
          }`}
        >
          <UserPlus className="w-3.5 h-3.5" />
          Sign Up
        </button>
      </div>

      {/* Error & Success Messages */}
      {error && (
        <div className="p-3 mb-4 rounded-xl bg-[#FCE8E6] border border-[#FAD2CF] text-[#C5221F] text-xs flex items-start gap-2">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-[#C5221F]" />
          <span>{error}</span>
        </div>
      )}

      {message && (
        <div className="p-3 mb-4 rounded-xl bg-[#E6F4EA] border border-[#CEEAD6] text-[#137333] text-xs flex items-start gap-2">
          <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5 text-[#137333]" />
          <span>{message}</span>
        </div>
      )}

      {/* Form */}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-xs font-semibold text-[#202124] mb-1.5">Email Address</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
            placeholder="planner@eventpilot.ai"
            className="input-google"
          />
        </div>

        <div>
          <label className="block text-xs font-semibold text-[#202124] mb-1.5">Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
            placeholder="••••••••"
            className="input-google"
          />
        </div>

        <button
          type="submit"
          disabled={loading}
          className="btn-primary w-full py-2.5 mt-2"
        >
          {loading && <Loader2 className="w-4 h-4 animate-spin motion-reduce:animate-none" />}
          {mode === 'signin' ? 'Sign In to Dashboard' : 'Create Free Account'}
        </button>
      </form>
    </div>
  );
}
