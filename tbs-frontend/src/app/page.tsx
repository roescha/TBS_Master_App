"use client";

import React, { useState } from 'react';
import PreFlight from '../components/PreFlight';
import Execution from '../components/Execution';
import {
    fetchAutoID,
    fetchSentinel,
    fetchFundamentals,
    fetchTechnical,
    fetchAnalystWACC,
    AuditConfig, fetchVisionAudit, fetchAnalystRadar, fetchSizing
} from '../services/api';

export default function MasterDashboard() {
    const [currentStep, setCurrentStep] = useState<number>(0);
    const [config, setConfig] = useState<AuditConfig | null>(null);
    const [isETF, setIsETF] = useState<boolean>(false);
    const [eventAware, setEventAware] = useState<boolean>(false);

    const [sentinelResult, setSentinelResult] = useState<any>(null);
    const [fundamentalResult, setFundamentalResult] = useState<any>(null);
    const [technicalResult, setTechnicalResult] = useState<any>(null);
    const [sizingResult, setSizingResult] = useState<any>(null); // [MANDATE: ADDED GOVERNOR STATE]

    const [loading, setLoading] = useState<boolean>(false);
    const [errorMsg, setErrorMsg] = useState<string | null>(null);

    const [visionResult, setVisionResult] = useState<any>(null);
    const [radarResult, setRadarResult] = useState<any>(null);

    const handleStartAudit = async (preFlightData: any) => {
        setErrorMsg(null);
        setLoading(true);
        setCurrentStep(1);

        try {
            const autoIdRes = await fetchAutoID(preFlightData.ticker, preFlightData.mode);
            setIsETF(autoIdRes.is_etf);

            const sentinelRes = await fetchSentinel();
            setSentinelResult(sentinelRes);

            const radarRes = await fetchAnalystRadar(preFlightData.ticker);
            setRadarResult(radarRes);

            if (radarRes.event_aware_triggered) {
                setEventAware(true);
            }

            // [FIX: Mapping preFlightData.capital to config.total_capital for Step 7 scope]
            // [MANDATE: PERSIST CAPITAL IN STATE]
            const fullConfig: AuditConfig = { // Ensure you use the AuditConfig type here
                ticker: preFlightData.ticker.toUpperCase(),
                profile: preFlightData.profile,
                mode: preFlightData.mode,
                is_etf: autoIdRes.is_etf,
                wacc: preFlightData.wacc ? preFlightData.wacc : null,
                total_capital: preFlightData.capital // [FIX: Saving from preFlightData to state]
            };
            setConfig(fullConfig);

            setCurrentStep(preFlightData.mode === "LIVE" ? 2 : 4);
        } catch (err: any) {
            setErrorMsg(err.message || "Pre-Flight Error");
        } finally {
            setLoading(false);
        }
    };

    const executeEngines = async () => {
        if (!config || loading) return;

        setLoading(true);
        setErrorMsg(null);
        setTechnicalResult(null);

        try {
            let fundRes = await fetchFundamentals(config);

            if (fundRes.diagnostic.includes("WACC data is missing")) {
                const analystData = await fetchAnalystWACC(config.ticker);
                const patchedConfig = { ...config, wacc: analystData.wacc };
                setConfig(patchedConfig);
                fundRes = await fetchFundamentals(patchedConfig);
            }
            setFundamentalResult(fundRes);

            const techRes = await fetchTechnical(config);
            setTechnicalResult(techRes);

            const visionRes = await fetchVisionAudit(config);
            setVisionResult(visionRes);

            setCurrentStep(6);
        } catch (err: any) {
            const msg = err.response?.data?.detail || err.message || "Pipeline Disruption";
            setErrorMsg(`Engine Failure: ${msg}`);
        } finally {
            setLoading(false);
        }
    };

    const calculateFinalSizing = async () => {
        if (!config || !technicalResult) return;
        setLoading(true);
        setErrorMsg(null);

        try {
            // [MANDATE: SSoT] Pull storm_watch directly from Python Sentinel [cite: 523]
            const isStormWatch = sentinelResult?.storm_watch || false;

            const sizingRes = await fetchSizing({
                profile: config.profile,
                mode: config.mode,
                regime: sentinelResult?.regime || "UNKNOWN",
                event_aware: eventAware,
                vix_storm: isStormWatch,
                audit_status: fundamentalResult?.status || "CLEAN",
                engine_metrics: technicalResult.metrics,
                total_capital: config.total_capital // [FIX: Pull from stored state]
            });

            setSizingResult(sizingRes);
            setCurrentStep(8);
        } catch (err: any) {
            const msg = err.response?.data?.detail || err.message || "Governor Calculation Failed";
            setErrorMsg(`Step 7 Halt: ${msg}`);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-gray-950 text-gray-200 pb-32 relative">
            {/* GLOBAL PROGRESS INDICATOR */}
            {loading && (
                <div className="absolute top-0 left-0 w-full h-1 bg-blue-900 z-50 overflow-hidden">
                    <div className="w-full h-full bg-blue-400 animate-pulse origin-left scale-x-100"></div>
                </div>
            )}

            <PreFlight onStartAudit={handleStartAudit} isLoading={loading} />

            <main className="p-6 max-w-7xl mx-auto space-y-6">
                {errorMsg && (
                    <div className="bg-red-900/50 border border-red-500 text-red-200 p-4 rounded shadow-lg font-mono text-sm">
                        <strong>🛑 PIPELINE HALTED:</strong> {errorMsg}
                    </div>
                )}

                {/* --- LAYER 4: ANALYST RADAR & PERMISSION --- */}
                {radarResult && (
                    <div className="bg-gray-900/50 border border-gray-800 p-6 rounded shadow-lg">
                        <h3 className="text-sm font-bold text-gray-400 uppercase mb-4 tracking-wider border-b border-gray-800 pb-2">Analyst Radar Summary</h3>
                        <div className="space-y-2 font-mono text-sm">
                            {[
                                { label: "SECURITY & GEO", data: radarResult.security_geo },
                                { label: "OPERATIONS & ENV", data: radarResult.operational_env },
                                { label: "INTEGRITY & LEGAL", data: radarResult.integrity_legal },
                                { label: "FINANCIAL SHOCKS", data: radarResult.financial_shock },
                                { label: "BINARY EVENTS", data: radarResult.binary_events },
                                { label: "SYMPATHY AUDIT", data: radarResult.sympathy_audit },
                            ].map((item, idx) => (
                                <div key={idx} className={`p-3 rounded border flex flex-col md:flex-row md:items-center gap-2 ${
                                    item.data?.status === 'FAIL' ? "bg-red-900/30 border-red-700 text-red-300" : "bg-green-900/20 border-green-800 text-green-400"
                                }`}>
                                    <div className="md:w-1/4 font-bold flex items-center gap-2">
                                        <span className={`w-2 h-2 rounded-full ${item.data?.status === 'FAIL' ? 'bg-red-500 animate-pulse' : 'bg-green-500'}`}></span>
                                        {item.label}
                                    </div>
                                    <div className="md:w-3/4 text-xs text-gray-300">
                                        {item.data?.details || "Scanning..."}
                                    </div>
                                </div>
                            ))}
                        </div>

                        <div className="mt-6 space-y-3 bg-black/30 p-4 rounded border border-gray-800">
                            <label className="flex items-center space-x-3 cursor-pointer group">
                                <input type="checkbox" className="w-5 h-5 rounded border-gray-700 bg-gray-800 text-blue-600 focus:ring-blue-600" />
                                <span className="text-gray-300 group-hover:text-white transition-colors text-sm font-bold">Operator Confirmation: Qualitative Master Veto passed.</span>
                            </label>
                            <label className="flex items-center space-x-3 cursor-pointer group">
                                <input
                                    type="checkbox"
                                    checked={eventAware}
                                    onChange={(e) => setEventAware(e.target.checked)}
                                    className="w-5 h-5 rounded border-gray-700 bg-gray-800 text-yellow-600 focus:ring-yellow-600"
                                />
                                <span className={`text-sm ${eventAware ? "text-yellow-500 font-bold" : "text-gray-500"}`}>Apply Event-Aware 50% Reduction (Earnings/Dividend &lt; 10d).</span>
                            </label>

                            <button
                                onClick={executeEngines}
                                disabled={loading}
                                className={`w-full font-bold py-4 rounded uppercase transition-all mt-4 ${
                                    loading
                                        ? "bg-gray-800 text-gray-600 cursor-not-allowed border border-gray-700"
                                        : "bg-green-600 hover:bg-green-500 text-white shadow-lg shadow-green-900/20"
                                }`}
                            >
                                {loading ? "⚙️ EXECUTING TBS LAYERS..." : "Authorize Asset Permission & Run Engines"}
                            </button>
                        </div>
                    </div>
                )}

                {/* --- LAYER 6: DATA AUDIT & VISION --- */}
                {currentStep >= 6 && technicalResult && fundamentalResult && (
                    <div className="bg-gray-900 border border-gray-700 p-6 rounded shadow-lg animate-in zoom-in-95">
                        <h2 className="text-xl font-bold text-blue-400 mb-6 uppercase tracking-tighter border-b border-gray-800 pb-4">Step 6: AI Vision & Data Audit</h2>

                        <div className="grid grid-cols-1 gap-3 mb-6">
                            <div className={`p-3 rounded border font-mono text-sm ${fundamentalResult.status.includes("HALT") ? "bg-red-900/30 border-red-700 text-red-300" : "bg-green-900/30 border-green-800 text-green-300"}`}>
                                <strong>FUNDAMENTAL ENGINE [{fundamentalResult.status}]:</strong> {fundamentalResult.diagnostic}
                            </div>

                            <div className={`p-3 rounded border font-mono text-sm ${technicalResult.status.includes("HALT") ? "bg-red-900/30 border-red-700 text-red-300" : "bg-green-900/30 border-green-800 text-green-300"}`}>
                                <strong>TECHNICAL ENGINE [{technicalResult.status}]:</strong> {technicalResult.diagnostic}
                            </div>

                            {visionResult && (
                                <div className={`p-3 rounded border font-mono text-sm ${visionResult.verdict.includes("HALT") ? "bg-red-900/30 border-red-700 text-red-300" : "bg-green-900/30 border-green-800 text-green-300"}`}>
                                    <strong>AI VISION AUDIT [{visionResult.verdict}]:</strong> {visionResult.reasoning}
                                </div>
                            )}
                        </div>

                        {/* RESTORED METRICS GRID */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
                            <div className="bg-black/40 p-4 rounded border border-gray-800">
                                <h3 className="text-blue-500 text-xs font-black uppercase mb-3 tracking-widest">Fundamental Metrics</h3>
                                <div className="space-y-1 font-mono text-xs text-blue-300">
                                    {Object.entries(fundamentalResult.metrics).map(([k, v]: any) => (
                                        <div key={k} className="flex justify-between border-b border-gray-900 pb-1">
                                            <span className="text-gray-500">{k}:</span>
                                            <span>{typeof v === 'number' ? v.toFixed(2) : String(v)}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            <div className="bg-black/40 p-4 rounded border border-gray-800">
                                <h3 className="text-purple-500 text-xs font-black uppercase mb-3 tracking-widest">Technical Metrics</h3>
                                <div className="space-y-1 font-mono text-xs text-purple-300">
                                    {Object.entries(technicalResult.metrics).map(([k, v]: any) => (
                                        <div key={k} className="flex justify-between border-b border-gray-900 pb-1">
                                            <span className="text-gray-500">{k}:</span>
                                            <span>{typeof v === 'number' ? v.toFixed(2) : String(v)}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>

                        <div className="bg-black border border-gray-800 rounded p-2 mb-6 text-center">
                            <img src={`${technicalResult.chart_url}?t=${Date.now()}`} alt="Triple View" className="inline-block max-w-full h-auto" />
                        </div>

                        <div className="flex gap-4">
                            <button onClick={calculateFinalSizing} className="flex-1 bg-green-600 hover:bg-green-500 text-white font-bold py-4 rounded uppercase">Authorize Final Execution</button>
                            <button className="flex-1 bg-red-900/20 border border-red-900/50 text-red-500 font-bold py-4 rounded uppercase hover:bg-red-900/40" onClick={() => setCurrentStep(0)}>Veto / Halt</button>
                        </div>
                    </div>
                )}
            </main>

            {/* SYNCED HANDSHAKE */}
            {currentStep === 8 && sizingResult && fundamentalResult && (
                <Execution
                    sizingData={sizingResult} // [MANDATE: EXPLICITLY PASSING GOVERNOR OUTPUT]
                    fundamentalResult={fundamentalResult}
                    eventAware={eventAware}
                />
            )}
        </div>
    );
}