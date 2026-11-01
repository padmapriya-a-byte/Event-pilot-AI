'use client';

import React, { useEffect, useState } from 'react';
import { MapPin, Plus, Trash2, Check, AlertCircle, Loader2 } from 'lucide-react';
import { venuesApi } from '@/lib/api';
import { EventRecord, VenueRecord, VenueStatus } from '@/types';

interface VenuesTabProps {
  event: EventRecord;
}

const VENUE_STATUSES: VenueStatus[] = ['shortlisted', 'viewing_scheduled', 'proposal_received', 'selected', 'rejected'];

export function VenuesTab({ event }: VenuesTabProps) {
  const [venues, setVenues] = useState<VenueRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Add Venue State
  const [showAddModal, setShowAddModal] = useState(false);
  const [name, setName] = useState('');
  const [address, setAddress] = useState('');
  const [city, setCity] = useState('');
  const [capacity, setCapacity] = useState('');
  const [rentalCost, setRentalCost] = useState('');
  const [amenitiesInput, setAmenitiesInput] = useState('');
  const [status, setStatus] = useState<VenueStatus>('shortlisted');
  const [savingVenue, setSavingVenue] = useState(false);
  const [selectingVenueId, setSelectingVenueId] = useState<string | null>(null);

  const loadVenues = async () => {
    setLoading(true);
    try {
      const res = await venuesApi.list(event.id);
      setError(null);
      if (res.success && res.data) {
        setVenues(res.data);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load venues.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let ignore = false;

    async function fetchVenues() {
      try {
        const res = await venuesApi.list(event.id);
        if (!ignore) {
          setError(null);
          if (res.success && res.data) {
            setVenues(res.data);
          }
        }
      } catch (err: unknown) {
        if (!ignore) {
          setError(err instanceof Error ? err.message : 'Failed to load venues.');
        }
      } finally {
        if (!ignore) {
          setLoading(false);
        }
      }
    }

    fetchVenues();
    return () => {
      ignore = true;
    };
  }, [event.id]);

  const handleSelectVenue = async (venueId: string) => {
    setSelectingVenueId(venueId);
    setError(null);
    try {
      const res = await venuesApi.update(event.id, venueId, { is_selected: true });
      if (res.success) {
        await loadVenues();
      } else {
        setError(res.error?.message || 'Failed to select venue.');
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error during venue selection.');
    } finally {
      setSelectingVenueId(null);
    }
  };

  const handleAddVenue = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    setSavingVenue(true);
    try {
      const amenities = amenitiesInput
        .split(',')
        .map((a) => a.trim())
        .filter((a) => a.length > 0);

      const res = await venuesApi.create(event.id, {
        name: name.trim(),
        address: address.trim() || null,
        city: city.trim() || null,
        capacity: capacity ? parseInt(capacity, 10) : null,
        rental_cost: rentalCost ? parseFloat(rentalCost) : null,
        amenities: amenities.length > 0 ? amenities : undefined,
        status,
      });

      if (res.success) {
        setShowAddModal(false);
        setName('');
        setAddress('');
        setCity('');
        setCapacity('');
        setRentalCost('');
        setAmenitiesInput('');
        loadVenues();
      } else {
        setError(res.error?.message || 'Failed to add venue.');
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error adding venue.');
    } finally {
      setSavingVenue(false);
    }
  };

  const handleDeleteVenue = async (venueId: string) => {
    if (!confirm('Are you sure you want to remove this venue?')) return;
    try {
      const res = await venuesApi.delete(event.id, venueId);
      if (res.success) {
        loadVenues();
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to delete venue.');
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Action Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h3 className="text-lg font-bold text-[#202124] flex items-center gap-2">
            <MapPin className="w-5 h-5 text-[#137333]" /> Venue Candidates & Contracting
          </h3>
          <p className="text-xs text-[#5F6368] mt-0.5">Manage site visits, pricing proposals, and lock in your primary venue with atomic concurrency enforcement.</p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="btn-primary self-start sm:self-auto"
        >
          <Plus className="w-3.5 h-3.5" /> Add Venue Candidate
        </button>
      </div>

      {/* Error Callout */}
      {error && (
        <div className="p-4 rounded-xl bg-[#FCE8E6] border border-[#FAD2CF] text-[#C5221F] text-xs flex items-start gap-2.5">
          <AlertCircle className="w-4 h-4 text-[#C5221F] shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {/* Venues Grid */}
      {loading ? (
        <div className="p-12 text-center text-xs text-[#5F6368] flex items-center justify-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin text-[#1A73E8] motion-reduce:animate-none" /> Loading venues...
        </div>
      ) : venues.length === 0 ? (
        <div className="card-google p-12 text-center space-y-2">
          <MapPin className="w-8 h-8 text-[#5F6368] mx-auto" />
          <h4 className="font-bold text-[#202124] text-sm">No Venues Shortlisted</h4>
          <p className="text-xs text-[#5F6368]">Click &quot;Add Venue Candidate&quot; above to log your first venue option.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {venues.map((venue) => (
            <div
              key={venue.id}
              className={`p-6 rounded-2xl border transition-all space-y-3 relative ${
                venue.is_selected
                  ? 'card-google border-[#CEEAD6] bg-[#F3FBF5] shadow-md'
                  : 'card-google hover:border-[#1A73E8]/30'
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h4 className="font-bold text-[#202124] text-base">{venue.name}</h4>
                  <p className="text-xs text-[#5F6368] flex items-center gap-1 mt-0.5">
                    <MapPin className="w-3.5 h-3.5 text-[#5F6368]" />
                    {venue.city ? `${venue.city}, ${venue.address || ''}` : venue.address || 'Address TBD'}
                  </p>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="badge-neutral font-mono text-[10px] capitalize">
                    {venue.status.replace('_', ' ')}
                  </span>
                  <button
                    onClick={() => handleDeleteVenue(venue.id)}
                    className="text-[#5F6368] hover:text-[#C5221F] p-1 transition-colors"
                    title="Delete venue"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>

              {/* Specs */}
              <div className="grid grid-cols-2 gap-2 text-xs pt-3 border-t border-[#E8EAED]">
                <div>
                  <span className="text-[11px] font-semibold text-[#5F6368]">Capacity:</span>
                  <p className="font-bold text-[#202124]">{venue.capacity ? `${venue.capacity} guests` : 'N/A'}</p>
                </div>
                <div>
                  <span className="text-[11px] font-semibold text-[#5F6368]">Rental Cost:</span>
                  <p className="font-bold text-[#137333] font-mono">
                    {venue.rental_cost !== null ? `${event.currency} ${venue.rental_cost?.toLocaleString()}` : 'TBD'}
                  </p>
                </div>
              </div>

              {/* Amenities */}
              {venue.amenities && venue.amenities.length > 0 && (
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {venue.amenities.map((am, i) => (
                    <span key={i} className="badge-champagne text-[10px]">
                      {am}
                    </span>
                  ))}
                </div>
              )}

              {/* Selection Button */}
              <div className="pt-2">
                {venue.is_selected ? (
                  <div className="badge-mint w-full justify-center py-2 text-xs font-semibold">
                    <Check className="w-3.5 h-3.5 text-[#137333]" /> Selected Venue
                  </div>
                ) : (
                  <button
                    onClick={() => handleSelectVenue(venue.id)}
                    disabled={selectingVenueId === venue.id}
                    className="btn-outline w-full py-2 text-xs"
                  >
                    {selectingVenueId === venue.id && <Loader2 className="w-3.5 h-3.5 animate-spin motion-reduce:animate-none" />}
                    Select Venue
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add Venue Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 bg-[#202124]/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-md rounded-2xl bg-white border border-[#E8EAED] p-6 space-y-4 shadow-2xl">
            <div className="flex justify-between items-center pb-3 border-b border-[#E8EAED]">
              <h4 className="font-bold text-[#202124] text-sm">Add Venue Candidate</h4>
              <button
                onClick={() => setShowAddModal(false)}
                className="text-[#5F6368] hover:text-[#202124] text-sm p-1"
                aria-label="Close dialog"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleAddVenue} className="space-y-3.5">
              <div>
                <label className="block text-xs font-semibold text-[#202124] mb-1">Venue Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Grand Horizon Convention Center"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="input-google"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-[#202124] mb-1">City</label>
                  <input
                    type="text"
                    placeholder="San Francisco"
                    value={city}
                    onChange={(e) => setCity(e.target.value)}
                    className="input-google"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[#202124] mb-1">Status</label>
                  <select
                    value={status}
                    onChange={(e) => setStatus(e.target.value as VenueStatus)}
                    className="input-google capitalize"
                  >
                    {VENUE_STATUSES.map((st) => (
                      <option key={st} value={st}>
                        {st.replace('_', ' ')}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-[#202124] mb-1">Capacity (Guests)</label>
                  <input
                    type="number"
                    min="1"
                    placeholder="500"
                    value={capacity}
                    onChange={(e) => setCapacity(e.target.value)}
                    className="input-google"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[#202124] mb-1">Rental Cost ({event.currency})</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    placeholder="7500.00"
                    value={rentalCost}
                    onChange={(e) => setRentalCost(e.target.value)}
                    className="input-google"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#202124] mb-1">Street Address</label>
                <input
                  type="text"
                  placeholder="100 Market St"
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  className="input-google"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#202124] mb-1">Amenities (Comma-separated)</label>
                <input
                  type="text"
                  placeholder="AV Equipment, Stage, Catering Kitchen, Valet Parking"
                  value={amenitiesInput}
                  onChange={(e) => setAmenitiesInput(e.target.value)}
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
                  disabled={savingVenue}
                  className="btn-primary"
                >
                  {savingVenue && <Loader2 className="w-3.5 h-3.5 animate-spin motion-reduce:animate-none" />} Save Venue
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
