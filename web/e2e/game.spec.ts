import { expect, test } from '@playwright/test'

test('full game from first request to reveal', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText(/Request 1 of 60/)).toBeVisible()
  await page.getByRole('button', { name: 'Accept' }).click()
  await expect(page.getByText(/Request 2 of 60/)).toBeVisible()
  const reject = page.getByRole('button', { name: 'Reject' })
  while (!page.url().endsWith('/reveal')) {
    if (await reject.isEnabled().catch(() => false)) await reject.click().catch(() => {})
    await page.waitForTimeout(20)
  }
  await expect(page.getByRole('heading', { name: /The ship has sailed/ })).toBeVisible()
  await expect(page.getByText('First come, first served').first()).toBeVisible()
})

test('manual placement loads a unit in the chosen zone', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'I place them' }).click()
  await page.getByRole('button', { name: 'Accept' }).click()
  await page.getByRole('button', { name: /^Load in/ }).first().click()
  await expect(page.getByText(/Request 2 of 60/)).toBeVisible()
})

test('reload keeps the game', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Reject' }).click()
  await expect(page.getByText(/Request 2 of 60/)).toBeVisible()
  await page.reload()
  await expect(page.getByText(/Request 2 of 60/)).toBeVisible()
})

test('the advisor gives a verdict', async ({ page }) => {
  await page.goto('/')
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
  await page.goto('/')
  await expect(page.getByText(/Request 1 of 60/)).toBeVisible()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(0)
})
