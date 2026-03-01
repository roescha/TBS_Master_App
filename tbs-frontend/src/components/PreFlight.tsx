import React, { useState } from 'react';

export default function PreFlight({ onStartAudit, isLoading }: { onStartAudit: (config: any) => void, isLoading: boolean }) {
    // --- Core Pipeline State ---
    const [ticker, setTicker] = useState('');
    const [profile, setProfile] = useState('TREND');
    const [mode, setMode] = useState('INFO');
    const [capital, setCapital] = useState('100000'); // [MANDATE: Dynamic Capital State]

    // --- Position Monitor State ---
    const [entryPrice, setEntryPrice] = useState('');
    const [shares, setShares] = useState('');

    // --- v8.3 Fallback Track Overrides State ---
    const [showOverrides, setShowOverrides] = useState(false);
    const [wacc, setWacc] = useState('');
    const [moat, setMoat] = useState('');
    const [tnx, setTnx] = useState('');
    const [roicOverride, setRoicOverride] = useState('');
    const [deOverride, setDeOverride] = useState('');
    const [fcfYieldOverride, setFcfYieldOverride] = useState('');
    const [revOverride, setRevOverride] = useState('');
    const [epsOverride, setEpsOverride] = useState('');
    const [sectorEtfOverride, setSectorEtfOverride] = useState('');
    const [pivotConfirmed, setPivotConfirmed] = useState(false);

    const handleStart = () => {
        if (!ticker || isLoading) return;

        // Ensure Position Monitor flags are paired if one is provided
        if ((entryPrice && !shares) || (!entryPrice && shares)) {
            alert("Position Monitor requires BOTH Entry Price and Shares.");
            return;
        }

        onStartAudit({
            ticker: ticker.toUpperCase(),
            profile,
            mode,
            total_capital: parseFloat(capital),

            // Monitor Mode payload
            entry_price: entryPrice ? parseFloat(entryPrice) : undefined,
            shares: shares ? parseInt(shares, 10) : undefined,

            // Overrides
            wacc: wacc ? parseFloat(wacc) : undefined,
            moat: moat || undefined,
            tnx: tnx ? parseFloat(tnx) : undefined,
            roic_override: roicOverride ? parseFloat(roicOverride) : undefined,
            de_override: deOverride ? parseFloat(deOverride) : undefined,
            fcf_yield_override: fcfYieldOverride ? parseFloat(fcfYieldOverride) : undefined,
            rev_override: revOverride ? parseFloat(revOverride) : undefined,
            eps_override: epsOverride ? parseFloat(epsOverride) : undefined,
            sector_etf_override: sectorEtfOverride ? sectorEtfOverride.toUpperCase() : undefined,
            pivot_confirmed: pivotConfirmed
        });
    };

    return (
        <div className="bg-black p-6 border-b border-gray-800">
            {/* --- Core Inputs --- */}
            <div className="flex flex-col md:flex-row gap-4 items-end mb-6">
                <div className="flex flex-col space-y-1 flex-grow">
                    <label className="text-gray-400 text-xs font-bold uppercase tracking-widest">Ticker</label>
                    <input
                        type="text"
                        value={ticker}
                        onChange={e => setTicker(e.target.value)}
                        placeholder="e.g. AAPL"
                        className="bg-gray-900 text-white border border-gray-700 px-4 py-3 rounded font-mono focus:border-blue-500 focus:outline-none uppercase text-lg"
                        onKeyDown={(e) => e.key === 'Enter' && handleStart()}
                    />
                </div>

                <div className="flex flex-col space-y-1 w-32">
                    <label className="text-gray-400 text-xs font-bold uppercase tracking-widest">Profile</label>
                    <select
                        value={profile}
                        onChange={e => setProfile(e.target.value)}
                        className="bg-gray-900 text-white border border-gray-700 px-3 py-3 rounded font-mono focus:border-blue-500 focus:outline-none"
                    >
                        <option value="SWING">SWING (A)</option>
                        <option value="TREND">TREND (B)</option>
                        <option value="WEALTH">WEALTH (C)</option>
                    </select>
                </div>

                <div className="flex flex-col space-y-1 w-32">
                    <label className="text-gray-400 text-xs font-bold uppercase tracking-widest">Mode</label>
                    <select
                        value={mode}
                        onChange={e => setMode(e.target.value)}
                        className={`bg-gray-900 border border-gray-700 px-3 py-3 rounded font-mono focus:outline-none font-bold ${mode === 'LIVE' ? 'text-red-500 focus:border-red-500' : 'text-blue-500 focus:border-blue-500'}`}
                    >
                        <option value="INFO">INFO</option>
                        <option value="LIVE">LIVE</option>
                    </select>
                </div>

                <div className="flex flex-col space-y-1 w-40">
                    <label className="text-gray-400 text-xs font-bold uppercase tracking-widest">Capital ($)</label>
                    <input
                        type="number"
                        value={capital}
                        onChange={e => setCapital(e.target.value)}
                        className="bg-gray-900 text-white border border-gray-700 px-3 py-3 rounded font-mono focus:border-blue-500 focus:outline-none"
                    />
                </div>
            </div>

            {/* --- Position Monitor Section --- */}
            <div className="p-4 rounded-lg border border-gray-800 bg-gray-950/50 flex flex-wrap gap-4 items-center mb-6">
                <div className="w-full text-xs font-bold text-gray-500 uppercase tracking-widest border-b border-gray-800 pb-2 mb-2">
                    Position Monitor (Evaluate Existing Holding)
                </div>
                <div className="flex flex-col space-y-1">
                    <label className="text-gray-400 text-[10px] font-semibold uppercase">Avg Entry Price ($)</label>
                    <input
                        type="number" step="0.01"
                        value={entryPrice} onChange={e => setEntryPrice(e.target.value)}
                        placeholder="e.g. 150.25"
                        className="bg-gray-900 text-white border border-gray-700 px-3 py-2 rounded text-sm font-mono focus:border-blue-500 outline-none w-36"
                    />
                </div>
                <div className="flex flex-col space-y-1">
                    <label className="text-gray-400 text-[10px] font-semibold uppercase">Shares Held</label>
                    <input
                        type="number"
                        value={shares} onChange={e => setShares(e.target.value)}
                        placeholder="e.g. 100"
                        className="bg-gray-900 text-white border border-gray-700 px-3 py-2 rounded text-sm font-mono focus:border-blue-500 outline-none w-32"
                    />
                </div>
                <div className="flex items-center pt-5">
                    <span className="text-xs text-gray-500 font-mono italic">
                        * Provide BOTH to bypass Fail-Fast and evaluate structural health.
                    </span>
                </div>
            </div>

            {/* --- Analyst Overrides Section --- */}
            <div className="flex items-center justify-between mb-4">
                <button
                    onClick={() => setShowOverrides(!showOverrides)}
                    className="text-xs text-yellow-600 hover:text-yellow-400 font-mono uppercase tracking-widest flex items-center transition-colors"
                >
                    {showOverrides ? '▼ Hide Manual Track Overrides' : '▶ Show Manual Track Overrides'}
                </button>
            </div>

            {showOverrides && (
                <div className="mb-6 grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 p-4 rounded border border-yellow-900/30 bg-yellow-900/10">
                    <div className="flex flex-col space-y-1">
                        <label className="text-gray-400 text-[10px] font-semibold uppercase">Rev Growth %</label>
                        <input type="number" step="0.1" value={revOverride} onChange={e => setRevOverride(e.target.value)} placeholder="e.g. 6.8" className="bg-gray-900 text-yellow-400 border border-gray-700 px-2 py-1 rounded text-sm font-mono focus:border-yellow-500 outline-none" />
                    </div>
                    <div className="flex flex-col space-y-1">
                        <label className="text-gray-400 text-[10px] font-semibold uppercase">EPS Growth %</label>
                        <input type="number" step="0.1" value={epsOverride} onChange={e => setEpsOverride(e.target.value)} placeholder="e.g. 8.5" className="bg-gray-900 text-yellow-400 border border-gray-700 px-2 py-1 rounded text-sm font-mono focus:border-yellow-500 outline-none" />
                    </div>
                    <div className="flex flex-col space-y-1">
                        <label className="text-gray-400 text-[10px] font-semibold uppercase">ROIC %</label>
                        <input type="number" step="0.1" value={roicOverride} onChange={e => setRoicOverride(e.target.value)} placeholder="e.g. 12.5" className="bg-gray-900 text-yellow-400 border border-gray-700 px-2 py-1 rounded text-sm font-mono focus:border-yellow-500 outline-none" />
                    </div>
                    <div className="flex flex-col space-y-1">
                        <label className="text-gray-400 text-[10px] font-semibold uppercase">Debt-to-Equity</label>
                        <input type="number" step="0.1" value={deOverride} onChange={e => setDeOverride(e.target.value)} placeholder="e.g. 139.8" className="bg-gray-900 text-yellow-400 border border-gray-700 px-2 py-1 rounded text-sm font-mono focus:border-yellow-500 outline-none" />
                    </div>
                    <div className="flex flex-col space-y-1">
                        <label className="text-gray-400 text-[10px] font-semibold uppercase">FCF Yield %</label>
                        <input type="number" step="0.1" value={fcfYieldOverride} onChange={e => setFcfYieldOverride(e.target.value)} placeholder="e.g. 3.5" className="bg-gray-900 text-yellow-400 border border-gray-700 px-2 py-1 rounded text-sm font-mono focus:border-yellow-500 outline-none" />
                    </div>
                    <div className="flex flex-col space-y-1">
                        <label className="text-gray-400 text-[10px] font-semibold uppercase">WACC % (Turnaround)</label>
                        <input type="number" step="0.1" value={wacc} onChange={e => setWacc(e.target.value)} placeholder="e.g. 9.2" className="bg-gray-900 text-yellow-400 border border-gray-700 px-2 py-1 rounded text-sm font-mono focus:border-yellow-500 outline-none" />
                    </div>
                    <div className="flex flex-col space-y-1">
                        <label className="text-gray-400 text-[10px] font-semibold uppercase">TNX Yield %</label>
                        <input type="number" step="0.1" value={tnx} onChange={e => setTnx(e.target.value)} placeholder="e.g. 4.1" className="bg-gray-900 text-yellow-400 border border-gray-700 px-2 py-1 rounded text-sm font-mono focus:border-yellow-500 outline-none" />
                    </div>
                    <div className="flex flex-col space-y-1">
                        <label className="text-gray-400 text-[10px] font-semibold uppercase">Moat (WEALTH)</label>
                        <select value={moat} onChange={e => setMoat(e.target.value)} className="bg-gray-900 text-yellow-400 border border-gray-700 px-2 py-1 rounded text-sm font-mono focus:border-yellow-500 outline-none">
                            <option value="">-- Select --</option>
                            <option value="WIDE">WIDE</option>
                            <option value="NARROW">NARROW</option>
                            <option value="NONE">NONE</option>
                        </select>
                    </div>
                    <div className="flex flex-col space-y-1">
                        <label className="text-gray-400 text-[10px] font-semibold uppercase">Sector ETF</label>
                        <input type="text" value={sectorEtfOverride} onChange={e => setSectorEtfOverride(e.target.value)} placeholder="e.g. XLK" className="bg-gray-900 text-yellow-400 border border-gray-700 px-2 py-1 rounded text-sm font-mono focus:border-yellow-500 outline-none uppercase" />
                    </div>
                    <div className="flex flex-col space-y-1 justify-end">
                        <label className="flex items-center space-x-2 text-gray-400 text-[10px] font-semibold uppercase cursor-pointer mb-2">
                            <input type="checkbox" checked={pivotConfirmed} onChange={(e) => setPivotConfirmed(e.target.checked)} className="form-checkbox h-4 w-4 text-yellow-500 bg-gray-900 border-gray-700 rounded focus:ring-yellow-500" />
                            <span>Pivot Confirmed</span>
                        </label>
                    </div>
                </div>
            )}

            {/* --- Engage Action --- */}
            <div className="flex justify-end pt-2 border-t border-gray-800">
                <button
                    onClick={handleStart}
                    disabled={isLoading || !ticker}
                    className={`px-10 py-3 rounded font-bold uppercase tracking-widest transition-all ${
                        isLoading || !ticker
                            ? 'bg-gray-800 text-gray-600 cursor-not-allowed'
                            : mode === 'LIVE'
                                ? 'bg-red-600 hover:bg-red-500 text-white shadow-[0_0_15px_rgba(220,38,38,0.5)]'
                                : 'bg-blue-600 hover:bg-blue-500 text-white shadow-[0_0_15px_rgba(37,99,235,0.5)]'
                    }`}
                >
                    {isLoading ? 'Processing...' : 'Engage Pipeline'}
                </button>
            </div>
        </div>
    );
}