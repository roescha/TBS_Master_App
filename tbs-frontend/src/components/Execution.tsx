import React, { useState } from 'react';

// [MANDATE: TYPE SYNC] Synchronized with Step 7 Governor Response [cite: 536, 542]
interface ExecutionProps {
    sizingData: {
        entry_price: number;
        stop_price: number;
        target_price: number | string;
        final_units: number;
        multiplier: number;
        total_risk: number;
    };
    fundamentalResult: any;
    eventAware: boolean;
}

export default function Execution({ sizingData, fundamentalResult, eventAware }: ExecutionProps) {
    const [showTicket, setShowTicket] = useState(false);

    if (!sizingData) return null;

    // --- [MANDATE: DATA EXTRACTION] Strictly consuming Python Governor API output [cite: 512, 532] ---
    const price = sizingData.entry_price || 0;
    const stopValue = sizingData.stop_price || 0;
    const units = sizingData.final_units || 0;
    const multiplier = sizingData.multiplier || 1.0;
    const totalRisk = sizingData.total_risk || 0;
    const targetPriceRaw = sizingData.target_price || "OPEN-ENDED";

    // Format target for Profile C display [cite: 196]
    const displayTarget = typeof targetPriceRaw === 'number' ? `$${targetPriceRaw.toFixed(2)}` : targetPriceRaw;

    return (
        <div className="fixed bottom-0 left-0 right-0 bg-gray-950 border-t-4 border-blue-600 shadow-2xl z-50">

            {/* --- TOP ROW: THE GOVERNOR DASHBOARD --- */}
            <div className="max-w-7xl mx-auto flex items-center justify-between p-6">
                <div className="flex space-x-12">
                    <div>
                        <span className="text-blue-400 text-xs font-black uppercase tracking-widest block mb-1">
                            Unit Sizing (Total Heat: ${totalRisk.toFixed(2)})
                        </span>
                        <span className="text-3xl font-mono font-bold text-white">
                            {units} <span className="text-sm text-gray-500 font-sans uppercase">Shares</span>
                        </span>
                    </div>

                    <div className="border-l border-gray-800 pl-12">
                        <span className="text-yellow-400 text-xs font-black uppercase tracking-widest block mb-1">Posture Multiplier</span>
                        <span className="text-2xl font-mono text-white">{multiplier.toFixed(2)}x</span>
                    </div>

                    <div className="border-l border-gray-800 pl-12">
                        <span className="text-red-400 text-xs font-black uppercase tracking-widest block mb-1">1.5x ATR Stop</span>
                        <span className="text-2xl font-mono text-white">${stopValue.toFixed(2)}</span>
                    </div>

                    <div className="border-l border-gray-800 pl-12">
                        <span className="text-green-400 text-xs font-black uppercase tracking-widest block mb-1">Primary Target</span>
                        <span className="text-2xl font-mono text-white">{displayTarget}</span>
                    </div>
                </div>

                <button
                    onClick={() => setShowTicket(!showTicket)}
                    className={`font-black py-4 px-10 rounded-xl transition-all uppercase text-lg tracking-wider ${
                        showTicket ? 'bg-gray-800 text-white border border-gray-600' : 'bg-blue-600 hover:bg-blue-500 text-white'
                    }`}
                >
                    {showTicket ? 'Hide Ticket' : 'Generate IBKR Ticket'}
                </button>
            </div>

            {/* --- BOTTOM ROW: THE IBKR BRACKET ORDER [cite: 503] --- */}
            {showTicket && (
                <div className="border-t border-gray-800 bg-black p-6 animate-in zoom-in-95">
                    <div className="max-w-7xl mx-auto">
                        <h3 className="text-gray-400 text-sm font-bold uppercase tracking-widest mb-4">Bracket Order Parameters (Manual Entry)</h3>
                        <div className="grid grid-cols-3 gap-6">

                            {/* Parent Leg (Entry) [cite: 389] */}
                            <div className="bg-gray-900 border border-gray-700 p-4 rounded-lg">
                                <span className="text-blue-400 font-bold text-xs uppercase block mb-2">1. Parent Leg (BUY)</span>
                                <div className="text-white font-mono text-lg flex justify-between">
                                    <span>Quantity:</span> <span>{units}</span>
                                </div>
                                <div className="text-white font-mono text-lg flex justify-between">
                                    <span>LMT Price:</span> <span>${price.toFixed(2)}</span>
                                </div>
                            </div>

                            {/* Child Leg (Stop Loss) [cite: 194, 535] */}
                            <div className="bg-gray-900 border border-red-900/50 p-4 rounded-lg">
                                <span className="text-red-400 font-bold text-xs uppercase block mb-2">2. Child Leg (SELL - STP)</span>
                                <div className="text-white font-mono text-lg flex justify-between">
                                    <span>Order Type:</span> <span>STOP</span>
                                </div>
                                <div className="text-white font-mono text-lg flex justify-between">
                                    <span>Stop Price:</span> <span className="text-red-400">${stopValue.toFixed(2)}</span>
                                </div>
                            </div>

                            {/* Child Leg (Profit Target) [cite: 108, 196] */}
                            <div className="bg-gray-900 border border-green-900/50 p-4 rounded-lg">
                                <span className="text-green-400 font-bold text-xs uppercase block mb-2">3. Child Leg (SELL - LMT)</span>
                                <div className="text-white font-mono text-lg flex justify-between">
                                    <span>Order Type:</span> <span>LIMIT</span>
                                </div>
                                <div className="text-white font-mono text-lg flex justify-between">
                                    <span>LMT Price:</span> <span className="text-green-400">{displayTarget}</span>
                                </div>
                            </div>

                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}