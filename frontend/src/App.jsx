import React, { useState, useEffect } from 'react'
import { 
  Shield, 
  AlertTriangle, 
  Activity, 
  Terminal, 
  GitBranch, 
  BookOpen, 
  Network, 
  CheckCircle, 
  Flame, 
  Cpu, 
  Clock, 
  FileText,
  UserCheck,
  RefreshCw,
  Zap,
  XCircle
} from 'lucide-react'
import './App.css'

const BACKEND_URL = 'http://127.0.0.1:8001';

function App() {
  const [incidents, setIncidents] = useState([])
  const [selectedIncident, setSelectedIncident] = useState(null)
  const [activeTab, setActiveTab] = useState('logs')
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [chaosLoading, setChaosLoading] = useState(null)
  const [selectedTopologyNode, setSelectedTopologyNode] = useState(null)

  const [isReplayMode, setIsReplayMode] = useState(false)
  const [replayStepIndex, setReplayStepIndex] = useState(0)
  const [isReplayPlaying, setIsReplayPlaying] = useState(false)

  // Reset replay state when incident changes
  useEffect(() => {
    setIsReplayMode(false)
    setReplayStepIndex(0)
    setIsReplayPlaying(false)
  }, [selectedIncident?.id])

  // Auto-play control loop
  useEffect(() => {
    let timer = null
    if (isReplayPlaying && isReplayMode && selectedIncident) {
      const snapshots = selectedIncident.state_json?.snapshots || []
      timer = setInterval(() => {
        setReplayStepIndex(prev => {
          if (prev >= snapshots.length - 1) {
            setIsReplayPlaying(false)
            return prev
          }
          return prev + 1
        })
      }, 1500)
    } else {
      clearInterval(timer)
    }
    return () => clearInterval(timer)
  }, [isReplayPlaying, isReplayMode, selectedIncident])

  // Fetch all incidents
  const fetchIncidents = async (selectLatest = false) => {
    setIsRefreshing(true)
    try {
      const response = await fetch(`${BACKEND_URL}/api/v1/incidents`)
      if (response.ok) {
        const data = await response.json()
        setIncidents(data)
        if (data.length > 0) {
          if (selectLatest || !selectedIncident) {
            setSelectedIncident(data[0])
          }
        }
      }
    } catch (err) {
      console.error("Failed to fetch incidents:", err)
    } finally {
      setIsRefreshing(false)
    }
  }

  // Load initial list on mount
  useEffect(() => {
    fetchIncidents()
  }, [])

  // Coordinated Real-Time SSE Listener for the selected active incident
  useEffect(() => {
    if (!selectedIncident) return

    console.log(`Connecting SSE stream for: ${selectedIncident.id}`)
    const sse = new EventSource(`${BACKEND_URL}/api/v1/incidents/${selectedIncident.id}/stream`)

    sse.addEventListener('step', (event) => {
      try {
        const payload = JSON.parse(event.data)
        console.log("Real-time SSE event received:", payload)
        
        // Dynamic state mapping
        setSelectedIncident(prev => {
          if (!prev || prev.id !== selectedIncident.id) return prev
          return {
            ...prev,
            status: payload.state.status || prev.status,
            state_json: payload.state
          }
        })
        
        // Also refresh list to show updated status
        setIncidents(prevList => {
          return prevList.map(inc => {
            if (inc.id === selectedIncident.id) {
              return {
                ...inc,
                status: payload.state.status || inc.status,
                state_json: payload.state
              }
            }
            return inc
          })
        })
      } catch (err) {
        console.error("Failed to parse SSE payload:", err)
      }
    })

    sse.addEventListener('error', (err) => {
      console.log("SSE Connection closed or errored, closing listener.")
      sse.close()
    })

    return () => {
      console.log(`Disconnecting SSE stream for: ${selectedIncident.id}`)
      sse.close()
    }
  }, [selectedIncident?.id])

  // Triggers chaos alert webhook to backend
  const triggerChaosScenario = async (scenarioType) => {
    setChaosLoading(scenarioType)
    let payload = {
      receiver: "sentinelgraph-webhook",
      status: "firing",
      alerts: [],
      commonLabels: { severity: "critical" },
      commonAnnotations: {}
    }

    if (scenarioType === 'sc1') {
      payload.alerts.push({
        status: "firing",
        labels: {
          alertname: "HighLatencySpike",
          service: "payment-service",
          severity: "critical",
          instance: "payment-service:8013"
        },
        annotations: {
          summary: "High HTTP checkout latency on payment-service",
          description: "Payment service average latency exceeded 2.5 seconds on order checkouts."
        },
        startsAt: new Date().toISOString(),
        generatorURL: "http://prometheus:9090"
      })
      payload.commonLabels.alertname = "HighLatencySpike"
      payload.commonLabels.service = "payment-service"
      payload.commonAnnotations.summary = "High HTTP checkout latency on payment-service"
    } else if (scenarioType === 'sc2') {
      payload.alerts.push({
        status: "firing",
        labels: {
          alertname: "MemoryLeakAlert",
          service: "order-service",
          severity: "warning",
          instance: "order-service:8012"
        },
        annotations: {
          summary: "Linear memory leak growth detected on order-service",
          description: "Order-service resident set heap size increased linearly past 512MB."
        },
        startsAt: new Date().toISOString(),
        generatorURL: "http://prometheus:9090"
      })
      payload.commonLabels.alertname = "MemoryLeakAlert"
      payload.commonLabels.service = "order-service"
      payload.commonLabels.severity = "warning"
      payload.commonAnnotations.summary = "Linear memory leak growth detected on order-service"
    } else { // sc3
      payload.alerts.push({
        status: "firing",
        labels: {
          alertname: "Http5xxSpike",
          service: "user-service",
          severity: "critical",
          instance: "user-service:8011"
        },
        annotations: {
          summary: "HTTP 500 error spike detected on user-service",
          description: "User profile queries returning 500 errors following v1.1.0 JWT rollouts."
        },
        startsAt: new Date().toISOString(),
        generatorURL: "http://prometheus:9090"
      })
      payload.commonLabels.alertname = "Http5xxSpike"
      payload.commonLabels.service = "user-service"
      payload.commonAnnotations.summary = "HTTP 500 error spike detected on user-service"
    }

    try {
      const response = await fetch(`${BACKEND_URL}/api/v1/alerts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      if (response.ok) {
        const newInc = await response.json()
        setIncidents(prev => [newInc, ...prev])
        setSelectedIncident(newInc)
      }
    } catch (err) {
      console.error("Failed to inject chaos:", err)
    } finally {
      setChaosLoading(null)
    }
  }

  // Handle mitigation approval or rejection
  const handleApproval = async (action) => {
    if (!selectedIncident) return
    try {
      const response = await fetch(`${BACKEND_URL}/api/v1/incidents/${selectedIncident.id}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action })
      })
      if (response.ok) {
        const updated = await response.json()
        setSelectedIncident(updated)
        // refresh list to show updated status immediately
        setIncidents(prevList => prevList.map(inc => inc.id === selectedIncident.id ? updated : inc))
      }
    } catch (err) {
      console.error("Failed to submit approval action:", err)
    }
  }

  const finalState = selectedIncident?.state_json || {}
  const snapshots = finalState.snapshots || []
  const isReplayAvailable = snapshots.length > 0
  
  const state = (isReplayMode && isReplayAvailable)
    ? (snapshots[replayStepIndex] || finalState)
    : finalState
    
  const history = state.execution_history || []
  const service = selectedIncident?.service || 'N/A'
  
  const getMetricsPath = (val, max) => {
    const pct = Math.min(1.0, val / max)
    const yVal = 38 - (pct * 28) // scale y-axis value from 38 down to 10
    return {
      path: `M0 38 Q30 32, 60 ${38 - (pct * 10)} T120 ${38 - (pct * 18)} T180 ${38 - (pct * 22)} T240 ${yVal} L240 40 L0 40 Z`,
      stroke: `M0 38 Q30 32, 60 ${38 - (pct * 10)} T120 ${38 - (pct * 18)} T180 ${38 - (pct * 22)} T240 ${yVal}`
    }
  }
  
  // Timeline node logic
  const getTimelineNodes = () => {
    const nodes = [
      { id: 'supervisor', label: 'Supervisor', key: 'Supervisor:' },
      { id: 'triage', label: 'Triage', key: 'Alert Triage Agent:' },
      { id: 'logs', label: 'Logs', key: 'Logs Investigator:' },
      { id: 'metrics', label: 'Metrics', key: 'Metrics Analyst:' },
      { id: 'deploy', label: 'Deploy Detective', key: 'Deploy Detective:' },
      { id: 'docs', label: 'Runbooks', key: 'Runbook Assistant:' },
      { id: 'dependencies', label: 'Dependencies', key: 'Dependency Detective:' },
      { id: 'root_cause', label: 'Root Cause', key: 'Root Cause Agent:' },
      { id: 'recovery', label: 'Recovery Planner', key: 'Recovery Planner Agent:' }
    ]

    return nodes.map(n => {
      const isCompleted = history.some(line => line.includes(n.key) && !line.includes("actively") && !line.includes("Fetching"))
      const isActive = history.length > 0 && !isCompleted && history[history.length - 1].includes(n.key)
      return { ...n, status: isCompleted ? 'completed' : isActive ? 'active' : 'pending' }
    })
  }

  const timelineNodes = getTimelineNodes()
  const completedCount = timelineNodes.filter(n => n.status === 'completed').length
  const progressPct = timelineNodes.length > 0 ? (completedCount / timelineNodes.length) * 100 : 0

  return (
    <div className="app-container">
      {/* Header */}
      <header className="app-header glass-panel">
        <div className="brand-section">
          <span className="brand-icon animate-float">🛡️</span>
          <div>
            <h1 className="brand-name">SentinelGraph</h1>
            <p style={{ fontSize: '10px', color: 'var(--text-muted)' }}>AUTONOMOUS SRE INCIDENT COMMANDER</p>
          </div>
        </div>

        <div className="header-status">
          <div className="service-pill">
            <span className="status-dot green"></span>
            <span>user-service</span>
          </div>
          <div className="service-pill">
            <span className="status-dot green"></span>
            <span>order-service</span>
          </div>
          <div className="service-pill">
            <span className="status-dot green"></span>
            <span>payment-service</span>
          </div>
          <button className="btn btn-secondary" onClick={() => fetchIncidents()} disabled={isRefreshing}>
            <RefreshCw className={isRefreshing ? "animate-spin" : ""} size={14} />
          </button>
        </div>
      </header>

      {/* Main Workspace */}
      <main className="app-workspace">
        {/* Left Sidebar - Incidents List */}
        <section className="sidebar-panel glass-panel">
          <div className="sidebar-title">Active Incidents ({incidents.length})</div>
          <div className="incidents-list">
            {incidents.map(inc => (
              <div 
                key={inc.id} 
                className={`incident-card ${selectedIncident?.id === inc.id ? 'active' : ''}`}
                onClick={() => setSelectedIncident(inc)}
              >
                <div className="card-header">
                  <span className="alert-name">{inc.alertname}</span>
                  <span className={`severity-badge ${inc.severity.toLowerCase()}`}>{inc.severity}</span>
                </div>
                <div className="card-service">Service: {inc.service}</div>
                <div className="card-meta">
                  <span>{inc.id}</span>
                  <span style={{ color: inc.status === 'recovered' ? 'var(--color-success)' : 'var(--color-warning)', fontWeight: '700' }}>
                    {inc.status.toUpperCase()}
                  </span>
                </div>
              </div>
            ))}

            {incidents.length === 0 && (
              <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>
                <CheckCircle size={32} style={{ color: 'var(--color-success)', marginBottom: '8px' }} />
                <p style={{ fontSize: '12px' }}>System Healthy. No active incidents.</p>
              </div>
            )}
            
            <div style={{ marginTop: 'auto', padding: '16px', borderTop: '1px solid var(--border-glass)' }}>
              <h3 style={{ fontSize: '12px', fontWeight: '700', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                Chaos Playground
              </h3>
              <div className="chaos-controller">
                <button className="chaos-btn" onClick={() => triggerChaosScenario('sc1')} disabled={chaosLoading !== null}>
                  <Flame size={12} style={{ marginRight: '6px', display: 'inline' }} />
                  {chaosLoading === 'sc1' ? 'Injecting...' : 'SC-1: Latency Spike (Payment)'}
                </button>
                <button className="chaos-btn" onClick={() => triggerChaosScenario('sc2')} disabled={chaosLoading !== null}>
                  <Cpu size={12} style={{ marginRight: '6px', display: 'inline' }} />
                  {chaosLoading === 'sc2' ? 'Injecting...' : 'SC-2: Memory Leak (Order)'}
                </button>
                <button className="chaos-btn" onClick={() => triggerChaosScenario('sc3')} disabled={chaosLoading !== null}>
                  <AlertTriangle size={12} style={{ marginRight: '6px', display: 'inline' }} />
                  {chaosLoading === 'sc3' ? 'Injecting...' : 'SC-3: Config Bug (User)'}
                </button>
              </div>
            </div>
          </div>
        </section>

        {/* Right Workspace */}
        {selectedIncident ? (
          <section className="workspace-panel glass-panel">
            <div className="incident-details-header" style={{ marginBottom: isReplayAvailable ? '8px' : '20px' }}>
              <div className="details-title-section">
                <h2>{selectedIncident.alertname}</h2>
                <div className="details-subtitle">
                  <span>Incident ID: <strong>{selectedIncident.id}</strong></span>
                  <span style={{ margin: '0 8px' }}>|</span>
                  <span>Target Service: <strong>{selectedIncident.service}</strong></span>
                </div>
              </div>
              <div className="action-bar">
                <span className={`severity-badge ${selectedIncident.severity.toLowerCase()}`} style={{ padding: '6px 12px', fontSize: '12px' }}>
                  {selectedIncident.severity.toUpperCase()}
                </span>
                <span className="service-pill" style={{ background: 'rgba(99, 102, 241, 0.1)', borderColor: 'var(--color-primary)', color: 'white' }}>
                  {selectedIncident.status.toUpperCase()}
                </span>
              </div>
            </div>

            {/* Playback Replay Scrubber Controller */}
            {isReplayAvailable && (
              <div className="replay-controller-bar glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '8px', padding: '12px 20px', marginBottom: '16px', background: isReplayMode ? 'rgba(99, 102, 241, 0.08)' : 'rgba(255,255,255,0.01)', border: isReplayMode ? '1px solid rgba(99, 102, 241, 0.3)' : '1px solid var(--border-glass)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <button 
                      className={`btn ${isReplayMode ? 'btn-primary' : 'btn-secondary'}`}
                      style={{ padding: '4px 12px', fontSize: '11px', height: '28px', textTransform: 'uppercase', letterSpacing: '0.5px' }}
                      onClick={() => {
                        setIsReplayMode(!isReplayMode);
                        setIsReplayPlaying(false);
                        setReplayStepIndex(0);
                      }}
                    >
                      {isReplayMode ? "📡 Live View" : "⏪ Replay Mode"}
                    </button>
                    
                    {isReplayMode && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <button 
                          className="chaos-btn" 
                          style={{ margin: 0, padding: '4px 8px', fontSize: '11px', minWidth: '32px' }}
                          onClick={() => setReplayStepIndex(prev => Math.max(0, prev - 1))}
                          disabled={replayStepIndex === 0}
                        >
                          ⏮️
                        </button>
                        <button 
                          className="chaos-btn" 
                          style={{ margin: 0, padding: '4px 8px', fontSize: '11px', minWidth: '50px' }}
                          onClick={() => setIsReplayPlaying(!isReplayPlaying)}
                        >
                          {isReplayPlaying ? "⏸️ Pause" : "▶️ Play"}
                        </button>
                        <button 
                          className="chaos-btn" 
                          style={{ margin: 0, padding: '4px 8px', fontSize: '11px', minWidth: '32px' }}
                          onClick={() => setReplayStepIndex(prev => Math.min(snapshots.length - 1, prev + 1))}
                          disabled={replayStepIndex === snapshots.length - 1}
                        >
                          ⏭️
                        </button>
                      </div>
                    )}
                  </div>
                  
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    {isReplayMode ? `Step ${replayStepIndex + 1} of ${snapshots.length}` : `${snapshots.length} investigation phases recorded`}
                  </span>
                </div>

                {isReplayMode && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '4px' }}>
                    <input 
                      type="range" 
                      min="0" 
                      max={snapshots.length - 1} 
                      value={replayStepIndex} 
                      onChange={(e) => {
                        setReplayStepIndex(Number(e.target.value));
                        setIsReplayPlaying(false);
                      }}
                      style={{ width: '100%', accentColor: 'var(--color-primary)', cursor: 'pointer', height: '4px', background: 'rgba(255,255,255,0.1)', borderRadius: '2px', outline: 'none' }}
                    />
                    <div style={{ fontSize: '11px', fontWeight: '600', color: 'var(--color-secondary)', marginTop: '2px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      ⚡ {state.message || (snapshots[replayStepIndex]?.message) || "No message recorded"}
                    </div>
                  </div>
                )}
              </div>
            )}

            <div className="incident-dashboard-layout">
              {/* Timeline Row */}
              <div className="timeline-section glass-panel" style={{ background: 'rgba(255,255,255,0.01)' }}>
                <div className="timeline-title">MULTI-AGENT COORDINATED EXPLORATION RUN</div>
                <div className="timeline-steps">
                  <div className="timeline-bar">
                    <div className="timeline-bar-progress" style={{ width: `${progressPct}%` }}></div>
                  </div>
                  {timelineNodes.map(node => (
                    <div key={node.id} className={`timeline-step-node ${node.status}`}>
                      <div className="step-circle">
                        {node.status === 'completed' ? <CheckCircle size={16} /> : node.status === 'active' ? <Zap size={14} className="animate-pulse" /> : <Clock size={14} />}
                      </div>
                      <span className="step-label">{node.label}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Tabs and Details Workspace */}
              <div className="tabs-and-details-section">
                <div className="tabs-panel glass-panel" style={{ background: 'rgba(255,255,255,0.01)' }}>
                  <div className="tabs-header">
                    <button className={`tab-btn ${activeTab === 'logs' ? 'active' : ''}`} onClick={() => setActiveTab('logs')}>
                      <Terminal size={14} style={{ marginRight: '6px', verticalAlign: 'middle' }} /> Logs
                    </button>
                    <button className={`tab-btn ${activeTab === 'metrics' ? 'active' : ''}`} onClick={() => setActiveTab('metrics')}>
                      <Activity size={14} style={{ marginRight: '6px', verticalAlign: 'middle' }} /> Metrics
                    </button>
                    <button className={`tab-btn ${activeTab === 'deploys' ? 'active' : ''}`} onClick={() => setActiveTab('deploys')}>
                      <GitBranch size={14} style={{ marginRight: '6px', verticalAlign: 'middle' }} /> Deploys
                    </button>
                    <button className={`tab-btn ${activeTab === 'runbooks' ? 'active' : ''}`} onClick={() => setActiveTab('runbooks')}>
                      <BookOpen size={14} style={{ marginRight: '6px', verticalAlign: 'middle' }} /> Runbooks
                    </button>
                    <button className={`tab-btn ${activeTab === 'dependencies' ? 'active' : ''}`} onClick={() => setActiveTab('dependencies')}>
                      <Network size={14} style={{ marginRight: '6px', verticalAlign: 'middle' }} /> Dependencies
                    </button>
                    <button className={`tab-btn ${activeTab === 'postmortem' ? 'active' : ''}`} onClick={() => setActiveTab('postmortem')}>
                      <FileText size={14} style={{ marginRight: '6px', verticalAlign: 'middle' }} /> Postmortem
                    </button>
                  </div>

                  <div className="tab-content">
                    {activeTab === 'logs' && (
                      <div>
                        <h3 style={{ fontSize: '14px', marginBottom: '10px' }}>Active Logs Stream - {selectedIncident.service}</h3>
                        <div className="logs-terminal">
                          {state.logs && state.logs[selectedIncident.service] ? (
                            state.logs[selectedIncident.service].map((line, idx) => (
                              <div 
                                key={idx} 
                                className={`log-line ${line.includes('ERROR') ? 'log-line-error' : line.includes('WARNING') ? 'log-line-warn' : ''}`}
                              >
                                {line}
                              </div>
                            ))
                          ) : (
                            <div style={{ color: 'var(--text-dark)' }}>No log events received. Run Logs Investigator agent node.</div>
                          )}
                        </div>
                      </div>
                    )}

                    {activeTab === 'metrics' && (
                      <div>
                        <h3 style={{ fontSize: '14px', marginBottom: '14px' }}>System Performance Indicators</h3>
                        {state.metrics && state.metrics[selectedIncident.service] ? (
                          (() => {
                            const currentMetrics = state.metrics[selectedIncident.service];
                            const latencyData = getMetricsPath(currentMetrics.average_latency_ms || 0, 3000);
                            const cpuData = getMetricsPath(currentMetrics.cpu_usage_pct || 0, 100);
                            const errorData = getMetricsPath((currentMetrics.http_5xx_rate || 0) * 100, 100);
                            const memoryData = getMetricsPath(currentMetrics.memory_usage_mb || 0, 1024);

                            return (
                              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                                <div className="glass-panel" style={{ padding: '16px', display: 'flex', flexDirection: 'column', justifycontent: 'space-between' }}>
                                  <div>
                                    <p style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Average HTTP Latency</p>
                                    <p style={{ fontSize: '24px', fontWeight: '800', color: 'var(--color-warning)' }}>{currentMetrics.average_latency_ms} ms</p>
                                  </div>
                                  <div style={{ marginTop: '12px', height: '40px' }}>
                                    <svg width="100%" height="40" viewBox="0 0 240 40" preserveAspectRatio="none" style={{ overflow: 'visible' }}>
                                      <path d={latencyData.path} fill="rgba(245, 158, 11, 0.15)" />
                                      <path d={latencyData.stroke} stroke="var(--color-warning)" strokeWidth="1.5" fill="none" />
                                    </svg>
                                  </div>
                                </div>
                                <div className="glass-panel" style={{ padding: '16px', display: 'flex', flexDirection: 'column', justifycontent: 'space-between' }}>
                                  <div>
                                    <p style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>CPU Saturation</p>
                                    <p style={{ fontSize: '24px', fontWeight: '800', color: 'var(--color-error)' }}>{currentMetrics.cpu_usage_pct} %</p>
                                  </div>
                                  <div style={{ marginTop: '12px', height: '40px' }}>
                                    <svg width="100%" height="40" viewBox="0 0 240 40" preserveAspectRatio="none" style={{ overflow: 'visible' }}>
                                      <path d={cpuData.path} fill="rgba(239, 68, 68, 0.15)" />
                                      <path d={cpuData.stroke} stroke="var(--color-error)" strokeWidth="1.5" fill="none" />
                                    </svg>
                                  </div>
                                </div>
                                <div className="glass-panel" style={{ padding: '16px', display: 'flex', flexDirection: 'column', justifycontent: 'space-between' }}>
                                  <div>
                                    <p style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>HTTP 5xx Rate</p>
                                    <p style={{ fontSize: '24px', fontWeight: '800', color: 'var(--color-error)' }}>{Math.round((currentMetrics.http_5xx_rate || 0) * 100)} %</p>
                                  </div>
                                  <div style={{ marginTop: '12px', height: '40px' }}>
                                    <svg width="100%" height="40" viewBox="0 0 240 40" preserveAspectRatio="none" style={{ overflow: 'visible' }}>
                                      <path d={errorData.path} fill="rgba(239, 68, 68, 0.15)" />
                                      <path d={errorData.stroke} stroke="var(--color-error)" strokeWidth="1.5" fill="none" />
                                    </svg>
                                  </div>
                                </div>
                                <div className="glass-panel" style={{ padding: '16px', display: 'flex', flexDirection: 'column', justifycontent: 'space-between' }}>
                                  <div>
                                    <p style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Memory Allocated</p>
                                    <p style={{ fontSize: '24px', fontWeight: '800', color: 'var(--color-primary)' }}>{currentMetrics.memory_usage_mb} MB</p>
                                  </div>
                                  <div style={{ marginTop: '12px', height: '40px' }}>
                                    <svg width="100%" height="40" viewBox="0 0 240 40" preserveAspectRatio="none" style={{ overflow: 'visible' }}>
                                      <path d={memoryData.path} fill="rgba(99, 102, 241, 0.15)" />
                                      <path d={memoryData.stroke} stroke="var(--color-primary)" strokeWidth="1.5" fill="none" />
                                    </svg>
                                  </div>
                                </div>
                              </div>
                            );
                          })()
                        ) : (
                          <p style={{ color: 'var(--text-dark)' }}>No metrics loaded.</p>
                        )}
                      </div>
                    )}

                    {activeTab === 'deploys' && (
                      <div>
                        <h3 style={{ fontSize: '14px', marginBottom: '12px' }}>Code Deployment Log</h3>
                        {state.deploys ? (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                            {state.deploys.map((dep, idx) => (
                              <div key={idx} className="glass-panel" style={{ padding: '12px 16px', display: 'flex', justifycontent: 'space-between', alignItems: 'center' }}>
                                <div>
                                  <p style={{ fontSize: '13px', fontWeight: '600' }}>Version: {dep.version}</p>
                                  <p style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Deployed by: {dep.author} | {dep.timestamp}</p>
                                </div>
                                <span className={`severity-badge ${dep.status === 'active' ? 'warning' : 'critical'}`}>{dep.status}</span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p style={{ color: 'var(--text-dark)' }}>No deploy history queried.</p>
                        )}
                      </div>
                    )}

                    {activeTab === 'runbooks' && (
                      <div>
                        <h3 style={{ fontSize: '14px', marginBottom: '10px' }}>SRE Operational Guidelines</h3>
                        {state.runbooks && state.runbooks.map((rb, idx) => (
                          <div key={idx} className="glass-panel" style={{ padding: '16px' }}>
                            <h4 style={{ fontSize: '13px', fontWeight: '700', marginBottom: '6px', color: 'var(--color-secondary)' }}>{rb.title}</h4>
                            <p style={{ fontSize: '12px', lineheight: '1.6', color: 'var(--text-muted)' }}>{rb.steps}</p>
                          </div>
                        ))}
                      </div>
                    )}

                    {activeTab === 'dependencies' && (
                      <div>
                        <h3 style={{ fontSize: '14px', marginBottom: '16px' }}>Coordinated Platform Topology Map</h3>
                        {state.dependencies ? (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                            <div className="glass-panel" style={{ padding: '16px', background: 'rgba(9, 13, 22, 0.65)', overflow: 'hidden' }}>
                              <svg width="100%" height="280" style={{ overflow: 'visible' }}>
                                <defs>
                                  {/* Arrow Markers */}
                                  <marker id="arrow" viewBox="0 0 10 10" refX="22" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                                    <path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(255,255,255,0.25)" />
                                  </marker>
                                  <marker id="arrow-error" viewBox="0 0 10 10" refX="22" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                                    <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--color-error)" />
                                  </marker>
                                  
                                  {/* Glow Filters */}
                                  <filter id="glow-green-filter" x="-20%" y="-20%" width="140%" height="140%">
                                    <feGaussianBlur in="SourceGraphic" stdDeviation="4" result="blur" />
                                    <feMerge>
                                      <feMergeNode in="blur" />
                                      <feMergeNode in="SourceGraphic" />
                                    </feMerge>
                                  </filter>
                                  <filter id="glow-red-filter" x="-20%" y="-20%" width="140%" height="140%">
                                    <feGaussianBlur in="SourceGraphic" stdDeviation="6" result="blur" />
                                    <feMerge>
                                      <feMergeNode in="blur" />
                                      <feMergeNode in="SourceGraphic" />
                                    </feMerge>
                                  </filter>
                                </defs>

                                {/* Connection Edges */}
                                <g>
                                  {/* order-service (120, 140) to user-service (450, 70) */}
                                  <path 
                                    d="M 120 140 L 450 70" 
                                    stroke={state.dependencies.root_service === "user-service" ? "var(--color-error)" : "rgba(99, 102, 241, 0.4)"} 
                                    strokeWidth={state.dependencies.root_service === "user-service" ? "2" : "1.5"} 
                                    fill="none" 
                                    markerEnd={state.dependencies.root_service === "user-service" ? "url(#arrow-error)" : "url(#arrow)"}
                                    strokeDasharray={state.dependencies.root_service === "user-service" ? "4" : "0"}
                                  />
                                  <text x="260" y="90" fill="var(--text-dark)" fontSize="10" fontFamily="var(--font-mono)">HTTP/1.1</text>

                                  {/* order-service (120, 140) to payment-service (450, 210) */}
                                  <path 
                                    d="M 120 140 L 450 210" 
                                    stroke={state.dependencies.root_service === "payment-service" ? "var(--color-error)" : "rgba(99, 102, 241, 0.4)"} 
                                    strokeWidth={state.dependencies.root_service === "payment-service" ? "2" : "1.5"} 
                                    fill="none" 
                                    markerEnd={state.dependencies.root_service === "payment-service" ? "url(#arrow-error)" : "url(#arrow)"}
                                    strokeDasharray={state.dependencies.root_service === "payment-service" ? "4" : "0"}
                                  />
                                  <text x="260" y="195" fill="var(--text-dark)" fontSize="10" fontFamily="var(--font-mono)">HTTP/1.1</text>
                                </g>

                                {/* Nodes Group */}
                                <g>
                                  {state.dependencies.nodes.map(node => {
                                    let x = 120;
                                    let y = 140;
                                    if (node.id === 'user-service') { x = 450; y = 70; }
                                    if (node.id === 'payment-service') { x = 450; y = 210; }

                                    const isError = node.status === 'error';
                                    const rectStroke = isError ? 'var(--color-error)' : 'rgba(255,255,255,0.08)';
                                    const shadowFilter = isError ? 'url(#glow-red-filter)' : 'url(#glow-green-filter)';
                                    const dotColor = isError ? 'var(--color-error)' : 'var(--color-success)';

                                    return (
                                      <g 
                                        key={node.id} 
                                        transform={`translate(${x - 90}, ${y - 25})`} 
                                        style={{ cursor: 'pointer' }}
                                        onClick={() => setSelectedTopologyNode(node)}
                                      >
                                        {/* Background glass box */}
                                        <rect 
                                          width="180" 
                                          height="50" 
                                          rx="8" 
                                          fill="rgba(13, 20, 38, 0.85)" 
                                          stroke={rectStroke} 
                                          strokeWidth="1.5"
                                          filter={shadowFilter}
                                        />
                                        
                                        {/* Status indicator dot */}
                                        <circle 
                                          cx="20" 
                                          cy="25" 
                                          r="5" 
                                          fill={dotColor} 
                                          className={isError ? "animate-pulse" : ""}
                                        />
                                        
                                        {/* Node Texts */}
                                        <text x="35" y="20" fill="var(--text-main)" fontSize="12" fontWeight="700" fontFamily="var(--font-display)">
                                          {node.id}
                                        </text>
                                        <text x="35" y="38" fill="var(--text-muted)" fontSize="10">
                                          {node.label}
                                        </text>
                                      </g>
                                    );
                                  })}
                                </g>
                              </svg>
                            </div>

                            {/* Node details selection panel */}
                            <div className="glass-panel" style={{ padding: '16px', background: 'rgba(255,255,255,0.01)' }}>
                              {selectedTopologyNode ? (
                                <div>
                                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                                    <h4 style={{ fontSize: '13px', fontWeight: '700', color: 'var(--color-secondary)' }}>
                                      {selectedTopologyNode.id} Profile Summary
                                    </h4>
                                    <span className={`severity-badge ${selectedTopologyNode.status === 'error' ? 'critical' : 'warning'}`}>
                                      {selectedTopologyNode.status.toUpperCase()}
                                    </span>
                                  </div>
                                  <table style={{ width: '100%', fontSize: '12px', borderCollapse: 'collapse' }}>
                                    <tbody>
                                      <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                        <td style={{ padding: '6px 0', color: 'var(--text-muted)' }}>Host Port Target</td>
                                        <td style={{ padding: '6px 0', textAlign: 'right', fontWeight: '600', fontFamily: 'var(--font-mono)' }}>
                                          {selectedTopologyNode.id === 'user-service' ? '8011' : selectedTopologyNode.id === 'order-service' ? '8012' : '8013'}
                                        </td>
                                      </tr>
                                      <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                        <td style={{ padding: '6px 0', color: 'var(--text-muted)' }}>Service Version</td>
                                        <td style={{ padding: '6px 0', textAlign: 'right', fontWeight: '600', fontFamily: 'var(--font-mono)' }}>v1.0.0</td>
                                      </tr>
                                      <tr>
                                        <td style={{ padding: '6px 0', color: 'var(--text-muted)' }}>Health Scrape Outcome</td>
                                        <td style={{ padding: '6px 0', textAlign: 'right', fontWeight: '600', color: selectedTopologyNode.status === 'error' ? 'var(--color-error)' : 'var(--color-success)' }}>
                                          {selectedTopologyNode.status === 'error' ? 'Active Failure Alert Fired' : 'OK (Healthy metrics scaped)'}
                                        </td>
                                      </tr>
                                    </tbody>
                                  </table>
                                </div>
                              ) : (
                                <p style={{ fontSize: '11px', color: 'var(--text-dark)', textAlign: 'center' }}>
                                  Click any node container in the SVG architecture graph to view host config parameters.
                                </p>
                              )}
                            </div>
                          </div>
                        ) : (
                          <p style={{ color: 'var(--text-dark)' }}>No topology calculated.</p>
                        )}
                      </div>
                    )}

                    {activeTab === 'postmortem' && (
                      <div>
                        <h3 style={{ fontSize: '14px', marginBottom: '14px' }}>Automated Postmortem Summary Report</h3>
                        {state.postmortem ? (
                          <div className="postmortem-markdown glass-panel" style={{ padding: '20px', background: 'rgba(9, 13, 22, 0.4)', color: 'var(--text-main)', lineHeight: '1.6', overflowY: 'auto', maxHeight: '450px' }}>
                            <div style={{ whiteSpace: 'pre-wrap', fontFamily: 'var(--font-sans)', fontSize: '13px' }}>
                              {state.postmortem}
                            </div>
                          </div>
                        ) : (
                          <div className="glass-panel" style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>
                            <Clock size={32} style={{ color: 'var(--color-warning)', marginBottom: '8px', display: 'inline-block' }} />
                            <p style={{ fontSize: '13px' }}>Postmortem is pending. The report will generate automatically once the mitigation action is approved and the incident is recovered.</p>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                {/* Right sidebar - Hypotheses & Recovery Action */}
                <div className="mitigation-panel glass-panel" style={{ background: 'rgba(255,255,255,0.01)' }}>
                  <div>
                    <h3 style={{ fontSize: '12px', fontWeight: '700', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '12px' }}>
                      Root Cause Isolated
                    </h3>
                    {state.hypotheses && state.hypotheses.map((hyp, idx) => (
                      <div key={idx} className="hypothesis-card">
                        <div className="hyp-header">
                          <span className="hyp-title">Hypothesis #{hyp.rank}</span>
                          <div className="confidence-indicator">
                            <span style={{ fontSize: '11px', fontWeight: '700', color: 'var(--color-secondary)' }}>{Math.round(hyp.confidence * 100)}%</span>
                            <div className="confidence-bar-bg">
                              <div className="confidence-bar-fill" style={{ width: `${hyp.confidence * 100}%` }}></div>
                            </div>
                          </div>
                        </div>
                        <p style={{ fontSize: '13px', fontWeight: '600', marginBottom: '4px' }}>{hyp.hypothesis}</p>
                        <p className="hyp-rationale">{hyp.rationale}</p>
                      </div>
                    ))}
                  </div>

                  {state.recovery_plan && state.recovery_plan.action && (
                    <div className="mitigation-box">
                      <h3 className="mitigation-title">Safe Recovery Suggestion</h3>
                      <p style={{ fontSize: '13px', fontWeight: '600', marginBottom: '6px' }}>{state.recovery_plan.action}</p>
                      <p style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '14px' }}>
                        Safety Rating: <strong>{state.recovery_plan.safety_level?.toUpperCase()}</strong><br />
                        Client Impact: <strong>{state.recovery_plan.impact}</strong>
                      </p>
                      
                      {selectedIncident.status === 'recovery_pending' && (
                        <div style={{ display: 'flex', gap: '8px' }}>
                          <button 
                            className="btn btn-primary" 
                            style={{ flex: 1, backgroundColor: 'rgba(16, 185, 129, 0.2)', borderColor: '#10b981', color: '#10b981' }} 
                            onClick={() => handleApproval('approve')}
                          >
                            <UserCheck size={14} style={{ marginRight: '4px' }} /> Approve
                          </button>
                          <button 
                            className="btn" 
                            style={{ flex: 1, backgroundColor: 'rgba(239, 68, 68, 0.2)', borderColor: '#ef4444', color: '#ef4444', border: '1px solid #ef4444', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '4px', cursor: 'pointer', borderRadius: '4px', padding: '6px 12px', fontSize: '12px', fontWeight: '600', transition: 'all 0.2s' }} 
                            onClick={() => handleApproval('reject')}
                          >
                            <XCircle size={14} /> Reject
                          </button>
                        </div>
                      )}

                      {(selectedIncident.status === 'recovered' || selectedIncident.status === 'postmortem_written') && (
                        <div style={{ padding: '10px', borderRadius: '6px', background: 'rgba(16, 185, 129, 0.15)', border: '1px solid #10b981', color: '#10b981', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}>
                          <CheckCircle size={14} />
                          <span>Mitigation Action Executed Successfully</span>
                        </div>
                      )}

                      {selectedIncident.status === 'rejected' && (
                        <div style={{ padding: '10px', borderRadius: '6px', background: 'rgba(239, 68, 68, 0.15)', border: '1px solid #ef4444', color: '#ef4444', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}>
                          <XCircle size={14} />
                          <span>Mitigation Action Rejected</span>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Execution Audit Trail Log */}
                  <div style={{ marginTop: 'auto' }}>
                    <h3 style={{ fontSize: '11px', fontWeight: '700', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '8px' }}>
                      Execution Logs
                    </h3>
                    <div className="logs-terminal" style={{ fontSize: '10px', height: '110px', overflowY: 'auto', padding: '10px' }}>
                      {history.map((logLine, idx) => (
                        <div key={idx} style={{ borderBottom: 'none', color: '#8892b0', padding: '1px 0' }}>
                          ⚡ {logLine.split('\n')[0]}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>
        ) : (
          <section className="workspace-panel glass-panel" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center' }}>
            <div>
              <Shield size={48} className="animate-float" style={{ color: 'var(--color-primary)', marginBottom: '16px' }} />
              <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '22px', fontWeight: '800', marginBottom: '6px' }}>
                Incident Commander Workspace
              </h2>
              <p style={{ fontSize: '13px', color: 'var(--text-muted)', maxWidth: '380px', margin: '0 auto 20px' }}>
                No active incident selected. Inject a chaos event using the controller playground in the sidebar panel to see specialized agent timelines in real-time.
              </p>
            </div>
          </section>
        )}
      </main>
    </div>
  )
}

export default App
