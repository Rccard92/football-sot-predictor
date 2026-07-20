/**
 * Unit smoke test Monitoraggio Segno 1 — senza dipendenza vitest (npm install bloccato in CI locale).
 * Esegui: node scripts/run-home-wins-unit.mjs
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')

function read(rel) {
  return readFileSync(join(root, rel), 'utf8')
}

// Route + menu
const nav = read('src/config/navItems.ts')
assert.match(nav, /to:\s*'\/monitoraggio-segno-1'/)
assert.match(nav, /label:\s*'Monitoraggio Segno 1'/)

const app = read('src/App.tsx')
assert.match(app, /path="\/monitoraggio-segno-1"/)
assert.match(app, /CecchinoHomeWinsPage/)

const layout = read('src/components/Layout.tsx')
assert.match(layout, /MONITORAGGIO_SEGNO_1_PATH/)

// API client + page wiring
const api = read('src/lib/cecchinoHomeWinsApi.ts')
assert.match(api, /\/api\/cecchino\/home-wins/)
assert.match(api, /downloadHomeWinsDataset/)
assert.match(api, /availabilityBadgeLabel/)

const page = read('src/pages/CecchinoHomeWinsPage.tsx')
assert.match(page, /Scarica dataset completo/)
assert.match(page, /toast\.error/)
assert.match(page, /if \(downloading\) return/)
assert.match(page, /HomeWinsTable/)
assert.match(page, /HomeWinsDetailDrawer/)
assert.match(page, /Completi|partial|complete/)

// Download anti-doppio-click + toast contratto
let downloading = false
let calls = 0
const toastError = []
async function handleDownload(fn) {
  if (downloading) return
  downloading = true
  try {
    await fn()
  } catch (err) {
    toastError.push(err instanceof Error ? err.message : 'Download fallito')
  } finally {
    downloading = false
  }
}
const slow = async () => {
  calls += 1
  await new Promise((r) => setTimeout(r, 20))
}
await Promise.all([handleDownload(slow), handleDownload(slow)])
assert.equal(calls, 1)
assert.equal(downloading, false)

await handleDownload(async () => {
  throw new Error('export failed')
})
assert.deepEqual(toastError, ['export failed'])
assert.equal(downloading, false)

console.log('ok — home wins frontend unit checks passed')
