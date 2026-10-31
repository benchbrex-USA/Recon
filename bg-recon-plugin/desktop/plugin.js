/**
 * BG Recon — BeGuardit recon pane for the Hermes desktop app.
 * Created by Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex).
 * Scans (private-network gated) + local posture audit via the plugin's
 * Python backend (/api/plugins/bg-recon/). Plain ESM, jsx() calls.
 */

import { Button, Checkbox, Input, cn } from '@hermes/plugin-sdk'
import { Fragment, jsx, jsxs } from 'react/jsx-runtime'
import { useState } from 'react'

const ID = 'bg-recon'

let pluginCtx = null

function Banner({ text }) {
  return jsx('div', {
    className: 'text-xs text-(--ui-text-tertiary)',
    children: text,
  })
}

function Row({ cells }) {
  return jsxs('div', {
    className: 'flex items-baseline gap-2 py-[2px]',
    children: cells.map((cell, i) =>
      jsx('span', { key: i, className: cell.className, children: cell.text }, i)
    ),
  })
}

function ScanCard() {
  const [target, setTarget] = useState('127.0.0.1')
  const [ports, setPorts] = useState('')
  const [allowExternal, setAllowExternal] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [report, setReport] = useState(null)

  const runScan = async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await pluginCtx.rest('/scan', {
        method: 'POST',
        body: { target, ports, allow_external: allowExternal },
        timeoutMs: 120000,
      })
      if (res && res.error) {
        setError(res.detail ? `${res.error}: ${res.detail}` : res.error)
        setReport(null)
      } else {
        setReport(res)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return jsxs('div', {
    className: 'flex flex-col gap-2 rounded-md border border-(--ui-stroke-secondary) p-2.5',
    children: [
      jsx('div', { className: 'text-xs font-medium', children: 'Port scan' }),
      jsx(Input, {
        placeholder: 'target (ip / host)',
        value: target,
        onChange: e => setTarget(e.target.value),
      }),
      jsx(Input, {
        placeholder: 'ports — "top" or 80,443,8000-8100',
        value: ports,
        onChange: e => setPorts(e.target.value),
      }),
      jsx(Checkbox, {
        checked: allowExternal,
        onCheckedChange: setAllowExternal,
        children: 'allow external — I own it or hold written scope',
      }),
      jsx(Button, { disabled: busy || !target.trim(), onClick: () => void runScan(), size: 'sm', children: busy ? 'Scanning…' : 'Scan' }),
      error && jsx('div', { className: 'text-xs text-(--ui-text-secondary)', children: `⚠ ${error}` }),
      report && jsxs(Fragment, {
        children: [
          jsx(Banner, {
            text: `${report.scanned} ports · ${report.open_count} open · ${report.closed_count} closed · ${report.filtered_count} filtered · ${report.duration_ms}ms`,
          }),
          jsxs('div', {
            className: 'min-h-0 flex-1 overflow-y-auto',
            children: [
              report.open.length === 0
                ? jsx(Banner, { text: 'No open ports found.' })
                : report.open.map(row =>
                    jsxs(Row, {
                      cells: [
                        { text: `${row.port}`, className: 'text-xs font-medium' },
                        { text: row.service || '', className: 'text-xs text-(--ui-text-tertiary)' },
                        { text: row.banner ? String(row.banner).slice(0, 60) : '', className: 'text-xs text-(--ui-text-tertiary) truncate' },
                        { text: `${row.latency_ms}ms`, className: 'text-xs text-(--ui-text-tertiary) ml-auto' },
                      ],
                    }, row.port)
                  ),
            ],
          }),
        ],
      }),
    ],
  })
}

function PostureCard() {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [data, setData] = useState(null)

  const refresh = async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await pluginCtx.rest('/posture', { timeoutMs: 30000 })
      if (res && res.error) {
        setError(res.error)
      } else {
        setData(res)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return jsxs('div', {
    className: 'flex flex-col gap-2 rounded-md border border-(--ui-stroke-secondary) p-2.5',
    children: [
      jsxs('div', {
        className: 'flex items-center justify-between',
        children: [
          jsx('div', { className: 'text-xs font-medium', children: 'Local posture' }),
          jsx(Button, { disabled: busy, onClick: () => void refresh(), size: 'xs', variant: 'secondary', children: busy ? 'Checking…' : 'Refresh' }),
        ],
      }),
      error && jsx('div', { className: 'text-xs text-(--ui-text-secondary)', children: `⚠ ${error}` }),
      !data && !error && jsx(Banner, { text: 'Run Refresh to audit listeners, AI runtimes and secrets permissions on this host.' }),
      data && jsx(Banner, { text: `${data.summary} · ${data.checked_at}` }),
      data && jsxs(Fragment, {
        children: [
          jsx('div', {
            className: 'min-h-0 flex-1 overflow-y-auto',
            children: data.listeners.map((l, i) =>
              jsxs(Row, {
                cells: [
                  { text: l.exposed ? 'EXPOSED' : 'local', className: cn('text-[0.65rem] font-medium', l.exposed && 'font-semibold') },
                  { text: `${l.addr}:${l.port}`, className: 'text-xs' },
                  { text: l.process, className: 'text-xs text-(--ui-text-tertiary)' },
                  { text: l.ai_runtime || l.service || '', className: 'text-xs text-(--ui-text-tertiary) ml-auto' },
                ],
              }, `${l.addr}:${l.port}:${i}`)
            ),
          }),
          data.ai_runtimes.length > 0 && jsxs('div', {
            children: [
              jsx('div', { className: 'text-xs font-medium', children: 'AI runtimes' }),
              data.ai_runtimes.map((a, i) =>
                jsx(Row, {
                  cells: [
                    { text: a.runtime, className: 'text-xs' },
                    { text: `${a.addr}:${a.port}`, className: 'text-xs text-(--ui-text-tertiary) ml-auto' },
                  ],
                }, `ai${i}`)
              ),
            ],
          }),
          data.secrets_findings.length > 0 && jsxs('div', {
            children: [
              jsx('div', { className: 'text-xs font-medium', children: 'Secrets permissions' }),
              data.secrets_findings.map((f, i) =>
                jsxs(Row, {
                  cells: [
                    { text: f.path.replace(/^\/Users\/[^/]+/, '~'), className: 'text-xs' },
                    { text: `${f.mode} — ${f.issue}`, className: 'text-xs text-(--ui-text-tertiary) ml-auto' },
                  ],
                }, `sec${i}`)
              ),
            ],
          }),
        ],
      }),
    ],
  })
}

function ReconPane() {
  return jsxs('div', {
    className: 'flex h-full min-h-0 flex-col gap-2 overflow-y-auto p-3',
    children: [
      jsxs('div', {
        children: [
          jsx('div', { className: 'text-sm font-medium', children: 'BG Recon' }),
          jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children: 'BeGuardit recon · by Parth Patel, founder of BenchBrex.com · private-network gated' }),
        ],
      }),
      jsx(ScanCard, {}),
      jsx(PostureCard, {}),
    ],
  })
}

export default {
  id: ID,
  name: 'BG Recon',
  register(ctx) {
    pluginCtx = ctx
    ctx.register({
      id: 'pane',
      area: 'panes',
      title: 'bg recon',
      data: { placement: 'right', width: '340px' },
      render: () => jsx(ReconPane, {}),
    })
  },
}
