import { expect, test } from '@playwright/test'

test('full game from first request to reveal', async ({ page }) => {
  await page.goto('/game')
  await expect(page.getByText(/Request 1 of 60/)).toBeVisible()
  await page.getByRole('button', { name: 'Accept' }).click()
  await expect(page.getByText(/Request 2 of 60/)).toBeVisible()
  const reject = page.getByRole('button', { name: 'Reject' })
  const revealed = page.getByRole('heading', { name: /The ship has sailed/ })
  while (!(await revealed.isVisible().catch(() => false))) {
    if (await reject.isEnabled().catch(() => false)) await reject.click().catch(() => {})
    await page.waitForTimeout(20)
  }
  await expect(page.getByRole('heading', { name: /The ship has sailed/ })).toBeVisible()
  await expect(page.getByText('First come, first served').first()).toBeVisible()
})

test('manual placement loads a unit in the chosen zone', async ({ page }) => {
  await page.goto('/game')
  await page.getByRole('button', { name: 'I place them' }).click()
  await page.getByRole('button', { name: 'Accept' }).click()
  await page.getByRole('button', { name: /^Load in/ }).first().click()
  await expect(page.getByText(/Request 2 of 60/)).toBeVisible()
})

test('reload keeps the game', async ({ page }) => {
  await page.goto('/game')
  await page.getByRole('button', { name: 'Reject' }).click()
  await expect(page.getByText(/Request 2 of 60/)).toBeVisible()
  await page.reload()
  await expect(page.getByText(/Request 2 of 60/)).toBeVisible()
})

test('the advisor gives a verdict', async ({ page }) => {
  await page.goto('/game')
  await page.getByRole('button', { name: 'Advisor on' }).click()
  await expect(page.getByText(/Advisor:/)).toBeVisible({ timeout: 30_000 })
})

test('the lab compares plans', async ({ page }) => {
  await page.goto('/lab')
  await expect(page.getByRole('columnheader', { name: /optimizer|best/i })).toBeVisible({ timeout: 30_000 })
})

test('the lab runs at phone width with no horizontal scroll', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 740 })
  await page.goto('/lab')
  await expect(page.getByRole('button', { name: 'Compare plans' })).toBeVisible()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(0)
})

test('the game at phone width has no horizontal scroll', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 740 })
  await page.goto('/game')
  await expect(page.getByText(/Request 1 of 60/)).toBeVisible()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(0)
})

test('the reveal share link opens the same result in a fresh page', async ({ page, browser }) => {
  await page.goto('/game')
  const reject = page.getByRole('button', { name: 'Reject' })
  const revealed = page.getByRole('heading', { name: /The ship has sailed/ })
  while (!(await revealed.isVisible().catch(() => false))) {
    if (await reject.isEnabled().catch(() => false)) await reject.click().catch(() => {})
    await page.waitForTimeout(20)
  }
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.getByRole('button', { name: 'Copy share link' }).click()
  const url = await page.evaluate(() => navigator.clipboard.readText())
  expect(url).toContain('/reveal#g=')
  const other = await (await browser.newContext()).newPage()
  await other.goto(url)
  await expect(other.getByText(/Shared result/)).toBeVisible()
  await expect(other.getByText('First come, first served').first()).toBeVisible()
})

test('the lab downloads a PDF', async ({ page }) => {
  await page.goto('/lab')
  await expect(page.getByRole('button', { name: 'Download PDF' })).toBeVisible({ timeout: 30_000 })
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download PDF' }).click()
  expect((await download).suggestedFilename()).toMatch(/\.pdf$/)
})

test('choosing the RoPax preset runs a comparison', async ({ page }) => {
  test.setTimeout(300_000)  // may queue behind smart plans started by earlier tests
  await page.goto('/lab')
  await expect(page.getByRole('button', { name: 'Download PDF' })).toBeVisible({ timeout: 30_000 })
  await page.getByLabel('Vessel').selectOption('ropax')
  await expect(page.getByText(/Usable 1800 of 1800 lane-m/)).toBeVisible({ timeout: 240_000 })
})
