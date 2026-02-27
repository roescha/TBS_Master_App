import React, { useState } from 'react';

export default function PreFlight({ onStartAudit, isLoading }: { onStartAudit: (config: any) => void, isLoading: boolean }) {
    // --- Core Pipeline State ---
    const [ticker, setTicker] = useState('');
    const [profile, setProfile] = useState('TREND');
    const [mode, setMode] = useState('INFO');
    const [capital, setCapital] = useState('100000'); // [MANDATE: Dynamic Capital State]

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

        onStartAudit({
            ticker: ticker.toUpperCase(),
            profile,
            mode,
            capital: parseFloat(capital) || 100000,

            // [v8.3] Injecting Analyst Fallback Overrides
            wacc: wacc ? parseFloat(wacc) : null,
            moat: moat.trim().toUpperCase() || null,
            tnx: tnx ? parseFloat(tnx) : null,
            roic_override: roicOverride ? parseFloat(roicOverride) : null,
            de_override: deOverride ? parseFloat(deOverride) : null,
            fcf_yield_override: fcfYieldOverride ? parseFloat(fcfYieldOverride) : null,
            rev_override: revOverride ? parseFloat(revOverride) : null,
            eps_override: epsOverride ? parseFloat(epsOverride) : null,
            sector_etf_override: sectorEtfOverride ? sectorEtfOverride.toUpperCase() : null,
            pivot_confirmed: pivotConfirmed
        });
    };

    return (
        <div className="bg-gray-900 border-b border-gray-700 p-4 shadow-lg relative z-10">
            {/* Top Bar: Primary Inputs */}
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center space-x-6">
                    <h1 className="text-xl font-bold text-white tracking-widest">TBS<span className="text-blue-500">v8.3</span></h1>

                    <div className="flex items-center space-x-2">
                        <label className="text-gray-400 text-sm font-semibold uppercase">Ticker</label>
                        <input
                            type="text"
                            value={ticker}
                            onChange={(e) => setTicker(e.target.value.toUpperCase())}
                            disabled={isLoading}
                            placeholder="e.g. MSFT"
                            className="bg-gray-800 text-green-400 border border-gray-600 px-2 py-1 rounded focus:outline-none focus:border-green-500 w-28 font-mono disabled:opacity-50 uppercase"
                        />
                    </div>

                    <div className="flex items-center space-x-2 border-l border-gray-700 pl-4">
                        <label className="text-gray-400 text-sm font-semibold uppercase">Profile</label>
                        <select
                            value={profile}
                            onChange={(e) => setProfile(e.target.value)}
                            disabled={isLoading}
                            className="bg-gray-800 text-white border border-gray-600 px-2 py-1 rounded focus:outline-none focus:border-blue-500 disabled:opacity-50"
                        >
                            <option value="SWING">A - SWING</option>
                            <option value="TREND">B - TREND</option>
                            <option value="WEALTH">C - WEALTH</option>
                        </select>
                    </div>

                    <div className="flex items-center space-x-2 border-l border-gray-700 pl-4">
                        <label className="text-gray-400 text-sm font-semibold uppercase">Mode</label>
                        <select
                            value={mode}
                            onChange={(e) => setMode(e.target.value)}
                            disabled={isLoading}
                            className={`border px-2 py-1 rounded focus:outline-none disabled:opacity-50 ${mode === 'LIVE' ? 'bg-red-900/20 text-red-400 border-red-900/50' : 'bg-gray-800 text-blue-400 border-gray-600'}`}
                        >
                            <option value="INFO">INFO (Paper)</option>
                            <option value="LIVE">LIVE (Exec)</option>
                        </select>
                    </div>

                    <div className="flex items-center space-x-2 border-l border-gray-700 pl-4">
                        <label className="text-gray-400 text-sm font-semibold uppercase">Capital</label>
                        <input
                            type="number"
                            value={capital}
                            onChange={(e) => setCapital(e.target.value)}
                            disabled={isLoading}
                            className="bg-gray-800 text-white border border-gray-600 px-2 py-1 rounded focus:outline-none focus:border-blue-500 w-32 font-mono disabled:opacity-50"
                        />
                    </div>
                </div>

                <div className="flex space-x-4">
                    <button
                        onClick={() => setShowOverrides(!showOverrides)}
                        className="text-sm font-bold py-2 px-4 rounded border border-gray-600 text-gray-400 hover:text-white transition-all uppercase"
                    >
                        {showOverrides ? 'Hide Overrides' : 'Analyst Overrides'}
                    </button>

                    <button
                        onClick={handleStart}
                        disabled={isLoading}
                        className={`font-bold py-2 px-6 rounded shadow-md transition-all uppercase tracking-widest ${
                            isLoading
                                ? 'bg-gray-800 text-blue-500 border border-blue-900/50 cursor-not-allowed animate-pulse'
                                : 'bg-blue-600 hover:bg-blue-500 text-white'
                        }`}
                    >
                        {isLoading ? 'Executing...' : 'Start Audit'}
                    </button>
                </div>
            </div>

            {/* v8.3 Fallback Track: Analyst Overrides Panel */}
            {showOverrides && (
                <div className="bg-black/50 border border-yellow-900/50 p-4 rounded mt-4 grid grid-cols-5 gap-4">
                    <div className="col-span-5 mb-2">
                        <span className="text-yellow-500 font-bold text-xs uppercase tracking-widest block">Doc 8 Sec V: Fallback Track Injection</span>
                        <span className="text-gray-400 text-xs">Use only if Yahoo/IBKR APIs return missing or masked data.</span>
                    </div>

                    {/* Row 1 */}
                    <div className="flex flex-col space-y-1">
                        <label className="text-gray-400 text-xs font-semibold uppercase">TNX Yield %</label>
                        <input type="number" step="0.01" value={tnx} onChange={e => setTnx(e.target.value)} placeholder="e.g. 4.05" className="bg-gray-800 text-yellow-400 border border-gray-600 px-2 py-1 rounded text-sm font-mono focus:border-yellow-500" />
                    </div>
                    <div className="flex flex-col space-y-1">
                        <label className="text-gray-400 text-xs font-semibold uppercase">ROIC %</label>
                        <input type="number" step="0.1" value={roicOverride} onChange={e => setRoicOverride(e.target.value)} placeholder="e.g. 15.4" className="bg-gray-800 text-yellow-400 border border-gray-600 px-2 py-1 rounded text-sm font-mono focus:border-yellow-500" />
                    </div>
                    <div className="flex flex-col space-y-1">
                        <label className="text-gray-400 text-xs font-semibold uppercase">Rev Growth %</label>
                        <input type="number" step="0.1" value={revOverride} onChange={e => setRevOverride(e.target.value)} placeholder="e.g. 21.5" className="bg-gray-800 text-yellow-400 border border-gray-600 px-2 py-1 rounded text-sm font-mono focus:border-yellow-500" />
                    </div>
                    <div className="flex flex-col space-y-1">
                        <label className="text-gray-400 text-xs font-semibold uppercase">EPS Growth %</label>
                        <input type="number" step="0.1" value={epsOverride} onChange={e => setEpsOverride(e.target.value)} placeholder="e.g. 8.2" className="bg-gray-800 text-yellow-400 border border-gray-600 px-2 py-1 rounded text-sm font-mono focus:border-yellow-500" />
                    </div>
                    <div className="flex flex-col space-y-1">
                        <label className="text-gray-400 text-xs font-semibold uppercase">D/E Ratio %</label>
                        <input type="number" step="0.1" value={deOverride} onChange={e => setDeOverride(e.target.value)} placeholder="e.g. 110.5" className="bg-gray-800 text-yellow-400 border border-gray-600 px-2 py-1 rounded text-sm font-mono focus:border-yellow-500" />
                    </div>

                    {/* Row 2 */}
                    <div className="flex flex-col space-y-1">
                        <label className="text-gray-400 text-xs font-semibold uppercase">FCF Yield %</label>
                        <input type="number" step="0.1" value={fcfYieldOverride} onChange={e => setFcfYieldOverride(e.target.value)} placeholder="e.g. 4.1" className="bg-gray-800 text-yellow-400 border border-gray-600 px-2 py-1 rounded text-sm font-mono focus:border-yellow-500" />
                    </div>
                    <div className="flex flex-col space-y-1">
                        <label className="text-gray-400 text-xs font-semibold uppercase">WACC % (Turnaround)</label>
                        <input type="number" step="0.1" value={wacc} onChange={e => setWacc(e.target.value)} placeholder="e.g. 9.5" className="bg-gray-800 text-yellow-400 border border-gray-600 px-2 py-1 rounded text-sm font-mono focus:border-yellow-500" />
                    </div>
                    <div className="flex flex-col space-y-1">
                        <label className="text-gray-400 text-xs font-semibold uppercase">Moat (Wealth)</label>
                        <select value={moat} onChange={e => setMoat(e.target.value)} className="bg-gray-800 text-yellow-400 border border-gray-600 px-2 py-1 rounded text-sm font-mono focus:border-yellow-500">
                            <option value="">-- Select --</option>
                            <option value="WIDE">WIDE</option>
                            <option value="NARROW">NARROW</option>
                            <option value="NONE">NONE</option>
                        </select>
                    </div>
                    <div className="flex flex-col space-y-1">
                        <label className="text-gray-400 text-xs font-semibold uppercase">Sector ETF</label>
                        <input type="text" value={sectorEtfOverride} onChange={e => setSectorEtfOverride(e.target.value)} placeholder="e.g. XLK" className="bg-gray-800 text-yellow-400 border border-gray-600 px-2 py-1 rounded text-sm font-mono focus:border-yellow-500 uppercase" />
                    </div>
                    <div className="flex flex-col space-y-1 justify-end">
                        <label className="flex items-center space-x-2 text-gray-400 text-xs font-semibold uppercase cursor-pointer">
                            <input type="checkbox" checked={pivotConfirmed} onChange={(e) => setPivotConfirmed(e.target.checked)} className="form-checkbox h-4 w-4 text-yellow-500 bg-gray-800 border-gray-600 rounded focus:ring-yellow-500" />
                            <span>Pivot Confirmed</span>
                        </label>
                    </div>
                </div>
            )}
        </div>
    );
}