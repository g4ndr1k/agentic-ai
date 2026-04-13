import { queueMutation, cacheGet, cacheSet } from '../db/index.js'

const BASE = '/api'
const API_KEY = import.meta.env.VITE_FINANCE_API_KEY || ''
const AUTH_HEADERS = API_KEY
  ? { 'X-Api-Key': API_KEY }
  : (console.warn('VITE_FINANCE_API_KEY not set — requests will be unauthenticated'), {})

function isNetworkError(error) {
  return !navigator.onLine || error?.name === 'TypeError'
}

function getCacheKey(url) {
  return `GET:${url.pathname}${url.search}`
}

async function get(path, params = {}) {
  const url = new URL(BASE + path, location.origin)
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') {
      url.searchParams.set(k, String(v))
    }
  }
  const cacheKey = getCacheKey(url)

  try {
    const res = await fetch(url.toString(), { headers: AUTH_HEADERS })
    if (!res.ok) {
      const text = await res.text().catch(() => '')
      throw new Error(`${res.status}: ${text || res.statusText}`)
    }
    const payload = await res.json()
    await cacheSet(cacheKey, payload)
    return payload
  } catch (error) {
    if (!isNetworkError(error)) throw error
    const cached = await cacheGet(cacheKey)
    if (cached !== null) {
      console.warn(`[Cache] Using cached GET for ${url.pathname}:`, error.message)
      return cached
    }
    throw error
  }
}

async function post(path, body = {}) {
  const res = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...AUTH_HEADERS },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`${res.status}: ${text || res.statusText}`)
  }
  return res.json()
}

async function postQueued(path, body = {}) {
  try {
    return await post(path, body)
  } catch (error) {
    if (!isNetworkError(error)) throw error
    await queueMutation('POST', BASE + path, body, AUTH_HEADERS)
    return { queued: true }
  }
}

// Multipart upload — do NOT set Content-Type; browser injects the boundary automatically.
async function postMultipart(path, formData) {
  const res = await fetch(BASE + path, {
    method: 'POST',
    headers: { ...AUTH_HEADERS },
    body: formData,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`${res.status}: ${text || res.statusText}`)
  }
  return res.json()
}

async function del(path) {
  const res = await fetch(BASE + path, { method: 'DELETE', headers: AUTH_HEADERS })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`${res.status}: ${text || res.statusText}`)
  }
  return res.json()
}

async function delQueued(path) {
  try {
    return await del(path)
  } catch (error) {
    if (!isNetworkError(error)) throw error
    await queueMutation('DELETE', BASE + path, undefined, AUTH_HEADERS)
    return { queued: true }
  }
}

async function patch(path, body = {}) {
  const res = await fetch(BASE + path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...AUTH_HEADERS },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`${res.status}: ${text || res.statusText}`)
  }
  return res.json()
}

async function patchQueued(path, body = {}) {
  try {
    return await patch(path, body)
  } catch (error) {
    if (!isNetworkError(error)) throw error
    await queueMutation('PATCH', BASE + path, body, AUTH_HEADERS)
    const transaction = { category: body.category }
    if (Object.prototype.hasOwnProperty.call(body, 'notes')) {
      transaction.notes = body.notes
    }
    return { queued: true, transaction }
  }
}

export const api = {
  health: () => get('/health'),
  owners: () => get('/owners'),
  categories: () => get('/categories'),
  transactions: (p = {}) => get('/transactions', p),
  foreignTransactions: (p = {}) => get('/transactions/foreign', p),
  summaryYears: () => get('/summary/years'),
  summaryYear: (y) => get(`/summary/year/${y}`),
  summaryMonth: (y, m) => get(`/summary/${y}/${m}`),
  summaryExplanation: (y, m, p = {}) => get(`/summary/${y}/${m}/explanation`, p),
  summaryExplanationQuery: (y, m, body) => post(`/summary/${y}/${m}/explanation/query`, body),
  reviewQueue: (limit = 100) => get('/review-queue', { limit }),
  saveAlias: (body) => postQueued('/alias', body),
  backfillAliases: () => postQueued('/backfill-aliases'),
  sync: () => postQueued('/sync'),
  importData: (body = {}) => postQueued('/import', body),
  pipelineStatus: () => get('/pipeline/status'),
  runPipeline: () => postQueued('/pipeline/run'),
  patchCategory: (hash, body) => patchQueued(`/transaction/${hash}/category`, body),

  wealthSummary: (p = {}) => get('/wealth/summary', p),
  wealthHistory: (limit = 24) => get('/wealth/history', { limit }),
  wealthExplanation: (p = {}) => get('/wealth/explanation', p),
  wealthExplanationQuery: (body) => post('/wealth/explanation/query', body),
  wealthSnapshotDates: () => get('/wealth/snapshot/dates'),
  createSnapshot: (body) => postQueued('/wealth/snapshot', body),

  getBalances: (p = {}) => get('/wealth/balances', p),
  upsertBalance: (body) => postQueued('/wealth/balances', body),
  deleteBalance: (id) => delQueued(`/wealth/balances/${id}`),

  getHoldings: (p = {}) => get('/wealth/holdings', p),
  upsertHolding: (body) => postQueued('/wealth/holdings', body),
  deleteHolding: (id) => delQueued(`/wealth/holdings/${id}`),
  carryForwardHoldings: (body) => postQueued('/wealth/holdings/carry-forward', body),

  getLiabilities: (p = {}) => get('/wealth/liabilities', p),
  upsertLiability: (body) => postQueued('/wealth/liabilities', body),
  deleteLiability: (id) => delQueued(`/wealth/liabilities/${id}`),

  aiQuery: (query) => post('/ai/query', { query }),
  pdfLocalFiles: () => get('/pdf/local-files'),
  pdfLocalWorkspace: () => get('/pdf/local-workspace'),
  processLocalPdf: (folder, relativePath) => post('/pdf/process-local', { folder, relative_path: relativePath }),
  pdfLocalStatus: (jobId) => get(`/pdf/local-status/${jobId}`),
  postMultipart,
}
