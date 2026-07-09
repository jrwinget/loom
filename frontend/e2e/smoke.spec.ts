import { expect, test } from '@playwright/test';
import * as OTPAuth from 'otpauth';

// end-to-end smoke: one continuous journey through a real lite
// backend. auth tokens live only in memory (no persist middleware),
// so every navigation after login must be in-app — page.goto() or
// reload would drop the session.

const ADMIN = {
  name: 'E2E Admin',
  email: 'e2e-admin@example.com',
  password: 'correct-horse-battery-staple',
};
const CASE_NAME = 'E2E Smoke Case';
const FILE_NAME = 'field-notes.txt';
const EVENT_TITLE = 'March reached the intersection';
const EXPORT_NAME = 'E2E smoke export';

function caseTab(page: import('@playwright/test').Page, name: string) {
  return page
    .getByRole('navigation', { name: 'Case sections' })
    .getByRole('link', { name });
}

function sidebarLink(page: import('@playwright/test').Page, name: string) {
  return page
    .getByRole('navigation', { name: 'Primary' })
    .getByRole('link', { name });
}

test('first run through export', async ({ page }) => {
  let totp: OTPAuth.TOTP;

  await test.step('first-run: create the admin account', async () => {
    await page.goto('/');
    // a fresh database redirects to /first-run; the lite profile
    // shows the data-directory step first
    await expect(page.getByTestId('first-run-data-dir')).toBeVisible();
    await page
      .getByRole('button', { name: 'Use this directory' })
      .click();

    await page.getByLabel('Full name').fill(ADMIN.name);
    await page.getByLabel('Email').fill(ADMIN.email);
    await page.getByLabel(/^Password \(minimum/).fill(ADMIN.password);
    await page.getByLabel('Confirm password').fill(ADMIN.password);
    await page
      .getByRole('button', { name: 'Create admin account' })
      .click();

    await expect(page.getByTestId('recovery-codes-panel')).toBeVisible();
    await page.getByTestId('recovery-codes-ack').check();
    await page.getByRole('button', { name: 'Continue to Loom' }).click();
    await expect(page.getByTestId('user-menu-button')).toBeVisible();
  });

  await test.step('enroll mfa from security settings', async () => {
    await sidebarLink(page, 'Settings').click();
    await page.getByRole('button', { name: 'Enable MFA' }).click();

    // the provisioning uri renders as copyable text; derive the
    // totp generator from it like an authenticator app would
    const uri = await page
      .getByText(/^otpauth:\/\//)
      .textContent();
    totp = OTPAuth.URI.parse(uri ?? '') as OTPAuth.TOTP;

    await page
      .getByPlaceholder('Enter code from app')
      .fill(totp.generate());
    await page.getByRole('button', { name: 'Verify' }).click();
    await expect(
      page.getByRole('heading', { name: 'MFA Enabled' }),
    ).toBeVisible();
    await expect(page.getByTestId('recovery-codes')).toBeVisible();
  });

  await test.step('log out, log back in through the challenge', async () => {
    await page.getByTestId('user-menu-button').click();
    await page.getByTestId('logout-button').click();
    await expect(
      page.getByRole('heading', { name: 'Sign in to Loom' }),
    ).toBeVisible();

    await page.getByLabel('Email').fill(ADMIN.email);
    await page.getByLabel('Password').fill(ADMIN.password);
    await page.getByRole('button', { name: 'Sign in' }).click();

    await expect(
      page.getByRole('heading', { name: 'Two-Factor Authentication' }),
    ).toBeVisible();
    await page.getByLabel('Code').fill(totp.generate());
    await page.getByRole('button', { name: 'Verify' }).click();
    await expect(page.getByTestId('user-menu-button')).toBeVisible();
  });

  await test.step('create a case', async () => {
    await sidebarLink(page, 'Cases').click();
    await page.getByRole('button', { name: 'Create Case' }).click();
    await page.getByPlaceholder('Case name').fill(CASE_NAME);
    await page
      .getByRole('button', { name: 'Create', exact: true })
      .click();

    const card = page
      .getByTestId(/^case-card-/)
      .filter({ hasText: CASE_NAME });
    await expect(card).toBeVisible();
    await card.click();
  });

  await test.step('upload an asset', async () => {
    await caseTab(page, 'Assets').click();
    await page.getByTestId('file-input').setInputFiles({
      name: FILE_NAME,
      mimeType: 'text/plain',
      buffer: Buffer.from(
        'observer field notes captured during the e2e smoke run\n',
      ),
    });
    await page.getByRole('button', { name: 'Upload all' }).click();
    await expect(page.getByTestId('file-status')).toHaveText('Complete', {
      timeout: 30_000,
    });
    await expect(page.getByTestId('asset-filename')).toHaveText(
      FILE_NAME,
    );
  });

  await test.step('add a timeline event', async () => {
    await caseTab(page, 'Timeline').click();
    await page.getByTestId('add-event-btn').click();
    await page.getByLabel('Title').fill(EVENT_TITLE);
    await page.getByLabel('Occurred at').fill('2026-07-01T12:00');
    await page.getByRole('button', { name: 'Create Event' }).click();
    await expect(
      page.getByTestId('timeline-canvas').getByText(EVENT_TITLE),
    ).toBeVisible();
  });

  await test.step('create an export', async () => {
    await caseTab(page, 'Export').click();
    await page.getByTestId('new-export-btn').click();
    await page
      .getByPlaceholder('e.g. Case export 2026-03')
      .fill(EXPORT_NAME);
    await page.getByRole('button', { name: 'Next' }).click();
    await page.getByRole('button', { name: 'Next' }).click();
    await page.getByTestId('export-submit').click();

    // the record appears immediately; completion depends on engines
    // and is out of scope for the smoke run
    const row = page
      .getByTestId(/^export-row-/)
      .filter({ hasText: EXPORT_NAME });
    await expect(row).toBeVisible();
  });
});
