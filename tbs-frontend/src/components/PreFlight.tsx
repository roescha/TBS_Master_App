import React, { useState } from 'react';

export default function PreFlight({ onStartAudit, isLoading }: { onStartAudit: (config: any) => void, isLoading: boolean }) {
    const [ticker, setTicker] = useState('');
    const [profile, setProfile] = useState('TREND');
    const [mode, setMode] = useState('INFO');
    const [wacc, setWacc] = useState('');
    const [capital, setCapital] = useState('100000'); // [MANDATE: Dynamic Capital State]

    const handleStart = () => {
        if (!ticker || isLoading) return;
        onStartAudit({
            ticker: ticker.toUpperCase(),
            profile,
            mode,
            wacc: wacc ? parseFloat(wacc) : null,
            capital: parseFloat(capital) || 100000 // [MANDATE: Pass to Orchestrator]
        });
    };

    return (
        <div className="bg-gray-900 border-b border-gray-700 p-4 flex items-center justify-between shadow-lg relative z-10">
            <div className="flex items-center space-x-6">
                <h1 className="text-xl font-bold text-white tracking-widest">TBS<span className="text-blue-500">v8.2</span></h1>

                <div className="flex items-center space-x-2">
                    <label className="text-gray-400 text-sm font-semibold uppercase">Target</label>
                    <input
                        type="text"
                        value={ticker}
                        onChange={(e) => setTicker(e.target.value)}
                        disabled={isLoading}
                        placeholder="TICKER"
                        className="bg-gray-800 text-white border border-gray-600 px-3 py-1 rounded focus:outline-none focus:border-blue-500 uppercase w-24 font-mono disabled:opacity-50"
                    />
                </div>

                <div className="flex items-center space-x-2">
                    <label className="text-gray-400 text-sm font-semibold uppercase">Profile</label>
                    <select
                        value={profile}
                        onChange={(e) => setProfile(e.target.value)}
                        disabled={isLoading}
                        className="bg-gray-800 text-white border border-gray-600 px-3 py-1 rounded focus:outline-none focus:border-blue-500 font-mono disabled:opacity-50"
                    >
                        <option value="SWING">Profile A (Swing)</option>
                        <option value="TREND">Profile B (Trend)</option>
                        <option value="WEALTH">Profile C (Wealth)</option>
                    </select>
                </div>

                <div className="flex items-center space-x-2">
                    <label className="text-gray-400 text-sm font-semibold uppercase">Audit</label>
                    <select
                        value={mode}
                        onChange={(e) => setMode(e.target.value)}
                        disabled={isLoading}
                        className={`bg-gray-800 border px-3 py-1 rounded focus:outline-none font-mono font-bold disabled:opacity-50 ${mode === 'LIVE' ? 'text-red-500 border-red-500' : 'text-green-400 border-gray-600'}`}
                    >
                        <option value="INFO">INFO</option>
                        <option value="LIVE">LIVE</option>
                    </select>
                </div>

                {/* [MANDATE: NEW CAPITAL INPUT UI] */}
                <div className="flex items-center space-x-2 border-l border-gray-700 pl-4">
                    <label className="text-gray-400 text-sm font-semibold uppercase">Capital $</label>
                    <input
                        type="number"
                        step="1000"
                        value={capital}
                        onChange={(e) => setCapital(e.target.value)}
                        disabled={isLoading}
                        className="bg-gray-800 text-green-400 border border-gray-600 px-2 py-1 rounded focus:outline-none focus:border-green-500 w-28 font-mono disabled:opacity-50"
                    />
                </div>

                <div className="flex items-center space-x-2 border-l border-gray-700 pl-4">
                    <label className="text-gray-400 text-sm font-semibold uppercase">WACC %</label>
                    <input
                        type="number"
                        step="0.1"
                        value={wacc}
                        onChange={(e) => setWacc(e.target.value)}
                        disabled={isLoading}
                        placeholder="AI Value"
                        className="bg-gray-800 text-yellow-400 border border-gray-600 px-2 py-1 rounded focus:outline-none focus:border-yellow-500 w-24 font-mono disabled:opacity-50"
                    />
                </div>
            </div>

            <button
                onClick={handleStart}
                disabled={isLoading}
                className={`font-bold py-2 px-6 rounded shadow-md transition-all uppercase tracking-widest ${
                    isLoading
                        ? 'bg-gray-800 text-blue-500 border border-blue-900/50 cursor-not-allowed animate-pulse'
                        : 'bg-blue-600 hover:bg-blue-500 text-white'
                }`}
            >
                {isLoading ? 'SYSTEM ACTIVE ⏳' : 'START AUDIT'}
            </button>
        </div>
    );
}