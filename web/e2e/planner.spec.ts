import { expect, test } from '@playwright/test'

async function uploadTemplate(page: import('@playwright/test').Page) {
  const template = await page.request.get('/api/planner/template.xlsx')
  expect(template.ok()).toBeTruthy()
  await page.getByLabel('Upload bookings').setInputFiles({
    name: 'bookings.xlsx',
    mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    buffer: Buffer.from(await template.body()),
  })
  await expect(page.getByRole('img', { name: /Deck plan/ })).toBeVisible({ timeout: 60_000 })
}

test('the template uploads and gives a plan', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Planner' })).toBeVisible()
  await uploadTemplate(page)
  await expect(page.getByText(/3 of 3/)).toBeVisible()
})

test('a unit goes on board and a new request is accepted', async ({ page }) => {
  test.setTimeout(180_000)
  await page.goto('/')
  await uploadTemplate(page)
  await page.getByRole('checkbox', { name: 'B001 on board' }).check()
  await expect(page.getByRole('checkbox', { name: 'B001 on board' })).toBeChecked()
  await page.getByLabel('Booking id').fill('NEW1')
  await page.getByLabel('Customer').fill('Spot haulier')
  await page.getByLabel('Unit type').selectOption('van')
  await page.getByLabel('Price per metre (€)').fill('95')
  await page.getByRole('button', { name: 'Ask the advisor' }).click()
  await expect(page.getByText(/Advisor:/)).toBeVisible({ timeout: 60_000 })
  await page.getByRole('button', { name: 'Accept request' }).click()
  await expect(page.getByText(/4 of 4/)).toBeVisible({ timeout: 60_000 })
  await expect(page.getByText('NEW1: accepted', { exact: false })).toBeVisible()
})

test('the planner plan downloads as PDF', async ({ page }) => {
  await page.goto('/')
  await uploadTemplate(page)
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download PDF' }).click()
  expect((await download).suggestedFilename()).toMatch(/\.pdf$/)
})

test('a file that is not an xlsx shows the error and no plan', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('Upload bookings').setInputFiles({
    name: 'bookings.csv', mimeType: 'text/csv', buffer: Buffer.from('booking_id,customer\nB1,X\n'),
  })
  await expect(page.getByText(/not an .xlsx file/)).toBeVisible()
})

test('a reservation keeps space free and can be released', async ({ page }) => {
  test.setTimeout(180_000)
  await page.goto('/')
  await uploadTemplate(page)
  const section = page.getByRole('region', { name: 'Reserved space' })
  await section.getByLabel('Reservation holder').fill('Nordfreight')
  await section.getByLabel('Reservation metres').fill('300')
  await section.getByRole('button', { name: 'Reserve' }).click()
  const row = section.getByRole('row', { name: /Nordfreight/ })
  await expect(row).toContainText('300 m')
  await expect(row).toContainText(/Left|\d+\.\d m/, { timeout: 60_000 })
  await section.getByRole('button', { name: 'Release Nordfreight' }).click()
  await expect(section.getByText('No space reserved.')).toBeVisible({ timeout: 60_000 })
})
