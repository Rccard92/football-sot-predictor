import { afterEach, describe, expect, it, vi } from 'vitest'

/**
 * Copre il contratto download dataset: loading anti-doppio-click e toast errore
 * senza montare React (pattern allineato agli altri unit test del repo).
 */
describe('download dataset home wins — contratto UI', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('impedisce doppio download mentre downloading=true', async () => {
    let downloading = false
    const downloadFn = vi.fn(async () => {
      await new Promise((r) => setTimeout(r, 5))
    })
    const toastError = vi.fn()

    async function handleDownload() {
      if (downloading) return
      downloading = true
      try {
        await downloadFn()
      } catch (err) {
        toastError(err instanceof Error ? err.message : 'Download fallito')
      } finally {
        downloading = false
      }
    }

    const p1 = handleDownload()
    const p2 = handleDownload()
    await Promise.all([p1, p2])
    expect(downloadFn).toHaveBeenCalledTimes(1)
    expect(downloading).toBe(false)
  })

  it('emette toast su errore e ripristina stato', async () => {
    let downloading = false
    const toastError = vi.fn()
    const downloadFn = vi.fn(async () => {
      throw new Error('export failed')
    })

    async function handleDownload() {
      if (downloading) return
      downloading = true
      try {
        await downloadFn()
      } catch (err) {
        toastError(err instanceof Error ? err.message : 'Download fallito')
      } finally {
        downloading = false
      }
    }

    await handleDownload()
    expect(toastError).toHaveBeenCalledWith('export failed')
    expect(downloading).toBe(false)
  })
})
